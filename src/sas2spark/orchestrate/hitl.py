"""Component 6 — Human-in-the-loop.

Only nodes that fail after N repair attempts are surfaced for human review, each
with full context: the SAS source, the generated PySpark, the failing eval, and
the diff/critique. We emit a single Markdown report.
"""
from __future__ import annotations

import os

from ..models import NodeStatus
from .pipeline import PipelineResult


def render_human_review(result: PipelineResult) -> str:
    nodes = result.needs_human
    lines: list[str] = []
    lines.append("# Human review — unresolved translations\n")
    lines.append(f"_{result.summary()}_\n")
    if not nodes:
        lines.append("\n All nodes passed the eval gauntlet. Nothing to review. \n")
        return "\n".join(lines)

    for node in nodes:
        step = node.step
        lines.append(f"\n## {node.module_name}  (status: {node.status.value})\n")
        lines.append(f"- inputs: {[r.key for r in step.inputs] or 'none'}")
        lines.append(f"- outputs: {[r.key for r in step.outputs] or 'none'}")
        lines.append(f"- attempts: {node.attempts}\n")

        lines.append("### SAS source\n")
        lines.append("```sas")
        lines.append(step.text.strip())
        lines.append("```\n")

        lines.append("### Generated PySpark (last attempt)\n")
        lines.append("```python")
        lines.append((node.python_code or "(none)").strip())
        lines.append("```\n")

        lines.append("### Failing evaluations\n")
        fails = [r for r in node.eval_results if not r.passed and not r.skipped]
        if fails:
            for r in fails:
                lines.append("```")
                lines.append(r.feedback())
                lines.append("```")
        else:
            lines.append("_(no captured eval failures — likely an upstream dependency gap)_")
        if node.notes:
            lines.append("\n### Notes\n")
            for n in node.notes:
                lines.append(f"- {n}")
    return "\n".join(lines) + "\n"


def write_human_review(result: PipelineResult, out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "human_review.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(render_human_review(result))
    return path
