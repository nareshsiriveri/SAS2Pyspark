const pptxgen = require("pptxgenjs");

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5
pres.author = "Risklab";
pres.title = "sas2spark — Architecture & Component Flow (v2)";

const W = 13.333, H = 7.5;

// ---- Palette (semantic per pipeline band) ----
const BG_DARK = "0F1E33";
const INK     = "16243A";
const MUTE    = "5B6B7E";
const LIGHT   = "FFFFFF";
const MINT    = "5EEAD4";

const BLUE    = "2F6DB5", BLUE_LT   = "E7F1FB";
const PURPLE  = "6A5AC6", PURPLE_LT = "ECEAFB";
const TEAL    = "0E8C8C", TEAL_LT   = "E1F2F2", TEAL_DK = "0A6A6A";
const AMBER   = "D9822B", AMBER_LT  = "FBEBD8";
const CORAL   = "C8503A", CORAL_LT  = "FAE7E1";
const GREEN   = "3C8C4A", GREEN_LT  = "E8F3E9";
const GRAY    = "5B6B7E", GRAY_LT   = "EDEFF2";

const HF = "Trebuchet MS"; // header
const BF = "Calibri";      // body
const MF = "Consolas";     // mono

const sh = () => ({ type: "outer", color: "1A2A3A", blur: 8, offset: 2, angle: 90, opacity: 0.14 });

let pageNo = 0;
function footer(slide, dark) {
  pageNo++;
  const c = dark ? "7C93A8" : MUTE;
  slide.addText("sas2spark · SAS → PySpark v2 · architecture", {
    x: 0.6, y: H - 0.42, w: 9, h: 0.3, fontFace: BF, fontSize: 9, color: c, align: "left", margin: 0,
  });
  slide.addText(String(pageNo), {
    x: W - 1.0, y: H - 0.42, w: 0.4, h: 0.3, fontFace: BF, fontSize: 9, color: c, align: "right", margin: 0,
  });
}

function titleBlock(slide, eyebrow, title) {
  slide.addText(eyebrow.toUpperCase(), {
    x: 0.62, y: 0.4, w: 11.5, h: 0.3, fontFace: BF, fontSize: 12, bold: true,
    color: TEAL, charSpacing: 3, margin: 0,
  });
  slide.addText(title, {
    x: 0.6, y: 0.72, w: 12.2, h: 0.7, fontFace: HF, fontSize: 28, bold: true, color: INK, margin: 0,
  });
}

// straight arrow from (x1,y1) to (x2,y2); arrow flag controls arrowhead
function arrow(slide, x1, y1, x2, y2, color, withHead, dash) {
  slide.addShape(pres.shapes.LINE, {
    x: x1, y: y1, w: x2 - x1, h: y2 - y1,
    line: Object.assign({ color: color || MUTE, width: 1.75, endArrowType: withHead === false ? "none" : "triangle" },
      dash ? { dashType: "dash" } : {}),
  });
}

// =====================================================================
// SLIDE 1 — TITLE
// =====================================================================
{
  const s = pres.addSlide();
  s.background = { color: BG_DARK };
  s.addShape(pres.shapes.OVAL, { x: 10.4, y: -2.2, w: 5.6, h: 5.6, fill: { type: "none" }, line: { color: "1E3C5A", width: 1.5 } });
  s.addShape(pres.shapes.OVAL, { x: 11.6, y: -1.0, w: 5.6, h: 5.6, fill: { type: "none" }, line: { color: "1E3C5A", width: 1.5 } });

  s.addText("ARCHITECTURE  ·  COMPONENT FLOW", {
    x: 0.9, y: 1.5, w: 11, h: 0.4, fontFace: BF, fontSize: 14, bold: true, color: MINT, charSpacing: 4, margin: 0,
  });
  s.addText("sas2spark", {
    x: 0.85, y: 1.95, w: 11.6, h: 1.0, fontFace: HF, fontSize: 52, bold: true, color: LIGHT, margin: 0,
  });

  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.9, y: 3.2, w: 1.7, h: 0.62, fill: { color: AMBER }, rectRadius: 0.31, shadow: sh() });
  s.addText("SAS", { x: 0.9, y: 3.2, w: 1.7, h: 0.62, fontFace: HF, fontSize: 20, bold: true, color: "2A1500", align: "center", valign: "middle", margin: 0 });
  s.addText("→", { x: 2.7, y: 3.2, w: 0.7, h: 0.62, fontFace: HF, fontSize: 26, bold: true, color: MINT, align: "center", valign: "middle", margin: 0 });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 3.45, y: 3.2, w: 2.4, h: 0.62, fill: { color: TEAL }, rectRadius: 0.31, shadow: sh() });
  s.addText("PySpark", { x: 3.45, y: 3.2, w: 2.4, h: 0.62, fontFace: HF, fontSize: 20, bold: true, color: LIGHT, align: "center", valign: "middle", margin: 0 });

  s.addText(
    "How the project works, component by component: one ordinary SAS run is flattened, decomposed into a dependency graph of DATA/PROC steps, translated to PySpark per step by an LLM, verified value-for-value against golden data through an eval gauntlet, repaired or escalated to a human, then integrated into a single runnable pipeline.",
    { x: 0.9, y: 4.2, w: 11.0, h: 1.4, fontFace: BF, fontSize: 16, color: "C7D6E2", lineSpacingMultiple: 1.25, margin: 0 }
  );
  footer(s, true);
}

