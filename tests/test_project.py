"""Multi-file project: cross-file dependency wiring + consolidated report (offline)."""
import os

from sas2spark.config import Settings
from sas2spark.llm import StubLLM
from sas2spark.orchestrate import (
    Pipeline,
    discover_files,
    load_project_steps,
    render_report,
    run_project,
)

PROJECT_DIR = os.path.join("examples", "project")
FILES = [
    os.path.join(PROJECT_DIR, "01_load.sas"),
    os.path.join(PROJECT_DIR, "02_price.sas"),
    os.path.join(PROJECT_DIR, "03_summary.sas"),
]


def _settings():
    s = Settings()
    s.llm_provider = "stub"
    s.max_repair_attempts = 1
    return s


def test_discover_directory_sorted():
    files = discover_files([PROJECT_DIR])
    assert [os.path.basename(f) for f in files] == [
        "01_load.sas", "02_price.sas", "03_summary.sas"
    ]


def test_steps_tagged_with_source_and_renumbered():
    steps = load_project_steps(FILES)
    # 2 steps in file1, 1 in file2, 1 in file3
    assert [s.source for s in steps] == [
        "01_load.sas", "01_load.sas", "02_price.sas", "03_summary.sas"
    ]
    assert [s.index for s in steps] == [0, 1, 2, 3]  # globally unique


def test_cross_file_dependencies_wired():
    steps = load_project_steps(FILES)
    pipeline = Pipeline(_settings(), llm=StubLLM())
    project = run_project(pipeline, FILES)
    g = project.result.graph
    # file2's priced step (index 2) depends on file1's accounts(0) and rates(1)
    assert 2 in g.successors(0)
    assert 2 in g.successors(1)
    # file3's summary (index 3) depends on file2's priced (index 2)
    assert 3 in g.successors(2)
    assert g.external_inputs == {"raw.accounts", "raw.rates"}
    assert "work.region_summary" in g.final_outputs


def test_report_groups_by_file():
    pipeline = Pipeline(_settings(), llm=StubLLM())
    project = run_project(pipeline, FILES)
    report = render_report(project)
    assert "01_load.sas" in report
    assert "02_price.sas" in report
    assert "03_summary.sas" in report
    assert "By file" in report
    # all stub steps pass static; judge skipped offline -> all passed
    assert "passed" in report.lower()
