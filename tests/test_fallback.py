"""Fallback behaviour: primary failure routes to the secondary provider."""
import pytest

from sas2spark.config import Settings
from sas2spark.llm import FallbackClient, StubLLM, build_client
from sas2spark.llm.client import LLMResponse


class _FailingClient:
    model = "primary-boom"

    def complete(self, system, user, *, max_tokens=None):
        raise RuntimeError("insufficient_quota (simulated)")


class _OKClient:
    model = "secondary-ok"

    def complete(self, system, user, *, max_tokens=None):
        return LLMResponse(text="from secondary", model=self.model)


def test_fallback_used_when_primary_fails():
    client = FallbackClient(_FailingClient(), _OKClient())
    resp = client.complete("sys", "user")
    assert resp.text == "from secondary"
    assert client.model == "primary-boom->secondary-ok"


def test_primary_used_when_it_succeeds():
    client = FallbackClient(_OKClient(), _FailingClient())
    assert client.complete("sys", "user").text == "from secondary"  # _OKClient is primary here


def test_secondary_error_propagates():
    client = FallbackClient(_FailingClient(), _FailingClient())
    with pytest.raises(RuntimeError):
        client.complete("sys", "user")


def test_build_client_skips_unavailable_fallback():
    # Primary stub, fallback anthropic but no ANTHROPIC_API_KEY -> primary only.
    s = Settings()
    s.llm_provider = "stub"
    s.fallback_provider = "anthropic"
    s.anthropic_api_key = None
    client = build_client(s)
    assert isinstance(client, StubLLM)


def test_build_client_no_fallback_when_disabled():
    s = Settings()
    s.llm_provider = "stub"
    s.fallback_provider = None
    assert isinstance(build_client(s), StubLLM)
