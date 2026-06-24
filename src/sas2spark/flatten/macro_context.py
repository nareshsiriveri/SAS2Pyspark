"""Dual-source macro provenance.

The plain :mod:`macro_flattener` harvests the MPRINT log into concrete steps. That
is exactly right for *structural* macro variables (loop indices, dataset-name
suffixes, ``%scan``'d list items): the expansion IS the code we want.

It is wrong for *data-derived* macro variables. Consider a scoring macro::

    %macro score(snapshot=, score_name=, n_var=, var_list=);
       data &snapshot.;
          set &snapshot.;
          &score_name. = 0 %do i=1 %to &n_var.;
             %let var_name = %scan(&var_list., &i.);
             + &&&var_name..*&var_name. %end;;
       run;
    %mend;

Here ``&&&var_name.`` resolves to a coefficient (``INTERCEPT`` -> ``-0.00637``)
that was pushed into a macro variable elsewhere (typically ``CALL SYMPUT`` from a
parameter-estimates table). MPRINT bakes that coefficient in as a literal::

    SCORE = 0 + -0.00637*INTERCEPT + 0*BIGCITY + ... + 0.2762*CCI;

That flattened step is a snapshot of one run, not a translatable program — a
PySpark version generated from it would hardcode the coefficients.

This module captures the missing provenance so the translator can generalize:

* the original parametric ``%macro...%mend`` source (the *intent*), and
* which baked-in literals came from data-derived macro variables (so they can be
  externalized as parameters instead of hardcoded).

The two kinds are separated by cross-referencing what the log and source already
tell us: loop indices (``MLOGIC ... index variable X``), macro parameters
(``MLOGIC ... Parameter X has value``) and ``%let``-assigned variables are
*structural*; a numeric-valued macro variable that is none of those came from
outside the macro and is treated as *data-derived*.
"""
from __future__ import annotations

import re

from ..models import MacroContext, MacroSubstitution, SasStep

# Log line shapes.
_MPRINT_NAME_RE = re.compile(r"^\s*MPRINT\(([^)]*)\):\s?(.*)$")
_SYMBOLGEN_RE = re.compile(
    r"^\s*SYMBOLGEN:\s*Macro variable\s+(\w+)\s+resolves to\s+(.*)$", re.IGNORECASE
)
_LOOP_IDX_RE = re.compile(r"index variable\s+(\w+)", re.IGNORECASE)
_PARAM_RE = re.compile(r"Parameter\s+(\w+)\s+has value", re.IGNORECASE)
# %let NAME = ... (assignment inside the original macro source).
_LET_RE = re.compile(r"%let\s+(\w+)\s*=", re.IGNORECASE)
# %macro NAME(...) ... %mend; (definition in the original source).
_MACRO_DEF_RE = re.compile(
    r"%macro\s+(\w+)\b.*?%mend\b[^;]*;", re.IGNORECASE | re.DOTALL
)
_NUMERIC_RE = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")
_TERMINATORS = {"run", "quit", "endsas", ""}


class LogInfo:
    """Macro-variable facts harvested from one MPRINT/SYMBOLGEN/MLOGIC log."""

    def __init__(self) -> None:
        self.symbol_values: dict[str, str] = {}  # var -> last resolved value
        self.loop_vars: set[str] = set()  # %do loop index variables
        self.param_vars: set[str] = set()  # macro parameters
        # macro name -> set of normalized statements MPRINT emitted under it.
        self.macro_emitted: dict[str, set[str]] = {}


def _norm(stmt: str) -> str:
    """Whitespace-normalize and lowercase a statement for robust matching."""
    return re.sub(r"\s+", " ", stmt).strip().rstrip(";").strip().lower()


