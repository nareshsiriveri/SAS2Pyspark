"""Macro flattening: turn a SAS run's MPRINT log into concrete, unrolled steps."""
from __future__ import annotations

from .macro_context import (
    attach_macro_context,
    derived_substitutions,
    extract_macro_defs,
    harvest_log,
)
from .macro_flattener import flatten, flatten_log, looks_like_log

__all__ = [
    "flatten",
    "flatten_log",
    "looks_like_log",
    "attach_macro_context",
    "extract_macro_defs",
    "harvest_log",
    "derived_substitutions",
]
