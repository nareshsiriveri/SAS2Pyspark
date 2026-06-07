"""Macro flattening: turn a SAS run's MPRINT log into concrete, unrolled steps."""
from __future__ import annotations

from .macro_flattener import flatten, flatten_log, looks_like_log

__all__ = ["flatten", "flatten_log", "looks_like_log"]
