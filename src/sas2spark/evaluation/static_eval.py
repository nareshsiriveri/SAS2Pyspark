"""Eval phase 1 — Static (instant).

Cheapest checks first: does it compile, does it satisfy the transform contract,
are there top-level side effects, undefined names, or contract violations such as
creating a SparkSession. Uses ``pyflakes`` and ``ruff`` when installed; degrades to
``ast`` checks otherwise.
"""
from __future__ import annotations

import ast
import shutil
import subprocess
import tempfile
from typing import Optional

from ..models import EvalPhase, EvalResult

_BANNED_SUBSTRINGS = {
    "SparkSession.builder": "creates its own SparkSession (use the passed-in `spark`)",
}


def evaluate_static(code: str) -> EvalResult:
    diagnostics: list[str] = []

    # 1. Compiles?
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return EvalResult(
            phase=EvalPhase.STATIC,
            passed=False,
            summary="does not compile",
            diagnostics=[f"SyntaxError: {exc.msg} (line {exc.lineno})"],
        )

    # 2. transform contract present, correct arity, no top-level side effects.
    transform_fn: Optional[ast.FunctionDef] = None
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "transform":
            transform_fn = node  # type: ignore[assignment]
        elif isinstance(node, ast.Expr) and isinstance(node.value, (ast.Constant,)):
            continue  # module docstring
        elif isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef,
                               ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        elif isinstance(node, ast.Assign):
            continue  # module-level constants are allowed
        elif isinstance(node, ast.If) and _is_main_guard(node):
            continue
        else:
            diagnostics.append(
                f"top-level side effect not allowed: {type(node).__name__} "
                f"at line {getattr(node, 'lineno', '?')}"
            )

    if transform_fn is None:
        return EvalResult(
            phase=EvalPhase.STATIC,
            passed=False,
            summary="missing `transform` function",
            diagnostics=diagnostics + ["module must define def transform(spark, inputs)"],
        )

    args = transform_fn.args
    n_pos = len(args.posonlyargs) + len(args.args)
    if n_pos < 2:
        diagnostics.append(
            f"transform must accept (spark, inputs); found {n_pos} positional parameter(s)"
        )

    # 3. Contract-violating substrings.
    for needle, why in _BANNED_SUBSTRINGS.items():
        if needle in code:
            diagnostics.append(f"{needle}: {why}")

    # 4. pyflakes / ruff if available.
    flake_diags, flake_fatal = _run_pyflakes(code)
    diagnostics.extend(flake_diags)
    _run_ruff(code, diagnostics)  # lint warnings are advisory, not fatal

    passed = not flake_fatal and not any(
        d for d in diagnostics
        if "undefined name" in d
        or d.startswith("top-level side effect")
        or "transform must accept" in d
        or ": creates its own SparkSession" in d
        or d.endswith("(use the passed-in `spark`)")
    )
    summary = "ok" if passed else "static checks failed"
    return EvalResult(
        phase=EvalPhase.STATIC,
        passed=passed,
        summary=summary,
        diagnostics=diagnostics,
    )


def _is_main_guard(node: ast.If) -> bool:
    test = node.test
    return (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name)
        and test.left.id == "__name__"
    )


def _run_pyflakes(code: str) -> tuple[list[str], bool]:
    """Return (diagnostics, fatal). Fatal if pyflakes reports undefined names."""
    try:
        from pyflakes.api import check  # type: ignore
        from pyflakes.reporter import Reporter  # type: ignore
    except ImportError:
        return [], False

    import io

    out, err = io.StringIO(), io.StringIO()
    reporter = Reporter(out, err)
    check(code, "generated_step", reporter)
    diags: list[str] = []
    fatal = False
    for line in (out.getvalue() + err.getvalue()).splitlines():
        line = line.strip()
        if not line:
            continue
        diags.append(f"pyflakes: {line}")
        if "undefined name" in line:
            fatal = True
    return diags, fatal


def _run_ruff(code: str, diagnostics: list[str]) -> None:
    if shutil.which("ruff") is None:
        return
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
            f.write(code)
            path = f.name
        proc = subprocess.run(
            ["ruff", "check", "--quiet", "--no-cache", path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        for line in proc.stdout.splitlines():
            line = line.strip()
            if line:
                diagnostics.append(f"ruff: {line}")
    except Exception:  # noqa: BLE001 - linting must never crash the gauntlet
        pass
