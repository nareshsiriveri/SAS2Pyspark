# Code Assistant — SAS → PySpark (v2)

Translate large SAS codebases (incl. a 25,000-line program) to high-quality **PySpark**.
The pipeline flattens macros, decomposes the program into a dependency graph of
DATA/PROC steps, translates each step with an LLM, and **verifies every step
value-for-value against your real SAS outputs** (the "golden" datasets).

This README is the complete operator guide: what to do in **SAS Studio**, how to set
up the Python environment, where to put your SAS code, how to run the conversion
from **bash**, and what to do with the output. The design rationale is in
[DESIGN_SAS2Python_v2.md](DESIGN_SAS2Python_v2.md); extra reference detail
(PowerShell variants, programmatic API, env-var table) is in [RUNNING.md](RUNNING.md).

```
SAS source / log ─▶ 1. Macro Flattener (MPRINT log harvest)
                 ─▶ 2. Segmenter + Dependency Grapher (DATA/PROC DAG, topo-sorted)
                 ─▶ per node:  3. Translator (LLM) ─▶ 4. Eval Gauntlet ─pass─▶ commit
                                      ▲                      │ fail
                                      └──── 5. Repair ◀──────┘  (stuck → 6. Human review)
                 ─▶ 7. Integrator → one runnable pipeline.py
```

---

## Part 1 — In SAS Studio: produce the two inputs

You need two things from **one normal run** of your existing SAS program. No code
rewrites, no instrumentation — just logging options and a dataset dump.

### 1.1 Turn on macro logging and run the program

In SAS Studio, open your program and add these lines **at the very top**, then run
it as usual (F3):

```sas
options mprint mlogic symbolgen;   /* makes the log contain the unrolled, concrete steps */
```

> Why: if your code uses macros / `%do` loops, the translator works from the
> **MPRINT log**, where every macro is already expanded into plain DATA/PROC steps.
> If a file has **no macros at all**, you can skip the log and feed the raw `.sas`
> file directly.

### 1.2 Save the log file(s)

After the run, open the **Log** tab and use the **download/save** button (disk icon
in the Log toolbar) to save it, e.g. `myprog.log`. For a multi-file codebase, run
the files in their normal order and save **one log per file**, named so the order
is obvious:

```
01_load.log, 02_clean.log, ..., 20_report.log
```

### 1.3 Export the golden datasets

These are the per-step output tables SAS wrote during that same run — they are what
the tool value-compares the PySpark against. Add this at the **end** of your program
(or run it right after, in the same session so WORK still exists):

```sas
libname golden "/home/<your-user>/golden";   /* a folder under Files (Home) */
proc copy in=work out=golden memtype=data; run;   /* dump every WORK dataset */
```

Also copy any **permanent input libraries** your program reads (the source tables),
e.g. `proc copy in=raw out=golden ...` — or download them separately.

Then in the **Files (Home)** pane: open the `golden` folder, select all the
`.sas7bdat` files → right-click → **Download**. (`.parquet` / `.csv` exports are
also accepted if you prefer `proc export`.)

File names become dataset keys on this side:

```
work.priced.sas7bdat   → work.priced
accounts.sas7bdat      → work.accounts        (default library)
raw/accounts.csv       → raw.accounts         (subfolder = library)
```

> **Naming tip:** the safest layout is one subfolder per library
> (`golden/work/*.sas7bdat`, `golden/raw/*.sas7bdat`) or `lib.name.sas7bdat`
> dotted names, exactly as `proc copy` writes them.

### 1.4 What you should have on your machine

```
C:\SAS2PythonLatest\
├── mysas\        ← your SAS sources and/or the saved .log files, in run order
│   ├── 01_load.log
│   ├── 02_clean.log
│   └── ...
└── golden\       ← the downloaded .sas7bdat (or .parquet/.csv) datasets
    ├── work.accounts.sas7bdat
    ├── work.priced.sas7bdat
    └── raw\accounts.sas7bdat
```

