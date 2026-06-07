const pptxgen = require("pptxgenjs");

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.3 x 7.5
pres.author = "Risklab";
pres.title = "Risklab Code Assistant — SAS → Python (v2 Redesign)";

const W = 13.333, H = 7.5;

// ---- Palette (tech / data-migration) ----
const BG_DARK = "0F1E33"; // deep navy
const PANEL   = "16314D"; // navy panel
const TEAL    = "0E8C8C"; // primary teal (Python)
const TEAL_DK = "0A6A6A";
const MINT     = "5EEAD4";
const AMBER   = "E0852F"; // SAS
const AMBER_LT= "F6E2C8";
const INK     = "16243A"; // near-black text
const MUTE    = "5B6B7E"; // muted text
const LIGHT   = "FFFFFF";
const CARD    = "F1F6F8"; // light card
const ICE     = "DCEAF0";

const HF = "Trebuchet MS"; // header font
const BF = "Calibri";      // body font
const MF = "Consolas";     // mono

const mkShadow = () => ({ type: "outer", color: "1A2A3A", blur: 9, offset: 3, angle: 90, opacity: 0.16 });

let pageNo = 0;
function footer(slide, dark) {
  pageNo++;
  const c = dark ? "7C93A8" : MUTE;
  slide.addText("Risklab Code Assistant · SAS → PySpark v2", {
    x: 0.6, y: H - 0.45, w: 8, h: 0.3, fontFace: BF, fontSize: 9, color: c, align: "left", margin: 0,
  });
  slide.addText(String(pageNo), {
    x: W - 1.0, y: H - 0.45, w: 0.4, h: 0.3, fontFace: BF, fontSize: 9, color: c, align: "right", margin: 0,
  });
}

// Standard content-slide title block (light slides)
function titleBlock(slide, eyebrow, title) {
  slide.addText(eyebrow.toUpperCase(), {
    x: 0.62, y: 0.42, w: 11, h: 0.3, fontFace: BF, fontSize: 12, bold: true,
    color: TEAL, charSpacing: 3, margin: 0,
  });
  slide.addText(title, {
    x: 0.6, y: 0.74, w: 12.1, h: 0.8, fontFace: HF, fontSize: 30, bold: true,
    color: INK, margin: 0,
  });
}

// =====================================================================
// SLIDE 1 — TITLE (dark)
// =====================================================================
{
  const s = pres.addSlide();
  s.background = { color: BG_DARK };

  // faint motif: large offset rings
  s.addShape(pres.shapes.OVAL, { x: 10.4, y: -2.2, w: 5.6, h: 5.6, fill: { type: "none" }, line: { color: "1E3C5A", width: 1.5 } });
  s.addShape(pres.shapes.OVAL, { x: 11.6, y: -1.0, w: 5.6, h: 5.6, fill: { type: "none" }, line: { color: "1E3C5A", width: 1.5 } });

  s.addText("V2 REDESIGN  ·  TECHNICAL DESIGN", {
    x: 0.9, y: 1.55, w: 10, h: 0.4, fontFace: BF, fontSize: 14, bold: true,
    color: MINT, charSpacing: 4, margin: 0,
  });

  s.addText("Risklab Code Assistant", {
    x: 0.85, y: 2.0, w: 11.6, h: 0.95, fontFace: HF, fontSize: 50, bold: true,
    color: LIGHT, margin: 0,
  });

  // SAS -> Python pills
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.9, y: 3.15, w: 1.7, h: 0.62, fill: { color: AMBER }, rectRadius: 0.31, shadow: mkShadow() });
  s.addText("SAS", { x: 0.9, y: 3.15, w: 1.7, h: 0.62, fontFace: HF, fontSize: 20, bold: true, color: "2A1500", align: "center", valign: "middle", margin: 0 });
  s.addText("→", { x: 2.7, y: 3.15, w: 0.7, h: 0.62, fontFace: HF, fontSize: 26, bold: true, color: MINT, align: "center", valign: "middle", margin: 0 });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 3.45, y: 3.15, w: 2.4, h: 0.62, fill: { color: TEAL }, rectRadius: 0.31, shadow: mkShadow() });
  s.addText("PySpark", { x: 3.45, y: 3.15, w: 2.4, h: 0.62, fontFace: HF, fontSize: 20, bold: true, color: LIGHT, align: "center", valign: "middle", margin: 0 });

  s.addText(
    "Translate large SAS codebases (incl. a 25,000-line program) to high-quality PySpark — without the brittle preprocessing / instrumentation layer. A generalized, IR-based translator plus a layered evaluation gauntlet that guarantees correctness.",
    { x: 0.9, y: 4.15, w: 10.6, h: 1.3, fontFace: BF, fontSize: 16, color: "C7D6E2", lineSpacingMultiple: 1.25, margin: 0 }
  );

  footer(s, true);
}

