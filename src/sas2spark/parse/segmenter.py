"""Component 2a — Segmenter.

A *lightweight* partial parser (not a full SAS grammar). It strips comments,
splits the program into statements while respecting quoted strings, then groups
statements into DATA/PROC step units. Step boundaries are:

* a ``data`` or ``proc`` statement starts a new step (implicitly closing the
  previous one, matching SAS's step-boundary semantics), and
* ``run;`` / ``quit;`` close the current step.
"""
from __future__ import annotations

import re

from ..models import SasStep, StepKind
from .io_extract import extract_io

_WORD_RE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")
_TERMINATORS = {"run", "quit", "endsas"}


def strip_comments(text: str) -> str:
    """Remove ``/* ... */`` block comments, respecting quoted strings.

    Single-line ``* ... ;`` comments are statements and are dropped later in
    :func:`split_statements`.
    """
    out: list[str] = []
    i, n = 0, len(text)
    in_squote = in_dquote = in_block = False
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if in_block:
            if c == "*" and nxt == "/":
                in_block = False
                out.append(" ")
                i += 2
                continue
            # preserve newlines so line counts stay roughly stable
            out.append("\n" if c == "\n" else " ")
            i += 1
            continue
        if in_squote:
            out.append(c)
            if c == "'":
                in_squote = False
            i += 1
            continue
        if in_dquote:
            out.append(c)
            if c == '"':
                in_dquote = False
            i += 1
            continue
        # not in any string/comment
        if c == "/" and nxt == "*":
            in_block = True
            out.append(" ")
            i += 2
            continue
        if c == "'":
            in_squote = True
            out.append(c)
            i += 1
            continue
        if c == '"':
            in_dquote = True
            out.append(c)
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def split_statements(text: str) -> list[str]:
    """Split into statements on ``;`` outside of quotes; drop comment statements."""
    cleaned = strip_comments(text)
    statements: list[str] = []
    buf: list[str] = []
    in_squote = in_dquote = False
    for c in cleaned:
        if in_squote:
            buf.append(c)
            if c == "'":
                in_squote = False
            continue
        if in_dquote:
            buf.append(c)
            if c == '"':
                in_dquote = False
            continue
        if c == "'":
            in_squote = True
            buf.append(c)
            continue
        if c == '"':
            in_dquote = True
            buf.append(c)
            continue
        if c == ";":
            stmt = "".join(buf).strip()
            buf = []
            if stmt and not stmt.startswith("*"):
                statements.append(_normalize_ws(stmt))
            continue
        buf.append(c)
    tail = "".join(buf).strip()
    if tail and not tail.startswith("*"):
        statements.append(_normalize_ws(tail))
    return statements


def _normalize_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _first_word(statement: str) -> str:
    m = _WORD_RE.match(statement.lstrip())
    return m.group(0).lower() if m else ""


def _proc_name(statement: str) -> str | None:
    # "proc sql" -> "sql"; "proc sort data=..." -> "sort"
    toks = statement.split()
    if len(toks) >= 2 and toks[0].lower() == "proc":
        m = _WORD_RE.match(toks[1])
        return m.group(0).lower() if m else None
    return None


def segment(text: str, default_library: str = "work") -> list[SasStep]:
    """Group flattened SAS source into DATA/PROC/OTHER step units with I/O filled in."""
    statements = split_statements(text)
    steps: list[SasStep] = []

    cur_stmts: list[str] = []
    cur_kind: StepKind | None = None
    cur_proc: str | None = None

    def flush() -> None:
        nonlocal cur_stmts, cur_kind, cur_proc
        if not cur_stmts:
            cur_kind = None
            cur_proc = None
            return
        kind = cur_kind or StepKind.OTHER
        step = SasStep(
            index=len(steps),
            kind=kind,
            text=";\n".join(cur_stmts) + ";",
            statements=list(cur_stmts),
            proc_name=cur_proc,
        )
        extract_io(step, default_library=default_library)
        steps.append(step)
        cur_stmts = []
        cur_kind = None
        cur_proc = None

    for stmt in statements:
        fw = _first_word(stmt)
        if fw in ("data", "proc"):
            flush()  # implicit step boundary
            cur_kind = StepKind.DATA if fw == "data" else StepKind.PROC
            cur_proc = _proc_name(stmt) if fw == "proc" else None
            cur_stmts.append(stmt)
            continue
        if fw in _TERMINATORS:
            cur_stmts.append(stmt)
            flush()
            continue
        # statement belongs to the current step, or forms/extends an OTHER block
        cur_stmts.append(stmt)

    flush()
    return steps
