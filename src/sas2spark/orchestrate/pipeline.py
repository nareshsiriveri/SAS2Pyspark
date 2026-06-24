"""The per-node loop (LangGraph-style, implemented as a dependency-ordered sweep).

For each node in topological order:
    translate → eval gauntlet → (repair ×N) → commit  or  mark for human review.

Independent nodes are translated concurrently (``settings.translate_workers``
threads): LLM calls are I/O-bound, so a wide dependency graph parallelizes almost
linearly. Spark-backed eval phases are serialized inside the gauntlet. Set
``translate_workers=1`` for a strictly sequential, reproducible-order run.

When a :class:`TranslationCache` is supplied, each node's verified code is stored
under a content fingerprint and re-runs seed from it — passing steps are
re-evaluated but never re-translated.
"""
from __future__ import annotations

import concurrent.futures as _futures
from dataclasses import dataclass, field
from typing import Callable, Optional

from ..config import Settings
from ..evaluation.base import EvalContext
from ..evaluation.gauntlet import Gauntlet
from ..flatten import attach_macro_context, flatten, looks_like_log
from ..golden import GoldenStore
from ..graph import DependencyGraph, build_graph
from ..llm import LLMClient, build_client
from ..models import NodeStatus, TranslationNode
from ..parse import segment
from ..repair import RepairLoop
from ..translate import Translator
from .cache import TranslationCache, fingerprint


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
        cached = sum(1 for n in self.nodes if n.from_cache)
        extra = f" ({cached} from cache)" if cached else ""
        return f"{passed}/{len(self.nodes)} nodes passed; {human} need human review{extra}"