// =====================================================================
// SLIDE 2 — WHY v1 HURT (light, table + root cause)
// =====================================================================
{
  const s = pres.addSlide();
  s.background = { color: LIGHT };
  titleBlock(s, "Motivation", "Why v1 hurt");

  const rows = [
    [
      { text: "v1 COMPONENT", options: { fill: { color: PANEL }, color: LIGHT, bold: true, fontFace: BF, fontSize: 12, align: "left", valign: "middle" } },
      { text: "PROBLEM", options: { fill: { color: PANEL }, color: LIGHT, bold: true, fontFace: BF, fontSize: 12, align: "left", valign: "middle" } },
    ],
    ["SAS Code Scanner", "Line-level parsing of arbitrary SAS (multi-line, macros, comments) is brittle"],
    ["SAS Code Instrumentation", "Injecting checkpoints into SAS internals is invasive and error-prone"],
    ["SAS Runtime Instrumentation", "Needs special instrumented runs; hard to maintain"],
    ["Construct-based Translator", "Hard-coded construct → Python rules; fails on arbitrary nested loops / variations"],
  ];
  const body = rows.map((r, i) => {
    if (i === 0) return r;
    const shade = i % 2 === 0 ? CARD : LIGHT;
    return [
      { text: r[0], options: { fill: { color: shade }, color: INK, bold: true, fontFace: BF, fontSize: 14, align: "left", valign: "middle" } },
      { text: r[1], options: { fill: { color: shade }, color: "33485C", fontFace: BF, fontSize: 13, align: "left", valign: "middle" } },
    ];
  });

  s.addTable(body, {
    x: 0.62, y: 1.75, w: 12.1, colW: [3.5, 8.6], rowH: [0.45, 0.72, 0.72, 0.72, 0.72],
    border: { type: "solid", pt: 1, color: ICE }, margin: [4, 8, 4, 8], valign: "middle",
  });

  // Root cause callout
  s.addShape(pres.shapes.RECTANGLE, { x: 0.62, y: 5.75, w: 0.1, h: 1.05, fill: { color: AMBER } });
  s.addShape(pres.shapes.RECTANGLE, { x: 0.72, y: 5.75, w: 12.0, h: 1.05, fill: { color: AMBER_LT }, shadow: mkShadow() });
  s.addText([
    { text: "ROOT CAUSE   ", options: { bold: true, color: "8A4B12", fontSize: 12, charSpacing: 2 } },
    { text: "v1 tries to understand and instrument SAS internals line-by-line.", options: { color: "5A3308", fontSize: 16, bold: true } },
  ], { x: 1.0, y: 5.75, w: 11.5, h: 1.05, fontFace: BF, valign: "middle", margin: 0 });

  footer(s, false);
}

