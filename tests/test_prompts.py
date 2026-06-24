"""Prompt construction: golden sample rows are shown to the translator."""
from sas2spark.llm.prompts import repair_prompt, translation_prompt
from sas2spark.parse import segment

STEP = segment("data work.a; set raw.x; run;")[0]


def test_translation_prompt_includes_samples():
    text = translation_prompt(
        STEP,
        input_samples={"raw.x": "id amount\n 1   10.5"},
        output_sample="id amount\n 1   11.0",
    )
    assert "Sample rows from the ACTUAL input data" in text
    assert "id amount" in text
    assert "EXPECTED output" in text


def test_translation_prompt_without_samples_unchanged():
    text = translation_prompt(STEP)
    assert "Sample rows" not in text
    assert "Return the PySpark module now." in text


def test_proc_sql_group_by_gets_remerge_warning():
    step = segment(
        "proc sql; create table work.r as "
        "select dept, salary, salary/sum(salary) as pct from work.emp group by dept; quit;"
    )[0]
    text = translation_prompt(step)
    assert "SAS PROC SQL" in text
    assert "REMERGING" in text
    assert "Window.partitionBy" in text
    assert "ORDERING" in text


def test_proc_sql_without_group_by_omits_remerge_block():
    step = segment(
        "proc sql; create table work.r as select a, b from work.t where a > 0; quit;"
    )[0]
    text = translation_prompt(step)
    assert "SAS PROC SQL" in text  # general PROC SQL note still present
    assert "REMERGING" not in text  # but no group-by-specific block


def test_non_sql_step_has_no_proc_sql_block():
    text = translation_prompt(STEP)  # a plain DATA step
    assert "SAS PROC SQL" not in text


def test_repair_prompt_carries_samples():
    text = repair_prompt(
        STEP,
        previous_code="def transform(spark, inputs): ...",
        failure_feedback="row count 1 != golden 2",
        input_samples={"raw.x": "id\n1"},
    )
    assert "Sample rows from the ACTUAL input data" in text
    assert "Previous PySpark" in text
