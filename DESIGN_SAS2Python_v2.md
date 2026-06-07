# Risklab Code Assistant — SAS → Python / PySpark (v2 Redesign)

> Goal: translate large SAS codebases (incl. a 25,000-line program) to high-quality
> **PySpark** (Spark DataFrame API + Spark SQL) **without the brittle SAS
> preprocessing/instrumentation layer**, with a generalized translator (not
> construct-rule based) and **layered evaluation phases** that guarantee correctness.

---

## 1. Why v1 hurt

| v1 component | Problem |
|---|---|
| SAS Code Scanner | Line-level parsing of arbitrary SAS (multi-line, macros, comments) is brittle |
| SAS Code Instrumentation | Injecting checkpoints into SAS internals is invasive and error-prone |
| SAS Runtime Instrumentation | Needs special instrumented runs; hard to maintain |
| Construct-based Translator | Hard-coded SAS construct → Python rules; fails on arbitrary nested loops / variations |

**Root cause:** v1 tries to understand and instrument SAS *internals line-by-line*.

**v2 principle:** treat SAS programs as **data transformations validated at their natural
boundaries** (DATA/PROC steps), translate **intent** with an LLM, and verify with a
**differential-testing eval gauntlet**. No instrumentation.

---

## 2. Core idea shift

| v1 | v2 |
|---|---|
| Instrument every line / inject checkpoints | **No instrumentation.** Capture dataset I/O at step boundaries from one ordinary SAS run |
| Translator = predefined construct rules | **Semantic, IR-based translation** of self-contained step units (idiomatic PySpark DataFrame API / Spark SQL) |
| Handle macro/loop nesting with rules | **Flatten macros first** via `MPRINT` log expansion, then translate concrete unrolled steps |
| Monolithic translation | **Dependency-graph decomposition** → translate + eval one step at a time (scales to 25K LOC) |

---

## 3. Architecture

```
                         ┌──────────────────────────────────────────────┐
  SAS source (25K LOC) ─▶ │ 1. Macro Flattener (MPRINT log harvest)       │  ← one normal SAS run
                         └──────────────────────────────────────────────┘
                                          │ flattened concrete steps
                                          ▼
                         ┌──────────────────────────────────────────────┐
                         │ 2. Segmenter + Dependency Grapher (static)    │  ← no instrumentation
                         │    nodes = DATA/PROC steps                     │
                         │    edges = dataset read/write deps             │
                         │    topological order                           │
                         └──────────────────────────────────────────────┘
                                          │  DAG of small step-units
                                          ▼
        ┌────────────────────── per-node loop (LangGraph) ───────────────────────┐
        │  3. Translator (LLM)  ──▶  4. Eval Gauntlet  ──pass──▶ commit node      │
        │        ▲                         │ fail                                  │
        │        └──── 5. Repair  ◀────────┘ (error/diff fed back)                 │
        │                  │ stuck after N tries                                   │
        │                  ▼                                                       │
        │           6. Human-in-the-loop (only unresolved nodes)                   │
        └──────────────────────────────────────────────────────────────────────┘
                                          │ all nodes pass
                                          ▼
                         ┌──────────────────────────────────────────────┐
                         │ 7. Integrator → full-pipeline E2E eval         │
                         └──────────────────────────────────────────────┘
```

---

## 4. Components

### 1. Macro Flattener (replaces the need to handle infinite construct variations)
- Run SAS **once** with `options mprint mlogic symbolgen;`.
- Harvest the **expanded code from the SAS log** → concrete, already-unrolled DATA/PROC steps.
- Macro layer (`%macro`, `%do`, `&var`) is resolved *before* translation, so nested-loop
  combinatorics disappear. You translate flat, concrete steps.

### 2. Segmenter + Dependency Grapher (replaces Scanner; no instrumentation)
- Lightweight partial parser (not a full grammar): find step boundaries
  (`data`/`proc` … `run;`/`quit;`) and each step's:
  - **inputs**: `set` / `merge` / `update` / `from`
  - **outputs**: `data X;` / `create table X` / `out=X`
- Build a DAG: nodes = steps, edges = dataset read/write dependencies.
- Topologically sort; independent nodes can be translated in parallel.

### 3. Translator (replaces construct-rule translator)
- Per node, prompt the LLM with: the SAS step, **input schema**, **expected output schema**,
  and project conventions (target: **PySpark** — DataFrame API, `Window` functions, Spark SQL).
- Generates idiomatic PySpark for that unit only. Small prompt → reliable, cheap, local errors.
- No construct catalog; the model generalizes over nesting.

### 4. Eval Gauntlet (see §5)

