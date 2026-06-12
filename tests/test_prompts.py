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


def test_repair_prompt_carries_samples():
    text = repair_prompt(
        STEP,
        previous_code="def transform(spark, inputs): ...",
        failure_feedback="row count 1 != golden 2",
        input_samples={"raw.x": "id\n1"},
    )
    assert "Sample rows from the ACTUAL input data" in text
    assert "Previous PySpark" in text
