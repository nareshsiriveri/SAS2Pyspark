"""Component 6 — Golden data, without instrumentation.

Because SAS writes datasets between steps during a normal run, those ``.sas7bdat``
files *are* step-level golden data — no checkpoint injection required. This module
discovers them in a directory and loads them into pandas (and, on demand, Spark).

Discovery maps file names to dataset keys:
    work.accounts.sas7bdat        -> work.accounts
    accounts.sas7bdat             -> work.accounts   (default library)
    raw/accounts.sas7bdat         -> raw.accounts    (subdir = library)
"""
from __future__ import annotations

import os
from typing import Any, Optional

from ..models import Schema


def _pandas():
    try:
        import pandas as pd  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "pandas is required to read golden datasets. "
            "Install with: pip install 'sas2spark[golden]'"
        ) from exc
    return pd


def read_sas_dataset(path: str):
    """Read a golden dataset into a pandas DataFrame.

    Primary format is SAS ``.sas7bdat`` (what a normal SAS run writes between
    steps). ``.parquet`` and ``.csv`` are also accepted — convenient for tests and
    for golden data exported from other tooling.
    """
    pd = _pandas()
    low = path.lower()
    if low.endswith(".parquet"):
        return pd.read_parquet(path)
    if low.endswith((".csv", ".tsv")):
        sep = "\t" if low.endswith(".tsv") else ","
        return pd.read_csv(path, sep=sep)
    try:
        import pyreadstat  # type: ignore

        df, _meta = pyreadstat.read_sas7bdat(path)
        return df
    except ImportError:
        # pandas can read sas7bdat directly for many files.
        return pd.read_sas(path)


def write_golden_dataset(pdf, path: str) -> str:
    """Write a pandas DataFrame as a golden dataset (format from the extension).

    Used to build test fixtures. Supports ``.parquet`` and ``.csv``.
    """
    low = path.lower()
    if low.endswith(".parquet"):
        pdf.to_parquet(path, index=False)
    elif low.endswith((".csv", ".tsv")):
        pdf.to_csv(path, index=False, sep="\t" if low.endswith(".tsv") else ",")
    else:
        raise ValueError(f"unsupported golden write format for {path!r}")
    return path


def schema_of_dataframe(pdf, *, with_rows: bool = True) -> Schema:
    """Infer a lightweight :class:`Schema` from a pandas DataFrame."""
    pd = _pandas()
    cols: dict[str, str] = {}
    for name in pdf.columns:
        dtype = pdf[name].dtype
        cols[str(name)] = _simple_dtype(pd, dtype)
    row_count = int(len(pdf)) if with_rows else None
    return Schema(columns=cols, row_count=row_count)


def _simple_dtype(pd, dtype) -> str:
    name = str(dtype)
    if pd.api.types.is_bool_dtype(dtype):
        return "bool"
    if pd.api.types.is_integer_dtype(dtype):
        return "int"
    if pd.api.types.is_float_dtype(dtype):
        return "double"
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return "datetime"
    if "date" in name:
        return "date"
    return "string"


class GoldenStore:
    """Index of golden datasets discovered under a directory."""

    def __init__(self, root: str, default_library: str = "work"):
        self.root = root
        self.default_library = default_library
        self._index: dict[str, str] = {}
        self._pandas_cache: dict[str, Any] = {}
        if root and os.path.isdir(root):
            self._discover()

    def _discover(self) -> None:
        for dirpath, _dirs, files in os.walk(self.root):
            for fn in files:
                low = fn.lower()
                if not low.endswith((".sas7bdat", ".sashdat", ".parquet", ".csv", ".tsv")):
                    continue
                stem = os.path.splitext(fn)[0].lower()
                rel_dir = os.path.relpath(dirpath, self.root)
                if "." in stem:  # lib.name.sas7bdat
                    key = stem
                elif rel_dir not in (".", ""):  # lib/name.sas7bdat
                    lib = os.path.basename(dirpath).lower()
                    key = f"{lib}.{stem}"
                else:
                    key = f"{self.default_library}.{stem}"
                self._index[key] = os.path.join(dirpath, fn)

    # --- queries ---
    def keys(self) -> list[str]:
        return sorted(self._index)

    def has(self, dataset_key: str) -> bool:
        return dataset_key.lower() in self._index

    def path(self, dataset_key: str) -> Optional[str]:
        return self._index.get(dataset_key.lower())

    def pandas(self, dataset_key: str):
        key = dataset_key.lower()
        if key not in self._pandas_cache:
            p = self._index.get(key)
            if p is None:
                raise KeyError(f"no golden dataset for {dataset_key!r}")
            self._pandas_cache[key] = read_sas_dataset(p)
        return self._pandas_cache[key]

    def schema(self, dataset_key: str) -> Schema:
        return schema_of_dataframe(self.pandas(dataset_key))

    def spark(self, spark, dataset_key: str):
        """Load a golden dataset as a Spark DataFrame (via pandas)."""
        return spark.createDataFrame(self.pandas(dataset_key))
