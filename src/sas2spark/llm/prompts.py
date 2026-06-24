"""Prompt templates for translation, repair, and the LLM-as-judge eval.

Prompts are small and per-step: one SAS step plus its input/output schemas.
This keeps each LLM call cheap, reliable, and locally debuggable.
"""
from __future__ import annotations

import re

from ..models import SasStep, Schema, StepKind

TARGET_CONTRACT = '''\
Target: PySpark (Spark DataFrame API and/or Spark SQL via spark.sql).

Emit ONE self-contained Python module as a single ```python fenced code block.
It MUST define exactly this function and nothing that runs at import time:

    def transform(spark, inputs: dict) -> "DataFrame":
        ...
        return out_df

Rules:
- `inputs` maps each INPUT dataset name (e.g. "work.accounts") to a Spark DataFrame.
  Access them by those exact keys.
- Return the single PRIMARY output DataFrame for this step.
- Put all imports (e.g. `from pyspark.sql import functions as F, Window`) at module top.
- Use idiomatic PySpark: `withColumn`/`select`/`groupBy`/`join`, and `Window`
  functions for RETAIN / BY+FIRST./LAST. semantics. Translate PROC SQL with
  `spark.sql(...)` (register inputs as temp views) or the DataFrame API.
- Do NOT iterate row-by-row and do NOT call `.collect()` to loop.
- SAS missing values map to Spark `null`. SAS dates are days since 1960-01-01.
- No top-level side effects, no `print`, no file or network I/O, no SparkSession
  creation (use the passed-in `spark`).
'''

SYSTEM_TRANSLATOR = (
    "You are an expert at translating SAS DATA/PROC steps into correct, idiomatic "
    "PySpark. You translate the INTENT of a step, not a line-by-line transliteration. "
    "You output only a single Python module in one fenced code block."
)

SYSTEM_JUDGE = (
    "You are a meticulous code reviewer comparing a SAS step to a candidate PySpark "
    "translation for logical equivalence. You flag risky constructs (RETAIN, implicit "
    "DATA-step loop, MERGE many-to-many, PROC SQL joins). You answer in strict JSON."
)


def _schema_block(label: str, schema: Schema | None) -> str:
    if schema is None or not schema.columns:
        return f"{label}: (schema unknown)"
    cols = ", ".join(f"{n}:{t}" for n, t in schema.columns.items())
    rc = "" if schema.row_count is None else f" (rows≈{schema.row_count})"
    return f"{label}: {cols}{rc}"


def _sample_lines(
    step: SasStep,
    input_samples: dict[str, str] | None,
    output_sample: str | None,
) -> list[str]:
    """Render golden sample rows (when available) as prompt sections."""
    lines: list[str] = []
    input_samples = input_samples or {}
    shown = [k for k in (r.key for r in step.inputs) if input_samples.get(k)]
    if shown:
        lines.append("")
        lines.append("# Sample rows from the ACTUAL input data (from the SAS run):")
        for k in shown:
            lines.append(f"## {k}")
            lines.append("```")
            lines.append(input_samples[k].rstrip())
            lines.append("```")
    if output_sample:
        lines.append("")
        lines.append("# Sample rows of the EXPECTED output (golden SAS result your "
                      "code must reproduce):")
        lines.append("```")
        lines.append(output_sample.rstrip())
        lines.append("```")
    return lines


_GROUP_BY_RE = re.compile(r"\bgroup\s+by\b", re.IGNORECASE)


def _is_proc_sql(step: SasStep) -> bool:
    if step.kind is StepKind.PROC and (step.proc_name or "").lower() == "sql":
        return True
    # Macro-flattened OTHER blocks may still contain a PROC SQL body.
    return bool(re.search(r"\bproc\s+sql\b", step.text, re.IGNORECASE))


def _proc_sql_lines(step: SasStep) -> list[str]:
    """SAS PROC SQL semantics that differ from Spark SQL — injected per step.

    The big one is GROUP BY *remerging*: SAS keeps detail rows and merges the
    group aggregate back onto each, where Spark would collapse to one row per
    group. That maps to a window function, not groupBy — and getting it wrong
    silently drops rows.
    """
    if not _is_proc_sql(step):
        return []
    lines = [
        "",
        "# SAS PROC SQL — translate the INTENT; SAS SQL is not Spark SQL:",
        "# - Register each input as a temp view and use `spark.sql(...)`, or use the",
        "#   DataFrame API. Identifiers are case-insensitive in SAS.",
        "# - Aggregates ignore NULLs; `count(*)` counts rows but `count(col)` and",
        "#   `count(distinct col)` ignore NULLs — preserve the exact variant.",
    ]
    if _GROUP_BY_RE.search(step.text):
        lines += [
            "# - ⚠ GROUP BY REMERGING (critical, differs from Spark): if the SELECT",
            "#   lists a column that is NOT in GROUP BY *alongside* an aggregate",
            "#   (e.g. `select dept, salary, salary/sum(salary) as pct ... group by dept`),",
            "#   SAS does NOT collapse to one row per group — it KEEPS EVERY detail row",
            "#   and remerges the group aggregate onto each. Translate that with a",
            "#   WINDOW function: `F.sum(x).over(Window.partitionBy(<group keys>))`,",
            "#   NOT groupBy/agg (which drops rows). Use groupBy ONLY when the SELECT",
            "#   is purely group keys + aggregates (a genuine one-row-per-group summary).",
            "# - ⚠ ORDERING: SAS GROUP BY returns rows ORDERED by the group keys; Spark",
            "#   does not. Add an explicit `.orderBy(<group keys>)` if output order",
            "#   matters. HAVING filters on the aggregate (per group, after remerge).",
        ]
    return lines