**Where do the 25,000 lines go?** Anywhere under a folder like `mysas\` — the tool
doesn't care about size; it segments everything into individual DATA/PROC steps and
translates them one at a time (in parallel). If it's **one giant file/log**, just
point the command at that one file. If it's **many files**, either name them
`01_…`, `02_…` so directory order = run order, or list them in a `run_order.txt`
manifest (one path per line) and pass `--order run_order.txt`.

---

## Part 2 — One-time setup of the Python environment

All commands below are **bash** (use **Git Bash** on Windows).

```bash
cd /c/SAS2PythonLatest

# 2.1 Create and activate a virtual environment
python -m venv .venv
source .venv/Scripts/activate          # (Linux/macOS: source .venv/bin/activate)

# 2.2 Install the tool + all extras (LLM clients, Spark, golden readers, evals)
pip install -e ".[all]"
pip install "numpy<2"                  # only if you hit a pandas/numpy ABI error

# 2.3 Java — needed only for the data-equivalence (Spark) step.
# Any JDK 8/11/17 works; a portable unzip is fine (this repo has one under .jdk/):
export JAVA_HOME="/c/SAS2PythonLatest/.jdk/jdk-17.0.19+10"
export PATH="$JAVA_HOME/bin:$PATH"
java -version                          # should print "openjdk version 17..."

# 2.4 API key(s) — put them in .env (never commit it) or export directly
cp .env.example .env                   # then edit .env and paste your key(s)
set -a; source .env; set +a            # load .env into this shell
# .env contents look like:
#   ANTHROPIC_API_KEY=sk-ant-...       (and/or OPENAI_API_KEY=sk-...)
```

Installing with `pip install -e .` registers the **`sas2spark`** command on your
PATH — that's the CLI used below.

> The default provider is OpenAI (`gpt-5.5`) with Anthropic Claude as automatic
> fallback. If you only have an Anthropic key, run with
> `--provider anthropic --fallback none`. A fully offline `--provider stub` exists
> for testing the plumbing without any key.

---

## Part 3 — Run the conversion (bash CLI)

### 3.1 Free sanity check first (no LLM, no Spark, no cost)

Confirm the flattening and the dependency graph look right **before** spending on
LLM calls:

```bash
sas2spark segment mysas/01_load.log      # lists the unrolled DATA/PROC steps
sas2spark graph   mysas/01_load.log      # dependency DAG: nodes, edges, external inputs
```

### 3.2 Convert + verify the whole codebase

One command translates every step, executes each on Spark, and value-compares to
your golden data:

```bash
sas2spark project mysas/ \
    --golden-dir golden/ \
    --provider anthropic --fallback none \
    --out build
```

Variants:

```bash
# explicit file order (most reliable for a big codebase)
sas2spark project mysas/01_load.log mysas/02_clean.log ... mysas/20_report.log \
    --golden-dir golden/ --out build

