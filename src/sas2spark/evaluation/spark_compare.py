"""Distributed (Spark-native) reconciliation for the schema/property/diff phases.

The pandas path in :mod:`compare` collects both the actual output and the golden
dataset to the driver and compares them in pandas/numpy. That is exact and well
tested, but it is single-node: every row lives in driver RAM, so it does not
scale much past a few million rows per dataset.

This module compares two **Spark DataFrames** without ever collecting the rows:

* schema   — column sets + dtype families + distributed row counts;
* property — one ``agg`` per frame (null count, distinct count, sum, mean per
  column), so only a handful of scalars come back to the driver;
* values   — order-insensitive, tolerance-aware multiset diff via ``exceptAll``;
  only a small sample of mismatching rows is ever collected.

Tolerance handling for the value diff is *absolute*: float columns are rounded to
``decimals = round(-log10(atol))`` on both sides before the diff, so values that
agree within ``atol`` collapse to equal. (The pandas path additionally honours a
relative tolerance; the distributed diff is absolute-only — see the diagnostics
note.) Non-numeric columns are compared by their string form, matching the
object-equality semantics of the pandas path. Nulls compare equal to nulls.
"""
from __future__ import annotations

import math


def _functions():
    from pyspark.sql import functions as F  # type: ignore

    return F


_NUMERIC_TYPES = {
    "byte", "short", "integer", "long", "float", "double", "decimal",
}


def _families(df) -> dict[str, str]:
    """Lowercased column name -> dtype family (numeric/bool/datetime/string)."""
    fams: dict[str, str] = {}
    for field in df.schema.fields:
        t = field.dataType.typeName().lower()
        if t == "boolean":
            fam = "bool"
        elif t in _NUMERIC_TYPES or t.startswith("decimal"):
            fam = "numeric"
        elif t in ("timestamp", "date", "timestamp_ntz"):
            fam = "datetime"
        else:
            fam = "string"
        fams[field.name.lower()] = fam
    return fams


def _lower(df):
    """Re-alias every column to its lowercased name (parity with the pandas path)."""
    F = _functions()
    return df.select([F.col(c).alias(c.lower()) for c in df.columns])


def _decimals_for(atol: float) -> int | None:
    if atol and atol > 0:
        return max(0, min(12, int(round(-math.log10(atol)))))
    return None


def compare_schema_spark(actual, golden) -> tuple[bool, list[str]]:
    a, g = _lower(actual), _lower(golden)
    fa, fg = _families(a), _families(g)
    diags: list[str] = []

    aset, gset = set(fa), set(fg)
    missing = sorted(gset - aset)
    extra = sorted(aset - gset)
    if missing:
        diags.append(f"missing columns vs golden: {missing}")
    if extra:
        diags.append(f"unexpected extra columns: {extra}")

    family_mismatch = False
    for col in sorted(gset & aset):
        if fa[col] != fg[col]:
            family_mismatch = True
            diags.append(f"column '{col}' dtype family {fa[col]} != golden {fg[col]}")

    na, ng = a.count(), g.count()
    if na != ng:
        diags.append(f"row count {na} != golden {ng}")

    passed = not missing and not extra and not family_mismatch and na == ng
    return passed, diags


def _profile(df, fams: dict[str, str]) -> dict:
    """One distributed agg: null/distinct counts (+ sum/mean for numerics)."""
    F = _functions()
    aggs = []
    for col, fam in fams.items():
        aggs.append(F.count(F.when(F.col(col).isNull(), F.lit(1))).alias(f"{col}__nulls"))
        aggs.append(F.countDistinct(F.col(col)).alias(f"{col}__distinct"))
        if fam == "numeric":
            aggs.append(F.sum(F.col(col).cast("double")).alias(f"{col}__sum"))
            aggs.append(F.avg(F.col(col).cast("double")).alias(f"{col}__mean"))
    row = df.agg(*aggs).collect()[0].asDict()
    return row


