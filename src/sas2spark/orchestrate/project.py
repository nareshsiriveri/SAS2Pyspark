"""Multi-file project support.

A real SAS codebase is many files that share datasets (one file writes ``work.x``,
another reads it). This module loads several files **in execution order**, segments
each, tags every step with its source file, renumbers them into one global sequence,
and builds a single cross-file dependency graph. The result is one integrated
PySpark pipeline plus a consolidated correctness report grouped by source file.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from ..flatten import attach_macro_context, flatten, looks_like_log
from ..models import NodeStatus, SasStep
from ..parse import segment
from .pipeline import Pipeline, PipelineResult

_SAS_EXTS = (".sas", ".log")


def discover_files(inputs: list[str], order_file: str | None = None) -> list[str]:
    """Resolve the ordered list of source files.

    * If ``order_file`` is given, read newline-separated paths from it (the order
      of execution — this is the reliable way to order a real codebase).
    * Else if a single directory is given, glob ``*.sas``/``*.log`` sorted by name.
    * Else use the given file paths in the order provided.
    """
    if order_file:
        base = os.path.dirname(os.path.abspath(order_file))
        paths: list[str] = []
        with open(order_file, "r", encoding="utf-8") as f:
            for line in f:
                p = line.strip()
                if not p or p.startswith("#"):
                    continue
                paths.append(p if os.path.isabs(p) else os.path.join(base, p))
        return paths

    if len(inputs) == 1 and os.path.isdir(inputs[0]):
        root = inputs[0]
        return sorted(
            os.path.join(root, fn)
            for fn in os.listdir(root)
            if fn.lower().endswith(_SAS_EXTS)
        )

    return list(inputs)


def _sibling_macro_source(path: str) -> str | None:
    """The original ``.sas`` next to a ``.log`` (same basename), for dual-source.

    A real macro run is logged to ``01_load.log`` but the parametric ``%macro``
    definitions live in ``01_load.sas``. When both are present we read the ``.sas``
    so macro provenance (parametric source + data-derived substitutions) can be
    attached to the steps harvested from the log.
    """
    root, ext = os.path.splitext(path)
    if ext.lower() != ".log":
        return None
    sas_path = root + ".sas"
    if not os.path.isfile(sas_path):
        return None
    with open(sas_path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def load_project_steps(paths: list[str], default_library: str = "work") -> list[SasStep]:
    """Flatten+segment each file, tag with source, renumber into one sequence."""
    steps: list[SasStep] = []
    for path in paths:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        file_steps = segment(flatten(text), default_library=default_library)
        macro_source = _sibling_macro_source(path)
        if macro_source and looks_like_log(text):
            attach_macro_context(file_steps, macro_source, text)
        src = os.path.basename(path)
        for s in file_steps:
            s.source = src
        steps.extend(file_steps)
    for i, s in enumerate(steps):  # global, unique indices for the graph
        s.index = i
    return steps


@dataclass
class ProjectResult:
    result: PipelineResult
    files: list[str]

    def per_file(self) -> dict[str, list]:
        groups: dict[str, list] = {}
        for node in self.result.nodes:
            groups.setdefault(node.step.source or "(unknown)", []).append(node)
        return groups


def run_project(
    pipeline: Pipeline,
    paths: list[str],
    default_library: str = "work",
) -> ProjectResult:
    steps = load_project_steps(paths, default_library=default_library)
    result = pipeline.translate_steps(steps)
    return ProjectResult(result=result, files=[os.path.basename(p) for p in paths])


# --------------------------------------------------------------------------- #
# Consolidated correctness report
# --------------------------------------------------------------------------- #
def render_report(project: ProjectResult) -> str:
    res = project.result
    groups = project.per_file()
    total = len(res.nodes)
    passed = len(res.committed)
    review = len(res.needs_human)

    lines: list[str] = ["# Translation report\n"]
    verdict = (
        f"**✅ All {total} steps across {len(groups)} file(s) passed.**"
        if review == 0
        else f"**⚠️ {passed}/{total} steps passed; {review} need human review.**"
    )
    lines.append(verdict + "\n")
    lines.append(f"- files: {len(groups)}")
    lines.append(f"- steps: {total}")
    lines.append(f"- passed: {passed}")
    lines.append(f"- need review: {review}\n")

    # How correctness was established (the strength of the verdict).
    data_phases = ("schema", "property", "data_equivalence")
    verified_by_data = any(
        any(r.phase.value in data_phases and r.passed and not r.skipped
            for r in n.eval_results)
        for n in res.nodes
    )
    data_ran = any(
        any(r.phase.value in data_phases and not r.skipped for r in n.eval_results)
        for n in res.nodes
    )
    judged = any(
        any(r.phase.value == "llm_judge" and r.passed and not r.skipped
            for r in n.eval_results)
        for n in res.nodes
    )
    lines.append("## How correctness was checked\n")
    lines.append("- static analysis: every committed step compiles and meets the "
                 "`transform(spark, inputs)` contract.")
    if verified_by_data:
        lines.append("- **data equivalence**: steps with golden datasets were "
                     "value-compared to the SAS output (schema, invariants, full diff).")
    if judged:
        lines.append("- LLM-as-judge: steps without golden data were reviewed for "
                     "logical equivalence (weaker than a data diff — see caveat below).")
    if not data_ran:
        lines.append("\n> ⚠️ **No golden data was supplied**, so no value-level "
                     "verification ran. Provide `--golden-dir` with the SAS step outputs "
                     "for a real correctness guarantee.")
    elif not verified_by_data:
        lines.append("\n> ⚠️ Golden data was supplied and value-level checks **ran but "
                     "did not all pass** — see the failing steps below.")

    lines.append("\n## By file\n")
    for src in sorted(groups):
        nodes = groups[src]
        n_pass = sum(1 for n in nodes if n.status is NodeStatus.PASSED)
        flag = "✅" if n_pass == len(nodes) else "⚠️"
        lines.append(f"### {flag} {src} — {n_pass}/{len(nodes)} passed\n")
        for n in nodes:
            ev = " ".join(
                f"{r.phase.value}="
                + ("skip" if r.skipped else ("ok" if r.passed else "FAIL"))
                for r in n.eval_results
            )
            cached = " (cache)" if n.from_cache else ""
            lines.append(f"- `{n.module_name}` [{n.status.value}]{cached} {ev}")
            for note in n.notes:
                if note.startswith("⚠"):  # e.g. unverified secondary outputs
                    lines.append(f"  - {note}")
        lines.append("")
    return "\n".join(lines) + "\n"


def write_report(project: ProjectResult, out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "report.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(render_report(project))
    return path
