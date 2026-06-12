"""Component 3 — Translator.

Given one SAS step plus its input/output schemas, prompt the LLM for an idiomatic
PySpark module that satisfies the ``transform(spark, inputs)`` contract, and pull
the code out of the model's reply.
"""
from __future__ import annotations

import re

from ..llm import LLMClient
from ..llm.prompts import (
    SYSTEM_TRANSLATOR,
    repair_prompt,
    translation_prompt,
)
from ..models import SasStep, Schema

_FENCE_RE = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_code(reply: str) -> str:
    """Pull the first Python code block out of an LLM reply.

    Falls back to the whole reply (stripped) if no fenced block is present.
    """
    matches = _FENCE_RE.findall(reply)
    if matches:
        # Prefer a block that actually defines `transform`.
        for block in matches:
            if "def transform" in block:
                return block.strip() + "\n"
        return matches[0].strip() + "\n"
    return reply.strip() + "\n"


class Translator:
    def __init__(self, client: LLMClient):
        self.client = client

    def translate(
        self,
        step: SasStep,
        input_schemas: dict[str, Schema] | None = None,
        output_schema: Schema | None = None,
        input_samples: dict[str, str] | None = None,
        output_sample: str | None = None,
    ) -> str:
        prompt = translation_prompt(
            step, input_schemas, output_schema, input_samples, output_sample
        )
        resp = self.client.complete(SYSTEM_TRANSLATOR, prompt)
        return extract_code(resp.text)

    def repair(
        self,
        step: SasStep,
        previous_code: str,
        failure_feedback: str,
        input_schemas: dict[str, Schema] | None = None,
        output_schema: Schema | None = None,
        input_samples: dict[str, str] | None = None,
        output_sample: str | None = None,
    ) -> str:
        prompt = repair_prompt(
            step, previous_code, failure_feedback, input_schemas, output_schema,
            input_samples, output_sample,
        )
        resp = self.client.complete(SYSTEM_TRANSLATOR, prompt)
        return extract_code(resp.text)