def _close(a, b, atol: float, rtol: float) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(a - b) <= atol + rtol * abs(b)


def compare_properties_spark(
    actual, golden, *, atol: float, rtol: float = 1e-6
) -> tuple[bool, list[str]]:
    a, g = _lower(actual), _lower(golden)
    fa, fg = _families(a), _families(g)
    common = sorted(set(fa) & set(fg))
    diags: list[str] = []

    na, ng = a.count(), g.count()
    if na != ng:
        diags.append(f"row count {na} != golden {ng}")

    pa = _profile(a, {c: fa[c] for c in common})
    pg = _profile(g, {c: fg[c] for c in common})

    for col in common:
        if pa[f"{col}__nulls"] != pg[f"{col}__nulls"]:
            diags.append(
                f"'{col}' null count {pa[f'{col}__nulls']} != golden {pg[f'{col}__nulls']}"
            )
        if pa[f"{col}__distinct"] != pg[f"{col}__distinct"]:
            diags.append(
                f"'{col}' distinct count {pa[f'{col}__distinct']} "
                f"!= golden {pg[f'{col}__distinct']}"
            )
        if fa[col] == "numeric" and fg[col] == "numeric":
            for stat in ("sum", "mean"):
                av, gv = pa[f"{col}__{stat}"], pg[f"{col}__{stat}"]
                if not _close(av, gv, atol, rtol):
                    diags.append(f"'{col}' {stat} {av!r} != golden {gv!r}")

    passed = not diags
    return passed, diags


def _canonical(df, common: list[str], fams: dict[str, str], decimals: int | None):
    """Project to ``common`` with stable, comparable types for an exceptAll diff."""
    F = _functions()
    exprs = []
    for col in common:
        if fams[col] == "numeric":
            c = F.col(col).cast("double")
            if decimals is not None:
                c = F.round(c, decimals)
            exprs.append(c.alias(col))
        else:
            # String form gives well-defined, type-stable equality (and matches
            # the object-equality the pandas path uses for non-numerics).
            exprs.append(F.col(col).cast("string").alias(col))
    return df.select(exprs)


def compare_values_spark(
    actual, golden, *, atol: float, rtol: float = 1e-6, max_report: int = 20
) -> tuple[bool, list[str]]:
    a, g = _lower(actual), _lower(golden)
    fa, fg = _families(a), _families(g)
    diags: list[str] = []

    common = sorted(set(fa) & set(fg))
    if set(fa) != set(fg):
        diags.append(f"column sets differ; comparing intersection of {len(common)} columns")
    if not common:
        diags.append("no common columns to compare")
        return False, diags

    na, ng = a.count(), g.count()
    if na != ng:
        diags.append(f"row count {na} != golden {ng}; cannot value-compare")
        return False, diags

    decimals = _decimals_for(atol)
    a2 = _canonical(a, common, fa, decimals)
    g2 = _canonical(g, common, fg, decimals)

    # Multiset difference both ways — order-insensitive, duplicate-aware, and
    # null-safe. limit(max_report+1) lets Spark short-circuit instead of
    # materializing a potentially huge diff.
    only_actual = a2.exceptAll(g2).limit(max_report + 1).collect()
    only_golden = g2.exceptAll(a2).limit(max_report + 1).collect()

    if not only_actual and not only_golden:
        if decimals is not None:
            diags.append(
                f"value diff used absolute tolerance (rounded to {decimals} decimals); "
                "relative tolerance is not applied in spark engine"
            )
        return True, diags

    for label, rows in (("only in actual", only_actual), ("only in golden", only_golden)):
        for r in rows[:max_report]:
            diags.append(f"{label}: {r.asDict()}")
    a_more = "+" if len(only_actual) > max_report else ""
    g_more = "+" if len(only_golden) > max_report else ""
    diags.append(
        f"rows only in actual: {min(len(only_actual), max_report)}{a_more}; "
        f"rows only in golden: {min(len(only_golden), max_report)}{g_more}"
    )
    return False, diags