// =====================================================================
// SLIDE 3 — CORE IDEA SHIFT (v1 vs v2 two columns)
// =====================================================================
{
  const s = pres.addSlide();
  s.background = { color: LIGHT };
  titleBlock(s, "Core idea shift", "From instrumenting internals to validating boundaries");

  const pairs = [
    ["Instrument every line / inject checkpoints", "No instrumentation — capture dataset I/O at step boundaries from one ordinary SAS run"],
    ["Translator = predefined construct rules", "Semantic, IR-based translation of self-contained step units (idiomatic PySpark DataFrame API / Spark SQL)"],
    ["Handle macro & loop nesting with rules", "Flatten macros first via MPRINT log expansion, then translate concrete unrolled steps"],
    ["Monolithic translation", "Dependency-graph decomposition → translate + eval one step at a time (scales to 25K LOC)"],
  ];

  const colW = 5.95, gap = 0.2, x1 = 0.62, x2 = x1 + colW + gap;
  const topY = 1.7, rowH = 1.0, rowGap = 0.12;

  // column headers
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: x1, y: topY, w: colW, h: 0.55, fill: { color: AMBER }, rectRadius: 0.08 });
  s.addText("v1  ·  the old way", { x: x1, y: topY, w: colW, h: 0.55, fontFace: HF, fontSize: 16, bold: true, color: "2A1500", align: "center", valign: "middle", margin: 0 });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: x2, y: topY, w: colW, h: 0.55, fill: { color: TEAL }, rectRadius: 0.08 });
  s.addText("v2  ·  the redesign", { x: x2, y: topY, w: colW, h: 0.55, fontFace: HF, fontSize: 16, bold: true, color: LIGHT, align: "center", valign: "middle", margin: 0 });

  let y = topY + 0.55 + rowGap + 0.05;
  pairs.forEach((p) => {
    s.addShape(pres.shapes.RECTANGLE, { x: x1, y, w: colW, h: rowH, fill: { color: CARD } });
    s.addShape(pres.shapes.RECTANGLE, { x: x1, y, w: 0.07, h: rowH, fill: { color: AMBER } });
    s.addText(p[0], { x: x1 + 0.25, y, w: colW - 0.45, h: rowH, fontFace: BF, fontSize: 13.5, color: "4A3520", valign: "middle", margin: 0 });

    s.addShape(pres.shapes.RECTANGLE, { x: x2, y, w: colW, h: rowH, fill: { color: "E7F2F2" } });
    s.addShape(pres.shapes.RECTANGLE, { x: x2, y, w: 0.07, h: rowH, fill: { color: TEAL } });
    s.addText(p[1], { x: x2 + 0.25, y, w: colW - 0.45, h: rowH, fontFace: BF, fontSize: 13.5, color: "12424A", bold: false, valign: "middle", margin: 0 });
    y += rowH + rowGap;
  });

  footer(s, false);
}

