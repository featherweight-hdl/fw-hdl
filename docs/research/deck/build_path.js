// Builds docs/research/fw-hdl-adoption-path.pptx: fw-hdl as the SV->XLS adoption path.
// Same theme and layouts as build_pitch.js (companion deck).
//
//   NODE_PATH=<dir with pptxgenjs, react-icons, react, react-dom, sharp>/node_modules \
//   APPLY_THEME=<pptx skill>/scripts/apply_theme.js \
//     node docs/research/deck/build_path.js

const path = require("path");
const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const L = require("react-icons/lu");

const OUT = path.join(__dirname, "..", "fw-hdl-adoption-path.pptx");

const THEME = {
  name: "fw-hdl Copper",
  headFontFace: "Cambria",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "1E2A30", lt1: "FFFFFF", dk2: "34444C", lt2: "EEF1F2",
    accent1: "C8702E", accent2: "2A7F7A", accent3: "8A9BA3",
    accent4: "F3DCC6", accent5: "A8423A", accent6: "D7ECEA",
    hlink: "2A7F7A", folHlink: "8A9BA3",
  },
};
const HEX = THEME.colors;

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.title = "fw-hdl: the SystemVerilog to XLS adoption path";
pres.author = "Matthew Ballance";
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
const C = pres.SchemeColor;
const W = 13.333, MX = 0.6, CW = W - 2 * MX;

// ---------------------------------------------------------------- layouts
pres.defineSlideMaster({
  title: "TITLE_DARK",
  background: { color: C.text1 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: MX, y: 2.0, w: 11.5, h: 2.0,
        fontSize: 44, bold: true, color: C.background1, valign: "bottom", align: "left", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: MX, y: 4.3, w: 11.5, h: 1.2,
        fontSize: 20, color: C.accent4, valign: "top", margin: 0 }, text: "" } },
  ],
});
pres.defineSlideMaster({
  title: "CONTENT",
  background: { color: C.background1 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: MX, y: 0.35, w: CW, h: 0.9,
        fontSize: 32, bold: true, color: C.text1, valign: "middle", align: "left", margin: 0 }, text: "" } },
    { text: { text: "fw-hdl: the SV → XLS adoption path", options: { x: MX, y: 7.0, w: 7, h: 0.3,
        fontSize: 10, color: C.accent3, margin: 0 } } },
  ],
  slideNumber: { x: 12.2, y: 7.0, w: 0.5, h: 0.3, fontSize: 10, color: C.accent3, align: "right" },
});

// ---------------------------------------------------------------- helpers
async function iconPng(name, hex) {
  const svg = ReactDOMServer.renderToStaticMarkup(
    React.createElement(L[name], { color: "#" + hex, size: 256 }));
  const buf = await sharp(Buffer.from(svg)).png().toBuffer();
  return "image/png;base64," + buf.toString("base64");
}
async function badge(slide, x, y, d, icon, fill, iconHex, name) {
  slide.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: fill },
    line: { type: "none" }, objectName: name + " circle" });
  const pad = d * 0.24;
  slide.addImage({ data: await iconPng(icon, iconHex), x: x + pad, y: y + pad,
    w: d - 2 * pad, h: d - 2 * pad, altText: name, objectName: name + " icon" });
}
async function icon(slide, x, y, d, name, hex, alt) {
  slide.addImage({ data: await iconPng(name, hex), x, y, w: d, h: d, altText: alt,
    objectName: alt + " " + x.toFixed(2) + "," + y.toFixed(2) });
}
function card(slide, x, y, w, h, fill, name, line) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.12,
    fill: { color: fill }, line: line ? { color: line, width: 1 } : { type: "none" }, objectName: name });
}
function text(slide, t, opts) {
  slide.addText(t, Object.assign({ isTextBox: true, margin: 0, fontSize: 16,
    color: C.text1, valign: "top" }, opts));
}
function box(slide, t, x, y, w, h, fill, opts) {
  card(slide, x, y, w, h, fill, "Box " + t.slice(0, 20));
  text(slide, t, Object.assign({ x: x + 0.12, y, w: w - 0.24, h, align: "center", valign: "middle",
    fontSize: 15 }, opts || {}));
}
function arrow(slide, x1, y1, x2, y2, color, name) {
  slide.addShape(pres.shapes.LINE, { x: Math.min(x1, x2), y: Math.min(y1, y2),
    w: Math.abs(x2 - x1), h: Math.abs(y2 - y1), flipH: x2 < x1, flipV: y2 < y1,
    line: { color: color || HEX.accent3, width: 2, endArrowType: "triangle" }, objectName: name || "Arrow" });
}
function pill(slide, t, x, y, w, fill, color) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h: 0.38, rectRadius: 0.19,
    fill: { color: fill }, line: { type: "none" }, objectName: "Pill " + t });
  text(slide, t, { x, y, w, h: 0.38, fontSize: 13, bold: true, color, align: "center", valign: "middle" });
}

// The value-slide frame: a V-tag, the "XLS alone" strip and the impact/status pills.
async function valueFrame(s, tag, xlsAlone, impact, status) {
  pill(s, tag, MX, 1.32, 1.3, C.accent1, C.background1);
  card(s, MX + 1.45, 1.25, CW - 1.45, 0.55, C.background2, "XLS alone strip");
  await icon(s, MX + 1.65, 1.36, 0.33, "LuCircleDashed", HEX.accent5, "XLS alone");
  text(s, [{ text: "XLS alone: ", options: { bold: true, color: C.accent5 } },
           { text: xlsAlone, options: { color: C.text2 } }],
    { x: MX + 2.1, y: 1.25, w: CW - 2.25, h: 0.55, fontSize: 15, valign: "middle" });
  pill(s, "Impact on you: " + impact, MX, 6.42, 3.9, C.accent6, C.accent2);
  pill(s, "Status: " + status, MX + 4.05, 6.42, 6.6, C.accent4, C.accent1);
}