// =====================================================================
// SLIDE 2 — ARCHITECTURE & DATA FLOW (the diagram)
// =====================================================================
{
  const s = pres.addSlide();
  s.background = { color: LIGHT };
  titleBlock(s, "Architecture", "Architecture & data flow");

  // small box helper for the diagram
  function dbox(o) {
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: o.x, y: o.y, w: o.w, h: o.h, fill: { color: o.lt }, line: { color: o.c, width: 1.5 }, rectRadius: 0.06, shadow: sh(),
    });
    s.addText(o.t, { x: o.x + 0.12, y: o.y + (o.sub ? 0.08 : 0), w: o.w - 0.24, h: o.sub ? 0.34 : o.h,
      fontFace: HF, fontSize: o.ts || 12.5, bold: true, color: INK, align: "center", valign: o.sub ? "top" : "middle", margin: 0 });
    if (o.sub) s.addText(o.sub, { x: o.x + 0.1, y: o.y + 0.38, w: o.w - 0.2, h: o.h - 0.58,
      fontFace: BF, fontSize: o.ss || 9.5, color: "47596B", align: "center", valign: "top", margin: 0, lineSpacingMultiple: 0.95 });
    if (o.file) s.addText(o.file, { x: o.x + 0.1, y: o.y + o.h - 0.26, w: o.w - 0.2, h: 0.22,
      fontFace: MF, fontSize: 8, color: o.c, align: "center", valign: "middle", margin: 0 });
  }

  // ---- Band 1: decomposition ----
  const bw = 2.75, by = 1.5, bh = 0.92, step = 3.10;
  const bx = [0.55, 0.55 + step, 0.55 + 2 * step, 0.55 + 3 * step];
  dbox({ x: bx[0], y: by, w: bw, h: bh, c: BLUE, lt: BLUE_LT, t: "Inputs", sub: "MPRINT log + golden data", file: "golden/reader.py" });
  dbox({ x: bx[1], y: by, w: bw, h: bh, c: BLUE, lt: BLUE_LT, t: "Macro flattener", sub: "log → concrete steps", file: "flatten/macro_flattener.py" });
  dbox({ x: bx[2], y: by, w: bw, h: bh, c: BLUE, lt: BLUE_LT, t: "Segmenter + I/O", sub: "DATA/PROC step units", file: "parse/segmenter.py" });
  dbox({ x: bx[3], y: by, w: bw, h: bh, c: BLUE, lt: BLUE_LT, t: "Dependency grapher", sub: "DAG · topo · layers", file: "graph/depgraph.py" });
  arrow(s, bx[0] + bw, by + bh / 2, bx[1], by + bh / 2);
  arrow(s, bx[1] + bw, by + bh / 2, bx[2], by + bh / 2);
  arrow(s, bx[2] + bw, by + bh / 2, bx[3], by + bh / 2);

  // entry into the loop
  arrow(s, 6.4, by + bh, 6.4, 2.92);
  s.addText("DAG of step nodes (parallel where independent)", { x: 6.6, y: 2.46, w: 6, h: 0.3, fontFace: BF, fontSize: 10, italic: true, color: MUTE, margin: 0 });

  // ---- Per-node loop container ----
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.55, y: 2.92, w: 12.05, h: 3.5, fill: { color: "F6FAFB" }, line: { color: TEAL_DK, width: 1.25, dashType: "dash" }, rectRadius: 0.1 });
  s.addText("PER-NODE LOOP  ·  orchestrate/pipeline.py  (LangGraph-style sweep)", { x: 0.8, y: 3.0, w: 11, h: 0.3, fontFace: BF, fontSize: 11, bold: true, color: TEAL_DK, charSpacing: 1, margin: 0 });

  // support boxes
  dbox({ x: 0.8, y: 3.55, w: 1.95, h: 0.74, c: GRAY, lt: GRAY_LT, t: "LLM client", ts: 11.5, sub: "gpt-5.5·Claude·stub", ss: 9.5 });
  dbox({ x: 0.8, y: 4.42, w: 1.95, h: 0.74, c: GRAY, lt: GRAY_LT, t: "Cache", ts: 11.5, sub: "seeds verified code", ss: 9.5 });

  // translator
  dbox({ x: 3.05, y: 3.7, w: 2.35, h: 1.2, c: PURPLE, lt: PURPLE_LT, t: "Translator", sub: "prompt LLM per step", file: "translate/translator.py" });

  // gauntlet (with phase list)
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 5.75, y: 3.4, w: 2.95, h: 2.05, fill: { color: TEAL_LT }, line: { color: TEAL, width: 1.5 }, rectRadius: 0.06, shadow: sh() });
  s.addText("Eval gauntlet", { x: 5.85, y: 3.5, w: 2.75, h: 0.32, fontFace: HF, fontSize: 13, bold: true, color: INK, align: "center", margin: 0 });
  s.addText([
    { text: "1  static — compile + lint", options: { breakLine: true } },
    { text: "2  schema — vs golden", options: { breakLine: true } },
    { text: "3  property — invariants", options: { breakLine: true } },
    { text: "4  data-equiv — value diff", options: { breakLine: true } },
    { text: "5  judge — LLM fallback" },
  ], { x: 5.95, y: 3.86, w: 2.6, h: 1.2, fontFace: BF, fontSize: 10, color: "1C5A5A", valign: "top", margin: 0, lineSpacingMultiple: 1.12 });
  s.addText("evaluation/gauntlet.py · vs golden", { x: 5.85, y: 5.18, w: 2.75, h: 0.22, fontFace: MF, fontSize: 8, color: TEAL, align: "center", margin: 0 });

  // pass? decision
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 9.0, y: 3.85, w: 1.05, h: 0.8, fill: { color: "FFFFFF" }, line: { color: GRAY, width: 1.5 }, rectRadius: 0.4, shadow: sh() });
  s.addText("pass?", { x: 9.0, y: 3.85, w: 1.05, h: 0.8, fontFace: HF, fontSize: 12, bold: true, color: INK, align: "center", valign: "middle", margin: 0 });

  // commit
  dbox({ x: 10.4, y: 3.85, w: 1.85, h: 0.8, c: GREEN, lt: GREEN_LT, t: "Commit", ts: 12.5, sub: "store + cache", ss: 9.5 });

  // repair + human
  dbox({ x: 9.0, y: 5.42, w: 3.25, h: 0.72, c: AMBER, lt: AMBER_LT, t: "Repair loop", ts: 12.5, sub: "re-translate with feedback", ss: 10 });
  dbox({ x: 3.05, y: 5.42, w: 2.35, h: 0.72, c: CORAL, lt: CORAL_LT, t: "Human review", ts: 12.5, sub: "unresolved nodes", ss: 10 });

  // ---- arrows inside the loop ----
  arrow(s, 2.75, 3.92, 3.05, 3.98);          // llm -> translator
  arrow(s, 2.75, 4.79, 3.05, 4.62);          // cache -> translator
  arrow(s, 5.40, 4.30, 5.75, 4.30);          // translator -> gauntlet
  arrow(s, 8.70, 4.25, 9.00, 4.25);          // gauntlet -> pass?
  arrow(s, 10.05, 4.25, 10.40, 4.25);        // pass? -> commit (yes)
  s.addText("yes", { x: 10.02, y: 3.92, w: 0.5, h: 0.25, fontFace: BF, fontSize: 9, bold: true, color: GREEN, align: "center", margin: 0 });
  arrow(s, 9.52, 4.65, 9.52, 5.42);          // pass? -> repair (no)
  s.addText("no", { x: 9.6, y: 4.82, w: 0.5, h: 0.25, fontFace: BF, fontSize: 9, bold: true, color: AMBER, align: "left", margin: 0 });
  arrow(s, 9.0, 5.78, 5.40, 5.78);           // repair -> human (stuck)
  s.addText("stuck ×N", { x: 6.4, y: 5.5, w: 1.6, h: 0.25, fontFace: BF, fontSize: 9, color: CORAL, align: "center", margin: 0 });

  // feedback elbow: repair -> translator
  arrow(s, 9.0, 6.1, 9.0, 6.26, MUTE, false);
  arrow(s, 9.0, 6.26, 2.88, 6.26, MUTE, false);
  arrow(s, 2.88, 6.26, 2.88, 4.92, MUTE, false);
  arrow(s, 2.88, 4.92, 3.05, 4.92, MUTE, true);
  s.addText("repair feedback ≤N", { x: 5.0, y: 6.04, w: 3, h: 0.25, fontFace: BF, fontSize: 9, italic: true, color: MUTE, align: "center", margin: 0 });

  // exit to integrator (routed down the right edge, clear of the Repair box)
  arrow(s, 11.3, 4.65, 12.4, 4.65, MUTE, false);
  arrow(s, 12.4, 4.65, 12.4, 6.5, GREEN, true);
  s.addText("all nodes committed →  Integrator builds pipeline.py", { x: 5.4, y: 6.58, w: 6.5, h: 0.3, fontFace: BF, fontSize: 11, bold: true, color: GREEN, align: "right", margin: 0 });

  footer(s, false);
}

