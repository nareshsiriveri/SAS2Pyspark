"""Prompt templates for translation, repair, and the LLM-as-judge eval.

Prompts are small and per-step: one SAS step plus its input/output schemas.
This keeps each LLM call cheap, reliable, and locally debuggable.
"""
from __future__ import annotations

from ..models import SasStep, Schema

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


def translation_prompt(
    step: SasStep,
    input_schemas: dict[str, Schema] | None = None,
    output_schema: Schema | None = None,
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
        "",
        "# Input datasets (keys you will find in `inputs`):",
        *in_lines,
        "",
        "# Expected output schema:",
        "  " + _schema_block("cols", output_schema),
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
) -> str:
    base = translation_prompt(step, input_schemas, output_schema)
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
            "cardinality, join type, null handling, ordering) are not faithfully preserved.",
        ]
    )