class Pipeline:
    def __init__(
        self,
        settings: Settings,
        llm: Optional[LLMClient] = None,
        golden: Optional[GoldenStore] = None,
        cache: Optional[TranslationCache] = None,
    ):
        self.settings = settings
        self.llm = llm if llm is not None else build_client(settings)
        self.golden = golden
        self.cache = cache
        self.translator = Translator(self.llm)

    def translate_program(
        self,
        source_or_log: str,
        default_library: str | None = None,
        macro_source: str | None = None,
    ) -> PipelineResult:
        """Flatten, segment, and translate one program.

        ``macro_source`` is the original (parametric) ``.sas`` for the same run.
        When supplied alongside an MPRINT log it enables dual-source macro
        translation: steps expanded from a macro are tagged with the parametric
        source and their data-derived substitutions, so coefficients are
        externalized instead of hardcoded.
        """
        default_library = default_library or self.settings.default_library
        flat = flatten(source_or_log)
        steps = segment(flat, default_library=default_library)
        if macro_source and looks_like_log(source_or_log):
            attach_macro_context(steps, macro_source, source_or_log)
        return self.translate_steps(steps)

    def translate_steps(self, steps: list) -> PipelineResult:
        """Translate a pre-built list of steps (used for multi-file projects).

        Steps must have unique ``index`` values; ``build_graph`` keys nodes on them.
        """
        graph = build_graph(steps)

        nodes = {s.index: TranslationNode(step=s) for s in steps}

        ctx = EvalContext(
            settings=self.settings,
            golden=self.golden,
            llm=self.llm,
            judge_llm=self._judge_llm(),
        )
        gauntlet = Gauntlet(ctx)
        repair = RepairLoop(self.translator, gauntlet, self.settings.max_repair_attempts)

        def process(node: TranslationNode) -> None:
            self._fill_schemas(node)
            self._note_multi_output(node)
            cache_key = self._seed_from_cache(node)
            repair.run(node)
            if (
                cache_key
                and self.cache is not None
                and node.status is NodeStatus.PASSED
                and node.python_code
            ):
                # Also covers a cache-seeded node whose code was repaired.
                self.cache.put(cache_key, node.python_code, label=node.label)

        workers = max(1, self.settings.translate_workers)
        try:
            if workers == 1 or len(steps) <= 1:
                for idx in graph.topo_order():
                    process(nodes[idx])
            else:
                _run_dependency_parallel(graph, nodes, process, workers)
        finally:
            ctx.stop()

        ordered = [nodes[i] for i in graph.topo_order()]
        result = PipelineResult(graph=graph, nodes=ordered, settings=self.settings)
        return result

    # ------------------------------------------------------------------
    def _judge_llm(self) -> Optional[LLMClient]:
        """Prefer a different provider than the translator for the judge phase.

        Self-grading correlates errors; when a fallback provider is configured,
        the judge leads with it (and can still fall back to the primary).
        """
        from ..llm.client import FallbackClient

        if isinstance(self.llm, FallbackClient):
            return FallbackClient(self.llm.secondary, self.llm.primary)
        return self.llm

    def _seed_from_cache(self, node: TranslationNode) -> Optional[str]:
        """Look up a previously verified translation; returns the cache key."""
        if self.cache is None:
            return None
        key = fingerprint(
            node.step,
            node.input_schemas,
            node.output_schema,
            node.input_samples,
            node.output_sample,
            getattr(self.llm, "model", ""),
        )
        if node.python_code is None:
            cached = self.cache.get(key)
            if cached is not None:
                node.python_code = cached
                node.from_cache = True
                node.status = NodeStatus.TRANSLATED
                node.notes.append("seeded from translation cache (re-evaluated, not re-translated)")
        return key

    def _note_multi_output(self, node: TranslationNode) -> None:
        """Surface steps whose secondary outputs are neither verified nor wired."""
        outs = node.step.outputs
        if len(outs) > 1:
            others = ", ".join(r.key for r in outs[1:])
            node.notes.append(
                f"⚠ step writes {len(outs)} datasets but only the primary "
                f"'{outs[0].key}' is verified and wired into pipeline.py; "
                f"unverified outputs: {others}"
            )

    def _fill_schemas(self, node: TranslationNode) -> None:
        """Attach golden-derived schemas and sample rows when available (best effort)."""
        if self.golden is None:
            return
        sample_rows = max(0, self.settings.prompt_sample_rows)
        for ref in node.step.inputs:
            if self.golden.has(ref.key):
                try:
                    node.input_schemas[ref.key] = self.golden.schema(ref.key)
                    if sample_rows:
                        node.input_samples[ref.key] = self.golden.sample(ref.key, sample_rows)
                except Exception:  # noqa: BLE001 - schema/sample is advisory
                    pass
        if node.step.outputs:
            out_key = node.step.outputs[0].key
            if self.golden.has(out_key):
                try:
                    node.output_schema = self.golden.schema(out_key)
                    if sample_rows:
                        node.output_sample = self.golden.sample(out_key, sample_rows)
                except Exception:  # noqa: BLE001
                    pass


def _run_dependency_parallel(
    graph: DependencyGraph,
    nodes: dict[int, TranslationNode],
    process: Callable[[TranslationNode], None],
    workers: int,
) -> None:
    """Run ``process`` over all nodes, dispatching each as soon as its
    predecessors finish. Mirrors the sequential semantics (downstream nodes run
    even if an upstream node failed eval — failure is recorded on the node)."""
    indeg = {s.index: len(graph.pred.get(s.index, set())) for s in graph.steps}
    pending = set(indeg)
    in_flight: dict[_futures.Future, int] = {}

    with _futures.ThreadPoolExecutor(max_workers=workers) as pool:

        def submit_ready() -> None:
            ready = sorted(i for i in pending if indeg[i] == 0)
            for i in ready:
                pending.discard(i)
                in_flight[pool.submit(process, nodes[i])] = i

        submit_ready()
        while in_flight:
            done, _ = _futures.wait(in_flight, return_when=_futures.FIRST_COMPLETED)
            for fut in done:
                idx = in_flight.pop(fut)
                fut.result()  # propagate hard errors (LLM/client exceptions)
                for succ in graph.succ.get(idx, set()):
                    indeg[succ] -= 1
            submit_ready()

    if pending:  # unreachable unless the graph has a cycle
        raise ValueError(f"dependency graph stalled; unprocessed nodes: {sorted(pending)}")