// =====================================================================
// SLIDE 3 — STAGE A: decomposition (no LLM, no cost)
// =====================================================================
{
  const s = pres.addSlide();
  s.background = { color: LIGHT };
  titleBlock(s, "Stage A · decomposition", "Turn one SAS run into a graph of small steps");
  s.addText("Pure static analysis — no LLM, no Spark, no cost. Replaces v1's brittle SAS scanner / instrumentation.", {
    x: 0.62, y: 1.5, w: 12, h: 0.35, fontFace: BF, fontSize: 13, italic: true, color: MUTE, margin: 0 });

  const items = [
    ["Inputs", "golden/reader.py", "Two artifacts from one ordinary SAS run: the MPRINT .log and the golden datasets (.sas7bdat / .parquet / .csv). GoldenStore maps file names to dataset keys and serves schemas + sample rows."],
    ["Macro flattener", "flatten/macro_flattener.py", "Harvests the expanded code from MPRINT(...) log lines, so every %macro / %do / &var is already resolved. Raw SAS with no macros passes through unchanged."],
    ["Segmenter + I/O extract", "parse/segmenter.py · io_extract.py", "Lightweight partial parser (not a full grammar): strips comments, splits on data/proc … run;/quit;, and extracts each step's inputs (set/merge/from) and outputs (data X / create table X / out=)."],
    ["Dependency grapher", "graph/depgraph.py", "Builds a DAG (last-writer-wins on dataset names), topologically sorts it, and groups nodes into layers so independent steps translate in parallel. Unwritten reads become EXTERNAL_INPUTS."],
  ];
  const x0 = 0.62, y0 = 2.0, cw = 12.1, ch = 1.12, gy = 0.14;
  items.forEach((it, i) => {
    const y = y0 + i * (ch + gy);
    s.addShape(pres.shapes.RECTANGLE, { x: x0, y, w: cw, h: ch, fill: { color: BLUE_LT }, shadow: sh() });
    s.addShape(pres.shapes.RECTANGLE, { x: x0, y, w: 0.09, h: ch, fill: { color: BLUE } });
    s.addShape(pres.shapes.OVAL, { x: x0 + 0.28, y: y + 0.32, w: 0.48, h: 0.48, fill: { color: BLUE } });
    s.addText(String(i + 1), { x: x0 + 0.28, y: y + 0.32, w: 0.48, h: 0.48, fontFace: HF, fontSize: 19, bold: true, color: LIGHT, align: "center", valign: "middle", margin: 0 });
    s.addText([
      { text: it[0] + "    ", options: { bold: true, color: INK, fontSize: 15, fontFace: HF } },
      { text: it[1], options: { color: BLUE, fontSize: 10.5, fontFace: MF } },
    ], { x: x0 + 0.95, y: y + 0.14, w: cw - 1.2, h: 0.36, valign: "middle", margin: 0 });
    s.addText(it[2], { x: x0 + 0.95, y: y + 0.5, w: cw - 1.25, h: 0.55, fontFace: BF, fontSize: 11.5, color: "33485C", valign: "top", margin: 0, lineSpacingMultiple: 1.02 });
  });
  footer(s, false);
}

