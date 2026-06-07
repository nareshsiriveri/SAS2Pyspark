from sas2spark.evaluation.static_eval import evaluate_static
from sas2spark.models import EvalPhase

GOOD = """\
from pyspark.sql import functions as F


def transform(spark, inputs):
    df = inputs["work.a"]
    return df.withColumn("y", F.col("x") + 1)
"""


def test_good_code_passes():
    r = evaluate_static(GOOD)
    assert r.phase is EvalPhase.STATIC
    assert r.passed, r.feedback()


def test_syntax_error_fails():
    r = evaluate_static("def transform(spark, inputs):\n    return (")
    assert not r.passed
    assert "compile" in r.summary


def test_missing_transform_fails():
    r = evaluate_static("x = 1\n")
    assert not r.passed
    assert "transform" in r.summary


def test_wrong_arity_fails():
    r = evaluate_static("def transform(spark):\n    return spark\n")
    assert not r.passed


def test_top_level_side_effect_fails():
    code = "def transform(spark, inputs):\n    return inputs\n\nprint('side effect')\n"
    r = evaluate_static(code)
    assert not r.passed


def test_sparksession_creation_flagged():
    code = (
        "from pyspark.sql import SparkSession\n"
        "def transform(spark, inputs):\n"
        "    s = SparkSession.builder.getOrCreate()\n"
        "    return s\n"
    )
    r = evaluate_static(code)
    assert not r.passed
