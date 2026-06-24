"""Incremental translation cache.

Re-running ``sas2spark project``/``run`` over the same codebase should not pay
LLM cost for steps that already passed. Each verified translation is stored
under a content fingerprint of everything that influenced it:

* the (flattened) SAS step text,
* the input/output schemas and golden sample rows shown to the model,
* the model identifier and a prompt-format version.

On a cache hit the stored code is seeded onto the node *before* the repair
loop runs; the loop then re-evaluates the seeded code first and only calls the
LLM if it no longer passes (e.g. the golden data changed). So a hit costs zero
translation calls while keeping the eval guarantee.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from typing import Optional

from ..models import Schema, SasStep

# Bump when the prompt format changes in a way that should invalidate caches.
PROMPT_VERSION = "3"


def _macro_ctx_fingerprint(step: SasStep) -> Optional[dict]:
    """Macro provenance shown to the translator, folded into the cache key.

    Without this, a step cached before dual-source support would shadow the new,
    generalized translation on re-run.
    """
    ctx = getattr(step, "macro_context", None)
    if ctx is None:
        return None
    return {
        "src": ctx.original_source,
        "subs": sorted((s.macro_var, s.value) for s in ctx.substitutions),
    }


def fingerprint(
    step: SasStep,
    input_schemas: dict[str, Schema],
    output_schema: Optional[Schema],
    input_samples: dict[str, str],
    output_sample: Optional[str],
    model: str,
) -> str:
    payload = {
        "v": PROMPT_VERSION,
        "text": step.text,
        "kind": step.kind.value,
        "proc": step.proc_name,
        "inputs": sorted(r.key for r in step.inputs),
        "outputs": sorted(r.key for r in step.outputs),
        "in_schemas": {k: s.to_dict() for k, s in sorted(input_schemas.items())},
        "out_schema": output_schema.to_dict() if output_schema else None,
        "in_samples": dict(sorted(input_samples.items())),
        "out_sample": output_sample,
        "model": model,
        "macro_ctx": _macro_ctx_fingerprint(step),
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class TranslationCache:
    """JSON-file-backed store of verified translations, safe for threaded use."""

    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        self._entries: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if not os.path.isfile(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self._entries = {
                    k: v for k, v in data.items()
                    if isinstance(v, dict) and isinstance(v.get("code"), str)
                }
        except (OSError, json.JSONDecodeError):
            self._entries = {}  # corrupt/unreadable cache: start fresh

    def get(self, key: str) -> Optional[str]:
        with self._lock:
            entry = self._entries.get(key)
        return entry["code"] if entry else None

    def put(self, key: str, code: str, *, label: str = "") -> None:
        with self._lock:
            existing = self._entries.get(key)
            if existing and existing.get("code") == code:
                return  # unchanged: skip the disk write
            self._entries[key] = {"code": code, "label": label}
            self._flush_locked()

    def _flush_locked(self) -> None:
        parent = os.path.dirname(self.path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._entries, f, indent=1)
        os.replace(tmp, self.path)

    def __len__(self) -> int:  # pragma: no cover - trivial
        with self._lock:
            return len(self._entries)
