"""Spark session helper and execution of a generated ``transform``.

Kept separate so that importing the eval package never imports PySpark until a
Spark-backed phase actually runs.
"""
from __future__ import annotations

from typing import Any, Callable

from ..models import SasStep


def default_spark_session(app_name: str = "sas2spark-eval"):
    """Create a local SparkSession suitable for unit-level evaluation."""
    import os
    import sys

    try:
        from pyspark.sql import SparkSession  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "pyspark is required for schema/property/diff/E2E evals. "
            "Install with: pip install 'sas2spark[spark]'"
        ) from exc

    # Pin the worker/driver Python to *this* interpreter. Without this, the Spark
    # Python worker can fail to launch (java.io.EOFException in PythonRunner),
    # especially on Windows or inside a venv — and DataFrames built from pandas
    # need that worker to deserialize.
    os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
    os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)

    return (
        SparkSession.builder.appName(app_name)
        .master("local[*]")
        .config("spark.sql.shuffle.partitions", "4")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.session.timeZone", "UTC")
        # Arrow makes createDataFrame(pandas) / toPandas() columnar instead of
        # row-by-row through the Python worker. Spark silently falls back to the
        # non-Arrow path if pyarrow is unavailable or a dtype is unsupported.
        .config("spark.sql.execution.arrow.pyspark.enabled", "true")
        .config("spark.sql.execution.arrow.pyspark.fallback.enabled", "true")
        .getOrCreate()
    )


def run_transform(
    transform: Callable,
    spark,
    inputs: dict[str, Any],
):
    """Invoke a generated ``transform(spark, inputs)`` and return its DataFrame."""
    return transform(spark, inputs)


def load_inputs_from_golden(spark, step: SasStep, golden) -> dict[str, Any]:
    """Build the ``inputs`` dict for a step from the golden store."""
    inputs: dict[str, Any] = {}
    missing: list[str] = []
    for ref in step.inputs:
        if golden is not None and golden.has(ref.key):
            inputs[ref.key] = golden.spark(spark, ref.key)
        else:
            missing.append(ref.key)
    return inputs, missing  # type: ignore[return-value]
