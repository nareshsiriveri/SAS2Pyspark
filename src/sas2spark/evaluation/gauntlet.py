"""The eval gauntlet — run phases cheapest-first and fail fast.

Order:
  1. static            (always; no Spark, no golden)
  2-4. schema/property/diff  (need golden output + all golden inputs + PySpark)
  5. judge             (fallback when golden is unavailable; needs an LLM)

Execution happens once: if golden is available the transform is run a single time
and the resulting frame is reused by schema, property, and diff.
"""
from __future__ import annotations

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
            ran = self._run_spark_phases(step, code, out_key, report)
            if ran:
                return report
            # If execution failed, _run_spark_phases recorded a failing result.
            if any(not r.passed and not r.skipped for r in report.results):
                return report

        # --- Phase 5: judge fallback (no golden / cannot execute) ---
        from ..llm.client import StubLLM

        if self.ctx.llm is not None and not isinstance(self.ctx.llm, StubLLM):
            report.results.append(
                evaluate_judge(step, code, self.ctx.llm, input_schemas)
            )
        elif isinstance(self.ctx.llm, StubLLM):
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

        atol = self.ctx.settings.float_tolerance
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
            actual_pd = out_df.toPandas()
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

        golden_pd = self.ctx.golden.pandas(out_key)

        schema_res = evaluate_schema(actual_pd, golden_pd)
        report.results.append(schema_res)
        if not schema_res.passed:
            return True  # fail fast within the Spark phases

        prop_res = evaluate_property(actual_pd, golden_pd, atol=atol)
        report.results.append(prop_res)
        if not prop_res.passed:
            return True

        diff_res = evaluate_diff(actual_pd, golden_pd, atol=atol)
        report.results.append(diff_res)
        return True


def _pyspark_available() -> bool:
    try:
        import pyspark  # type: ignore  # noqa: F401

        return True
    except ImportError:
        return False
