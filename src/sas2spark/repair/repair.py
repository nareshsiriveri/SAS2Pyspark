"""Component 5 — Repair loop.

On an eval failure, feed the specific failure feedback (traceback, schema diff,
value diff, or judge critique) back to the translator and re-translate. Capped at
N attempts; a node that is still failing after the cap is handed to the
human-in-the-loop stage.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..evaluation.gauntlet import Gauntlet, GauntletReport
from ..models import NodeStatus, TranslationNode
from ..translate import Translator


@dataclass
class RepairOutcome:
    node: TranslationNode
    report: GauntletReport


class RepairLoop:
    def __init__(self, translator: Translator, gauntlet: Gauntlet, max_attempts: int = 3):
        self.translator = translator
        self.gauntlet = gauntlet
        self.max_attempts = max(1, max_attempts)

    def run(self, node: TranslationNode) -> RepairOutcome:
        """Translate, evaluate, and repair until the gauntlet passes or attempts run out."""
        step = node.step
        report: GauntletReport | None = None

        # Initial translation (unless the node already carries code to re-check).
        if node.python_code is None:
            node.python_code = self.translator.translate(
                step, node.input_schemas, node.output_schema
            )
            node.attempts = 1
            node.status = NodeStatus.TRANSLATED

        for attempt in range(self.max_attempts):
            report = self.gauntlet.run(step, node.python_code, node.input_schemas)
            node.eval_results = list(report.results)
            if report.passed:
                node.status = NodeStatus.PASSED
                return RepairOutcome(node=node, report=report)

            # Out of attempts? hand off to human review.
            if attempt >= self.max_attempts - 1:
                node.status = NodeStatus.NEEDS_HUMAN
                node.notes.append(
                    f"failed after {node.attempts} attempt(s): {report.summary_line()}"
                )
                return RepairOutcome(node=node, report=report)

            # Otherwise repair using the failure feedback.
            feedback = report.failure_feedback()
            node.python_code = self.translator.repair(
                step,
                node.python_code,
                feedback,
                node.input_schemas,
                node.output_schema,
            )
            node.attempts += 1
            node.status = NodeStatus.TRANSLATED

        node.status = NodeStatus.FAILED
        return RepairOutcome(node=node, report=report)  # type: ignore[arg-type]
