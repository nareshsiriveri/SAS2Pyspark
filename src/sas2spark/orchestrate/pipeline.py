"""The per-node loop (LangGraph-style, implemented as a dependency-ordered sweep).

For each node in topological order:
    translate → eval gauntlet → (repair ×N) → commit  or  mark for human review.

Independent nodes could be translated in parallel; this reference implementation
walks the topological order sequentially for clarity and reproducibility.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..config import Settings
from ..evaluation.base import EvalContext
from ..evaluation.gauntlet import Gauntlet
from ..flatten import flatten
from ..golden import GoldenStore
from ..graph import DependencyGraph, build_graph
from ..llm import LLMClient, build_client
from ..models import NodeStatus, TranslationNode
from ..parse import segment
from ..repair import RepairLoop
from ..translate import Translator


@dataclass
class PipelineResult:
    graph: DependencyGraph
    nodes: list[TranslationNode]
    settings: Settings
    notes: list[str] = field(default_factory=list)

    @property
    def by_index(self) -> dict[int, TranslationNode]:
        return {n.step.index: n for n in self.nodes}

    @property
    def committed(self) -> list[TranslationNode]:
        return [n for n in self.nodes if n.status is NodeStatus.PASSED]

    @property
    def needs_human(self) -> list[TranslationNode]:
        return [n for n in self.nodes if n.status in (NodeStatus.NEEDS_HUMAN, NodeStatus.FAILED)]

    def summary(self) -> str:
        passed = len(self.committed)
        human = len(self.needs_human)
        return f"{passed}/{len(self.nodes)} nodes passed; {human} need human review"


class Pipeline:
    def __init__(
        self,
        settings: Settings,
        llm: Optional[LLMClient] = None,
        golden: Optional[GoldenStore] = None,
    ):
        self.settings = settings
        self.llm = llm if llm is not None else build_client(settings)
        self.golden = golden
        self.translator = Translator(self.llm)

    def translate_program(self, source_or_log: str, default_library: str | None = None) -> PipelineResult:
        default_library = default_library or self.settings.default_library
        flat = flatten(source_or_log)
        steps = segment(flat, default_library=default_library)
        return self.translate_steps(steps)

    def translate_steps(self, steps: list) -> PipelineResult:
        """Translate a pre-built list of steps (used for multi-file projects).

        Steps must have unique ``index`` values; ``build_graph`` keys nodes on them.
        """
        graph = build_graph(steps)

        nodes = {s.index: TranslationNode(step=s) for s in steps}

        ctx = EvalContext(settings=self.settings, golden=self.golden, llm=self.llm)
        gauntlet = Gauntlet(ctx)
        repair = RepairLoop(self.translator, gauntlet, self.settings.max_repair_attempts)

        try:
            for idx in graph.topo_order():
                node = nodes[idx]
                self._fill_schemas(node)
                repair.run(node)
        finally:
            ctx.stop()

        ordered = [nodes[i] for i in graph.topo_order()]
        result = PipelineResult(graph=graph, nodes=ordered, settings=self.settings)
        return result

    # ------------------------------------------------------------------
    def _fill_schemas(self, node: TranslationNode) -> None:
        """Attach golden-derived input/output schemas when available (best effort)."""
        if self.golden is None:
            return
        for ref in node.step.inputs:
            if self.golden.has(ref.key):
                try:
                    node.input_schemas[ref.key] = self.golden.schema(ref.key)
                except Exception:  # noqa: BLE001 - schema is advisory
                    pass
        if node.step.outputs:
            out_key = node.step.outputs[0].key
            if self.golden.has(out_key):
                try:
                    node.output_schema = self.golden.schema(out_key)
                except Exception:  # noqa: BLE001
                    pass