// =====================================================================
// SLIDE 4 — ARCHITECTURE (pipeline flow, dark)
// =====================================================================
{
  const s = pres.addSlide();
  s.background = { color: BG_DARK };
  s.addText("ARCHITECTURE", { x: 0.62, y: 0.42, w: 11, h: 0.3, fontFace: BF, fontSize: 12, bold: true, color: MINT, charSpacing: 3, margin: 0 });
  s.addText("One normal SAS run in, a verified PySpark pipeline out", { x: 0.6, y: 0.74, w: 12.1, h: 0.7, fontFace: HF, fontSize: 28, bold: true, color: LIGHT, margin: 0 });

  // Linear stages (top row of 3 leading in)
  const stages = [
    { n: "1", t: "Macro Flattener", d: "MPRINT log harvest → concrete unrolled steps", c: AMBER },
    { n: "2", t: "Segmenter + Grapher", d: "DATA/PROC nodes, read/write dep DAG, topo-sort", c: TEAL },
    { n: "7", t: "Integrator + E2E", d: "assemble nodes, compare final outputs to SAS", c: "3E78A8" },
  ];

  // Stage 1 & 2 as wide boxes
  const boxW = 5.3;
  function stageBox(x, y, st, w, boxH) {
    w = w || boxW;
    boxH = boxH || 1.15;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h: boxH, fill: { color: PANEL }, line: { color: st.c, width: 1.5 }, rectRadius: 0.08, shadow: mkShadow() });
    s.addShape(pres.shapes.OVAL, { x: x + 0.22, y: y + (boxH - 0.55) / 2, w: 0.55, h: 0.55, fill: { color: st.c } });
    s.addText(st.n, { x: x + 0.22, y: y + (boxH - 0.55) / 2, w: 0.55, h: 0.55, fontFace: HF, fontSize: 20, bold: true, color: "0F1E33", align: "center", valign: "middle", margin: 0 });
    s.addText(st.t, { x: x + 0.95, y: y + 0.18, w: w - 1.1, h: 0.4, fontFace: HF, fontSize: 16, bold: true, color: LIGHT, valign: "middle", margin: 0 });
    s.addText(st.d, { x: x + 0.95, y: y + 0.56, w: w - 1.1, h: 0.5, fontFace: BF, fontSize: 11.5, color: "AEC2D4", valign: "top", margin: 0 });
  }

  stageBox(0.62, 1.55, stages[0], 5.9);
  s.addText("→", { x: 6.55, y: 1.55, w: 0.6, h: 1.15, fontFace: HF, fontSize: 26, bold: true, color: MINT, align: "center", valign: "middle", margin: 0 });
  stageBox(7.15, 1.55, stages[1], 5.55);

  // Per-node loop panel
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.62, y: 2.95, w: 12.1, h: 2.5, fill: { color: "12283F" }, line: { color: TEAL_DK, width: 1.25, dashType: "dash" }, rectRadius: 0.1 });
  s.addText("PER-NODE LOOP  ·  LangGraph", { x: 0.9, y: 3.1, w: 8, h: 0.3, fontFace: BF, fontSize: 12, bold: true, color: MINT, charSpacing: 2, margin: 0 });

  const loop = [
    { n: "3", t: "Translator (LLM)", c: TEAL },
    { n: "4", t: "Eval Gauntlet", c: TEAL },
    { n: "5", t: "Repair", c: AMBER },
    { n: "6", t: "Human-in-the-loop", c: "B05CC8" },
  ];
  const lw = 2.72, lgap = 0.32, lx0 = 0.95, ly = 3.55;
  loop.forEach((st, i) => {
    const x = lx0 + i * (lw + lgap);
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: ly, w: lw, h: 1.1, fill: { color: PANEL }, line: { color: st.c, width: 1.5 }, rectRadius: 0.08 });
    s.addShape(pres.shapes.OVAL, { x: x + 0.2, y: ly + 0.3, w: 0.5, h: 0.5, fill: { color: st.c } });
    s.addText(st.n, { x: x + 0.2, y: ly + 0.3, w: 0.5, h: 0.5, fontFace: HF, fontSize: 18, bold: true, color: "0F1E33", align: "center", valign: "middle", margin: 0 });
    s.addText(st.t, { x: x + 0.78, y: ly, w: lw - 0.9, h: 1.1, fontFace: HF, fontSize: 14, bold: true, color: LIGHT, valign: "middle", margin: 0 });
    if (i < loop.length - 1) {
      s.addText("→", { x: x + lw - 0.02, y: ly, w: lgap + 0.02, h: 1.1, fontFace: HF, fontSize: 20, bold: true, color: MINT, align: "center", valign: "middle", margin: 0 });
    }
  });
  s.addText("pass ✓  → commit node          fail ✗  → feed error / diff back to Repair          stuck after N tries → human review", {
    x: 0.95, y: 4.8, w: 11.5, h: 0.45, fontFace: BF, fontSize: 12, italic: true, color: "9FB6CA", valign: "middle", margin: 0,
  });

  // Final stage
  s.addText("↓  all nodes pass", { x: 0.95, y: 5.5, w: 5, h: 0.3, fontFace: BF, fontSize: 12, bold: true, color: MINT, margin: 0 });
  stageBox(0.62, 5.8, stages[2], 12.1, 1.0);

  footer(s, true);
}