// =====================================================================
// SLIDE 4 — STAGE B: the per-node loop
// =====================================================================
{
  const s = pres.addSlide();
  s.background = { color: LIGHT };
  titleBlock(s, "Stage B · per-node loop", "Translate, evaluate, repair — one step at a time");

  const comps = [
    ["Translator", "translate/translator.py", PURPLE, PURPLE_LT, "Prompts the LLM with one SAS step + input/output schemas + golden sample rows; extracts the transform(spark, inputs) code block."],
    ["LLM client", "llm/client.py", GRAY, GRAY_LT, "Provider-agnostic: OpenAI gpt-5.5 default, Anthropic Claude fallback, offline stub. The judge phase leads with the other provider."],
    ["Translation cache", "orchestrate/cache.py", GRAY, GRAY_LT, "Fingerprints each step (SAS text + schemas + model). A hit seeds verified code, so re-runs re-evaluate but never re-translate."],
    ["Eval gauntlet", "evaluation/gauntlet.py", TEAL, TEAL_LT, "Cheapest-first, fail-fast: static → schema → property → data-equivalence diff → LLM-judge. The step runs once on Spark vs golden."],
    ["Repair loop", "repair/repair.py", AMBER, AMBER_LT, "On failure, feeds the exact traceback / schema-diff / value-diff / critique back to the translator and re-translates, up to --max-repair (default 3)."],
    ["Human-in-the-loop", "orchestrate/hitl.py", CORAL, CORAL_LT, "Only nodes still failing after N attempts surface — with SAS source, generated PySpark, the failing eval, and the diff — in human_review.md."],
  ];
  const cols = 2, cw = 5.98, ch = 1.5, gx = 0.18, gy = 0.16, x0 = 0.62, y0 = 1.6;
  comps.forEach((c, i) => {
    const col = i % cols, row = Math.floor(i / cols);
    const x = x0 + col * (cw + gx), y = y0 + row * (ch + gy);
    s.addShape(pres.shapes.RECTANGLE, { x, y, w: cw, h: ch, fill: { color: c[3] }, shadow: sh() });
    s.addShape(pres.shapes.RECTANGLE, { x, y, w: 0.09, h: ch, fill: { color: c[2] } });
    s.addText(c[0], { x: x + 0.3, y: y + 0.16, w: cw - 0.55, h: 0.34, fontFace: HF, fontSize: 15.5, bold: true, color: INK, valign: "middle", margin: 0 });
    s.addText(c[1], { x: x + 0.3, y: y + 0.5, w: cw - 0.55, h: 0.26, fontFace: MF, fontSize: 9.5, color: c[2], valign: "middle", margin: 0 });
    s.addText(c[4], { x: x + 0.3, y: y + 0.78, w: cw - 0.6, h: 0.66, fontFace: BF, fontSize: 11, color: "3A4A5A", valign: "top", margin: 0, lineSpacingMultiple: 1.02 });
  });
  footer(s, false);
}