# order from a manifest file (one path per line)
sas2spark project --order run_order.txt --golden-dir golden/ --out build
```

Useful flags:

| Flag | Meaning |
|------|---------|
| `--golden-dir <dir>` | folder of golden datasets — enables the value-level verification (strongly recommended) |
| `--provider` / `--fallback` | `openai`, `anthropic`, `stub`; fallback kicks in on primary errors |
| `--workers <n>` | concurrent translations (default 4 — independent steps run in parallel) |
| `--max-repair <n>` | repair attempts per step before it goes to human review (default 3) |
| `--no-cache` | force fresh translations (by default verified steps are cached) |
| `--include-unverified` | also emit modules for steps that didn't pass verification |

### 3.3 Read the verdict

```bash
cat build/report.md
```

- **`✅ All N steps across F files passed`** with `data_equivalence=ok` on every
  step → each step's PySpark output matched SAS **value-for-value**. You're done.
- **`⚠️ X/N passed; K need review`** → open `build/human_review.md`: each failing
  step is listed with its SAS source, the generated PySpark, and the **exact data
  diff** that failed.

### 3.4 Fix and re-run (only if needed)

Hand-edit the failing step in `build/steps/<label>.py` (or adjust your golden data)
and re-run the same command. Verified translations are cached in
`build/.cache/translations.json`, so a re-run **re-checks but never re-translates**
passing steps — zero LLM cost for everything that already passed.

---

## Part 4 — The output, and whether you need to combine anything

```
build/
├── steps/<label>.py     one PySpark module per SAS step, with the original SAS
│                        quoted at the top of each file
├── pipeline.py          ★ the integrated runner — already wires every step
│                        together in dependency order
├── report.md            the correctness verdict, per file and per step
├── manifest.json        machine-readable status + eval results + the graph
├── human_review.md      only the steps that failed verification
└── .cache/              translation cache (safe to delete)
```

**No, you do not combine the Python files yourself.** The integrator already did
it: `pipeline.py` imports every verified step module and threads each step's output
DataFrame into the inputs of the steps that consume it, in dependency order. You
use it as a single entry point — locally, on Databricks, EMR, or Glue:

```python
import sys; sys.path.insert(0, "/c/SAS2PythonLatest/build")
from pipeline import run_pipeline, EXTERNAL_INPUTS, FINAL_OUTPUTS

# EXTERNAL_INPUTS lists the source tables you must supply as Spark DataFrames
# (everything your SAS program read but never created itself, e.g. "raw.accounts").
print(EXTERNAL_INPUTS)

datasets = run_pipeline(spark, {
    "raw.accounts": spark.read.parquet("..."),
    "raw.rates":    spark.read.parquet("..."),
})

datasets[FINAL_OUTPUTS[0]].show()     # every produced dataset is in the dict
```

The generated modules are plain PySpark with no dependency on this tool — you can
copy the `build/` folder anywhere with Spark and run it.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `pandas`/`numpy` import error on install | `pip install "numpy<2"` |
| Spark can't find Java | re-export `JAVA_HOME`/`PATH` (Part 2.3); on Git Bash issues, set a Windows-style `JAVA_HOME` from PowerShell |
| `WARN ... winutils.exe` / `NativeCodeLoader` lines during the run | harmless noise from local Spark on Windows — ignore |
| `java.io.EOFException` / PythonRunner worker errors | shouldn't happen — `PYSPARK_PYTHON` is auto-pinned by the tool; make sure you run inside the venv |
| Primary LLM quota/auth error mid-run | calls auto-route to the fallback provider; or rerun with `--provider anthropic` |
| Step keeps failing for a row-order/float reason | comparison is order-insensitive with float tolerance (`SAS2SPARK_FLOAT_TOLERANCE`, default 1e-9) — a persistent diff is a real logic difference |

## Testing the install (no key needed)

```bash
pytest -q                               # unit suite (Spark tests self-skip without Java)
sas2spark project examples/project --provider stub --out /tmp/smoke   # offline end-to-end
```

## Repo layout

| Path | What |
|------|------|
| `src/sas2spark/flatten/` | MPRINT log → concrete unrolled steps |
| `src/sas2spark/parse/`   | step segmentation + I/O extraction |
| `src/sas2spark/graph/`   | dependency DAG + topological layering |
| `src/sas2spark/llm/`     | provider-agnostic clients (OpenAI / Anthropic / stub) + prompts |
| `src/sas2spark/translate/` | per-step translator |
| `src/sas2spark/golden/`  | golden-dataset reader (`.sas7bdat`/`.parquet`/`.csv`) |
| `src/sas2spark/evaluation/` | static / schema / property / diff / judge gauntlet |
| `src/sas2spark/repair/`  | feedback-driven re-translation |
| `src/sas2spark/orchestrate/` | per-node loop, parallel scheduler, cache, integrator, HITL |
| `src/sas2spark/cli.py`   | the `sas2spark` command |
