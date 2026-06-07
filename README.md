#  Code Assistant — SAS → PySpark (v2)

Translate large SAS codebases (incl. a 25,000-line program) to high-quality **PySpark**
without the brittle preprocessing/instrumentation layer. The pipeline flattens macros,
decomposes the program into a dependency graph of DATA/PROC steps, translates each step
with an LLM, and verifies every step with a **layered evaluation gauntlet**.

The design is described in [DESIGN_SAS2Python_v2.md](DESIGN_SAS2Python_v2.md).

> **LLM providers:** the translator and the LLM-as-judge eval call the **OpenAI ChatGPT API**
> (default model `gpt-5.5`) as the primary, with **Anthropic Claude** (default `claude-opus-4-8`)
> as an automatic **fallback** — if OpenAI errors (quota, auth, outage), calls transparently
> route to Claude. Both models are configurable; a fully offline `stub` provider is included so
> the deterministic parts of the pipeline can run and be tested without any API key.
>
> Set `OPENAI_API_KEY` (primary) and `ANTHROPIC_API_KEY` (fallback). Disable fallback with
> `--fallback none` or `SAS2SPARK_LLM_FALLBACK_PROVIDER=none`. You can also flip the roles —
> `--provider anthropic --fallback openai` — to lead with Claude.

## Architecture

```
SAS source / log ─▶ 1. Macro Flattener (MPRINT log harvest)
                 ─▶ 2. Segmenter + Dependency Grapher (DATA/PROC DAG, topo-sorted)
                 ─▶ per node:  3. Translator (LLM) ─▶ 4. Eval Gauntlet ─pass─▶ commit
                                      ▲                      │ fail
                                      └──── 5. Repair ◀──────┘  (stuck → 6. Human review)
                 ─▶ 7. Integrator → full-pipeline E2E eval
```

## Install

> For a full step-by-step guide to running this outside Claude Code (venv, keys,
> commands, Spark/Java setup), see **[RUNNING.md](RUNNING.md)**.

```bash
python -m pip install -e ".[all]"        # everything
# or pick what you need:
python -m pip install -e ".[llm,static]" # translate + static eval only (no Spark)
```

`pyspark`, `pyreadstat`, and `openai` are all optional at import time — the parser, graph,
and static-eval phases work without them.

## Quickstart

```bash
# 1. Inspect the dependency graph of a SAS program (no LLM, no Spark needed)
sas2spark graph examples/example.sas

# 2. Translate every step to PySpark (needs OPENAI_API_KEY, or use --provider stub)
sas2spark translate examples/example.sas --out build/ --provider stub

# 3. Run the full pipeline: flatten → segment → translate → eval → integrate
sas2spark run examples/example.sas \
    --golden-dir golden/ \
    --out build/ \
    --provider openai --model gpt-5.5
```

## The generated-code contract

Every translated step is a self-contained Python module that exposes:

```python
def transform(spark, inputs: dict[str, "DataFrame"]) -> "DataFrame":
    """`inputs` maps each input dataset name to a Spark DataFrame.
    Returns the single primary output DataFrame for this step."""
```

The eval gauntlet, the repair loop, and the integrator all rely on this contract.

## Layout

| Path | What |
|------|------|
| `src/sas2spark/flatten/` | MPRINT log → concrete unrolled steps |
| `src/sas2spark/parse/`   | step segmentation + I/O extraction |
| `src/sas2spark/graph/`   | dependency DAG + topological layering |
| `src/sas2spark/llm/`     | provider-agnostic client (OpenAI GPT-5.5 / stub) + prompts |
| `src/sas2spark/translate/` | per-step translator |
| `src/sas2spark/golden/`  | `.sas7bdat` golden-dataset reader |
| `src/sas2spark/evaluation/` | static / schema / property / diff / judge / gauntlet |
| `src/sas2spark/repair/`  | feedback-driven re-translation |
| `src/sas2spark/orchestrate/` | per-node loop, integrator, human-in-the-loop |
| `src/sas2spark/cli.py`   | command-line entry point |
```
