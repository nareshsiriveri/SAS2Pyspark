"""Eval phases 2-4 (schema / property / data-equivalence) over pandas frames.

The PySpark output is materialized to pandas once by the gauntlet and handed to
these wrappers, which turn the comparison helpers in :mod:`compare` into
:class:`EvalResult` objects.
"""
from __future__ import annotations

from ..models import EvalPhase, EvalResult
from .compare import compare_properties, compare_schema, compare_values


def evaluate_schema(actual_pd, golden_pd) -> EvalResult:
    passed, diags = compare_schema(actual_pd, golden_pd)
    return EvalResult(
        phase=EvalPhase.SCHEMA,
        passed=passed,
        summary="schema matches golden" if passed else "schema mismatch",
        diagnostics=diags,
    )


def evaluate_property(actual_pd, golden_pd, *, atol: float) -> EvalResult:
    passed, diags = compare_properties(actual_pd, golden_pd, atol=atol)
    return EvalResult(
        phase=EvalPhase.PROPERTY,
        passed=passed,
        summary="invariants match golden" if passed else "property/invariant mismatch",
        diagnostics=diags,
    )


def evaluate_diff(actual_pd, golden_pd, *, atol: float) -> EvalResult:
    passed, diags = compare_values(actual_pd, golden_pd, atol=atol)
    return EvalResult(
        phase=EvalPhase.DIFF,
        passed=passed,
        summary="values match golden (within tolerance)" if passed else "value-level diff",
        diagnostics=diags,
    )