// Shifts every y on a slide by dy (to make room for the "XLS alone" strip).
function shift(slide, dy) {
  const sh = (o) => (o && typeof o.y === "number") ? Object.assign({}, o, { y: o.y + dy }) : o;
  return {
    addText: (t, o) => slide.addText(t, sh(o)),
    addShape: (k, o) => slide.addShape(k, sh(o)),
    addImage: (o) => slide.addImage(sh(o)),
    addChart: (k, d, o) => slide.addChart(k, d, sh(o)),
    addTable: (r, o) => slide.addTable(r, sh(o)),
    addNotes: (n) => slide.addNotes(n),
  };
}
// The "XLS alone" contrast strip under a pillar slide's title; returns the shifted slide.
async function xlsAlone(slide, msg) {
  card(slide, MX, 1.28, CW, 0.5, C.background2, "XLS alone strip");
  await icon(slide, MX + 0.2, 1.37, 0.32, "LuCircleDashed", HEX.accent5, "XLS alone");
  text(slide, [{ text: "XLS alone: ", options: { bold: true, color: C.accent5 } },
               { text: msg, options: { color: C.text2 } }],
    { x: MX + 0.65, y: 1.28, w: CW - 0.8, h: 0.5, fontSize: 15, valign: "middle" });
  return shift(slide, 0.5);
}