def harvest_log(log_text: str) -> LogInfo:
    """Pull macro-variable provenance out of an MPRINT/SYMBOLGEN/MLOGIC log."""
    info = LogInfo()
    for line in log_text.splitlines():
        sg = _SYMBOLGEN_RE.match(line)
        if sg:
            info.symbol_values[sg.group(1).upper()] = sg.group(2).strip()
            continue
        m = _MPRINT_NAME_RE.match(line)
        if m:
            name = m.group(1).upper()
            code = m.group(2)
            bucket = info.macro_emitted.setdefault(name, set())
            # MPRINT may emit several statements on one line; split on ';'.
            for piece in code.split(";"):
                n = _norm(piece)
                if n and n not in _TERMINATORS:
                    bucket.add(n)
            continue
        # MLOGIC lines: loop indices and parameters.
        li = _LOOP_IDX_RE.search(line)
        if li and "MLOGIC" in line.upper():
            info.loop_vars.add(li.group(1).upper())
        pm = _PARAM_RE.search(line)
        if pm and "MLOGIC" in line.upper():
            info.param_vars.add(pm.group(1).upper())
    return info


def extract_macro_defs(sas_text: str) -> dict[str, str]:
    """Map MACRONAME -> its full ``%macro...%mend`` source text."""
    defs: dict[str, str] = {}
    for m in _MACRO_DEF_RE.finditer(sas_text):
        defs[m.group(1).upper()] = m.group(0).strip()
    return defs


def _let_vars(sas_text: str) -> set[str]:
    return {m.group(1).upper() for m in _LET_RE.finditer(sas_text)}


def derived_substitutions(info: LogInfo, let_vars: set[str]) -> dict[str, str]:
    """Macro vars whose baked-in value is data-derived (should be externalized).

    A variable qualifies when its resolved value is numeric and it is *not*
    structural — i.e. not a loop index, not a macro parameter, and not assigned by
    ``%let`` inside the macro. Those are the coefficients/parameters that came from
    outside the macro (commonly ``CALL SYMPUT`` from a data step or PROC).
    """
    out: dict[str, str] = {}
    structural = info.loop_vars | info.param_vars | let_vars
    for var, value in info.symbol_values.items():
        if var in structural:
            continue
        if _NUMERIC_RE.match(value):
            out[var] = value
    return out


def _value_in_text(value: str, text: str) -> bool:
    """True if ``value`` appears in ``text`` as a standalone numeric token."""
    pat = re.compile(r"(?<![\w.])" + re.escape(value) + r"(?![\w.])")
    return bool(pat.search(text))


def _macros_for_step(step: SasStep, info: LogInfo) -> list[str]:
    """Which macro(s) emitted this step, by matching its statements to MPRINT output."""
    step_stmts = {
        _norm(s) for s in step.statements if _norm(s) not in _TERMINATORS
    }
    if not step_stmts:
        return []
    names = [
        name
        for name, emitted in info.macro_emitted.items()
        if step_stmts & emitted
    ]
    return sorted(names)


def attach_macro_context(
    steps: list[SasStep], sas_text: str, log_text: str
) -> list[SasStep]:
    """Attach :class:`MacroContext` to steps expanded from a macro.

    ``sas_text`` is the original (parametric) SAS with ``%macro`` definitions;
    ``log_text`` is the MPRINT/SYMBOLGEN/MLOGIC log from the same run. Steps that
    did not come from a macro, or that carry no data-derived substitutions, are
    left untouched. Returns ``steps`` for convenience.
    """
    info = harvest_log(log_text)
    if not info.macro_emitted:
        return steps  # nothing was macro-expanded
    defs = extract_macro_defs(sas_text)
    derived = derived_substitutions(info, _let_vars(sas_text))

    for step in steps:
        macro_names = _macros_for_step(step, info)
        if not macro_names:
            continue
        subs = [
            MacroSubstitution(macro_var=var, value=val)
            for var, val in derived.items()
            if _value_in_text(val, step.text)
        ]
        # Only attach context when there are data-derived literals to externalize.
        # A purely structural macro (loop indices, %scan'd lists) expands to exactly
        # the right code — flagging it as a "snapshot" would wrongly push the model
        # to re-parameterize faithful constants.
        if not subs:
            continue
        source = "\n\n".join(defs[n] for n in macro_names if n in defs)
        step.macro_context = MacroContext(
            macro_names=macro_names,
            original_source=source,
            substitutions=subs,
        )
    return steps
