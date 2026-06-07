"""The layered evaluation gauntlet (cheapest checks first, fail fast)."""
from __future__ import annotations

from .base import EvalContext, load_transform
from .gauntlet import Gauntlet, GauntletReport

__all__ = ["EvalContext", "load_transform", "Gauntlet", "GauntletReport"]