async function main() {
  // ============================================================ 1. title
  pres.addSection({ title: "Thesis" });
  let s = pres.addSlide({ masterName: "TITLE_DARK", sectionTitle: "Thesis" });
  s.addText("fw-hdl: the SV → XLS adoption path", { placeholder: "title" });
  s.addText([{ text: "Adopt XLS without learning a new language: keep writing SystemVerilog, not DSLX.", options: { bold: true, breakLine: true } },
             { text: "A curated, open path to high-level synthesis for Verilog RTL engineers." }], { placeholder: "body" });
  await badge(s, MX, 0.9, 0.9, "LuRoute", HEX.accent1, HEX.lt1, "Path");
  s.addNotes("One sentence: fw-hdl is a ready-to-use package that lets SystemVerilog RTL engineers " +
    "adopt Google's XLS high-level synthesis engine without leaving their language, tools or " +
    "practices.");

  // ============================================================ 2. engine + ring
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Thesis" });
  s.addText("XLS is a powerful engine. Everything around it is left to you", { placeholder: "title" });
  const ring = ["Source language", "Behavioral tests", "Signal-level integration", "Reports to source",
    "Multiple views", "RTL debug", "Hand-off"];
  const cx = 4.3, cy = 4.15;
  for (let i = 0; i < ring.length; i++) {
    const a = -Math.PI / 2 + i * 2 * Math.PI / ring.length;
    const x = cx + 2.6 * Math.cos(a) - 1.05, y = cy + 1.95 * Math.sin(a) - 0.3;
    box(s, ring[i], x, y, 2.1, 0.6, C.accent4, { fontSize: 14, bold: true });
  }
  s.addShape(pres.shapes.OVAL, { x: cx - 1.25, y: cy - 1.0, w: 2.5, h: 2.0, fill: { color: C.text1 },
    line: { type: "none" }, objectName: "Engine" });
  text(s, [{ text: "XLS", options: { bold: true, fontSize: 26, breakLine: true, color: C.background1 } },
           { text: "optimize · schedule · codegen", options: { fontSize: 13, color: C.accent4 } }],
    { x: cx - 1.15, y: cy - 1.0, w: 2.3, h: 2.0, align: "center", valign: "middle", fontFace: THEME.headFontFace });
  card(s, 8.4, 1.6, 4.33, 4.95, C.background2, "Thesis text");
  text(s, [
    { text: "The core", options: { bold: true, fontSize: 18, color: C.text1, breakLine: true } },
    { text: "Excellent optimizer and scheduler, validated QoR, focused on producing RTL.",
      options: { fontSize: 15, color: C.text2, breakLine: true, paraSpaceAfter: 14 } },
    { text: "The ring", options: { bold: true, fontSize: 18, color: C.accent1, breakLine: true } },
    { text: "Language, testing, integration, reports, views, debug and hand-off are an exercise for the user.",
      options: { fontSize: 15, color: C.text2, breakLine: true, paraSpaceAfter: 14 } },
    { text: "fw-hdl is the ring", options: { bold: true, fontSize: 18, color: C.accent2, breakLine: true } },
    { text: "A ready-to-use package that makes SV engineers productive with XLS immediately.",
      options: { fontSize: 15, color: C.text2 } },
  ], { x: 8.7, y: 1.85, w: 3.8, h: 4.5 });
  s.addNotes("We don't compete with the engine. We take XLS as it is and supply everything a " +
    "Verilog team needs around it.");

  // ============================================================ 3. before synthesis
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Thesis" });
  s.addText("Our value is everything before RTL goes to synthesis", { placeholder: "title" });
  card(s, 0.45, 1.5, 10.0, 4.35, C.accent6, "fw-hdl span");
  const steps = [["LuCode", "Write", "in SV, not DSLX"], ["LuTestTube", "Test", "behaviorally"],
    ["LuPuzzle", "Integrate", "at signal level"], ["LuScanSearch", "Understand", "via reports"],
    ["LuLayers", "Simulate", "the right view"], ["LuBug", "Debug", "the RTL"]];
  for (let i = 0; i < 6; i++) {
    const x = MX + i * 1.64;
    await badge(s, x + 0.38, 1.8, 0.8, steps[i][0], HEX.accent2, HEX.lt1, steps[i][1]);
    card(s, x, 2.85, 1.52, 1.5, C.background1, "Step " + i);
    text(s, steps[i][1], { x, y: 3.0, w: 1.52, h: 0.45, fontSize: 17, bold: true, align: "center" });
    text(s, steps[i][2], { x: x + 0.05, y: 3.45, w: 1.42, h: 0.75, fontSize: 14, color: C.text2, align: "center" });
    if (i < 5) arrow(s, x + 1.52, 3.6, x + 1.64, 3.6, HEX.accent3, "Step arrow");
  }
  arrow(s, 10.45, 3.6, 10.75, 3.6, HEX.accent1, "To synth");
  card(s, 10.75, 2.65, 1.98, 1.9, C.text1, "Synthesis");
  text(s, "Synthesis\nXLS → your back end", { x: 10.85, y: 2.65, w: 1.78, h: 1.9, fontSize: 15, bold: true,
    color: C.background1, align: "center", valign: "middle" });
  text(s, "fw-hdl: integration and automation around the engine", { x: 0.75, y: 4.75, w: 9.5, h: 0.5,
    fontSize: 18, bold: true, color: C.accent2 });
  text(s, "XLS does the synthesis. fw-hdl makes the weeks before it productive, and the RTL that comes out debuggable.",
    { x: MX, y: 6.05, w: CW, h: 0.6, fontSize: 16, italic: true, color: C.accent1 });
  s.addNotes("The point: " +
    "most HLS adoption pain is not in the engine, it's in this span.");

  // ============================================================ 4. six pillars
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Thesis" });
  s.addText("The adoption path, in six parts", { placeholder: "title" });
  const pillars = [
    ["LuCode", "Keep your source language", "SystemVerilog classes and functions, your packages and types. No DSLX, no C++."],
    ["LuTestTube", "Test at the behavioral level", "SVUnit at the task/function level; the same test at model, RTL and gates."],
    ["LuPuzzle", "Automatic signal-level connection", "Generated shells put the class behind the final ready/valid pins."],
    ["LuScanSearch", "Reports connected to source", "Stages, critical path and widths shown on your SV lines."],
    ["LuLayers", "Multiple views, same pins", "Untimed, timed from XLS's schedule, staged, RTL. Swap per block."],
    ["LuBug", "Much better RTL debug", "Generated monitors, transaction views, divergence finder, replay."],
  ];
  for (let i = 0; i < 6; i++) {
    const x = MX + (i % 3) * 4.1, y = 1.5 + Math.floor(i / 3) * 2.6;
    card(s, x, y, 3.85, 2.4, i % 2 ? C.accent6 : C.accent4, "Pillar " + i);
    await badge(s, x + 0.25, y + 0.3, 0.75, pillars[i][0], HEX.accent1, HEX.lt1, pillars[i][1]);
    text(s, String(i + 1), { x: x + 3.1, y: y + 0.25, w: 0.5, h: 0.6, fontSize: 28, bold: true,
      color: C.accent3, align: "right", fontFace: THEME.headFontFace });
    text(s, pillars[i][1], { x: x + 1.2, y: y + 0.3, w: 1.95, h: 0.8, fontSize: 16, bold: true, valign: "middle" });
    text(s, pillars[i][2], { x: x + 0.25, y: y + 1.25, w: 3.35, h: 1.05, fontSize: 14, color: C.text2 });
  }
  s.addNotes("The next six slides take one part each.");

  // ============================================================ 5. pillar 1
  pres.addSection({ title: "The path" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "The path" });
  s.addText("1 · Keep your source language, and compose like software", { placeholder: "title" });
  s = await xlsAlone(s, "learn DSLX (or C++ via xlscc), re-express your SV types, and compose procs with spawn inside config blocks");
  card(s, MX, 1.5, 6.6, 4.4, C.background2, "Composition code");
  text(s, "A two-process network, as written in examples/xls/rle", { x: MX + 0.25, y: 1.62, w: 6.1, h: 0.35,
    fontSize: 13, italic: true, color: C.accent3 });
  text(s, [
    "class rle_loopback extends fw_component;",
    "  fw_port #(fw_get_if #(EncInData))  input_r;",
    "  fw_port #(fw_put_if #(DecOutData)) output_s;",
    "  RunLengthEncoder32 enc;",
    "  RunLengthDecoder32 dec;",
    "  fw_channel #(EncOutData, 0) compressed;",
    "",
    "  function void connect();",
    "    enc.input_r.connect(input_r);",
    "    enc.output_s.connect(compressed.put_ex);",
    "    dec.input_r.connect(compressed.get_ex);",
    "    dec.output_s.connect(output_s);",
    "  endfunction",
    "endclass"].join("\n"),
    { x: MX + 0.25, y: 2.05, w: 6.2, h: 3.75, fontSize: 13, fontFace: "Courier New" });
  const comp = [["LuPackage", "Your packages, structs and functions, unchanged"],
                ["LuCable", "Ports and exports bound at connect(), no pins"],
                ["LuLayers", "Interface-class APIs: swap implementations behind one contract"],
                ["LuNetwork", "Channels are the architecture: XLS gets the network as written"]];
  for (let i = 0; i < 4; i++) {
    const y = 1.55 + i * 0.95;
    await icon(s, 7.55, y + 0.12, 0.5, comp[i][0], HEX.accent2, comp[i][1]);
    text(s, comp[i][1], { x: 8.25, y, w: 4.45, h: 0.8, fontSize: 15, valign: "middle" });
  }
  card(s, 7.45, 5.4, 5.28, 0.95, C.text1, "QoR");
  text(s, [{ text: "As efficient as hand-written DSLX, sometimes more", options: { bold: true, color: C.accent4, fontSize: 16, breakLine: true } },
           { text: "AES: 6975 vs 6976 XLS IR nodes (SV vs DSLX)", options: { color: C.background1, fontSize: 13 } }],
    { x: 7.7, y: 5.4, w: 4.9, h: 0.95, valign: "middle" });
  s.addNotes("Class-based composition is a differentiator: commercial SV-entry HLS, as shown " +
    "publicly, is module-style. Speed advantage of classes is expected but is being benchmarked; " +
    "don't claim it yet.");

  // ============================================================ 6. pillar 2
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "The path" });
  s.addText("2 · Test at the behavioral level, then at every level", { placeholder: "title" });
  s = await xlsAlone(s, "DSLX tests in XLS's interpreter, then a second, separate SV testbench once RTL exists");
  card(s, MX, 1.5, 5.6, 3.6, C.background2, "Test code");
  text(s, "SVUnit, against the generated API (illustrative)", { x: MX + 0.25, y: 1.62, w: 5.1, h: 0.35,
    fontSize: 13, italic: true, color: C.accent3 });
  text(s, [
    "`SVTEST(encodes_a_run)",
    "  api.input_r_put('{symbol: 'hA5, last: 0});",
    "  api.input_r_put('{symbol: 'hA5, last: 1});",
    "  api.output_s_get(o);",
    "  `FAIL_UNLESS_EQUAL(o.count, 2)",
    "`SVTEST_END"].join("\n"),
    { x: MX + 0.25, y: 2.1, w: 5.2, h: 2.8, fontSize: 14, fontFace: "Courier New" });
  const lv = ["SV class model", "Timing shell", "XLS RTL", "Gate netlists"];
  for (let i = 0; i < 4; i++) {
    const y = 1.5 + i * 0.95;
    box(s, lv[i], 7.0, y, 2.6, 0.72, i === 0 ? C.accent6 : C.background2);
    arrow(s, MX + 5.6, 3.3, 7.0, y + 0.36);
    await icon(s, 9.75, y + 0.16, 0.4, "LuCircleCheck", HEX.accent2, "Pass");
  }
  card(s, 10.4, 1.5, 2.33, 3.6, C.accent4, "Evidence");
  text(s, "11", { x: 10.6, y: 1.65, w: 1.9, h: 0.9, fontSize: 48, bold: true, color: C.accent1, fontFace: THEME.headFontFace });
  text(s, "XLS examples pass, test file byte-identical at every level", { x: 10.6, y: 2.6, w: 1.95, h: 2.3, fontSize: 14 });
  text(s, [{ text: "Unit tests first. ", options: { bold: true } },
           { text: "Designers test functions and tasks in milliseconds at the model level. The same file later checks XLS's RTL and the gates: no second testbench." }],
    { x: MX, y: 5.4, w: CW, h: 1.0, fontSize: 16 });
  s.addNotes("The API is generated from the design's SV: one task per function or per port. " +
    "Exists today (examples/xls/RESULTS.md). The timing-shell level is on the roadmap.");

  // ============================================================ 7. pillar 3
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "The path" });
  s.addText("3 · Automatic connection back to the signal level", { placeholder: "title" });
  s = await xlsAlone(s, "flat bit-vector ports to hand-wire, and nothing to put in your SoC sim until RTL exists");
  box(s, "Top class\n(ports, exports, API types)", MX, 1.7, 3.0, 1.2, C.background2, { bold: true });
  box(s, "API → transactor map\n(kits describe themselves)", MX, 3.3, 3.0, 1.2, C.background2, { bold: true });
  arrow(s, MX + 3.0, 2.3, 4.6, 3.1, HEX.accent1); arrow(s, MX + 3.0, 3.9, 4.6, 3.1, HEX.accent1);
  card(s, 4.6, 2.35, 2.6, 1.5, C.text1, "Generator");
  text(s, "fw.hdl.shell\nGenerate", { x: 4.6, y: 2.35, w: 2.6, h: 1.5, fontSize: 18, bold: true,
    color: C.background1, align: "center", valign: "middle" });
  const outs = [["<top>_shell.sv", "module with struct-typed ready/valid pins, transactors, binds", C.accent6],
                ["shell.json", "pin contract: the same one wraps XLS's RTL", C.accent4],
                ["<top>_tb_shell.sv", "mirror transactors + monitors for a pin-level loopback", C.background2]];
  for (let i = 0; i < 3; i++) {
    const y = 1.5 + i * 1.25;
    arrow(s, 7.2, 3.1, 7.8, y + 0.52, HEX.accent1, "Out " + i);
    card(s, 7.8, y, 4.93, 1.05, outs[i][2], "Out card " + i);
    text(s, outs[i][0], { x: 8.0, y: y + 0.08, w: 4.6, h: 0.4, fontSize: 15, bold: true, fontFace: "Courier New" });
    text(s, outs[i][1], { x: 8.0, y: y + 0.48, w: 4.6, h: 0.5, fontSize: 14, color: C.text2 });
  }
  card(s, MX, 5.4, CW, 0.95, C.accent6, "Shell note");
  text(s, [{ text: "Replaces the hand-written top. ", options: { bold: true } },
           { text: "Instantiate the block in your RTL like any module; switch model ↔ XLS RTL by file list. Works for any fw-hdl design, XLS or not." }],
    { x: MX + 0.3, y: 5.4, w: CW - 0.6, h: 0.95, fontSize: 15, valign: "middle" });
  s.addNotes("Status: bind machinery and the runtime bind map exist; the generator is the " +
    "first build item (S–M). The ready/valid kit must move to src/std and take type T.");

  // ============================================================ 8. pillar 4
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "The path" });
  s.addText("4 · XLS's reports, connected back to your source", { placeholder: "title" });
  s = await xlsAlone(s, "schedule, delays and critical paths keyed by IR node names like add.1432, not your source");
  const rowsCode = [
    ["", "stage", "delay", "// pkt_csum.sv (illustrative)"],
    ["41", "0", " 92ps", "hdr = in_.hdr;"],
    ["42", "0", "310ps", "sum = hdr.len + hdr.proto;"],
    ["43", "1", "640ps", "sum = sum + fold(payload); ◀ critical"],
    ["44", "2", "180ps", "out_.csum = ~sum[15:0];"],
  ];
  card(s, MX, 1.5, 7.6, 3.3, C.background2, "Overlay");
  for (let i = 0; i < rowsCode.length; i++) {
    const y = 1.7 + i * 0.58;
    if (i === 3) s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: MX + 0.15, y: y - 0.04, w: 7.3, h: 0.5,
      rectRadius: 0.06, fill: { color: C.accent4 }, line: { type: "none" }, objectName: "Critical row" });
    text(s, rowsCode[i][0], { x: MX + 0.3, y, w: 0.4, h: 0.45, fontSize: 13, color: C.accent3, fontFace: "Courier New", valign: "middle" });
    text(s, rowsCode[i][1], { x: MX + 0.8, y, w: 0.7, h: 0.45, fontSize: 13, bold: true, color: C.accent2, fontFace: "Courier New", valign: "middle" });
    text(s, rowsCode[i][2], { x: MX + 1.5, y, w: 0.8, h: 0.45, fontSize: 13, color: C.text2, fontFace: "Courier New", valign: "middle" });
    text(s, rowsCode[i][3], { x: MX + 2.4, y, w: 5.0, h: 0.45, fontSize: 13, fontFace: "Courier New",
      color: i === 0 ? C.accent3 : C.text1, bold: i === 3, valign: "middle" });
  }
  const side = [["LuRuler", "Width feedback", "count needs 7 of its 32 bits"],
                ["LuEyeOff", "Dead logic", "hdr.ttl never reaches an output"],
                ["LuGauge", "Budgets", "latency ≤ 4, II = 1: checked every build"]];
  for (let i = 0; i < 3; i++) {
    const y = 1.5 + i * 1.12;
    card(s, 8.45, y, 4.28, 0.98, C.accent6, "Side " + i);
    await icon(s, 8.65, y + 0.24, 0.5, side[i][0], HEX.accent2, side[i][1]);
    text(s, side[i][1], { x: 9.35, y: y + 0.08, w: 3.25, h: 0.4, fontSize: 16, bold: true });
    text(s, side[i][2], { x: 9.35, y: y + 0.48, w: 3.25, h: 0.45, fontSize: 14, color: C.text2 });
  }
  card(s, MX, 5.1, CW, 1.25, C.text1, "PR diff");
  await icon(s, MX + 0.3, 5.42, 0.6, "LuGitPullRequest", HEX.accent4, "PR");
  text(s, [{ text: "On every pull request: ", options: { bold: true, color: C.accent4 } },
           { text: "“pkt_engine: stages 3 → 4, area estimate +3%, critical path now pkt_csum.sv:43”. HLS changes become reviewable.",
             options: { color: C.background1 } }],
    { x: MX + 1.15, y: 5.1, w: CW - 1.4, h: 1.25, fontSize: 16, valign: "middle" });
  s.addNotes("XLS keys its schedule and delays by IR node; fw-hdl already carries SV source " +
    "positions into the IR, so mapping back is mechanical. Mock-up; roadmap item.");

  // ============================================================ 9. pillar 5
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "The path" });
  s.addText("5 · Multiple views, same pins: pick speed or detail per block", { placeholder: "title" });
  s = await xlsAlone(s, "untimed procs (FIFO depth ignored) in XLS's tools, or RTL; nothing timed in between in your SV sim");
  const views = [["Untimed class", "behavior; fastest", C.accent6],
                 ["Timing shell", "latency, II from XLS's schedule", C.accent6],
                 ["Staged TLM", "pipeline structure, stage by stage", C.accent4],
                 ["XLS RTL", "ground truth", C.accent4],
                 ["Gates", "your back end", C.background2]];
  for (let i = 0; i < 5; i++) {
    const y = 1.5 + i * 0.98;
    card(s, MX, y, 4.6, 0.8, views[i][2], "View " + i);
    text(s, views[i][0], { x: MX + 0.25, y, w: 1.9, h: 0.8, fontSize: 16, bold: true, valign: "middle" });
    text(s, views[i][1], { x: MX + 2.15, y, w: 2.35, h: 0.8, fontSize: 13, color: C.text2, valign: "middle" });
  }
  card(s, 5.6, 1.5, 7.13, 4.6, C.background2, "Subsystem");
  text(s, "Subsystem simulation", { x: 5.85, y: 1.65, w: 6.6, h: 0.4, fontSize: 17, bold: true });
  const blocks = [["parser", "timing shell", C.accent6], ["lookup", "timing shell", C.accent6],
                  ["rewriter", "XLS RTL (under test)", C.accent4], ["dma", "your RTL", C.background1]];
  for (let i = 0; i < 4; i++) {
    const x = 5.9 + (i % 2) * 3.4, y = 2.25 + Math.floor(i / 2) * 1.55;
    card(s, x, y, 3.1, 1.25, blocks[i][2], "Block " + i, HEX.accent3);
    text(s, blocks[i][0], { x: x + 0.2, y: y + 0.12, w: 2.7, h: 0.45, fontSize: 16, bold: true, fontFace: "Courier New" });
    text(s, blocks[i][1], { x: x + 0.2, y: y + 0.6, w: 2.7, h: 0.5, fontSize: 14, color: C.text2 });
  }
  text(s, "Swap per block by file list. Each timed view is lockstep-checked against XLS's RTL.",
    { x: 5.85, y: 5.4, w: 6.7, h: 0.6, fontSize: 14, italic: true, color: C.accent1 });
  s.addNotes("Replace RTL with timed TLM at subsystem level for faster simulation, without " +
    "losing timing fidelity: the timing comes from XLS's own schedule, and lockstep proves it. " +
    "Status: latency-only timed model exists; exact function shell + lockstep next; staged TLM " +
    "and proc shells on the roadmap.");

  // ============================================================ 10. pillar 6
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "The path" });
  s.addText("6 · Much better RTL debug, from generated monitors", { placeholder: "title" });
  s = await xlsAlone(s, "debug in terms of cryptic RTL signals like p1_add_1432; channel traces only inside XLS's own tools");
  const tiers = [["LuSquareDashed", "Block boundary", "Every send/receive on the module's channels, decoded with your struct types"],
                 ["LuNetwork", "Internal channels", "Every push/pop on XLS's fifo_<channel> instances, plus occupancy"],
                 ["LuLayers", "Inside the pipeline", "One record per activation: received, state read/written, sent, with SV names"]];
  for (let i = 0; i < 3; i++) {
    const x = MX + i * 4.1;
    card(s, x, 1.5, 3.85, 2.3, C.background2, "Tier " + i);
    await badge(s, x + 0.25, 1.75, 0.7, tiers[i][0], HEX.accent2, HEX.lt1, tiers[i][1]);
    text(s, tiers[i][1], { x: x + 1.1, y: 1.75, w: 2.6, h: 0.7, fontSize: 17, bold: true, valign: "middle" });
    text(s, tiers[i][2], { x: x + 0.25, y: 2.6, w: 3.4, h: 1.1, fontSize: 14, color: C.text2 });
  }
  const flow = [["LuTriangleAlert", "Failure in the SoC RTL sim", HEX.accent5],
                ["LuScanSearch", "Divergence finder: first mismatching transaction", HEX.accent1],
                ["LuRewind", "Replay into the SV model: milliseconds, SV debugger", HEX.accent1]];
  for (let i = 0; i < 3; i++) {
    const x = MX + i * 4.1;
    await badge(s, x + 0.2, 4.35, 0.75, flow[i][0], flow[i][2], HEX.lt1, flow[i][1]);
    text(s, flow[i][1], { x: x + 1.1, y: 4.3, w: 2.75, h: 0.85, fontSize: 15, bold: true, valign: "middle" });
    if (i < 2) arrow(s, x + 3.85, 4.72, x + 4.1, 4.72, HEX.accent3, "Debug flow");
  }
  card(s, MX, 5.55, CW, 0.85, C.accent6, "Debug note");
  text(s, "Generated from XLS's signature and block IR every build, bound in with SV bind: no edits to the RTL, works in any simulator.",
    { x: MX + 0.3, y: 5.55, w: CW - 0.6, h: 0.85, fontSize: 15, valign: "middle" });
  s.addNotes("Kahn determinacy makes per-channel streams comparable between any two runs, so " +
    "the divergence finder is exact for blocking designs. Status: boundary monitors + " +
    "divergence finder are next; internal and per-activation tiers on the roadmap.");

  // ============================================================ 11. under the hood
  pres.addSection({ title: "Proof" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Proof" });
  s.addText("Under the hood: XLS untouched, its artifacts put to work", { placeholder: "title" });
  const chain = [["SV source", C.accent6], ["slang", C.background2], ["zuspec IR", C.background2],
                 ["XLS IR", C.accent4], ["XLS opt · schedule · codegen", C.text1], ["RTL", C.accent4]];
  const cw2 = [1.55, 1.3, 1.6, 1.4, 3.1, 1.3];
  let x0 = MX;
  for (let i = 0; i < chain.length; i++) {
    box(s, chain[i][0], x0, 1.6, cw2[i], 0.85, chain[i][1], { bold: true, fontSize: 15,
      color: i === 4 ? C.background1 : C.text1 });
    if (i < chain.length - 1) arrow(s, x0 + cw2[i], 2.02, x0 + cw2[i] + 0.25, 2.02, HEX.accent3, "Chain");
    x0 += cw2[i] + 0.25;
  }
  text(s, "no DSLX", { x: 3.5, y: 2.5, w: 3.0, h: 0.35, fontSize: 13, italic: true, color: C.accent3, align: "center" });
  const arts = ["signature", "schedule", "block IR"];
  for (let i = 0; i < 3; i++) {
    box(s, arts[i], 7.05 + i * 1.35, 3.25, 1.25, 0.6, C.background2, { fontSize: 13, fontFace: "Courier New" });
    arrow(s, 9.0, 2.45, 7.05 + i * 1.35 + 0.62, 3.25, HEX.accent3, "Artifact " + i);
  }
  arrow(s, 9.0, 3.85, 9.0, 4.3, HEX.accent1, "To fw-hdl");
  card(s, MX, 4.3, CW, 2.0, C.accent6, "fw-hdl uses");
  text(s, "fw-hdl reads XLS's own artifacts back", { x: MX + 0.3, y: 4.42, w: 8, h: 0.4, fontSize: 17, bold: true, color: C.accent2 });
  const uses = ["Shells and pin contract", "Timing shells and staged TLM", "Reports on SV lines", "Monitors and transaction records"];
  for (let i = 0; i < 4; i++) {
    box(s, uses[i], MX + 0.3 + i * 2.95, 5.0, 2.75, 1.0, C.background1, { fontSize: 15, bold: true });
  }
  s.addNotes("Nothing in XLS is modified or forked: we use its optimizer, scheduler and codegen " +
    "as shipped (xlsynth binaries), and build on its signature, schedule and block IR outputs.");

  // ============================================================ 12. QoR proof
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Proof" });
  s.addText("SV is as efficient as hand-written DSLX, and sometimes more", { placeholder: "title" });
  const names = ["CRC-32", "Adler-32", "LFSR", "Prefix sum", "FIR dot", "IDCT (Chen)", "SHA-256", "GCD", "Run-length enc."];
  const ratios = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.055, 0.672];
  s.addChart(pres.charts.BAR, [{ name: "SV / DSLX iCE40 cells", labels: names, values: ratios }], {
    x: MX, y: 1.4, w: 7.6, h: 5.3, barDir: "bar", chartColors: [HEX.accent2],
    showTitle: true, title: "iCE40 cells, SV source ÷ DSLX source (1.00 = identical)",
    titleFontSize: 14, titleColor: HEX.dk2, titleFontFace: "+mn-lt",
    showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "0.00",
    dataLabelFontSize: 12, dataLabelColor: HEX.dk1, dataLabelFontFace: "+mn-lt",
    catAxisLabelColor: HEX.dk2, catAxisLabelFontSize: 13, catAxisLabelFontFace: "+mn-lt", catAxisOrientation: "maxMin",
    valAxisMinVal: 0, valAxisMaxVal: 1.2, valAxisMajorUnit: 0.2, valAxisLabelFormatCode: "0.0",
    valAxisLabelColor: HEX.accent3, valAxisLabelFontSize: 11, valAxisLabelFontFace: "+mn-lt",
    valGridLine: { color: HEX.lt2, size: 0.75 }, catGridLine: { style: "none" }, showLegend: false, barGapWidthPct: 60,
  });
  card(s, 8.7, 1.5, 4.03, 5.1, C.background2, "QoR notes");
  text(s, [
    { text: "Identical on 7 of 9", options: { bold: true, fontSize: 18, breakLine: true } },
    { text: "Ported from the XLS repository. Run-length encoder 33% smaller; GCD the one case slightly larger (+5.5% cells).",
      options: { fontSize: 15, color: C.text2, breakLine: true, paraSpaceAfter: 14 } },
    { text: "AES: 6975 vs 6976 IR nodes", options: { bold: true, fontSize: 18, breakLine: true } },
    { text: "The SV port gives XLS essentially the same design as the DSLX original.",
      options: { fontSize: 15, color: C.text2, breakLine: true, paraSpaceAfter: 14 } },
    { text: "Equivalence checked", options: { bold: true, fontSize: 18, breakLine: true } },
    { text: "XLS's own checker proves SV and DSLX equivalent on most functions.", options: { fontSize: 15, color: C.text2 } },
  ], { x: 9.0, y: 1.75, w: 3.45, h: 4.7 });
  s.addNotes("From examples/xls/RESULTS.md. GCD +5.5%, run-length encoder 33% smaller. " +
    "SHA-256 equivalence partly proved; AES inconclusive (too large).");

  // ============================================================ 13. landscape
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Proof" });
  s.addText("Where fw-hdl sits", { placeholder: "title" });
  const hdr = (t) => ({ text: t, options: { bold: true, color: C.background1, fill: { color: C.text1 }, fontSize: 14 } });
  const rows = [
    ["1 · Source language", "DSLX or C++", "C++/SystemC; module-style SV (public)", "SV classes and functions"],
    ["2 · Unit tests reused through gates", "No", "Testbench reuse to RTL", "Yes"],
    ["3 · Model in your SV sim at final pins", "No", "Yes", "Yes (shell generator building)"],
    ["4 · Reports keyed to", "IR node names", "HL↔RTL line correlation", "Your SV lines (building)"],
    ["5 · Schedule-timed model + lockstep", "No", "Not shown publicly", "Yes (building)"],
    ["6 · RTL debug in terms of", "Cryptic RTL signals", "Line annotations, txn waveforms", "Transactions, divergence, replay (building)"],
    ["Engine", "XLS", "Proprietary (some build on XLS)", "XLS, unmodified"],
    ["Open and inspectable", "Engine only", "No", "Engine and flow"],
    ["Cost", "Free", "Commercial license", "Free"],
  ];
  const tb = [[hdr(""), hdr("XLS alone"), hdr("Commercial HLS suites"), hdr("fw-hdl")]].concat(rows.map((r, i) =>
    r.map((c, j) => ({ text: c, options: { fontSize: 14, bold: j === 0 || j === 3, color: j === 3 ? C.accent2 : C.text1,
      fill: { color: i % 2 ? C.background1 : C.background2 } } }))));
  s.addTable(tb, { x: MX, y: 1.4, w: CW, colW: [3.45, 1.95, 3.28, 3.45], rowH: 0.5,
    border: { type: "solid", pt: 0.5, color: HEX.lt2 }, valign: "middle", margin: [0.04, 0.15, 0.04, 0.15] });
  text(s, "Based on public material as of November 2026. We don't claim to be the first SV-entry HLS; we claim the open SV → XLS path.",
    { x: MX, y: 6.55, w: CW, h: 0.35, fontSize: 12, italic: true, color: C.accent3 });
  s.addNotes("Commercial column: Rise Design Automation (SV/C++/SystemC entry, uses XLS IR " +
    "internally, closed), Siemens Catapult and Cadence Stratus (C++/SystemC). Rise publishes no " +
    "code; 'module-style' is from our observation of their material. Details: " +
    "docs/research/market-rise-da.md.");

  // ============================================================ 14. status
  pres.addSection({ title: "Next" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Next" });
  s.addText("What's real today, and what's next", { placeholder: "title" });
  const cols = [
    ["Available today", C.accent6, C.accent2, "LuCircleCheck", HEX.accent2,
      ["SV → XLS at QoR parity (11 examples + AES)", "One test at model, RTL and gates",
       "FIFO-depth-accurate class models", "All-XLS networks to one RTL top", "Latency-only timed model"]],
    ["Building next", C.accent4, C.accent1, "LuHammer", HEX.accent1,
      ["Typed ready/valid kit in src/std", "Shell generator + pin contract", "Exact function timing shell + lockstep",
       "Boundary monitors + divergence finder", "Accept 'logic'; designer coding guide"]],
    ["Roadmap", C.background2, C.text2, "LuMap", HEX.accent3,
      ["Proc timing shell, staged TLM", "Schedule overlay, PR QoR diff", "Generated SVA, UVM agents, coverage",
       "Hand-off bundle: SDC, datasheet", "Class-vs-module speed benchmark"]],
  ];
  for (let c = 0; c < 3; c++) {
    const x = MX + c * 4.1;
    card(s, x, 1.5, 3.85, 5.0, cols[c][1], cols[c][0]);
    text(s, cols[c][0], { x: x + 0.3, y: 1.7, w: 3.3, h: 0.45, fontSize: 20, bold: true, color: cols[c][2] });
    for (let i = 0; i < 5; i++) {
      const y = 2.4 + i * 0.8;
      await icon(s, x + 0.3, y + 0.06, 0.32, cols[c][3], cols[c][4], cols[c][0]);
      text(s, cols[c][5][i], { x: x + 0.8, y, w: 2.85, h: 0.72, fontSize: 14 });
    }
  }
  s.addNotes("Be straight: the signal-level shell, timing shell and monitors are the next " +
    "build, not shipped. The SV→XLS flow, one-test-every-level and QoR parity are real today.");

  // ============================================================ 15. adoption steps
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Next" });
  s.addText("Adopt it one step at a time", { placeholder: "title" });
  const ad = [["LuCode", "One function", "Pull a CRC or round function out of hand RTL. XLS pipelines it; your RTL instantiates it.", "Works today", C.accent6],
              ["LuBoxes", "One block", "A whole block as a class behind its generated shell, in your SoC sim on day one.", "With the shell generator", C.accent4],
              ["LuWorkflow", "A subsystem", "A process network; timed views where you need speed, RTL where you need truth.", "With timing shells", C.background2]];
  for (let i = 0; i < 3; i++) {
    const x = MX + i * 4.1;
    card(s, x, 1.6, 3.6, 4.4, ad[i][4], "Adopt " + i);
    await badge(s, x + 0.3, 1.9, 0.9, ad[i][0], HEX.accent1, HEX.lt1, ad[i][1]);
    text(s, ad[i][1], { x: x + 0.3, y: 3.0, w: 3.0, h: 0.5, fontSize: 21, bold: true });
    text(s, ad[i][2], { x: x + 0.3, y: 3.55, w: 3.0, h: 1.6, fontSize: 15, color: C.text2 });
    text(s, ad[i][3], { x: x + 0.3, y: 5.35, w: 3.0, h: 0.4, fontSize: 14, bold: true, italic: true, color: C.accent1 });
    if (i < 2) arrow(s, x + 3.6, 3.8, x + 4.1, 3.8, HEX.accent1, "Adopt arrow");
  }
  text(s, "Nothing written at an earlier step is rewritten later.", { x: MX, y: 6.25, w: CW, h: 0.4,
    fontSize: 16, italic: true, color: C.accent1 });
  s.addNotes("Lead with the function step: lowest risk, works today.");

  // ============================================================ 16. closing
  s = pres.addSlide({ masterName: "TITLE_DARK", sectionTitle: "Next" });
  s.addText("Keep your SV. Get XLS's QoR. Skip the exercises.", { placeholder: "title" });
  s.addText("fw-hdl, the open SV → XLS adoption path. Next step: a pilot on one function from your design.", { placeholder: "body" });
  await badge(s, MX, 0.9, 0.9, "LuZap", HEX.accent1, HEX.lt1, "Spark");

  await pres.writeFile({ fileName: OUT });
  if (process.env.APPLY_THEME) {
    const { applyTheme } = require(process.env.APPLY_THEME);
    await applyTheme(OUT, THEME);
  }
  console.log("wrote " + OUT);
}

main().catch((e) => { console.error(e); process.exit(1); });