def _macro_context_lines(step: SasStep) -> list[str]:
    """Render dual-source macro provenance so the model generalizes the snapshot."""
    ctx = getattr(step, "macro_context", None)
    if ctx is None:
        return []
    lines = [
        "",
        "# ⚠ MACRO EXPANSION — the SAS step above is a SNAPSHOT of ONE run.",
        "# It was produced by MPRINT-expanding a SAS macro, so values that were",
        "# macro variables are now baked in as literals. Translate the GENERAL",
        "# logic from the parametric source below, NOT the snapshot's literals.",
    ]
    if ctx.original_source:
        lines += [
            "## Original parametric macro source:",
            "```sas",
            ctx.original_source.strip(),
            "```",
        ]
    if ctx.substitutions:
        lines += [
            "## Data-derived substitutions (NOT constants — externalize these):",
            "# Each literal below was substituted from a macro variable that came",
            "# from data (e.g. model coefficients via CALL SYMPUT). Do NOT scatter",
            "# them as inline literals. Lift them into a single, clearly-named",
            "# parameter mapping at the top of the module (e.g.",
            "# `COEFFICIENTS = {\"INTERCEPT\": -0.00637, ...}`) and compute the",
            "# result programmatically over that mapping (e.g. a dot-product with",
            "# `functions.col`). Add a comment that these are run-specific model",
            "# parameters and can later be replaced by a join to a coefficient table.",
        ]
        for s in ctx.substitutions:
            lines.append(f"#   {s.macro_var} = {s.value}")
    return lines


def translation_prompt(
    step: SasStep,
    input_schemas: dict[str, Schema] | None = None,
    output_schema: Schema | None = None,
    input_samples: dict[str, str] | None = None,
    output_sample: str | None = None,
) -> str:
    input_schemas = input_schemas or {}
    in_lines = [f"  {k} -> {_schema_block('cols', input_schemas.get(k))}" for k in
                [r.key for r in step.inputs]] or ["  (none)"]
    parts = [
        TARGET_CONTRACT,
        "",
        f"# SAS step ({step.kind.value}"
        + (f"/{step.proc_name}" if step.proc_name else "")
        + ")",
        "```sas",
        step.text,
        "```",
        *_proc_sql_lines(step),
        *_macro_context_lines(step),
        "",
        "# Input datasets (keys you will find in `inputs`):",
        *in_lines,
        "",
        "# Expected output schema:",
        "  " + _schema_block("cols", output_schema),
        *_sample_lines(step, input_samples, output_sample),
        "",
        "Return the PySpark module now.",
    ]
    return "\n".join(parts)


def repair_prompt(
    step: SasStep,
    previous_code: str,
    failure_feedback: str,
    input_schemas: dict[str, Schema] | None = None,
    output_schema: Schema | None = None,
    input_samples: dict[str, str] | None = None,
    output_sample: str | None = None,
) -> str:
    base = translation_prompt(
        step, input_schemas, output_schema, input_samples, output_sample
    )
    return "\n".join(
        [
            base,
            "",
            "# Your previous attempt FAILED the evaluation gauntlet.",
            "## Previous PySpark:",
            "```python",
            previous_code.strip(),
            "```",
            "## Failure details:",
            failure_feedback.strip() or "(no details captured)",
            "",
            "Fix the specific problems above and return a corrected, complete module "
            "in one fenced code block. Keep the same `transform(spark, inputs)` contract.",
        ]
    )


def judge_prompt(
    step: SasStep,
    candidate_code: str,
    input_schemas: dict[str, Schema] | None = None,
) -> str:
    input_schemas = input_schemas or {}
    in_desc = ", ".join(r.key for r in step.inputs) or "(none)"
    return "\n".join(
        [
            "Assess whether the PySpark below is logically equivalent to the SAS step.",
            f"Inputs available to the translation: {in_desc}",
            "",
            "## SAS step:",
            "```sas",
            step.text,
            "```",
            "## Candidate PySpark:",
            "```python",
            candidate_code.strip(),
            "```",
            "",
            "Respond with STRICT JSON only, no prose, of the form:",
            '{"equivalent": <bool>, "confidence": <0..1>, '
            '"issues": [<short strings>], "explanation": <short string>}',
            "Set equivalent=false if any SAS semantics (RETAIN, FIRST./LAST., merge "
            "cardinality, join type, null handling, ordering) are not faithfully preserved. "
            "In particular, flag PROC SQL GROUP BY *remerging*: if the SAS SELECT mixes a "
            "non-grouped column with an aggregate, SAS keeps all detail rows (window "
            "semantics) — a PySpark groupBy/agg that collapses to one row per group is NOT "
            "equivalent.",
        ]
    )
