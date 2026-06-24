"""The eval gauntlet — run phases cheapest-first and fail fast.

Order:
  1. static            (always; no Spark, no golden)
  2-4. schema/property/diff  (need golden output + all golden inputs + PySpark)
  5. judge             (fallback when golden is unavailable; needs an LLM)

Execution happens once: if golden is available the transform is run a single time
and the resulting frame is reused by schema, property, and diff.
"""
from __future__ import annotations

import threading
import traceback
from dataclasses import dataclass, field

from ..models import EvalPhase, EvalResult, SasStep
from .base import EvalContext, TransformContractError, load_transform
from .dataframe_evals import evaluate_diff, evaluate_property, evaluate_schema
from .judge_eval import evaluate_judge
from .static_eval import evaluate_static


@dataclass
class GauntletReport:
    results: list[EvalResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(r.passed or r.skipped for r in self.results) and any(
            r.passed and not r.skipped for r in self.results
        )

    def failure_feedback(self) -> str:
        return "\n".join(r.feedback() for r in self.results if not r.passed and not r.skipped)

    def summary_line(self) -> str:
        parts = []
        for r in self.results:
            mark = "skip" if r.skipped else ("ok" if r.passed else "FAIL")
            parts.append(f"{r.phase.value}={mark}")
        return " ".join(parts)


class Gauntlet:
    def __init__(self, ctx: EvalContext):
        self.ctx = ctx
        # Spark-backed phases share one local session; serialize them so
        # concurrent translation workers don't interleave Spark jobs.
        self._spark_phase_lock = threading.Lock()

    def run(self, step: SasStep, code: str, input_schemas: dict | None = None) -> GauntletReport:
        report = GauntletReport()

        # --- Phase 1: static (always) ---
        static = evaluate_static(code)
        report.results.append(static)
        if not static.passed:
            return report  # fail fast — don't try to execute uncompilable code

        # Decide whether we can run the Spark-backed phases.
        golden = self.ctx.golden
        out_key = step.outputs[0].key if step.outputs else None
        have_golden_out = bool(golden and out_key and golden.has(out_key))
        missing_inputs = [r.key for r in step.inputs if not (golden and golden.has(r.key))]

        if have_golden_out and not missing_inputs and _pyspark_available():
            with self._spark_phase_lock:
                ran = self._run_spark_phases(step, code, out_key, report)
            if ran:
                return report
            # If execution failed, _run_spark_phases recorded a failing result.
            if any(not r.passed and not r.skipped for r in report.results):
                return report

        # --- Phase 5: judge fallback (no golden / cannot execute) ---
        from ..llm.client import StubLLM

        judge_llm = self.ctx.judge_llm or self.ctx.llm
        if judge_llm is not None and not isinstance(judge_llm, StubLLM):
            report.results.append(
                evaluate_judge(step, code, judge_llm, input_schemas)
            )
        elif isinstance(judge_llm, StubLLM):
            report.results.append(
                EvalResult(
                    phase=EvalPhase.JUDGE,
                    passed=True,
                    skipped=True,
                    summary="stub LLM: judge skipped (offline run)",
                )
            )
        else:
            reasons = []
            if not have_golden_out:
                reasons.append(f"no golden dataset for output {out_key!r}")
            if missing_inputs:
                reasons.append(f"missing golden inputs {missing_inputs}")
            if not _pyspark_available():
                reasons.append("pyspark not installed")
            report.results.append(
                EvalResult(
                    phase=EvalPhase.JUDGE,
                    passed=True,
                    skipped=True,
                    summary="no golden data and no LLM judge available",
                    diagnostics=reasons,
                )
            )
        return report

    # ------------------------------------------------------------------
    def _run_spark_phases(self, step, code, out_key, report) -> bool:
        """Execute the transform once and run schema/property/diff. Returns True
        if all execution-backed phases completed (pass or fail recorded)."""
        from .spark_runtime import load_inputs_from_golden, run_transform

        try:
            transform = load_transform(code, module_name=step.label)
        except (SyntaxError, TransformContractError) as exc:
            report.results.append(
                EvalResult(EvalPhase.SCHEMA, False, "could not load transform", [str(exc)])
            )
            return False

        spark = self.ctx.spark()
        try:
            inputs, missing = load_inputs_from_golden(spark, step, self.ctx.golden)
            if missing:
                report.results.append(
                    EvalResult(EvalPhase.SCHEMA, True, skipped=True,
                               summary="missing golden inputs", diagnostics=missing)
                )
                return False
            out_df = run_transform(transform, spark, inputs)
            golden_df = self.ctx.golden.spark(spark, out_key)
            engine = self._choose_engine(golden_df)
            if engine == "spark":
                self._reconcile_spark(out_df, golden_df, report)
            else:
                self._reconcile_pandas(out_df, out_key, report)
        except Exception:  # noqa: BLE001 - capture runtime errors as eval feedback
            tb = traceback.format_exc(limit=6)
            report.results.append(
                EvalResult(
                    phase=EvalPhase.SCHEMA,
                    passed=False,
                    summary="runtime error while executing transform",
                    diagnostics=[tb.strip().splitlines()[-1], tb[-1500:]],
                )
            )
            return False
        return True

    def _choose_engine(self, golden_df) -> str:
        """Resolve the reconciliation engine for this step ('spark' | 'pandas')."""
        engine = (self.ctx.settings.reconcile_engine or "auto").lower()
        if engine in ("spark", "pandas"):
            return engine
        # auto: distributed only when the golden output is large enough to make a
        # full driver collect wasteful/risky.
        try:
            n = golden_df.count()
        except Exception:  # noqa: BLE001 - if counting fails, fall back to pandas
            return "pandas"
        return "spark" if n > self.ctx.settings.reconcile_row_threshold else "pandas"

    def _reconcile_spark(self, out_df, golden_df, report) -> None:
        """Distributed schema/property/diff — no full collect (fail-fast)."""
        from .spark_compare import (
            compare_properties_spark,
            compare_schema_spark,
            compare_values_spark,
        )

        atol = self.ctx.settings.float_tolerance
        max_report = self.ctx.settings.reconcile_max_report

        passed, diags = compare_schema_spark(out_df, golden_df)
        report.results.append(EvalResult(
            EvalPhase.SCHEMA, passed,
            "schema matches golden" if passed else "schema mismatch", diags))
        if not passed:
            return

        passed, diags = compare_properties_spark(out_df, golden_df, atol=atol)
        report.results.append(EvalResult(
            EvalPhase.PROPERTY, passed,
            "invariants match golden" if passed else "property/invariant mismatch", diags))
        if not passed:
            return

        passed, diags = compare_values_spark(
            out_df, golden_df, atol=atol, max_report=max_report)
        report.results.append(EvalResult(
            EvalPhase.DIFF, passed,
            "values match golden (within tolerance)" if passed else "value-level diff", diags))

    def _reconcile_pandas(self, out_df, out_key, report) -> None:
        """Collect both sides to the driver and compare in pandas (fail-fast)."""
        atol = self.ctx.settings.float_tolerance
        actual_pd = out_df.toPandas()
        golden_pd = self.ctx.golden.pandas(out_key)

        schema_res = evaluate_schema(actual_pd, golden_pd)
        report.results.append(schema_res)
        if not schema_res.passed:
            return
        prop_res = evaluate_property(actual_pd, golden_pd, atol=atol)
        report.results.append(prop_res)
        if not prop_res.passed:
            return
        diff_res = evaluate_diff(actual_pd, golden_pd, atol=atol)
        report.results.append(diff_res)


def _pyspark_available() -> bool:
    try:
        import pyspark  # type: ignore  # noqa: F401

        return True
    except ImportError:
        return False
