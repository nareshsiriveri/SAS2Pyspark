"""Incremental translation cache + parallel node scheduling (offline, stub LLM)."""
import pytest

from sas2spark.config import Settings
from sas2spark.llm import StubLLM
from sas2spark.orchestrate import Pipeline, TranslationCache
from sas2spark.orchestrate.cache import fingerprint
from sas2spark.parse import segment

SRC = """
data work.a; set raw.x; run;
data work.b; set raw.y; run;
proc sql; create table work.c as select * from work.a; quit;
data work.d; set work.b; run;
"""


class CountingStub(StubLLM):
    """StubLLM that counts completions (still skips the judge phase offline)."""

    def __init__(self):
        super().__init__()
        self.calls = 0

    def complete(self, system, user, *, max_tokens=None):
        self.calls += 1
        return super().complete(system, user, max_tokens=max_tokens)


def _settings(workers: int = 4) -> Settings:
    s = Settings()
    s.llm_provider = "stub"
    s.max_repair_attempts = 1
    s.translate_workers = workers
    return s


def test_second_run_hits_cache_and_skips_llm(tmp_path):
    cache = TranslationCache(str(tmp_path / "translations.json"))

    llm1 = CountingStub()
    r1 = Pipeline(_settings(), llm=llm1, cache=cache).translate_program(SRC)
    assert llm1.calls == len(r1.nodes)  # one translate call per node
    assert not any(n.from_cache for n in r1.nodes)
    assert len(cache) == len(r1.nodes)

    llm2 = CountingStub()
    r2 = Pipeline(_settings(), llm=llm2, cache=cache).translate_program(SRC)
    assert llm2.calls == 0  # everything seeded from cache
    assert all(n.from_cache for n in r2.nodes)
    assert "from cache" in r2.summary()
    assert [n.status for n in r2.nodes] == [n.status for n in r1.nodes]


def test_cache_invalidated_by_step_or_model_change():
    steps = segment("data work.a; set raw.x; run;")
    base = fingerprint(steps[0], {}, None, {}, None, "model-a")
    assert fingerprint(steps[0], {}, None, {}, None, "model-b") != base
    changed = segment("data work.a; set raw.x; where x > 0; run;")
    assert fingerprint(changed[0], {}, None, {}, None, "model-a") != base


def test_cache_survives_corrupt_file(tmp_path):
    path = tmp_path / "translations.json"
    path.write_text("{not json", encoding="utf-8")
    cache = TranslationCache(str(path))
    assert len(cache) == 0
    cache.put("k", "code")
    assert cache.get("k") == "code"


@pytest.mark.parametrize("workers", [1, 8])
def test_parallel_matches_sequential(workers):
    result = Pipeline(_settings(workers), llm=StubLLM()).translate_program(SRC)
    assert len(result.nodes) == 4
    # Output order is the topological order regardless of scheduling.
    assert [n.step.index for n in result.nodes] == sorted(n.step.index for n in result.nodes)
    assert "4/4 nodes passed" in result.summary()


def test_multi_output_step_flagged():
    result = Pipeline(_settings(), llm=StubLLM()).translate_program(
        "data work.a work.b; set raw.x; run;"
    )
    node = result.nodes[0]
    assert any("only the primary" in note for note in node.notes)
