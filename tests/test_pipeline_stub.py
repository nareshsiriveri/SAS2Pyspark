"""End-to-end smoke test of the orchestrator using the offline stub LLM.

No network, no Spark, no golden data — exercises flatten -> segment -> graph ->
translate -> static eval -> integrate -> human review.
"""
import os

from sas2spark.config import Settings
from sas2spark.llm import StubLLM
from sas2spark.orchestrate import Pipeline, integrate, write_human_review

SRC = """
data work.a; set raw.a; run;
proc sql; create table work.b as select * from work.a; quit;
"""


def _settings():
    s = Settings()
    s.llm_provider = "stub"
    s.max_repair_attempts = 1
    return s


def test_pipeline_runs_offline():
    pipeline = Pipeline(_settings(), llm=StubLLM())
    result = pipeline.translate_program(SRC)
    assert len(result.nodes) == 2
    # Stub code passes static eval; judge is skipped offline -> nodes commit.
    assert all(n.python_code and "def transform" in n.python_code for n in result.nodes)
    assert "passed" in result.summary()


def test_integrate_writes_runner_and_modules(tmp_path):
    pipeline = Pipeline(_settings(), llm=StubLLM())
    result = pipeline.translate_program(SRC)
    out = str(tmp_path / "build")
    artifacts = integrate(result, out)
    assert os.path.isfile(artifacts.runner_path)
    assert os.path.isfile(artifacts.manifest_path)
    # A module per committed step.
    assert len(artifacts.step_files) == len(result.committed)
    # The generated runner imports cleanly and exposes run_pipeline.
    import importlib.util

    spec = importlib.util.spec_from_file_location("gen_pipeline", artifacts.runner_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "run_pipeline")
    assert "raw.a" in mod.EXTERNAL_INPUTS


def test_human_review_written(tmp_path):
    pipeline = Pipeline(_settings(), llm=StubLLM())
    result = pipeline.translate_program(SRC)
    path = write_human_review(result, str(tmp_path))
    assert os.path.isfile(path)
    assert "Human review" in open(path, encoding="utf-8").read()
