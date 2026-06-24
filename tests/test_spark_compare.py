"""Distributed (Spark-native) reconciliation — compares two Spark DataFrames
without collecting rows. Self-skips unless pandas, pyspark and a JRE are present.
"""
import shutil

import pytest

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

from sas2spark.evaluation.spark_compare import (  # noqa: E402
    compare_properties_spark,
    compare_schema_spark,
    compare_values_spark,
)
from sas2spark.evaluation.spark_runtime import default_spark_session  # noqa: E402


@pytest.fixture(scope="module")
def spark():
    s = default_spark_session("sas2spark-compare-test")
    s.sparkContext.setLogLevel("ERROR")
    yield s
    s.stop()


def _golden(spark):
    return spark.createDataFrame(
        [(1, "US", 100.0, 0.10, 10.0),
         (2, "EU", 200.0, 0.20, 40.0),
         (4, "EU", 50.0, 0.20, 10.0)],
        ["account_id", "region", "balance", "rate", "interest"],
    )


def test_correct_output_passes_all_phases(spark):
    golden = _golden(spark)
    # Same data, rows reordered + columns reordered + uppercased names.
    actual = spark.createDataFrame(
        [(40.0, "EU", 2, 0.20, 200.0),
         (10.0, "US", 1, 0.10, 100.0),
         (10.0, "EU", 4, 0.20, 50.0)],
        ["INTEREST", "REGION", "ACCOUNT_ID", "RATE", "BALANCE"],
    )
    assert compare_schema_spark(actual, golden)[0]
    assert compare_properties_spark(actual, golden, atol=1e-9)[0]
    ok, diags = compare_values_spark(actual, golden, atol=1e-9)
    assert ok, diags


def test_float_tolerance_in_value_diff(spark):
    golden = _golden(spark)
    actual = spark.createDataFrame(
        [(1, "US", 100.0, 0.10, 10.0 + 1e-12),
         (2, "EU", 200.0, 0.20, 40.0),
         (4, "EU", 50.0, 0.20, 10.0)],
        ["account_id", "region", "balance", "rate", "interest"],
    )
    assert compare_values_spark(actual, golden, atol=1e-9)[0]


def test_wrong_values_fail(spark):
    golden = _golden(spark)
    actual = spark.createDataFrame(
        [(1, "US", 100.0, 0.10, 10.0),
         (2, "EU", 200.0, 0.20, 999.0),   # wrong
         (4, "EU", 50.0, 0.20, 10.0)],
        ["account_id", "region", "balance", "rate", "interest"],
    )
    assert not compare_properties_spark(actual, golden, atol=1e-9)[0]
    ok, diags = compare_values_spark(actual, golden, atol=1e-9)
    assert not ok
    assert any("only in" in d for d in diags)


def test_missing_column_fails_schema(spark):
    golden = _golden(spark)
    actual = golden.drop("rate")
    ok, diags = compare_schema_spark(actual, golden)
    assert not ok
    assert any("rate" in d for d in diags)


def test_row_count_mismatch_fails_schema(spark):
    golden = _golden(spark)
    actual = golden.limit(2)
    assert not compare_schema_spark(actual, golden)[0]


def test_null_count_mismatch_fails_property(spark):
    golden = _golden(spark)
    actual = spark.createDataFrame(
        [(1, "US", 100.0, None, 10.0),    # null introduced
         (2, "EU", 200.0, 0.20, 40.0),
         (4, "EU", 50.0, 0.20, 10.0)],
        ["account_id", "region", "balance", "rate", "interest"],
    )
    assert not compare_properties_spark(actual, golden, atol=1e-9)[0]


def test_duplicate_rows_detected_by_value_diff(spark):
    # Same multiset size, but a row duplicated in actual and another dropped —
    # exceptAll (multiset) must catch it where naive set-difference would not.
    golden = _golden(spark)
    actual = spark.createDataFrame(
        [(1, "US", 100.0, 0.10, 10.0),
         (1, "US", 100.0, 0.10, 10.0),    # dup of row 1
         (2, "EU", 200.0, 0.20, 40.0)],   # row 4 missing
        ["account_id", "region", "balance", "rate", "interest"],
    )
    assert not compare_values_spark(actual, golden, atol=1e-9)[0]
