"""Core data model shared across the pipeline.

These are plain dataclasses with no heavy dependencies so they can be imported
anywhere (parser, graph, evals, orchestrator) without pulling in Spark/OpenAI.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class StepKind(str, Enum):
    DATA = "data"
    PROC = "proc"
    OTHER = "other"


@dataclass(frozen=True)
class DatasetRef:
    """A normalized reference to a SAS dataset (``library.name``)."""

    library: str
    name: str

    @property
    def key(self) -> str:
        return f"{self.library}.{self.name}"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.key

    @classmethod
    def parse(cls, token: str, default_library: str = "work") -> "DatasetRef":
        """Parse a dataset token, dropping any dataset options in parentheses.

        ``mylib.accounts(where=(x>0))`` -> DatasetRef('mylib', 'accounts')
        ``accounts``                    -> DatasetRef('work', 'accounts')
        """
        t = token.strip().strip(";").strip()
        # Strip dataset options: foo(keep=a b) -> foo
        paren = t.find("(")
        if paren != -1:
            t = t[:paren]
        t = t.strip().strip("'\"").lower()
        if "." in t:
            lib, _, name = t.partition(".")
            lib = lib or default_library
        else:
            lib, name = default_library, t
        return cls(library=lib, name=name)


@dataclass
class MacroSubstitution:
    """A literal in flattened code that was substituted from a SAS macro variable.

    These come from MPRINT expansion: SAS replaces ``&var`` with the variable's
    value at run time. For *data-derived* variables (e.g. model coefficients pushed
    into macro vars via ``CALL SYMPUT``) the resulting literal is a snapshot of one
    run, not a constant — the translation must treat it as a parameter/input.
    """

    macro_var: str
    value: str


@dataclass
class MacroContext:
    """Provenance for a step produced by macro expansion (dual-source translation).

    Lets the translator see the *parametric* macro alongside the *expanded*
    snapshot, so it generalizes (externalizes coefficients) instead of hardcoding
    the run-specific literals MPRINT baked in.
    """

    macro_names: list[str] = field(default_factory=list)
    original_source: str = ""  # the %macro...%mend body/bodies this step came from
    substitutions: list[MacroSubstitution] = field(default_factory=list)


@dataclass
class SasStep:
    """One DATA or PROC step (already macro-flattened, concrete)."""

    index: int
    kind: StepKind
    text: str
    statements: list[str] = field(default_factory=list)
    proc_name: Optional[str] = None
    inputs: list[DatasetRef] = field(default_factory=list)
    outputs: list[DatasetRef] = field(default_factory=list)
    line_start: int = 0
    line_end: int = 0
    source: Optional[str] = None  # originating file (multi-file projects)
    # Macro provenance (set only for steps expanded from a macro when the original
    # .sas source is available alongside the MPRINT log).
    macro_context: Optional["MacroContext"] = None

    @property
    def label(self) -> str:
        if self.kind is StepKind.PROC:
            return f"step{self.index:03d}_proc_{(self.proc_name or 'proc').lower()}"
        if self.kind is StepKind.DATA:
            out = self.outputs[0].name if self.outputs else "data"
            return f"step{self.index:03d}_data_{out}"
        return f"step{self.index:03d}_other"


@dataclass
class Schema:
    """A lightweight column schema for an input or output dataset."""

    columns: dict[str, str] = field(default_factory=dict)  # name -> dtype string
    row_count: Optional[int] = None

    @property
    def names(self) -> list[str]:
        return list(self.columns.keys())

    def to_dict(self) -> dict[str, Any]:
        return {"columns": dict(self.columns), "row_count": self.row_count}


class NodeStatus(str, Enum):
    PENDING = "pending"
    TRANSLATED = "translated"
    PASSED = "passed"
    FAILED = "failed"
    NEEDS_HUMAN = "needs_human"


class EvalPhase(str, Enum):
    STATIC = "static"
    SCHEMA = "schema"
    PROPERTY = "property"
    DIFF = "data_equivalence"
    JUDGE = "llm_judge"
    E2E = "end_to_end"


@dataclass
class EvalResult:
    phase: EvalPhase
    passed: bool
    summary: str = ""
    diagnostics: list[str] = field(default_factory=list)
    skipped: bool = False

    def feedback(self) -> str:
        """Compact, model-readable description of what went wrong."""
        head = f"[{self.phase.value}] {'PASS' if self.passed else 'FAIL'}: {self.summary}"
        if self.diagnostics:
            head += "\n" + "\n".join(f"  - {d}" for d in self.diagnostics)
        return head


@dataclass
class TranslationNode:
    """A graph node: one SAS step plus everything we learn while translating it."""

    step: SasStep
    status: NodeStatus = NodeStatus.PENDING
    python_code: Optional[str] = None
    attempts: int = 0
    eval_results: list[EvalResult] = field(default_factory=list)
    input_schemas: dict[str, Schema] = field(default_factory=dict)
    output_schema: Optional[Schema] = None
    # Rendered head-N rows of golden data, keyed like input_schemas. Shown to the
    # translator so it sees real values (dates, formats, nulls), not just dtypes.
    input_samples: dict[str, str] = field(default_factory=dict)
    output_sample: Optional[str] = None
    from_cache: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return self.step.label

    @property
    def module_name(self) -> str:
        return self.step.label

    def last_failure_feedback(self) -> str:
        fails = [r for r in self.eval_results if not r.passed and not r.skipped]
        return "\n".join(r.feedback() for r in fails) if fails else ""
