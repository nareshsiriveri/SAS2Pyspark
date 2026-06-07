"""Central configuration, resolved from environment variables with sane defaults.

Nothing here imports a heavy dependency, so ``Settings.from_env()`` is always cheap.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from typing import Any


def _get(name: str, default: str | None = None) -> str | None:
    val = os.environ.get(name)
    return val if val not in (None, "") else default


def _get_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw in (None, ""):
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _get_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw in (None, ""):
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass
class Settings:
    """Runtime configuration for the whole pipeline."""

    # --- LLM (primary) ---
    llm_provider: str = "openai"          # "openai" | "anthropic" | "stub"
    llm_model: str = "gpt-5.5"
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    llm_temperature: float | None = None  # None => use provider default
    llm_max_output_tokens: int = 4096
    llm_timeout_s: float = 120.0
    llm_max_retries: int = 3

    # --- LLM (secondary / fallback) ---
    # When the primary provider errors (quota, auth, outage), the client falls
    # back to this provider. Set to None to disable fallback.
    fallback_provider: str | None = "anthropic"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-4-8"

    # --- Translation target ---
    target: str = "pyspark"

    # --- Pipeline ---
    max_repair_attempts: int = 3
    float_tolerance: float = 1e-9
    # SAS dates are days since 1960-01-01; datetimes are seconds since then.
    sas_epoch: str = "1960-01-01"
    # Default SAS library for unqualified dataset names.
    default_library: str = "work"

    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            llm_provider=_get("SAS2SPARK_LLM_PROVIDER", "openai"),
            llm_model=_get("SAS2SPARK_LLM_MODEL", "gpt-5.5"),
            llm_api_key=_get("OPENAI_API_KEY"),
            llm_base_url=_get("OPENAI_BASE_URL"),
            fallback_provider=_get("SAS2SPARK_LLM_FALLBACK_PROVIDER", "anthropic"),
            anthropic_api_key=_get("ANTHROPIC_API_KEY"),
            anthropic_model=_get("SAS2SPARK_ANTHROPIC_MODEL", "claude-opus-4-8"),
            target=_get("SAS2SPARK_TARGET", "pyspark"),
            max_repair_attempts=_get_int("SAS2SPARK_MAX_REPAIR_ATTEMPTS", 3),
            float_tolerance=_get_float("SAS2SPARK_FLOAT_TOLERANCE", 1e-9),
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # Never serialize secrets (manifests/reports get written to disk).
        for secret_field in ("llm_api_key", "anthropic_api_key"):
            if d.get(secret_field):
                d[secret_field] = "***"
        return d