// =====================================================================
// SLIDE 5 — COMPONENTS (7 items grid, light)
// =====================================================================
{
  const s = pres.addSlide();
  s.background = { color: LIGHT };
  titleBlock(s, "Components", "Seven cooperating stages");

  const comps = [
    ["1", "Macro Flattener", "Run SAS once with mprint/mlogic; harvest expanded, unrolled DATA/PROC steps. Macro combinatorics gone."],
    ["2", "Segmenter + Grapher", "Partial parser finds step boundaries & I/O; builds a read/write dependency DAG, topologically sorted."],
    ["3", "Translator (LLM)", "Per node: SAS step + input/output schema + conventions → idiomatic PySpark. Small prompt, local errors."],
    ["4", "Eval Gauntlet", "Layered checks, cheapest first — static, schema, property, data-equivalence, judge, E2E."],
    ["5", "Repair loop", "On failure, feed the specific error / diff / critique back and re-translate. Capped at N attempts."],
    ["6", "Human-in-the-loop", "Only nodes failing after N repairs surface — with full context: SAS, PySpark, failing eval, diff."],
    ["7", "Integrator + E2E", "Assemble committed nodes in dependency order; run end-to-end vs SAS final outputs."],
  ];

  const cols = 2, cw = 5.95, ch = 1.16, gx = 0.2, gy = 0.16, x0 = 0.62, y0 = 1.6;
  comps.forEach((c, i) => {
    const col = i % cols, row = Math.floor(i / cols);
    const x = x0 + col * (cw + gx), y = y0 + row * (ch + gy);
    s.addShape(pres.shapes.RECTANGLE, { x, y, w: cw, h: ch, fill: { color: CARD }, shadow: mkShadow() });
    s.addShape(pres.shapes.OVAL, { x: x + 0.24, y: y + 0.3, w: 0.52, h: 0.52, fill: { color: TEAL } });
    s.addText(c[0], { x: x + 0.24, y: y + 0.3, w: 0.52, h: 0.52, fontFace: HF, fontSize: 21, bold: true, color: LIGHT, align: "center", valign: "middle", margin: 0 });
    s.addText(c[1], { x: x + 0.96, y: y + 0.14, w: cw - 1.16, h: 0.36, fontFace: HF, fontSize: 15, bold: true, color: INK, valign: "middle", margin: 0 });
    s.addText(c[2], { x: x + 0.96, y: y + 0.5, w: cw - 1.16, h: 0.58, fontFace: BF, fontSize: 11, color: "47596B", valign: "top", margin: 0, lineSpacingMultiple: 1.0 });
  });

  // 7th item spans nothing special; it lands in col0 row3 already. Good.
  footer(s, false);
}

// =====================================================================
// SLIDE 6 — EVAL GAUNTLET (staircase, dark)
// =====================================================================
{
  const s = pres.addSlide();
  s.background = { color: BG_DARK };
  s.addText("EVALUATION", { x: 0.62, y: 0.42, w: 11, h: 0.3, fontFace: BF, fontSize: 12, bold: true, color: MINT, charSpacing: 3, margin: 0 });
  s.addText("The eval gauntlet — cheapest checks first, fail fast", { x: 0.6, y: 0.74, w: 12.1, h: 0.7, fontFace: HF, fontSize: 26, bold: true, color: LIGHT, margin: 0 });

  const phases = [
    ["1", "Static eval", "Compiles · ruff + mypy · no undefined names/imports", "instant"],
    ["2", "Schema eval", "Output columns, dtypes, row count match golden schema", "fast"],
    ["3", "Property / invariant", "Sums, means, nulls, distinct keys, group cardinalities", "cheap"],
    ["4", "Data-equivalence (diff)", "Full value compare: float tol, missing values, 1960 epoch, BY/FIRST.LAST.", "fuller"],
    ["5", "LLM-as-judge", "No-golden steps: 2nd model checks logical equivalence; flags risk", "model"],
    ["6", "End-to-end", "Full pipeline output vs SAS final output", "E2E"],
  ];
  const x0 = 0.62, rowH = 0.72, gap = 0.12, y0 = 1.75, baseW = 5.2, stepW = 0.7;
  phases.forEach((p, i) => {
    const y = y0 + i * (rowH + gap);
    const w = baseW + i * stepW;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: x0, y, w, h: rowH, fill: { color: PANEL }, line: { color: TEAL, width: 1 }, rectRadius: 0.06, shadow: mkShadow() });
    s.addShape(pres.shapes.OVAL, { x: x0 + 0.16, y: y + 0.16, w: 0.4, h: 0.4, fill: { color: MINT } });
    s.addText(p[0], { x: x0 + 0.16, y: y + 0.16, w: 0.4, h: 0.4, fontFace: HF, fontSize: 15, bold: true, color: "0F1E33", align: "center", valign: "middle", margin: 0 });
    s.addText([
      { text: p[1] + "   ", options: { bold: true, color: LIGHT, fontSize: 13.5, fontFace: HF } },
      { text: p[2], options: { color: "A9BFD2", fontSize: 11, fontFace: BF } },
    ], { x: x0 + 0.7, y, w: w - 1.6, h: rowH, valign: "middle", margin: 0 });
    s.addText(p[3], { x: x0 + w - 0.95, y: y + 0.16, w: 0.85, h: 0.4, fontFace: MF, fontSize: 9.5, bold: true, color: MINT, align: "right", valign: "middle", margin: 0 });
  });

  // standing regression callout (right)
  const rx = 9.6, rw = 3.1;
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: rx, y: 4.0, w: rw, h: 2.55, fill: { color: "12283F" }, line: { color: AMBER, width: 1.25 }, rectRadius: 0.1 });
  s.addText("STANDING", { x: rx + 0.25, y: 4.18, w: rw - 0.5, h: 0.3, fontFace: BF, fontSize: 11, bold: true, color: AMBER, charSpacing: 2, margin: 0 });
  s.addText("Regression eval suite", { x: rx + 0.25, y: 4.46, w: rw - 0.5, h: 0.5, fontFace: HF, fontSize: 16, bold: true, color: LIGHT, margin: 0 });
  s.addText("Curated representative SAS snippets with verified PySpark, run on every translator / prompt change → an objective accuracy KPI over time.", {
    x: rx + 0.25, y: 4.95, w: rw - 0.5, h: 1.5, fontFace: BF, fontSize: 12, color: "C2D2E0", valign: "top", margin: 0, lineSpacingMultiple: 1.15,
  });

  footer(s, true);
}

