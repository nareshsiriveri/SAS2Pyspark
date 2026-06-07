"""Component 2c — Dependency Grapher.

Builds a DAG whose nodes are DATA/PROC steps and whose edges are dataset
read/write dependencies. SAS executes sequentially, so a step that reads dataset
``D`` depends on the **most recent earlier step that wrote ``D``** (last-writer-wins).
Datasets read but never written in-program are recorded as external sources.

The graph is topologically sorted (sequential tie-break) and grouped into layers
so independent nodes can be translated in parallel.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from ..models import DatasetRef, SasStep


@dataclass
class DependencyGraph:
    steps: list[SasStep]
    succ: dict[int, set[int]] = field(default_factory=lambda: defaultdict(set))
    pred: dict[int, set[int]] = field(default_factory=lambda: defaultdict(set))
    # dataset key -> producing step index (last writer overall, for reporting)
    producers: dict[str, list[int]] = field(default_factory=lambda: defaultdict(list))
    external_inputs: set[str] = field(default_factory=set)
    final_outputs: set[str] = field(default_factory=set)

    # --- queries ---
    def predecessors(self, i: int) -> set[int]:
        return set(self.pred.get(i, set()))

    def successors(self, i: int) -> set[int]:
        return set(self.succ.get(i, set()))

    def topo_order(self) -> list[int]:
        """Kahn's algorithm with a sequential (lowest-index-first) tie-break."""
        indeg = {s.index: len(self.pred.get(s.index, set())) for s in self.steps}
        ready = sorted(i for i, d in indeg.items() if d == 0)
        order: list[int] = []
        while ready:
            n = ready.pop(0)
            order.append(n)
            for m in sorted(self.succ.get(n, set())):
                indeg[m] -= 1
                if indeg[m] == 0:
                    # insert keeping `ready` sorted (small graphs; simplicity over speed)
                    ready.append(m)
                    ready.sort()
        if len(order) != len(self.steps):
            raise ValueError("dependency graph has a cycle; cannot topologically sort")
        return order

    def layers(self) -> list[list[int]]:
        """Group nodes by longest-path depth; nodes in a layer are independent."""
        depth: dict[int, int] = {}
        for n in self.topo_order():
            preds = self.pred.get(n, set())
            depth[n] = 0 if not preds else 1 + max(depth[p] for p in preds)
        by_depth: dict[int, list[int]] = defaultdict(list)
        for n, d in depth.items():
            by_depth[d].append(n)
        return [sorted(by_depth[d]) for d in sorted(by_depth)]

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [
                {
                    "index": s.index,
                    "label": s.label,
                    "kind": s.kind.value,
                    "proc": s.proc_name,
                    "inputs": [r.key for r in s.inputs],
                    "outputs": [r.key for r in s.outputs],
                }
                for s in self.steps
            ],
            "edges": [
                {"from": u, "to": v} for u in sorted(self.succ) for v in sorted(self.succ[u])
            ],
            "external_inputs": sorted(self.external_inputs),
            "final_outputs": sorted(self.final_outputs),
            "layers": self.layers(),
        }


def build_graph(steps: list[SasStep]) -> DependencyGraph:
    g = DependencyGraph(steps=steps)

    # last_writer[dataset_key] = step index that most recently wrote it
    last_writer: dict[str, int] = {}
    consumed: set[str] = set()
    produced: set[str] = set()

    for step in steps:
        # Resolve inputs against the most recent writer seen so far.
        for ref in step.inputs:
            consumed.add(ref.key)
            writer = last_writer.get(ref.key)
            if writer is not None and writer != step.index:
                g.succ[writer].add(step.index)
                g.pred[step.index].add(writer)
            elif writer is None:
                g.external_inputs.add(ref.key)
        # Register outputs (after wiring inputs so in-place ops link to the prior writer).
        for ref in step.outputs:
            produced.add(ref.key)
            g.producers[ref.key].append(step.index)
            last_writer[ref.key] = step.index

    # Datasets produced but never consumed downstream are pipeline outputs.
    g.final_outputs = {k for k in produced if k not in consumed}
    return g


def build_from_source(source_or_log: str, default_library: str = "work") -> DependencyGraph:
    """Convenience: flatten → segment → graph in one call."""
    from ..flatten import flatten
    from ..parse import segment

    flat = flatten(source_or_log)
    steps = segment(flat, default_library=default_library)
    return build_graph(steps)
