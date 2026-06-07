"""SAS-aware comparison helpers operating on pandas DataFrames.

Used by the schema / property / data-equivalence phases. The actual (PySpark)
output is collected to pandas once and compared against the golden pandas frame:

* float tolerance for numerics,
* SAS missing values treated as Spark/pandas null (null == null),
* order-insensitive comparison (Spark DataFrames are unordered) by sorting on all
  comparable columns before the value diff.
"""
from __future__ import annotations

from typing import Any


def _np_pd():
    import numpy as np  # type: ignore
    import pandas as pd  # type: ignore

    return np, pd


def _lower_cols(df):
    df = df.copy()
    df.columns = [str(c).lower() for c in df.columns]
    return df


def _family(pd, series) -> str:
    dtype = series.dtype
    if pd.api.types.is_bool_dtype(dtype):
        return "bool"
    if pd.api.types.is_numeric_dtype(dtype):
        return "numeric"
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return "datetime"
    return "string"


def compare_schema(actual, golden) -> tuple[bool, list[str]]:
    _np, pd = _np_pd()
    a, g = _lower_cols(actual), _lower_cols(golden)
    diags: list[str] = []
    aset, gset = set(a.columns), set(g.columns)
    missing = sorted(gset - aset)
    extra = sorted(aset - gset)
    if missing:
        diags.append(f"missing columns vs golden: {missing}")
    if extra:
        diags.append(f"unexpected extra columns: {extra}")

    for col in sorted(gset & aset):
        fa, fg = _family(pd, a[col]), _family(pd, g[col])
        if fa != fg:
            diags.append(f"column '{col}' dtype family {fa} != golden {fg}")

    if len(a) != len(g):
        diags.append(f"row count {len(a)} != golden {len(g)}")

    passed = not missing and not extra and not any("dtype family" in d for d in diags) \
        and len(a) == len(g)
    return passed, diags


def compare_properties(actual, golden, *, atol: float, rtol: float = 1e-6) -> tuple[bool, list[str]]:
    np, pd = _np_pd()
    a, g = _lower_cols(actual), _lower_cols(golden)
    diags: list[str] = []
    common = sorted(set(a.columns) & set(g.columns))

    if len(a) != len(g):
        diags.append(f"row count {len(a)} != golden {len(g)}")

    for col in common:
        an, gn = int(a[col].isna().sum()), int(g[col].isna().sum())
        if an != gn:
            diags.append(f"'{col}' null count {an} != golden {gn}")

        ad, gd = int(a[col].nunique(dropna=True)), int(g[col].nunique(dropna=True))
        if ad != gd:
            diags.append(f"'{col}' distinct count {ad} != golden {gd}")

        if pd.api.types.is_numeric_dtype(g[col].dtype) and pd.api.types.is_numeric_dtype(a[col].dtype):
            for stat, fn in (("sum", "sum"), ("mean", "mean")):
                av = getattr(a[col], fn)()
                gv = getattr(g[col], fn)()
                if pd.isna(av) and pd.isna(gv):
                    continue
                if pd.isna(av) or pd.isna(gv) or not _close(np, av, gv, atol, rtol):
                    diags.append(f"'{col}' {stat} {av!r} != golden {gv!r}")

    passed = not diags
    return passed, diags


def compare_values(
    actual, golden, *, atol: float, rtol: float = 1e-6, max_report: int = 10
) -> tuple[bool, list[str]]:
    np, pd = _np_pd()
    a, g = _lower_cols(actual), _lower_cols(golden)
    diags: list[str] = []

    common = sorted(set(a.columns) & set(g.columns))
    if set(a.columns) != set(g.columns):
        diags.append(
            f"column sets differ; comparing intersection of {len(common)} columns"
        )
    if len(a) != len(g):
        diags.append(f"row count {len(a)} != golden {len(g)}; cannot value-compare")
        return False, diags
    if not common:
        diags.append("no common columns to compare")
        return False, diags

    # Order-insensitive: sort both by all common columns.
    a_sorted = a[common].sort_values(by=common, kind="mergesort").reset_index(drop=True)
    g_sorted = g[common].sort_values(by=common, kind="mergesort").reset_index(drop=True)

    mismatches = 0
    for col in common:
        acol, gcol = a_sorted[col], g_sorted[col]
        if pd.api.types.is_numeric_dtype(gcol.dtype) and pd.api.types.is_numeric_dtype(acol.dtype):
            av = acol.to_numpy(dtype="float64", na_value=np.nan)
            gv = gcol.to_numpy(dtype="float64", na_value=np.nan)
            ok = np.isclose(av, gv, atol=atol, rtol=rtol, equal_nan=True)
        else:
            # Element-wise equality with null == null.
            a_na, g_na = acol.isna().to_numpy(), gcol.isna().to_numpy()
            eq = (acol.astype("object").to_numpy() == gcol.astype("object").to_numpy())
            ok = (eq | (a_na & g_na))
        bad_idx = np.nonzero(~ok)[0]
        for i in bad_idx[: max_report]:
            mismatches += 1
            if len(diags) < max_report:
                diags.append(
                    f"'{col}' row {int(i)}: actual={acol.iloc[int(i)]!r} "
                    f"golden={gcol.iloc[int(i)]!r}"
                )
        mismatches += max(0, len(bad_idx) - max_report)

    if mismatches:
        diags.append(f"total cell mismatches: {mismatches}")
        return False, diags
    return True, diags


def _close(np, a: Any, b: Any, atol: float, rtol: float) -> bool:
    try:
        return bool(np.isclose(float(a), float(b), atol=atol, rtol=rtol, equal_nan=True))
    except (TypeError, ValueError):
        return a == b
