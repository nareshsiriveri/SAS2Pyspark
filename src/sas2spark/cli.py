"""Command-line entry point.

Subcommands:
    flatten    SAS/log -> flattened concrete SAS source
    segment    list the DATA/PROC step units
    graph      print the dependency DAG (nodes, edges, layers) as JSON
    translate  translate every step to PySpark and write modules + manifest
    run        full pipeline: flatten -> segment -> translate -> eval -> integrate
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from .config import Settings
from .flatten import flatten
from .graph import build_graph
from .parse import segment


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def _settings_from_args(args) -> Settings:
    s = Settings.from_env()
    if getattr(args, "provider", None):
        s.llm_provider = args.provider
    if getattr(args, "model", None):
        s.llm_model = args.model
    if getattr(args, "max_repair", None) is not None:
        s.max_repair_attempts = args.max_repair
    if getattr(args, "fallback", None) is not None:
        s.fallback_provider = None if args.fallback == "none" else args.fallback
    if getattr(args, "anthropic_model", None):
        s.anthropic_model = args.anthropic_model
    if getattr(args, "workers", None) is not None:
        s.translate_workers = args.workers
    return s


def _build_cache(args):
    """Translation cache under <out>/.cache (disabled by --no-cache)."""
    if getattr(args, "no_cache", False):
        return None
    import os

    from .orchestrate import TranslationCache

    return TranslationCache(os.path.join(args.out, ".cache", "translations.json"))


def cmd_flatten(args) -> int:
    sys.stdout.write(flatten(_read(args.source)))
    return 0


def cmd_segment(args) -> int:
    steps = segment(flatten(_read(args.source)))
    for s in steps:
        print(f"[{s.index:03d}] {s.label}")
        print(f"      inputs : {[r.key for r in s.inputs] or '-'}")
        print(f"      outputs: {[r.key for r in s.outputs] or '-'}")
    print(f"\n{len(steps)} step(s).")
    return 0


def cmd_graph(args) -> int:
    steps = segment(flatten(_read(args.source)))
    g = build_graph(steps)
    print(json.dumps(g.to_dict(), indent=2))
    return 0


def cmd_translate(args) -> int:
    return _run_pipeline(args, integrate_output=True, do_run_e2e=False)


def cmd_run(args) -> int:
    return _run_pipeline(args, integrate_output=True, do_run_e2e=args.e2e)


def cmd_project(args) -> int:
    """Translate a multi-file SAS codebase into one integrated PySpark pipeline."""
    from .golden import GoldenStore
    from .orchestrate import (
        Pipeline,
        discover_files,
        integrate,
        run_project,
        write_human_review,
        write_report,
    )

    settings = _settings_from_args(args)
    files = discover_files(args.sources, order_file=args.order)
    if not files:
        print("error: no input files found", file=sys.stderr)
        return 2
    print(f"project: {len(files)} file(s) in order:", file=sys.stderr)
    for f in files:
        print(f"  - {f}", file=sys.stderr)

    golden = None
    if getattr(args, "golden_dir", None):
        golden = GoldenStore(args.golden_dir, default_library=settings.default_library)
        print(f"golden datasets discovered: {golden.keys()}", file=sys.stderr)

    try:
        pipeline = Pipeline(settings, golden=golden, cache=_build_cache(args))
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    project = run_project(pipeline, files, default_library=settings.default_library)
    result = project.result
    print(result.summary(), file=sys.stderr)

    integrate(result, args.out, include_unverified=args.include_unverified)
    write_human_review(result, args.out)
    report_path = write_report(project, args.out)
    print(f"wrote integrated pipeline + manifest to {args.out}", file=sys.stderr)
    print(f"wrote consolidated report {report_path}", file=sys.stderr)

    return 0 if not result.needs_human else 1


def _run_pipeline(args, *, integrate_output: bool, do_run_e2e: bool) -> int:
    # Heavy imports kept local so `flatten`/`segment`/`graph` work without them.
    from .golden import GoldenStore
    from .orchestrate import Pipeline, integrate, write_human_review

    settings = _settings_from_args(args)
    golden: Optional[GoldenStore] = None
    if getattr(args, "golden_dir", None):
        golden = GoldenStore(args.golden_dir, default_library=settings.default_library)
        print(f"golden datasets discovered: {golden.keys()}", file=sys.stderr)

    try:
        pipeline = Pipeline(settings, golden=golden, cache=_build_cache(args))
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    result = pipeline.translate_program(_read(args.source))
    print(result.summary(), file=sys.stderr)

    if integrate_output:
        artifacts = integrate(result, args.out, include_unverified=args.include_unverified)
        review_path = write_human_review(result, args.out)
        print(f"wrote modules to {artifacts.steps_dir}", file=sys.stderr)
        print(f"wrote runner    {artifacts.runner_path}", file=sys.stderr)
        print(f"wrote manifest  {artifacts.manifest_path}", file=sys.stderr)
        print(f"wrote review    {review_path}", file=sys.stderr)

    if do_run_e2e:
        rc = _e2e(result, args, golden)
        if rc != 0:
            return rc

    return 0 if not result.needs_human else 1


def _e2e(result, args, golden) -> int:
    from .evaluation.spark_runtime import default_spark_session

    if golden is None:
        print("--e2e requires --golden-dir for source datasets", file=sys.stderr)
        return 2
    sys.path.insert(0, args.out)
    try:
        import importlib.util

        runner_path = f"{args.out}/pipeline.py"
        spec = importlib.util.spec_from_file_location("generated_pipeline", runner_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        spark = default_spark_session()
        sources = {k: golden.spark(spark, k) for k in mod.EXTERNAL_INPUTS if golden.has(k)}
        datasets = mod.run_pipeline(spark, sources)
        print(f"E2E produced datasets: {sorted(datasets)}", file=sys.stderr)
        spark.stop()
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"E2E run failed: {exc}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sas2spark", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    def add_common(sp):
        sp.add_argument("source", help="path to a SAS program or MPRINT log")

    sp = sub.add_parser("flatten", help="harvest concrete SAS from an MPRINT log")
    add_common(sp)
    sp.set_defaults(func=cmd_flatten)

    sp = sub.add_parser("segment", help="list DATA/PROC step units")
    add_common(sp)
    sp.set_defaults(func=cmd_segment)

    sp = sub.add_parser("graph", help="print the dependency DAG as JSON")
    add_common(sp)
    sp.set_defaults(func=cmd_graph)

    def add_pipeline_opts(sp):
        add_common(sp)
        sp.add_argument("--out", default="build", help="output directory (default: build)")
        sp.add_argument("--golden-dir", help="directory of .sas7bdat golden datasets")
        sp.add_argument("--provider", choices=["openai", "anthropic", "stub"],
                        help="primary LLM provider")
        sp.add_argument("--model", help="primary LLM model id (default: gpt-5.5)")
        sp.add_argument("--fallback", choices=["anthropic", "openai", "none"],
                        help="secondary provider used if the primary errors "
                             "(default: anthropic; 'none' to disable)")
        sp.add_argument("--anthropic-model", dest="anthropic_model",
                        help="Anthropic model id (default: claude-opus-4-8)")
        sp.add_argument("--max-repair", type=int, dest="max_repair", help="max repair attempts")
        sp.add_argument("--include-unverified", action="store_true",
                        help="also emit modules for nodes that didn't pass the gauntlet")
        sp.add_argument("--workers", type=int,
                        help="concurrent node translations (default: 4; 1 = sequential)")
        sp.add_argument("--no-cache", action="store_true", dest="no_cache",
                        help="disable the incremental translation cache under <out>/.cache")

    sp = sub.add_parser("translate", help="translate all steps to PySpark + write modules")
    add_pipeline_opts(sp)
    sp.set_defaults(func=cmd_translate)

    sp = sub.add_parser("run", help="full pipeline (translate, eval, integrate)")
    add_pipeline_opts(sp)
    sp.add_argument("--e2e", action="store_true", help="also run the integrated pipeline end-to-end")
    sp.set_defaults(func=cmd_run)

    sp = sub.add_parser(
        "project",
        help="translate a multi-file SAS codebase into one integrated pipeline",
    )
    sp.add_argument("sources", nargs="+",
                    help="SAS/log files in execution order, or a single directory")
    sp.add_argument("--order", help="file listing source paths in execution order "
                                    "(one per line) — overrides positional ordering")
    sp.add_argument("--out", default="build", help="output directory (default: build)")
    sp.add_argument("--golden-dir", help="directory of golden datasets")
    sp.add_argument("--provider", choices=["openai", "anthropic", "stub"],
                    help="primary LLM provider")
    sp.add_argument("--model", help="primary LLM model id (default: gpt-5.5)")
    sp.add_argument("--fallback", choices=["anthropic", "openai", "none"],
                    help="secondary provider if the primary errors (default: anthropic)")
    sp.add_argument("--anthropic-model", dest="anthropic_model",
                    help="Anthropic model id (default: claude-opus-4-8)")
    sp.add_argument("--max-repair", type=int, dest="max_repair", help="max repair attempts")
    sp.add_argument("--include-unverified", action="store_true",
                    help="also emit modules for nodes that didn't pass the gauntlet")
    sp.add_argument("--workers", type=int,
                    help="concurrent node translations (default: 4; 1 = sequential)")
    sp.add_argument("--no-cache", action="store_true", dest="no_cache",
                    help="disable the incremental translation cache under <out>/.cache")
    sp.set_defaults(func=cmd_project)

    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