// =====================================================================
// SLIDE 5 — EVAL GAUNTLET (staircase, dark)
// =====================================================================
{
  const s = pres.addSlide();
  s.background = { color: BG_DARK };
  s.addText("EVAL GAUNTLET", { x: 0.62, y: 0.42, w: 11, h: 0.3, fontFace: BF, fontSize: 12, bold: true, color: MINT, charSpacing: 3, margin: 0 });
  s.addText("Cheapest checks first, fail fast", { x: 0.6, y: 0.74, w: 12.1, h: 0.6, fontFace: HF, fontSize: 26, bold: true, color: LIGHT, margin: 0 });

  const phases = [
    ["1", "Static", "static_eval.py", "compiles · ruff/pyflakes · transform contract · no SparkSession.builder", "instant"],
    ["2", "Schema", "dataframe_evals.py", "output columns, dtypes, row count match the golden schema", "fast"],
    ["3", "Property / invariant", "compare.py", "sums, means, null counts, distinct-key counts, min/max vs golden", "cheap"],
    ["4", "Data-equivalence diff", "spark_runtime.py", "full value compare: float tol · missing values · 1960 epoch · BY ordering", "fuller"],
    ["5", "LLM-as-judge", "judge_eval.py", "no-golden steps: the other provider checks logical equivalence", "model"],
  ];
  const x0 = 0.62, rowH = 0.84, gap = 0.14, y0 = 1.7, baseW = 6.0, stepW = 0.95;
  phases.forEach((p, i) => {
    const y = y0 + i * (rowH + gap);
    const w = baseW + i * stepW;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: x0, y, w, h: rowH, fill: { color: "16314D" }, line: { color: TEAL, width: 1.2 }, rectRadius: 0.06, shadow: sh() });
    s.addShape(pres.shapes.OVAL, { x: x0 + 0.18, y: y + 0.22, w: 0.4, h: 0.4, fill: { color: MINT } });
    s.addText(p[0], { x: x0 + 0.18, y: y + 0.22, w: 0.4, h: 0.4, fontFace: HF, fontSize: 15, bold: true, color: "0F1E33", align: "center", valign: "middle", margin: 0 });
    s.addText([
      { text: p[1] + "   ", options: { bold: true, color: LIGHT, fontSize: 14, fontFace: HF } },
      { text: p[2], options: { color: MINT, fontSize: 10, fontFace: MF } },
    ], { x: x0 + 0.75, y: y + 0.1, w: w - 1.7, h: 0.34, valign: "middle", margin: 0 });
    s.addText(p[3], { x: x0 + 0.75, y: y + 0.42, w: w - 1.7, h: 0.36, fontFace: BF, fontSize: 10.5, color: "A9BFD2", valign: "middle", margin: 0 });
    s.addText(p[4], { x: x0 + w - 0.98, y: y + 0.22, w: 0.9, h: 0.4, fontFace: MF, fontSize: 9.5, bold: true, color: MINT, align: "right", valign: "middle", margin: 0 });
  });

  s.addText("Spark runs the translated step once; schema / property / diff all reuse that single materialized frame. A passing gauntlet commits the node.", {
    x: 0.62, y: 6.55, w: 12.0, h: 0.5, fontFace: BF, fontSize: 12, italic: true, color: "9FB6CA", margin: 0 });
  footer(s, true);
}

