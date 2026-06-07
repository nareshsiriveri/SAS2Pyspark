"""Comparison-logic coverage for the schema / property / data-equivalence phases.

These operate purely on pandas DataFrames (no Spark / no Java), so they exercise
the heart of phases 2-4 — what counts as a pass, and what each kind of defect
trips. Skipped if pandas/numpy aren't importable in the environment.
"""
import pytest

try:  # pandas can fail to import on a NumPy ABI mismatch (ValueError, not ImportError)
    import numpy  # noqa: F401
    import pandas as pd
except Exception:  # noqa: BLE001
    pd = None

pytestmark = pytest.mark.skipif(pd is None, reason="pandas/numpy unavailable in this env")

from sas2spark.evaluation.dataframe_evals import (  # noqa: E402
    evaluate_diff,
    evaluate_property,
    evaluate_schema,
)


def _golden():
    return pd.DataFrame(
        {
            "account_id": [1, 2, 4],
            "region": ["US", "EU", "EU"],
            "balance": [100.0, 200.0, 50.0],
            "rate": [0.10, 0.20, 0.20],
            "interest": [10.0, 40.0, 10.0],
        }
    )


def test_correct_output_passes_all_phases():
    golden = _golden()
    # Same data, rows shuffled and columns reordered — must still pass (order-insensitive).
    actual = golden.sample(frac=1.0, random_state=1)[
        ["region", "interest", "account_id", "rate", "balance"]
    ].reset_index(drop=True)

    assert evaluate_schema(actual, golden).passed
    assert evaluate_property(actual, golden, atol=1e-9).passed
    assert evaluate_diff(actual, golden, atol=1e-9).passed


def test_float_tolerance_in_diff():
    golden = _golden()
    actual = golden.copy()
    actual.loc[0, "interest"] = 10.0 + 1e-12  # within tolerance
    assert evaluate_diff(actual, golden, atol=1e-9).passed


def test_missing_column_fails_schema():
    golden = _golden()
    actual = golden.drop(columns=["rate"])
    r = evaluate_schema(actual, golden)
    assert not r.passed
    assert any("rate" in d for d in r.diagnostics)


def test_row_count_mismatch_fails_schema():
    golden = _golden()
    actual = golden.iloc[:2]
    assert not evaluate_schema(actual, golden).passed


def test_wrong_values_fail_property_and_diff():
    golden = _golden()
    actual = golden.copy()
    actual["interest"] = actual["balance"] + actual["rate"]  # wrong formula
    assert not evaluate_property(actual, golden, atol=1e-9).passed  # sums/means differ
    diff = evaluate_diff(actual, golden, atol=1e-9)
    assert not diff.passed
    assert any("interest" in d for d in diff.diagnostics)


def test_null_count_mismatch_fails_property():
    golden = _golden()
    actual = golden.copy()
    actual.loc[0, "rate"] = None  # introduces a null not present in golden
    assert not evaluate_property(actual, golden, atol=1e-9).passed
