"""Shared eval plumbing: the execution context and a safe-ish module loader.

``load_transform`` compiles a generated module in an isolated namespace and
returns its ``transform`` callable. The Spark-dependent eval phases use
``EvalContext`` to access the golden store, the SparkSession factory, tolerances,
and the LLM client (for the judge phase).
"""
from __future__ import annotations

import types
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from ..config import Settings
from ..golden import GoldenStore
from ..llm import LLMClient


class TransformContractError(ValueError):
    """The generated module does not satisfy the transform(spark, inputs) contract."""


def load_transform(code: str, module_name: str = "generated_step") -> Callable:
    """Compile generated code and return its ``transform`` function.

    Raises :class:`SyntaxError` if it doesn't compile and
    :class:`TransformContractError` if no ``transform`` callable is defined.
    """
    compiled = compile(code, filename=f"<{module_name}>", mode="exec")
    module = types.ModuleType(module_name)
    module.__dict__["__name__"] = module_name
    exec(compiled, module.__dict__)  # noqa: S102 - executing generated code by design
    fn = module.__dict__.get("transform")
    if not callable(fn):
        raise TransformContractError("module does not define a callable `transform`")
    return fn


@dataclass
class EvalContext:
    settings: Settings
    golden: Optional[GoldenStore] = None
    spark_factory: Optional[Callable[[], Any]] = None
    llm: Optional[LLMClient] = None
    _spark: Any = field(default=None, repr=False)

    def spark(self):
        """Lazily create (and cache) a SparkSession via the configured factory."""
        if self._spark is not None:
            return self._spark
        if self.spark_factory is not None:
            self._spark = self.spark_factory()
            return self._spark
        from .spark_runtime import default_spark_session

        self._spark = default_spark_session()
        return self._spark

    def stop(self) -> None:
        if self._spark is not None:
            try:
                self._spark.stop()
            except Exception:  # noqa: BLE001 - best-effort teardown
                pass
            self._spark = None