// =====================================================================
// SLIDE 6 — INTEGRATOR + OUTPUTS
// =====================================================================
{
  const s = pres.addSlide();
  s.background = { color: LIGHT };
  titleBlock(s, "Stage C · integration", "One runnable pipeline + a correctness verdict");

  // integrator card
  s.addShape(pres.shapes.RECTANGLE, { x: 0.62, y: 1.7, w: 4.4, h: 3.55, fill: { color: GREEN_LT }, shadow: sh() });
  s.addShape(pres.shapes.RECTANGLE, { x: 0.62, y: 1.7, w: 0.1, h: 3.55, fill: { color: GREEN } });
  s.addText("Integrator", { x: 0.95, y: 1.9, w: 3.9, h: 0.4, fontFace: HF, fontSize: 19, bold: true, color: INK, margin: 0 });
  s.addText("orchestrate/integrator.py", { x: 0.95, y: 2.3, w: 3.9, h: 0.3, fontFace: MF, fontSize: 10, color: GREEN, margin: 0 });
  s.addText("Writes each committed step to steps/<label>.py and generates pipeline.py — threading each step's output DataFrame into its downstream consumers in topological order. External source tables are supplied by the caller (EXTERNAL_INPUTS).",
    { x: 0.95, y: 2.7, w: 3.85, h: 2.4, fontFace: BF, fontSize: 12.5, color: "33485C", valign: "top", margin: 0, lineSpacingMultiple: 1.18 });

  // outputs
  const outs = [
    ["pipeline.py", "the runnable, tool-free PySpark pipeline — single entry point for local / Databricks / EMR / Glue", GREEN, GREEN_LT],
    ["report.md", "the correctness verdict, per source file and per step (data_equivalence=ok / FAIL)", TEAL, TEAL_LT],
    ["manifest.json", "machine-readable status + eval results + the dependency graph", BLUE, BLUE_LT],
    ["human_review.md", "only the steps that failed verification, with SAS, PySpark, and the exact diff", CORAL, CORAL_LT],
  ];
  const ox = 5.3, ow = 7.4, oh = 0.78, ogy = 0.16, oy0 = 1.7;
  outs.forEach((o, i) => {
    const y = oy0 + i * (oh + ogy);
    s.addShape(pres.shapes.RECTANGLE, { x: ox, y, w: ow, h: oh, fill: { color: o[3] }, shadow: sh() });
    s.addShape(pres.shapes.RECTANGLE, { x: ox, y, w: 0.09, h: oh, fill: { color: o[2] } });
    s.addText(o[0], { x: ox + 0.28, y: y + 0.06, w: ow - 0.5, h: 0.3, fontFace: MF, fontSize: 13, bold: true, color: INK, valign: "middle", margin: 0 });
    s.addText(o[1], { x: ox + 0.28, y: y + 0.36, w: ow - 0.55, h: 0.38, fontFace: BF, fontSize: 11, color: "3A4A5A", valign: "top", margin: 0, lineSpacingMultiple: 1.0 });
  });

  // run command strip
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.62, y: 5.5, w: 12.1, h: 1.15, fill: { color: "16243A" }, rectRadius: 0.08, shadow: sh() });
  s.addText("RUN", { x: 0.85, y: 5.62, w: 2, h: 0.3, fontFace: BF, fontSize: 11, bold: true, color: MINT, charSpacing: 2, margin: 0 });
  s.addText("sas2spark project mysas/ --golden-dir golden/ --provider anthropic --fallback none --out build", {
    x: 0.85, y: 5.92, w: 11.6, h: 0.45, fontFace: MF, fontSize: 13, color: "DCEAF0", margin: 0 });
  s.addText("CLI: cli.py · multi-file orchestration: orchestrate/project.py · settings: config.py", {
    x: 0.85, y: 6.32, w: 11.6, h: 0.28, fontFace: BF, fontSize: 10, italic: true, color: "8FA6BA", margin: 0 });
  footer(s, false);
}