// =====================================================================
// SLIDE 7 — GOLDEN DATA (light, stat + cards)
// =====================================================================
{
  const s = pres.addSlide();
  s.background = { color: LIGHT };
  titleBlock(s, "Golden data", "Step-level golden data — without instrumentation");

  // big stat
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.62, y: 1.95, w: 3.9, h: 3.6, fill: { color: PANEL }, rectRadius: 0.12, shadow: mkShadow() });
  s.addText("for", { x: 0.62, y: 2.35, w: 3.9, h: 0.5, fontFace: BF, fontSize: 18, color: MINT, align: "center", margin: 0 });
  s.addText("FREE", { x: 0.62, y: 2.7, w: 3.9, h: 1.3, fontFace: HF, fontSize: 64, bold: true, color: LIGHT, align: "center", margin: 0 });
  s.addText("SAS already writes datasets between steps, so a normal run hands you step-level golden data.", {
    x: 0.95, y: 4.15, w: 3.25, h: 1.2, fontFace: BF, fontSize: 13, color: "C7D6E2", align: "center", valign: "top", margin: 0, lineSpacingMultiple: 1.15,
  });

  const cards = [
    ["Dump the datasets", "After a normal run, dump WORK + permanent library .sas7bdat files. They already exist between steps."],
    ["Capture the inputs", "Snapshot program inputs too, so the PySpark pipeline runs on byte-identical inputs."],
    ["No injection, no instrumented runtime", "Zero checkpoint injection. Zero special runs. SAS runs exactly as it normally would."],
  ];
  const cx = 4.85, cw = 7.85, ch = 1.05, cgap = 0.22, cy0 = 1.95;
  cards.forEach((c, i) => {
    const y = cy0 + i * (ch + cgap);
    s.addShape(pres.shapes.RECTANGLE, { x: cx, y, w: cw, h: ch, fill: { color: CARD } });
    s.addShape(pres.shapes.RECTANGLE, { x: cx, y, w: 0.08, h: ch, fill: { color: TEAL } });
    s.addText(c[0], { x: cx + 0.3, y: y + 0.14, w: cw - 0.5, h: 0.38, fontFace: HF, fontSize: 16, bold: true, color: INK, valign: "middle", margin: 0 });
    s.addText(c[1], { x: cx + 0.3, y: y + 0.5, w: cw - 0.5, h: 0.5, fontFace: BF, fontSize: 12.5, color: "47596B", valign: "top", margin: 0 });
  });

  footer(s, false);
}

