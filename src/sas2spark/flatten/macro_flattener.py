"""Component 1 — Macro Flattener.

Instead of handling the infinite variety of SAS macro constructs, we run SAS once
with ``options mprint mlogic symbolgen;`` and harvest the **expanded** code that
SAS writes to its log. After flattening, every ``%macro`` / ``%do`` / ``&var`` has
already been resolved, so downstream components only ever see concrete DATA/PROC
steps.

This module parses such a log. If it is handed raw SAS (no MPRINT lines), it
passes the source through unchanged so the pipeline also works on already-flat
programs.
"""
from __future__ import annotations

import re

# MPRINT(MACRONAME):   <expanded source>
_MPRINT_RE = re.compile(r"^\s*MPRINT\([^)]*\):\s?(.*)$")
# Some logs use a bare "MPRINT:" prefix.
_MPRINT_BARE_RE = re.compile(r"^\s*MPRINT:\s?(.*)$")
# Lines we never want in flattened source.
_LOG_NOISE_RE = re.compile(
    r"^\s*(MLOGIC|SYMBOLGEN|NOTE|WARNING|ERROR|INFO)[\s(:]", re.IGNORECASE
)


def looks_like_log(text: str) -> bool:
    """Heuristic: does this text contain SAS log instrumentation lines?"""
    for line in text.splitlines():
        if _MPRINT_RE.match(line) or _MPRINT_BARE_RE.match(line):
            return True
        if _LOG_NOISE_RE.match(line):
            return True
    return False


def flatten_log(log_text: str) -> str:
    """Extract the expanded, concrete SAS code from an MPRINT log.

    Returns the reconstructed SAS source. Lines that are not MPRINT output
    (NOTE/WARNING/MLOGIC/SYMBOLGEN/timing banners) are dropped.
    """
    out: list[str] = []
    for line in log_text.splitlines():
        m = _MPRINT_RE.match(line) or _MPRINT_BARE_RE.match(line)
        if m:
            code = m.group(1).rstrip()
            if code:
                out.append(code)
    return "\n".join(out) + ("\n" if out else "")


def flatten(source_or_log: str) -> str:
    """Flatten arbitrary input into concrete SAS source.

    * If the input looks like an MPRINT log, harvest the expanded code.
    * Otherwise return it unchanged (already-flat SAS, or no macros to expand).
    """
    if looks_like_log(source_or_log):
        flattened = flatten_log(source_or_log)
        if flattened.strip():
            return flattened
    return source_or_log