// =====================================================================
// SLIDE 7 — v1 (image) → v2 mapping
// =====================================================================
{
  const s = pres.addSlide();
  s.background = { color: LIGHT };
  titleBlock(s, "From the v1 diagram", "How the original design maps to this codebase");

  const rows = [
    [
      { text: "v1 COMPONENT (Alphacodium diagram)", options: { fill: { color: "16314D" }, color: LIGHT, bold: true, fontFace: BF, fontSize: 12, align: "left", valign: "middle" } },
      { text: "v2 IN THIS REPO", options: { fill: { color: "16314D" }, color: LIGHT, bold: true, fontFace: BF, fontSize: 12, align: "left", valign: "middle" } },
    ],
    ["SAS Code Scanner", "Segmenter + I/O extract — parse/segmenter.py (partial parser, no full grammar)"],
    ["SAS Code Instrumentation", "Removed — golden datasets captured at step boundaries from one normal run"],
    ["SAS Runtime Instrumentation", "Removed — Macro flattener harvests MPRINT log instead (flatten/macro_flattener.py)"],
    ["Model Inputs", "Inputs + schemas — golden/reader.py feeds schemas & sample rows into the prompt"],
    ["Translator agent + LLM", "Translator + LLM client — translate/translator.py, llm/client.py"],
    ["Python Code Syntax Checker", "Gauntlet phase 1 — static_eval.py (compile + lint + contract)"],
    ["Semantic Analyzer + StaticLib(VEGA)", "Gauntlet phases 2-5 — schema / property / data-equivalence vs golden"],
    ["Checkpoint cache · Human in the loop", "orchestrate/cache.py · orchestrate/hitl.py (unchanged in spirit)"],
    ["LangGraph", "orchestrate/pipeline.py — dependency-ordered sweep, parallel over independent nodes"],
  ];
  const body = rows.map((r, i) => {
    if (i === 0) return r;
    const shade = i % 2 === 0 ? "F1F6F8" : LIGHT;
    return [
      { text: r[0], options: { fill: { color: shade }, color: "8A4B12", bold: true, fontFace: BF, fontSize: 11.5, align: "left", valign: "middle" } },
      { text: r[1], options: { fill: { color: shade }, color: "12424A", fontFace: BF, fontSize: 11.5, align: "left", valign: "middle" } },
    ];
  });
  s.addTable(body, {
    x: 0.62, y: 1.6, w: 12.1, colW: [4.6, 7.5],
    rowH: [0.42, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5],
    border: { type: "solid", pt: 1, color: "DCEAF0" }, margin: [3, 8, 3, 8], valign: "middle",
  });
  footer(s, false);
}

pres.writeFile({ fileName: "C:/SAS2PythonLatest/SAS2Python_Architecture.pptx" }).then((fn) => {
  console.log("WROTE " + fn);
});