### 5. Repair loop
- On eval failure, feed back the specific error (traceback, schema diff, value diff, or
  judge critique) and re-translate. Cap at N attempts.

### 6. Human-in-the-loop
- Only nodes that fail after N repair attempts are surfaced for human review, with full
  context (SAS source, generated Python, the failing eval, the diff).

### 7. Integrator + E2E eval
- Assemble committed nodes in dependency order into a runnable Python pipeline.
- Run end-to-end; compare **final** outputs to SAS final outputs.

---

## 5. Eval phases (the core requirement)

Run as a **gauntlet** — cheapest checks first, fail fast:

1. **Static eval** — Python compiles; `ruff` + `mypy`; no undefined names/imports. (instant)
2. **Schema eval** — output columns, dtypes, row count match the SAS golden dataset schema.
3. **Property / invariant eval** — column sums, means, null counts, distinct-key counts,
   group cardinalities, min/max match golden. *Cheap; catches the majority of semantic bugs.*
4. **Data-equivalence eval (differential test)** — full value-level compare vs golden output
   dataset. The PySpark output is materialized (`.toPandas()` / `collect`, or compared in-Spark
   for large data) against the golden SAS dataset, with **SAS-aware handling**:
   - float tolerance
   - SAS missing-value semantics (`.`, `.A`–`.Z`) ↔ Spark `null`
   - date/datetime epoch (1960-01-01) ↔ Spark date/timestamp
   - numeric precision
   - BY-group ordering / FIRST./LAST. semantics (Spark is unordered → sort before compare)
5. **LLM-as-judge eval** — for steps with no golden data, a second model reviews SAS vs Python
   for logical equivalence; flags risky areas (RETAIN, implicit DATA-step loop, MERGE
   many-to-many, PROC SQL joins).
6. **End-to-end eval** — full pipeline output vs SAS final output.

**Regression eval suite (standing):** curated representative SAS snippets with verified
Python, run on every translator/prompt change → objective accuracy KPI over time.

---

## 6. Getting golden data WITHOUT instrumentation

Because you can run SAS normally:
- After a normal run, dump WORK + permanent library datasets (`.sas7bdat`) — SAS already
  writes these between steps, so you get **step-level golden data for free**.
- Capture program **inputs** too, so the Python pipeline runs on identical inputs.
- No checkpoint injection, no instrumented runtime.

---

## 7. Scaling to 25,000 LOC

- ~hundreds of DATA/PROC nodes after segmentation. **Never** put 25K lines in one prompt.
- Each LLM call sees one step (tens of lines) + schemas.
- Translate in **dependency layers**; parallelize independent nodes.
- **Idempotent caching**: a node re-translates only if its SAS source or input schema changed.
- Failures localized to a node → targeted repair + human review.

---

## 8. SAS-specific gotchas the design must cover

- Implicit DATA-step loop & output semantics → vectorized column expressions (`withColumn`,
  `select`); avoid per-row iteration (no `collect()`-and-loop).
- `RETAIN`, `BY` + `FIRST.`/`LAST.` → `Window` functions (`partitionBy` / `orderBy`) with
  `lag`/`lead`, `row_number`, and cumulative aggregates.
- `MERGE` (incl. many-to-many) → `DataFrame.join` with careful join-type / key semantics.
- `PROC SQL` → Spark SQL (`spark.sql(...)`) or the DataFrame API.
- Arrays, `DO` loops, `OUTPUT` statements → `explode` / array columns / `union` of frames.
- Formats/informats, character vs numeric, length truncation → explicit `cast` and Spark types.
- **Determinism / ordering:** Spark DataFrames are unordered; preserve SAS row order with an
  explicit index column or `orderBy` where semantics depend on it.

---

## 9. Tech stack (suggested)

- Orchestration: **LangGraph** (keep it).
- Target / runtime: **PySpark** — Spark DataFrame API + Spark SQL (`SparkSession`).
- Differential testing: read SAS golden `.sas7bdat` via `pyreadstat` / `pandas.read_sas`,
  then compare against the Spark output (collected to pandas, or compared in-Spark for large data).
- Static eval: `ruff`, `mypy`, `pytest` (with a shared `SparkSession` fixture for unit runs).
- SQL execution: **Spark SQL** (native to PySpark — no separate engine needed).

---

## 10. Open decisions

- Spark execution mode: local (single machine) vs cluster for the full 25K-LOC pipeline; partition tuning.
- Float comparison tolerances per domain (risk metrics may need tight tolerances).
- How aggressively to parallelize node translation (cost vs latency).
- Whether to keep intermediate PySpark modular per step (one DataFrame per node) or fuse steps post-validation.
- Value-compare strategy: collect to pandas vs in-Spark diff, given dataset sizes.