// =====================================================================
// SLIDE 8 — SCALING TO 25K LOC (light, stats + points)
// =====================================================================
{
  const s = pres.addSlide();
  s.background = { color: LIGHT };
  titleBlock(s, "Scale", "Scaling to 25,000 lines of code");

  const stats = [
    ["25,000", "LOC handled — never in one prompt", AMBER],
    ["~100s", "DATA / PROC nodes after segmentation", TEAL],
    ["1", "step per LLM call (tens of lines + schemas)", PANEL],
  ];
  const sw = 3.9, sgap = 0.2, sx0 = 0.62, sy = 1.85, sh = 1.85;
  stats.forEach((st, i) => {
    const x = sx0 + i * (sw + sgap);
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: sy, w: sw, h: sh, fill: { color: CARD }, rectRadius: 0.1, shadow: mkShadow() });
    s.addText(st[0], { x, y: sy + 0.28, w: sw, h: 0.95, fontFace: HF, fontSize: 48, bold: true, color: st[2], align: "center", margin: 0 });
    s.addText(st[1], { x: x + 0.3, y: sy + 1.18, w: sw - 0.6, h: 0.55, fontFace: BF, fontSize: 12.5, color: "47596B", align: "center", valign: "top", margin: 0 });
  });

  const pts = [
    "Translate in dependency layers; parallelize independent nodes.",
    "Idempotent caching — a node re-translates only if its SAS source or input schema changed.",
    "Failures localized to a node → targeted repair and human review, never a whole-program redo.",
  ];
  let py = 4.2;
  s.addShape(pres.shapes.RECTANGLE, { x: 0.62, y: py, w: 12.1, h: 2.15, fill: { color: "F4F9FA" } });
  s.addText(pts.map((p, i) => ({ text: p, options: { bullet: { code: "2022", indent: 18 }, breakLine: true, color: "33485C", fontSize: 15, paraSpaceAfter: 12 } })), {
    x: 1.0, y: py + 0.25, w: 11.4, h: 1.7, fontFace: BF, valign: "top", margin: 0,
  });

  footer(s, false);
}

// =====================================================================
// SLIDE 9 — SAS GOTCHAS (light, mapping grid)
// =====================================================================
{
  const s = pres.addSlide();
  s.background = { color: LIGHT };
  titleBlock(s, "Gotchas", "SAS-specific semantics the design must cover");

  const map = [
    ["Implicit DATA-step loop & OUTPUT", "withColumn / select — no per-row iteration"],
    ["RETAIN, BY + FIRST. / LAST.", "Window functions: lag / lead, cumulative aggregates"],
    ["MERGE (incl. many-to-many)", "DataFrame.join with careful key semantics"],
    ["PROC SQL", "Spark SQL (spark.sql) or DataFrame API"],
    ["Arrays, DO loops, OUTPUT", "explode / array columns / union of frames"],
    ["Formats, char vs numeric, length", "explicit cast & Spark types"],
  ];
  const cols = 2, cw = 5.95, ch = 1.32, gx = 0.2, gy = 0.18, x0 = 0.62, y0 = 1.75;
  map.forEach((m, i) => {
    const col = i % cols, row = Math.floor(i / cols);
    const x = x0 + col * (cw + gx), y = y0 + row * (ch + gy);
    s.addShape(pres.shapes.RECTANGLE, { x, y, w: cw, h: ch, fill: { color: CARD }, shadow: mkShadow() });
    // SAS chip
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: x + 0.25, y: y + 0.2, w: 0.9, h: 0.34, fill: { color: AMBER }, rectRadius: 0.17 });
    s.addText("SAS", { x: x + 0.25, y: y + 0.2, w: 0.9, h: 0.34, fontFace: HF, fontSize: 11, bold: true, color: "2A1500", align: "center", valign: "middle", margin: 0 });
    s.addText(m[0], { x: x + 1.3, y: y + 0.16, w: cw - 1.55, h: 0.45, fontFace: HF, fontSize: 14, bold: true, color: INK, valign: "middle", margin: 0 });
    s.addText([
      { text: "→  ", options: { color: TEAL, bold: true, fontSize: 14 } },
      { text: m[1], options: { color: "12424A", fontSize: 13 } },
    ], { x: x + 0.25, y: y + 0.68, w: cw - 0.5, h: 0.5, fontFace: BF, valign: "middle", margin: 0 });
  });

  footer(s, false);
}

