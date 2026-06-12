"""LLM client abstraction.

The translator and the LLM-as-judge eval depend only on the :class:`LLMClient`
protocol, so the provider is swappable. Two implementations ship here:

* :class:`OpenAIClient` — calls the OpenAI ChatGPT API (default model ``gpt-5.5``).
* :class:`StubLLM` — fully offline; emits a trivial-but-valid PySpark module and
  canned judge verdicts so the deterministic pipeline runs without an API key.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol, runtime_checkable

from ..config import Settings


@dataclass
class LLMResponse:
    text: str
    model: str
    usage: dict[str, Any] = field(default_factory=dict)
    raw: Any = None


@runtime_checkable
class LLMClient(Protocol):
    model: str

    def complete(self, system: str, user: str, *, max_tokens: int | None = None) -> LLMResponse:
        """Return a single completion for the given system + user messages."""
        ...


class OpenAIClient:
    """OpenAI ChatGPT client (GPT-5.5 by default).

    Uses the Chat Completions endpoint. New models expect ``max_completion_tokens``
    and may reject a custom ``temperature``; both are handled with graceful fallback.
    """

    def __init__(self, settings: Settings):
        try:
            from openai import OpenAI  # type: ignore
        except ImportError as exc:  # pragma: no cover - depends on env
            raise RuntimeError(
                "The 'openai' package is required for the OpenAI provider. "
                "Install it with: pip install 'sas2spark[llm]'  (or pip install openai)"
            ) from exc

        if not settings.llm_api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Export it, put it in .env, "
                "or use --provider stub for offline runs."
            )

        self.model = settings.llm_model
        self._settings = settings
        self._client = OpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url or None,
            timeout=settings.llm_timeout_s,
            max_retries=settings.llm_max_retries,
        )

    def complete(self, system: str, user: str, *, max_tokens: int | None = None) -> LLMResponse:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        limit = max_tokens or self._settings.llm_max_output_tokens
        resp = self._complete_with_limit(messages, limit)
        # A length-truncated module would fail static eval with a confusing
        # syntax error and burn a repair round — retry once with more room.
        if _openai_finish_reason(resp.raw) == "length":
            resp = self._complete_with_limit(messages, limit * 2)
        return resp

    def _complete_with_limit(self, messages: list[dict], limit: int) -> LLMResponse:
        temperature = self._settings.llm_temperature

        # Attempt with the modern parameter name, then fall back for older models.
        attempts: list[dict[str, Any]] = [
            {"max_completion_tokens": limit},
            {"max_tokens": limit},
        ]
        last_exc: Optional[Exception] = None
        for kwargs in attempts:
            params: dict[str, Any] = {"model": self.model, "messages": messages, **kwargs}
            if temperature is not None:
                params["temperature"] = temperature
            try:
                resp = self._client.chat.completions.create(**params)
                text = resp.choices[0].message.content or ""
                usage = getattr(resp, "usage", None)
                return LLMResponse(
                    text=text,
                    model=getattr(resp, "model", self.model),
                    usage=usage.model_dump() if hasattr(usage, "model_dump") else {},
                    raw=resp,
                )
            except TypeError as exc:  # unexpected kwarg for this SDK version
                last_exc = exc
                continue
            except Exception as exc:  # noqa: BLE001 - inspect message for param errors
                msg = str(exc).lower()
                if temperature is not None and "temperature" in msg:
                    temperature = None  # retry this same kwargs without temperature
                    try:
                        params.pop("temperature", None)
                        resp = self._client.chat.completions.create(**params)
                        text = resp.choices[0].message.content or ""
                        return LLMResponse(text=text, model=self.model, raw=resp)
                    except Exception as exc2:  # noqa: BLE001
                        last_exc = exc2
                        continue
                if "max_tokens" in msg or "max_completion_tokens" in msg:
                    last_exc = exc
                    continue
                raise
        raise RuntimeError(f"OpenAI completion failed: {last_exc}")


def _openai_finish_reason(raw: Any) -> str | None:
    try:
        return getattr(raw.choices[0], "finish_reason", None)
    except (AttributeError, IndexError, TypeError):
        return None


class AnthropicClient:
    """Anthropic Claude client (default model ``claude-opus-4-8``).

    Used as the secondary/fallback provider. Implements the same ``complete``
    contract as :class:`OpenAIClient` by mapping (system, user) onto the Messages
    API. Temperature is intentionally not sent: recent Claude models reject it.
    """

    def __init__(self, settings: Settings):
        try:
            from anthropic import Anthropic  # type: ignore
        except ImportError as exc:  # pragma: no cover - depends on env
            raise RuntimeError(
                "The 'anthropic' package is required for the Anthropic provider. "
                "Install it with: pip install anthropic"
            ) from exc

        if not settings.anthropic_api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set; cannot use the Anthropic provider."
            )

        self.model = settings.anthropic_model
        self._settings = settings
        self._client = Anthropic(
            api_key=settings.anthropic_api_key,
            timeout=settings.llm_timeout_s,
            max_retries=settings.llm_max_retries,
        )

    def complete(self, system: str, user: str, *, max_tokens: int | None = None) -> LLMResponse:
        limit = max_tokens or self._settings.llm_max_output_tokens
        resp = self._create(system, user, limit)
        if getattr(resp, "stop_reason", None) == "max_tokens":
            # Truncated module: retry once with more room (see OpenAIClient).
            resp = self._create(system, user, limit * 2)
        text = "".join(
            getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text"
        )
        usage = getattr(resp, "usage", None)
        return LLMResponse(
            text=text,
            model=getattr(resp, "model", self.model),
            usage={
                "input_tokens": getattr(usage, "input_tokens", None),
                "output_tokens": getattr(usage, "output_tokens", None),
            } if usage else {},
            raw=resp,
        )

    def _create(self, system: str, user: str, limit: int):
        return self._client.messages.create(
            model=self.model,
            max_tokens=limit,
            system=system,
            messages=[{"role": "user", "content": user}],
        )


class FallbackClient:
    """Try a primary client; on error, fall back to a secondary client.

    Exposes the union model string (``primary->secondary``) for logging. Errors
    from the primary are reported to stderr; if the secondary also fails, that
    exception propagates.
    """

    def __init__(self, primary: LLMClient, secondary: LLMClient):
        self.primary = primary
        self.secondary = secondary
        self.model = f"{primary.model}->{secondary.model}"

    def complete(self, system: str, user: str, *, max_tokens: int | None = None) -> LLMResponse:
        try:
            return self.primary.complete(system, user, max_tokens=max_tokens)
        except Exception as exc:  # noqa: BLE001 - any primary failure triggers fallback
            import sys

            print(
                f"[sas2spark] primary LLM ({self.primary.model}) failed: "
                f"{type(exc).__name__}: {str(exc)[:160]}; "
                f"falling back to {self.secondary.model}",
                file=sys.stderr,
            )
            return self.secondary.complete(system, user, max_tokens=max_tokens)


class StubLLM:
    """Offline stand-in. Detects translation vs. judge prompts heuristically.

    The translation it emits is intentionally trivial (returns the first input,
    or an empty frame) — enough to exercise segmentation, the graph, static eval,
    the repair plumbing, the integrator, and tests without any network access.
    """

    def __init__(self, model: str = "stub", translator: Optional[Callable[[str], str]] = None):
        self.model = model
        self._translator = translator

    def complete(self, system: str, user: str, *, max_tokens: int | None = None) -> LLMResponse:
        text = self._respond(system, user)
        return LLMResponse(text=text, model=self.model)

    def _respond(self, system: str, user: str) -> str:
        blob = (system + "\n" + user).lower()
        if "judge" in blob or "logically equivalent" in blob:
            return '{"equivalent": true, "confidence": 0.5, "issues": [], ' \
                   '"explanation": "stub judge: not a real assessment"}'
        if self._translator is not None:
            return self._translator(user)
        return _STUB_TRANSLATION


_STUB_TRANSLATION = '''```python
from pyspark.sql import DataFrame


def transform(spark, inputs: dict) -> "DataFrame":
    """STUB translation: returns the first input dataset unchanged.

    Replace by configuring a real LLM provider (--provider openai)."""
    if not inputs:
        return spark.createDataFrame([], schema="_stub string")
    first_key = sorted(inputs.keys())[0]
    return inputs[first_key]
```'''


def _build_single(provider: str, settings: Settings) -> LLMClient:
    provider = (provider or "openai").lower()
    if provider == "stub":
        return StubLLM(model=settings.llm_model or "stub")
    if provider == "openai":
        return OpenAIClient(settings)
    if provider == "anthropic":
        return AnthropicClient(settings)
    raise ValueError(
        f"unknown llm provider: {provider!r} (use 'openai', 'anthropic', or 'stub')"
    )


def build_client(settings: Settings) -> LLMClient:
    """Build the active LLM client, wrapping a fallback provider when configured.

    The primary is ``settings.llm_provider``. If ``settings.fallback_provider`` is
    set, differs from the primary, and can be constructed (package + key present),
    the two are composed into a :class:`FallbackClient` so a primary outage
    (e.g. OpenAI ``insufficient_quota``) transparently routes to the secondary.
    """
    import sys

    primary = _build_single(settings.llm_provider, settings)

    fb = (settings.fallback_provider or "").lower()
    if fb and fb != (settings.llm_provider or "").lower():
        try:
            secondary = _build_single(fb, settings)
        except (RuntimeError, ValueError) as exc:
            # Fallback not available (missing key/package): proceed with primary only.
            print(
                f"[sas2spark] fallback provider {fb!r} unavailable ({exc}); "
                f"using {primary.model} only.",
                file=sys.stderr,
            )
            return primary
        return FallbackClient(primary, secondary)

    return primary
