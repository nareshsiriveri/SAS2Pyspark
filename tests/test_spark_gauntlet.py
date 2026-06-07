"""End-to-end Spark-backed gauntlet test against synthetic golden data.

Runs a *real* generated transform on a local SparkSession, materializes the
output, and compares it to the golden dataset through the full gauntlet
(static -> schema -> property -> diff). Self-skips unless pandas, pyspark, and a
Java runtime are all present.
"""
import shutil

import pytest

# Robust skip: pandas may raise ValueError (NumPy ABI), pyspark needs Java.
try:
    import numpy  # noqa: F401
    import pandas  # noqa: F401
    _PANDAS_OK = True
except Exception:  # noqa: BLE001
    _PANDAS_OK = False

try:
    import pyspark  # noqa: F401
    _PYSPARK_OK = True
except Exception:  # noqa: BLE001
    _PYSPARK_OK = False

_JAVA_OK = shutil.which("java") is not None

pytestmark = pytest.mark.skipif(
    not (_PANDAS_OK and _PYSPARK_OK and _JAVA_OK),
    reason="needs pandas + pyspark + a Java runtime",
)

from sas2spark.config import Settings  # noqa: E402
from sas2spark.evaluation.base import EvalContext  # noqa: E402
from sas2spark.evaluation.gauntlet import Gauntlet  # noqa: E402
from sas2spark.flatten import flatten  # noqa: E402
from sas2spark.golden import GoldenStore  # noqa: E402
from sas2spark.parse import segment  # noqa: E402

from golden_fixtures import write_golden_dir  # noqa: E402

EXAMPLE = "examples/example.sas"

CORRECT_PRICED = '''
from pyspark.sql import functions as F


def transform(spark, inputs):
    a = inputs["work.accounts"].alias("a")
    r = inputs["work.rates"].alias("r")
    return (
        a.join(r, F.col("a.region") == F.col("r.region"), "left")
        .select(
            F.col("a.account_id").alias("account_id"),
            F.col("a.region").alias("region"),
            F.col("a.balance").alias("balance"),
            F.col("r.rate").alias("rate"),
            (F.col("a.balance") * F.col("r.rate")).alias("interest"),
        )
    )
'''

WRONG_PRICED = '''
from pyspark.sql import functions as F


def transform(spark, inputs):
    a = inputs["work.accounts"].alias("a")
    r = inputs["work.rates"].alias("r")
    return (
        a.join(r, F.col("a.region") == F.col("r.region"), "left")
        .select(
            F.col("a.account_id").alias("account_id"),
            F.col("a.region").alias("region"),
            F.col("a.balance").alias("balance"),
            F.col("r.rate").alias("rate"),
            (F.col("a.balance") + F.col("r.rate")).alias("interest"),  # BUG: + not *
        )
    )
'''


@pytest.fixture(scope="module")
def priced_step():
    steps = segment(flatten(open(EXAMPLE, encoding="utf-8").read()))
    # step index 2 is the PROC SQL that creates work.priced
    step = next(s for s in steps if any(o.key == "work.priced" for o in s.outputs))
    return step


@pytest.fixture(scope="module")
def golden(tmp_path_factory):
    root = str(tmp_path_factory.mktemp("golden"))
    write_golden_dir(root, fmt="csv")
    return GoldenStore(root)


def _ctx(golden):
    return EvalContext(settings=Settings(), golden=golden, llm=None)


def test_correct_transform_passes_full_gauntlet(priced_step, golden):
    ctx = _ctx(golden)
    try:
        report = Gauntlet(ctx).run(priced_step, CORRECT_PRICED)
    finally:
        ctx.stop()
    phases = {r.phase.value: r for r in report.results}
    assert phases["static"].passed
    assert phases["schema"].passed, phases["schema"].feedback()
    assert phases["property"].passed, phases["property"].feedback()
    assert phases["data_equivalence"].passed, phases["data_equivalence"].feedback()
    assert report.passed


def test_wrong_transform_fails_on_values(priced_step, golden):
    ctx = _ctx(golden)
    try:
        report = Gauntlet(ctx).run(priced_step, WRONG_PRICED)
    finally:
        ctx.stop()
    assert not report.passed
    # static passes (it compiles); the failure is in a value-level phase.
    failed = [r.phase.value for r in report.results if not r.passed and not r.skipped]
    assert ("property" in failed) or ("data_equivalence" in failed)
