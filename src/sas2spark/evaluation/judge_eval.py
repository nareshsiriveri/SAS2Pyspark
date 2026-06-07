"""Eval phase 5 — LLM-as-judge.

For steps with no golden data, a second model reviews the SAS step against the
candidate PySpark for logical equivalence and flags risky areas (RETAIN, implicit
DATA-step loop, MERGE many-to-many, PROC SQL joins).
"""
from __future__ import annotations

import json

from ..llm import LLMClient
from ..llm.prompts import SYSTEM_JUDGE, judge_prompt
from ..models import EvalPhase, EvalResult, SasStep


def evaluate_judge(
    step: SasStep,
    code: str,
    llm: LLMClient,
    input_schemas: dict | None = None,
    *,
    confidence_floor: float = 0.6,
) -> EvalResult:
    prompt = judge_prompt(step, code, input_schemas)
    resp = llm.complete(SYSTEM_JUDGE, prompt)
    verdict = _parse_verdict(resp.text)

    if verdict is None:
        return EvalResult(
            phase=EvalPhase.JUDGE,
            passed=False,
            summary="judge response was not parseable JSON",
            diagnostics=[resp.text[:500]],
        )

    equivalent = bool(verdict.get("equivalent", False))
    confidence = float(verdict.get("confidence", 0.0) or 0.0)
    issues = [str(i) for i in verdict.get("issues", []) or []]
    explanation = str(verdict.get("explanation", ""))

    # Pass only on a confident "equivalent" verdict; low confidence is treated as
    # a soft fail so the step is surfaced for human review.
    passed = equivalent and confidence >= confidence_floor
    summary = (
        f"judge: equivalent={equivalent} confidence={confidence:.2f}"
        if passed
        else f"judge not satisfied (equivalent={equivalent}, confidence={confidence:.2f})"
    )
    diags = ([f"explanation: {explanation}"] if explanation else []) + [
        f"issue: {i}" for i in issues
    ]
    return EvalResult(phase=EvalPhase.JUDGE, passed=passed, summary=summary, diagnostics=diags)


def _parse_verdict(text: str) -> dict | None:
    text = text.strip()
    # Tolerate code-fenced JSON.
    if text.startswith("```"):
        text = text.strip("`")
        if "\n" in text:
            text = text.split("\n", 1)[1]
    # Find the first {...} block.
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