// =====================================================================
// SLIDE 10 — TECH STACK (light, labeled cards)
// =====================================================================
{
  const s = pres.addSlide();
  s.background = { color: LIGHT };
  titleBlock(s, "Tech stack", "Suggested implementation stack");

  const stack = [
    ["Target / runtime", "PySpark", "Spark DataFrame API + SparkSession", TEAL],
    ["Orchestration", "LangGraph", "keep it", AMBER],
    ["SQL execution", "Spark SQL", "native to PySpark — no separate engine", TEAL],
    ["Read golden data", "pyreadstat · pandas.read_sas", "load SAS .sas7bdat for diff testing", PANEL],
    ["Static eval", "ruff · mypy · pytest", "SparkSession fixture for unit runs", AMBER],
  ];
  // 2 columns x up to 3 rows
  const cols = 2, cw = 5.95, ch = 1.5, gx = 0.2, gy = 0.2, x0 = 0.62, y0 = 1.75;
  stack.forEach((st, i) => {
    const col = i % cols, row = Math.floor(i / cols);
    const x = x0 + col * (cw + gx), y = y0 + row * (ch + gy);
    s.addShape(pres.shapes.RECTANGLE, { x, y, w: cw, h: ch, fill: { color: CARD }, shadow: mkShadow() });
    s.addShape(pres.shapes.RECTANGLE, { x, y, w: 0.09, h: ch, fill: { color: st[3] } });
    s.addText(st[0].toUpperCase(), { x: x + 0.32, y: y + 0.2, w: cw - 0.6, h: 0.3, fontFace: BF, fontSize: 11, bold: true, color: MUTE, charSpacing: 2, margin: 0 });
    s.addText(st[1], { x: x + 0.32, y: y + 0.5, w: cw - 0.6, h: 0.5, fontFace: HF, fontSize: 19, bold: true, color: INK, valign: "middle", margin: 0 });
    s.addText(st[2], { x: x + 0.32, y: y + 1.02, w: cw - 0.6, h: 0.4, fontFace: BF, fontSize: 12.5, italic: true, color: "47596B", valign: "middle", margin: 0 });
  });

  footer(s, false);
}

// =====================================================================
// SLIDE 11 — OPEN DECISIONS (dark, closing)
// =====================================================================
{
  const s = pres.addSlide();
  s.background = { color: BG_DARK };
  s.addShape(pres.shapes.OVAL, { x: -2.2, y: 4.6, w: 5.6, h: 5.6, fill: { type: "none" }, line: { color: "1E3C5A", width: 1.5 } });

  s.addText("OPEN DECISIONS", { x: 0.62, y: 0.55, w: 11, h: 0.3, fontFace: BF, fontSize: 12, bold: true, color: MINT, charSpacing: 3, margin: 0 });
  s.addText("Still to be decided", { x: 0.6, y: 0.9, w: 12, h: 0.8, fontFace: HF, fontSize: 30, bold: true, color: LIGHT, margin: 0 });

  const qs = [
    ["Spark execution mode", "Local single-machine vs cluster for the full 25K-LOC pipeline; partition tuning."],
    ["Comparison tolerances", "Float comparison tolerances per domain — risk metrics may need tight ones."],
    ["Value-compare strategy", "Collect to pandas vs in-Spark diff, given dataset sizes."],
    ["Module granularity", "Keep intermediate PySpark modular per step, or fuse steps post-validation."],
  ];
  const cols = 2, cw = 5.95, ch = 1.75, gx = 0.2, gy = 0.25, x0 = 0.62, y0 = 2.05;
  qs.forEach((q, i) => {
    const col = i % cols, row = Math.floor(i / cols);
    const x = x0 + col * (cw + gx), y = y0 + row * (ch + gy);
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: cw, h: ch, fill: { color: PANEL }, line: { color: TEAL_DK, width: 1 }, rectRadius: 0.08, shadow: mkShadow() });
    s.addText("?", { x: x + 0.3, y: y + 0.25, w: 0.7, h: 0.7, fontFace: HF, fontSize: 34, bold: true, color: MINT, margin: 0 });
    s.addText(q[0], { x: x + 1.1, y: y + 0.28, w: cw - 1.35, h: 0.5, fontFace: HF, fontSize: 17, bold: true, color: LIGHT, valign: "middle", margin: 0 });
    s.addText(q[1], { x: x + 1.1, y: y + 0.8, w: cw - 1.35, h: 0.8, fontFace: BF, fontSize: 13, color: "B6C8D8", valign: "top", margin: 0, lineSpacingMultiple: 1.12 });
  });

  footer(s, true);
}

pres.writeFile({ fileName: "C:/SAS2PythonLatest/DESIGN_SAS2Python_v2.pptx" }).then((fn) => {
  console.log("WROTE " + fn);
});
