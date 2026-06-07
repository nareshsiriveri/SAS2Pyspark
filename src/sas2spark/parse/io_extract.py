"""Component 2b — I/O extraction.

For each step we identify the datasets it **reads** (inputs) and **writes**
(outputs). These become the edges of the dependency graph. The rules are
deliberately shallow but cover the common SAS surface:

* DATA step:   ``data OUT...;``  outputs; ``set/merge/update/modify IN...;`` inputs.
* PROC SQL:    ``create table X``/``create view X`` output; ``from``/``join`` inputs.
* PROC SORT/others: ``data=`` input, ``out=``/``outest=`` output, ``base=`` (APPEND) output.
"""
from __future__ import annotations

import re

from ..models import DatasetRef, SasStep, StepKind

_OPTION_RE = re.compile(r"\b(data|out|outest|base|inest)\s*=\s*([A-Za-z_][\w.]*(?:\s*\([^)]*\))?)",
                        re.IGNORECASE)
_DATA_TOKEN_RE = re.compile(r"([A-Za-z_][\w.]*)(\s*\([^)]*\))?")
_SQL_CREATE_RE = re.compile(r"\bcreate\s+(?:table|view)\s+([A-Za-z_][\w.]*)", re.IGNORECASE)
_SQL_FROM_RE = re.compile(r"\bfrom\s+([A-Za-z_][\w.]*)", re.IGNORECASE)
_SQL_JOIN_RE = re.compile(r"\bjoin\s+([A-Za-z_][\w.]*)", re.IGNORECASE)
_SQL_INSERT_RE = re.compile(r"\binsert\s+into\s+([A-Za-z_][\w.]*)", re.IGNORECASE)
# An option assignment: key = value  (value may be parenthesized or a single token).
_OPTION_PAIR_RE = re.compile(r"[A-Za-z_]\w*\s*=\s*(?:\([^)]*\)|[\w.\"']+)")

_SET_KEYWORDS = ("set", "merge", "update", "modify")
_RESERVED = {"_null_", "_data_", "_last_"}


def _add(seq: list[DatasetRef], ref: DatasetRef) -> None:
    if ref.name in _RESERVED:
        return
    if ref not in seq:
        seq.append(ref)


def _dataset_tokens(clause: str, default_library: str) -> list[DatasetRef]:
    """Yield dataset refs from a clause, skipping ``key=value`` options.

    Statement options (``end=eof``, ``point=p``, ``nobs=n``, ``in=flag`` …) are
    blanked out first — both the key and its value — so neither side is mistaken
    for a dataset name.
    """
    clause = _OPTION_PAIR_RE.sub(" ", clause)
    refs: list[DatasetRef] = []
    for m in _DATA_TOKEN_RE.finditer(clause):
        token = m.group(0)
        name = m.group(1).lower()
        # Defensive: drop leftover statement keywords with no library qualifier.
        if name in {"end", "nobs", "point", "key", "in", "by"} and "." not in token:
            continue
        _add(refs, DatasetRef.parse(token, default_library))
    return refs


def _first_keyword(statement: str) -> str:
    s = statement.lstrip()
    m = re.match(r"[A-Za-z_][\w]*", s)
    return m.group(0).lower() if m else ""


def extract_io(step: SasStep, default_library: str = "work") -> SasStep:
    """Populate ``step.inputs`` and ``step.outputs`` in place; returns the step."""
    inputs: list[DatasetRef] = []
    outputs: list[DatasetRef] = []

    if step.kind is StepKind.DATA:
        for stmt in step.statements:
            kw = _first_keyword(stmt)
            if kw == "data":
                rest = stmt[len("data"):]
                for ref in _dataset_tokens(rest, default_library):
                    _add(outputs, ref)
            elif kw in _SET_KEYWORDS:
                rest = stmt[len(kw):]
                for ref in _dataset_tokens(rest, default_library):
                    _add(inputs, ref)

    elif step.kind is StepKind.PROC and (step.proc_name or "").lower() == "sql":
        text = step.text
        for m in _SQL_CREATE_RE.finditer(text):
            _add(outputs, DatasetRef.parse(m.group(1), default_library))
        for m in _SQL_INSERT_RE.finditer(text):
            _add(outputs, DatasetRef.parse(m.group(1), default_library))
        for rx in (_SQL_FROM_RE, _SQL_JOIN_RE):
            for m in rx.finditer(text):
                _add(inputs, DatasetRef.parse(m.group(1), default_library))

    elif step.kind is StepKind.PROC:
        # Generic option scan over the whole step.
        for m in _OPTION_RE.finditer(step.text):
            kind, token = m.group(1).lower(), m.group(2)
            ref = DatasetRef.parse(token, default_library)
            if kind in ("out", "outest", "base"):
                _add(outputs, ref)
            else:  # data=, inest=
                _add(inputs, ref)
        # PROC SORT with no out= sorts in place: it both reads and writes data=.
        if (step.proc_name or "").lower() == "sort" and not outputs and inputs:
            outputs.append(inputs[0])

    # Keep all inputs, including self-references such as `data X; set X;` or an
    # in-place `proc sort data=X`. The graph builder resolves each input against
    # the *previous* writer of that dataset, so a self-reference correctly links
    # to the step that produced the dataset (and never forms a self-edge).
    step.inputs = inputs
    step.outputs = outputs
    return step
