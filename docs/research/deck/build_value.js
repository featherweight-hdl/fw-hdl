// Builds docs/research/sv-value-over-xls.pptx from sv-value-over-xls.md.
// Same theme and layouts as build_pitch.js (companion deck).
//
//   NODE_PATH=<dir with pptxgenjs, react-icons, react, react-dom, sharp>/node_modules \
//   APPLY_THEME=<pptx skill>/scripts/apply_theme.js \
//     node docs/research/deck/build_value.js

const path = require("path");
const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const L = require("react-icons/lu");

const OUT = path.join(__dirname, "..", "sv-value-over-xls.pptx");

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
pres.title = "Low impact, high value: what SystemVerilog + fw-hdl adds to XLS";
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
    { text: { text: "Low impact, high value: SystemVerilog + fw-hdl + XLS", options: { x: MX, y: 7.0, w: 7, h: 0.3,
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

async function main() {
  // ============================================================ 1. title
  pres.addSection({ title: "Framing" });
  let s = pres.addSlide({ masterName: "TITLE_DARK", sectionTitle: "Framing" });
  s.addText("Low impact, high value", { placeholder: "title" });
  s.addText("What SystemVerilog + fw-hdl adds to XLS, beyond adopting XLS alone",
    { placeholder: "body" });
  await badge(s, MX, 0.9, 0.9, "LuTrendingUp", HEX.accent1, HEX.lt1, "Value");
  s.addNotes("Companion to the commercial pitch. Narrow question: if your team adopted XLS on " +
    "its own, what would you not get, and what would it cost you?");

  // ============================================================ 2. baseline
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Framing" });
  s.addText("Adopting XLS alone: what you get, and what you take on", { placeholder: "title" });
  card(s, MX, 1.45, 4.6, 5.2, C.accent6, "XLS gives you");
  text(s, "XLS gives you", { x: MX + 0.35, y: 1.65, w: 4, h: 0.45, fontSize: 21, bold: true, color: C.accent2 });
  const gives = ["Excellent optimizer and scheduler", "Ready/valid codegen", "DSLX tests in its interpreter and JIT",
    "Quickcheck proofs, IR equivalence", "SVA and $display in the RTL", "Signature and schedule protos"];
  for (let i = 0; i < gives.length; i++) {
    await icon(s, MX + 0.35, 2.3 + i * 0.68, 0.32, "LuCircleCheck", HEX.accent2, "Given");
    text(s, gives[i], { x: MX + 0.85, y: 2.27 + i * 0.68, w: 3.6, h: 0.6, fontSize: 15 });
  }
  card(s, 5.4, 1.45, 7.33, 5.2, C.background2, "XLS leaves you");
  text(s, "…and leaves your team to", { x: 5.75, y: 1.65, w: 6.6, h: 0.45, fontSize: 21, bold: true, color: C.accent5 });
  const leaves = [
    "Learn DSLX and re-express your SV types, constants and helpers",
    "Wait for RTL, or hand-build DPI glue, before the block enters your SoC sim",
    "Hand-wire flat bit-vector ports into your RTL",
    "Maintain two test suites in two languages",
    "Debug RTL with mangled names, no source coverage, FIFOs without depth",
    "Work out timing by hand from IR-node-keyed reports",
    "Build the hand-off yourself: SDC, file lists, docs",
  ];
  for (let i = 0; i < leaves.length; i++) {
    const y = 2.27 + i * 0.6;
    s.addShape(pres.shapes.OVAL, { x: 5.75, y: y + 0.02, w: 0.36, h: 0.36, fill: { color: C.accent5 },
      line: { type: "none" }, objectName: "Num " + i });
    text(s, String(i + 1), { x: 5.75, y: y + 0.02, w: 0.36, h: 0.36, fontSize: 13, bold: true,
      color: C.background1, align: "center", valign: "middle" });
    text(s, leaves[i], { x: 6.3, y, w: 6.2, h: 0.55, fontSize: 15 });
  }
  s.addNotes("Be fair to XLS: it gives a lot. The seven items on the right are the work a team " +
    "takes on every time. Sources: XLS issues #988 (FIFO depth), #1126/#2139 (coverage), " +
    "#2042 (mangled state names).");

  // ============================================================ 3. low impact
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Framing" });
  s.addText("“Low impact”: nothing changes except the XLS binaries", { placeholder: "title" });
  const same = [
    ["LuCode", "Language", "SystemVerilog"],
    ["LuPackage", "Types", "Your existing SV packages"],
    ["LuMonitorPlay", "Simulator & TB", "Your simulator, SVUnit or UVM"],
    ["LuPuzzle", "Integration", "A module in your RTL"],
    ["LuFactory", "Back end", "Fusion / DC / Genus, as today"],
  ];
  for (let i = 0; i < 5; i++) {
    const x = MX + i * 2.45;
    card(s, x, 1.6, 2.25, 3.4, C.background2, "Same " + i);
    await badge(s, x + 0.67, 1.9, 0.9, same[i][0], HEX.accent2, HEX.lt1, same[i][1]);
    text(s, same[i][1], { x: x + 0.1, y: 3.0, w: 2.05, h: 0.45, fontSize: 18, bold: true, align: "center" });
    text(s, same[i][2], { x: x + 0.15, y: 3.5, w: 1.95, h: 0.9, fontSize: 15, color: C.text2, align: "center" });
    text(s, "unchanged", { x: x + 0.1, y: 4.45, w: 2.05, h: 0.35, fontSize: 14, italic: true,
      bold: true, color: C.accent2, align: "center" });
  }
  card(s, MX, 5.35, CW, 1.2, C.accent4, "Only addition");
  await icon(s, MX + 0.35, 5.62, 0.65, "LuDownload", HEX.accent1, "Add");
  text(s, [{ text: "The only addition: ", options: { bold: true } },
           { text: "prebuilt XLS binaries from xlsynth (no Bazel build). Adoption starts with one function." }],
    { x: MX + 1.3, y: 5.35, w: CW - 1.6, h: 1.2, fontSize: 18, valign: "middle" });
  s.addNotes("This is the definition of low impact we hold every value item to: its impact " +
    "on the team's practice is none or low.");

  // ============================================================ 4. value map
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Framing" });
  s.addText("Eleven kinds of value, on top of the same XLS QoR", { placeholder: "title" });
  const vmap = [
    ["V1", "Your SV and types are the source", "LuPackage"], ["V2", "In your SoC sim on day one", "LuPuzzle"],
    ["V3", "Timing from XLS's schedule", "LuTimer"], ["V4", "Fast model proven against RTL", "LuShieldCheck"],
    ["V5", "One test suite, every level", "LuListChecks"], ["V6", "Honest multi-process models", "LuNetwork"],
    ["V7", "Debug in your terms", "LuBug"], ["V8", "Generated verification", "LuTestTube"],
    ["V9", "See the hardware in your source", "LuScanSearch"], ["V10", "Reviewable, safe to upgrade", "LuGitPullRequest"],
    ["V11", "RTL that drops into your back end", "LuFactory"],
  ];
  for (let i = 0; i < 11; i++) {
    const col = i % 4, row = Math.floor(i / 4);
    const x = MX + col * 3.07, y = 1.5 + row * 1.7;
    card(s, x, y, 2.87, 1.5, C.background2, "Map " + vmap[i][0]);
    await badge(s, x + 0.2, y + 0.3, 0.7, vmap[i][2], HEX.accent1, HEX.lt1, vmap[i][0]);
    text(s, vmap[i][0], { x: x + 1.05, y: y + 0.2, w: 1.7, h: 0.35, fontSize: 14, bold: true, color: C.accent1 });
    text(s, vmap[i][1], { x: x + 1.05, y: y + 0.55, w: 1.7, h: 0.85, fontSize: 15, bold: true });
  }
  card(s, MX + 3 * 3.07, 1.5 + 2 * 1.7, 2.87, 1.5, C.text1, "Map impact");
  text(s, "Impact on your practice: none or low, for every item", { x: MX + 3 * 3.07 + 0.25, y: 1.5 + 2 * 1.7,
    w: 2.4, h: 1.5, fontSize: 15, bold: true, color: C.background1, valign: "middle" });
  s.addNotes("The map of the deck. The next slides take them one or two at a time.");

  // ============================================================ 5. V1
  pres.addSection({ title: "The values" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "The values" });
  s.addText("Your existing SV is the source, including your types", { placeholder: "title" });
  await valueFrame(s, "V1", "re-express structs, constants and helpers in DSLX; DSLX becomes the source of truth for your types",
    "none", "✅ functions and packed structs · 🔴 S accept 'logic'");
  card(s, MX, 2.15, 6.1, 4.0, C.background2, "Package code");
  text(s, [
    "package pkt_pkg;     // already in your repo",
    "  typedef struct packed {",
    "    bit [15:0] len;",
    "    bit [7:0]  ttl;",
    "    bit [7:0]  proto;",
    "  } hdr_t;",
    "  localparam int MAX_LEN = 1500;",
    "  function automatic bit [15:0]",
    "      csum(hdr_t h); ... endfunction",
    "endpackage"].join("\n"),
    { x: MX + 0.25, y: 2.35, w: 5.7, h: 3.6, fontSize: 13, fontFace: "Courier New" });
  const uses = [["Your RTL", C.background2], ["Your testbench", C.background2], ["XLS block, via fw-hdl", C.accent6]];
  for (let i = 0; i < 3; i++) {
    const y = 2.25 + i * 1.3;
    arrow(s, MX + 6.1, 4.15, 8.1, y + 0.5, HEX.accent1, "Use arrow " + i);
    box(s, uses[i][0], 8.1, y, 4.63, 1.0, uses[i][1], { bold: i === 2, fontSize: 17 });
  }
  text(s, "One source of truth for all three.",
    { x: 8.1, y: 5.95, w: 4.63, h: 0.4, fontSize: 14, italic: true, color: C.accent1 });
  s.addNotes("xlsynth's dslx2sv-types bridge goes the other way: DSLX to SV packages. That " +
    "makes DSLX the owner of types the RTL already owns. With fw-hdl the RTL's package stays " +
    "the owner. Code here is illustrative.");

  // ============================================================ 6. V2 + V11
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "The values" });
  s.addText("It's just a module, from day one to hand-off", { placeholder: "title" });
  await valueFrame(s, "V2 · V11", "nothing in the SV sim until RTL (or DIY DPI); RTL arrives with flat ports and no hand-off collateral",
    "none", "🟡 bind machinery ✅ · 🔴 S–M shell generator · 🔴 S hand-off bundle");
  card(s, MX, 2.15, 7.4, 4.0, C.background2, "Module");
  text(s, "module pkt_engine  (struct-typed pins: pkt_t pkt_in, _vld, _rdy …)",
    { x: MX + 0.3, y: 2.3, w: 6.8, h: 0.45, fontSize: 15, bold: true, fontFace: "Courier New" });
  const views = [["SV class model", "day 1: behavior, in your SoC sim", C.accent6],
                 ["Timing shell", "from XLS's schedule (V3)", C.background1],
                 ["XLS RTL wrapper", "same pins, for synthesis", C.accent4]];
  for (let i = 0; i < 3; i++) {
    const y = 2.95 + i * 1.0;
    card(s, MX + 0.3, y, 6.8, 0.85, views[i][2], "View " + i, HEX.accent3);
    text(s, views[i][0], { x: MX + 0.55, y, w: 2.6, h: 0.85, fontSize: 17, bold: true, valign: "middle" });
    text(s, views[i][1], { x: MX + 3.2, y, w: 3.8, h: 0.85, fontSize: 15, color: C.text2, valign: "middle" });
  }
  card(s, 8.3, 2.15, 4.43, 4.0, C.text1, "Hand-off");
  text(s, "Hand-off bundle (V11)", { x: 8.6, y: 2.35, w: 3.9, h: 0.45, fontSize: 19, bold: true, color: C.accent4 });
  const ho = ["House reset and flop profile", "Struct-typed RTL wrapper", "SDC stub from the scheduled clock",
    "File lists per view", "Block datasheet, IP-XACT"];
  for (let i = 0; i < ho.length; i++) {
    await icon(s, 8.6, 3.0 + i * 0.6, 0.3, "LuCircleCheck", HEX.accent4, "Bundle item");
    text(s, ho[i], { x: 9.05, y: 2.97 + i * 0.6, w: 3.5, h: 0.5, fontSize: 15, color: C.background1 });
  }
  s.addNotes("Pick a view by file list; the parent RTL and testbench never change. The shell " +
    "is generated from the top class plus an API-to-transactor map (shell-generation.md). " +
    "Worth: the integration wall moves from the end of the block schedule to the start.");

  // ============================================================ 7. V3 + V4
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "The values" });
  s.addText("Timing you can simulate, proven against the RTL", { placeholder: "title" });
  await valueFrame(s, "V3 · V4", "a static schedule report; cycle-accurate execution only in C++ (block JIT), after scheduling",
    "none", "🟡 latency-only ✅ · 🔴 S exact function shell + lockstep · 🔴 M proc shell");
  box(s, "XLS signature + schedule", MX, 2.3, 2.9, 1.1, C.background2, { bold: true });
  arrow(s, MX + 2.9, 2.85, MX + 3.6, 2.85, HEX.accent1);
  card(s, MX + 3.6, 2.15, 4.4, 1.6, C.accent6, "Timing shell");
  text(s, "Timing shell around the SV class", { x: MX + 3.8, y: 2.25, w: 4.0, h: 0.4, fontSize: 17, bold: true });
  text(s, "latency · II · stage of each send/receive · I/O flop kinds · bubble flow control",
    { x: MX + 3.8, y: 2.7, w: 4.0, h: 0.9, fontSize: 14, color: C.text2 });
  arrow(s, MX + 8.0, 2.85, MX + 8.7, 2.85, HEX.accent1);
  box(s, "Your SoC sim, before RTL", MX + 8.7, 2.3, 3.43, 1.1, C.accent4, { bold: true });
  // lockstep
  text(s, "Lockstep check, every build (V4)", { x: MX, y: 4.0, w: 6, h: 0.4, fontSize: 18, bold: true, color: C.accent2 });
  box(s, "Random valid/ready stimulus", MX, 4.65, 2.9, 1.2, C.background2);
  box(s, "Timing shell", MX + 3.6, 4.5, 2.4, 0.6, C.accent6);
  box(s, "XLS RTL", MX + 3.6, 5.4, 2.4, 0.6, C.accent4);
  arrow(s, MX + 2.9, 5.25, MX + 3.6, 4.8); arrow(s, MX + 2.9, 5.25, MX + 3.6, 5.7);
  arrow(s, MX + 6.0, 4.8, MX + 6.7, 5.25); arrow(s, MX + 6.0, 5.7, MX + 6.7, 5.25);
  box(s, "Compare every pin, every cycle", MX + 6.7, 4.65, 2.8, 1.2, C.text1, { color: C.background1, bold: true });
  card(s, MX + 9.75, 4.1, 2.38, 2.05, C.background2, "Fidelity");
  text(s, [{ text: "Function pipelines: exact", options: { bold: true, breakLine: true } },
           { text: "Procs: stage-level flow control, verified by lockstep", options: { color: C.text2 } }],
    { x: MX + 9.95, y: 4.25, w: 2.0, h: 1.8, fontSize: 14 });
  s.addNotes("Numbers come from the tool that will build the RTL, and the lockstep check turns " +
    "'cycle-accurate' into a test result. It's also the regression guard when XLS is upgraded. " +
    "Today's StageTLM was cycle-exact with XLS RTL on AES (32 ops in 128 clocks) and 2.8-4.7x " +
    "faster than RTL.");

  // ============================================================ 8. V5
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "The values" });
  s.addText("One test suite, every level", { placeholder: "title" });
  await valueFrame(s, "V5", "DSLX tests and RTL tests are separate artifacts, in separate languages",
    "none", "✅ SVUnit on 11 XLS examples · 🔴 UVM via the shell (follows V2)");
  card(s, MX, 3.2, 3.0, 1.5, C.text1, "Test file");
  await icon(s, MX + 0.3, 3.55, 0.8, "LuListChecks", HEX.accent4, "Test");
  text(s, "your_test.sv\nunedited", { x: MX + 1.25, y: 3.2, w: 1.7, h: 1.5, fontSize: 17, bold: true,
    color: C.background1, valign: "middle" });
  const lv = ["SV class model", "Timing shell", "XLS RTL", "Gate netlists"];
  for (let i = 0; i < 4; i++) {
    const y = 2.2 + i * 1.0;
    box(s, lv[i], 4.7, y, 3.0, 0.75, i === 1 ? C.accent6 : C.background2);
    arrow(s, MX + 3.0, 3.95, 4.7, y + 0.37);
    await icon(s, 7.85, y + 0.18, 0.4, "LuCircleCheck", HEX.accent2, "Pass");
  }
  card(s, 8.8, 2.2, 3.93, 3.95, C.accent4, "Evidence");
  text(s, "11", { x: 9.1, y: 2.35, w: 3.4, h: 1.0, fontSize: 60, bold: true, color: C.accent1, fontFace: THEME.headFontFace });
  text(s, "XLS examples pass with a byte-identical test file at every level today.",
    { x: 9.1, y: 3.4, w: 3.4, h: 1.0, fontSize: 15 });
  text(s, "A gate-level failure reproduces at model level in milliseconds: same test, same message.",
    { x: 9.1, y: 4.55, w: 3.4, h: 1.4, fontSize: 15, italic: true, color: C.text2 });
  s.addNotes("Through the shell's pins, the team's own UVM environment works the same way.");

  // ============================================================ 9. V6
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "The values" });
  s.addText("Multi-process designs that are honest before RTL", { placeholder: "title" });
  await valueFrame(s, "V6", "the proc runtime ignores FIFO depth (XLS #988): deadlocks and throughput collapse first appear in RTL",
    "none", "✅ depth-accurate model · 🔴 M FIFO-sizing sweep");
  const nets = [["XLS proc simulation", "unbounded queue", "Deadlock hidden until RTL", C.background2, C.accent5, "LuCircleDashed", HEX.accent5],
                ["fw-hdl SV model", "fw_channel#(T,2)", "Deadlocks in the model, with an SV call stack", C.accent6, C.accent2, "LuCircleCheck", HEX.accent2]];
  for (let i = 0; i < 2; i++) {
    const y = 2.2 + i * 1.75;
    card(s, MX, y, 7.6, 1.55, nets[i][3], "Net " + i);
    text(s, nets[i][0], { x: MX + 0.25, y: y + 0.1, w: 4, h: 0.4, fontSize: 16, bold: true, color: nets[i][4] });
    box(s, "producer", MX + 0.25, y + 0.65, 1.6, 0.65, C.background1);
    arrow(s, MX + 1.85, y + 0.97, MX + 2.3, y + 0.97);
    box(s, nets[i][1], MX + 2.3, y + 0.65, 2.1, 0.65, C.background1, { fontFace: "Courier New", fontSize: 12 });
    arrow(s, MX + 4.4, y + 0.97, MX + 4.85, y + 0.97);
    box(s, "consumer", MX + 4.85, y + 0.65, 1.6, 0.65, C.background1);
    await icon(s, MX + 6.85, y + 0.75, 0.45, nets[i][5], nets[i][6], "Outcome");
    text(s, nets[i][2], { x: MX + 0.25 + 4.0, y: y + 0.1, w: 3.2, h: 0.4, fontSize: 14, italic: true, color: nets[i][4], align: "right" });
  }
  card(s, 8.5, 2.2, 4.23, 3.3, C.text1, "Sizing sweep");
  text(s, "FIFO-sizing sweep", { x: 8.8, y: 2.4, w: 3.7, h: 0.45, fontSize: 19, bold: true, color: C.accent4 });
  text(s, [{ text: "Over a network of timing shells, report per channel:", options: { breakLine: true, paraSpaceAfter: 8 } },
           { text: "the minimum depth that avoids deadlock", options: { bullet: true, breakLine: true } },
           { text: "the depth needed for full throughput", options: { bullet: true } }],
    { x: 8.8, y: 3.0, w: 3.7, h: 2.3, fontSize: 15, color: C.background1 });
  s.addNotes("The most expensive class of late HLS bug, found at the cheapest point.");

  // ============================================================ 10. V7
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "The values" });
  s.addText("Debug in the designer's own terms", { placeholder: "title" });
  await valueFrame(s, "V7", "generated RTL with mangled state names (#2042); traces and channel views only in XLS's tools",
    "none to low (a plusarg, a script)", "🟡 SV-line annotation wired, verify · 🔴 S–M the rest");
  const flow = [["LuTriangleAlert", "Failure in the full-chip RTL sim"],
                ["LuActivity", "Transactions recorded on every channel"],
                ["LuScanSearch", "First divergence: channel, transaction, activation"],
                ["LuRewind", "Replay into the SV model: ms, SV debugger"]];
  for (let i = 0; i < 4; i++) {
    const x = MX + i * 3.1;
    await badge(s, x + 1.0, 2.2, 0.85, flow[i][0], i === 0 ? HEX.accent5 : HEX.accent1, HEX.lt1, flow[i][1]);
    text(s, flow[i][1], { x: x + 0.1, y: 3.2, w: 2.7, h: 0.9, fontSize: 16, bold: true, align: "center" });
    if (i < 3) arrow(s, x + 2.0, 2.62, x + 4.0, 2.62, HEX.accent3, "Flow " + i);
  }
  const tools = [["SV-line annotations in the generated RTL", "LuFileCode"],
                 ["Waveform aliases: XLS registers → SV variables and stages", "LuWaves"],
                 ["Same transaction view at model, timed, RTL and gates", "LuLayers"]];
  for (let i = 0; i < 3; i++) {
    const x = MX + i * 4.1;
    card(s, x, 4.45, 3.9, 1.65, C.background2, "Debug tool " + i);
    await icon(s, x + 0.25, 4.7, 0.5, tools[i][1], HEX.accent2, "Debug tool");
    text(s, tools[i][0], { x: x + 0.95, y: 4.6, w: 2.8, h: 1.35, fontSize: 15, valign: "middle" });
  }
  s.addNotes("The divergence finder is exact for blocking designs: results don't depend on " +
    "timing, so per-channel streams are comparable between any two runs. This is where HLS " +
    "teams lose the most time.");

  // ============================================================ 11. V8
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "The values" });
  s.addText("Verification collateral, generated, with the class as reference", { placeholder: "title" });
  await valueFrame(s, "V8", "asserts and covers carried into RTL, and nothing else for the testbench; no coverage above RTL",
    "none (generated files DV may adopt)", "🟡 SVUnit API ✅ · 🔴 S SVA · 🔴 M UVM, coverage");
  card(s, 4.9, 3.35, 3.55, 1.45, C.text1, "Hub");
  text(s, "Pin contract\n(shell.json)", { x: 4.9, y: 3.35, w: 3.55, h: 1.45, fontSize: 19, bold: true,
    color: C.background1, align: "center", valign: "middle" });
  const spokes = [["Ready/valid protocol SVA on every channel", MX, 2.15],
                  ["Typed UVM agents (driver, monitor, sequencer)", MX, 4.95],
                  ["Functional coverage of struct fields and branches", 8.95, 2.15],
                  ["Scoreboard predicting from the SV class itself", 8.95, 4.95]];
  for (const [t, x, y] of spokes) {
    box(s, t, x, y, 3.78, 1.2, C.background2, { fontSize: 15 });
    arrow(s, x < 4 ? 4.9 : 8.45, y < 3 ? 3.45 : 4.7, x < 4 ? x + 3.78 : x, y + 0.6, HEX.accent1, "Spoke");
  }
  box(s, "SVUnit API: exists today", 4.9, 5.35, 3.55, 0.75, C.accent6, { fontSize: 15, bold: true, color: C.accent2 });
  s.addNotes("DV starts with a working environment and a free reference model. Coverage also " +
    "closes XLS's coverage gaps (#1126, #2139).");

  // ============================================================ 12. V9
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "The values" });
  s.addText("See the hardware in your source", { placeholder: "title" });
  await valueFrame(s, "V9", "schedule and delays keyed by IR node names; nothing maps back to your source",
    "low (an optional budget annotation)", "🔴 S–M · not offered by XLS even for DSLX");
  const rowsCode = [
    ["", "stage", "delay", "  // pkt_csum.sv (illustrative overlay)"],
    ["41", "0", "  92ps", "  hdr = in_.hdr;"],
    ["42", "0", " 310ps", "  sum = hdr.len + hdr.proto;"],
    ["43", "1", " 640ps", "  sum = sum + fold(payload); ◀ critical"],
    ["44", "2", " 180ps", "  out_.csum = ~sum[15:0];"],
    ["45", "2", "   —  ", "  out_q.t.put(out_);"],
  ];
  card(s, MX, 2.15, 8.0, 3.9, C.background2, "Overlay");
  for (let i = 0; i < rowsCode.length; i++) {
    const y = 2.35 + i * 0.58;
    if (i === 3) {
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: MX + 0.15, y: y - 0.04, w: 7.7, h: 0.5, rectRadius: 0.06,
        fill: { color: C.accent4 }, line: { type: "none" }, objectName: "Critical row" });
    }
    const hdr = i === 0;
    text(s, rowsCode[i][0], { x: MX + 0.3, y, w: 0.4, h: 0.45, fontSize: 13, color: C.accent3, fontFace: "Courier New", valign: "middle" });
    text(s, rowsCode[i][1], { x: MX + 0.8, y, w: 0.7, h: 0.45, fontSize: 13, bold: true, color: C.accent2, fontFace: "Courier New", valign: "middle" });
    text(s, rowsCode[i][2], { x: MX + 1.5, y, w: 0.8, h: 0.45, fontSize: 13, color: C.text2, fontFace: "Courier New", valign: "middle" });
    text(s, rowsCode[i][3], { x: MX + 2.35, y, w: 5.5, h: 0.45, fontSize: 13, fontFace: "Courier New",
      color: hdr ? C.accent3 : C.text1, bold: i === 3, valign: "middle" });
  }
  const side = [["LuRuler", "Width feedback", "count needs 7 of its 32 bits"],
                ["LuEyeOff", "Dead logic", "hdr.ttl never reaches an output"],
                ["LuGauge", "Budget check", "latency ≤ 4, II = 1: met"]];
  for (let i = 0; i < 3; i++) {
    const y = 2.15 + i * 1.33;
    card(s, 8.85, y, 3.88, 1.17, C.accent6, "Side " + i);
    await icon(s, 9.05, y + 0.32, 0.5, side[i][0], HEX.accent2, side[i][1]);
    text(s, side[i][1], { x: 9.75, y: y + 0.12, w: 2.85, h: 0.4, fontSize: 16, bold: true });
    text(s, side[i][2], { x: 9.75, y: y + 0.52, w: 2.85, h: 0.55, fontSize: 14, color: C.text2 });
  }
  s.addNotes("Illustrative mock-up. The data exists: XLS IR carries SV source positions " +
    "(fw-hdl emits pos=), and the schedule gives each node's stage and delay. Budgets stop " +
    "silent regressions.");

  // ============================================================ 13. V10
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "The values" });
  s.addText("HLS changes you can review, XLS upgrades you can trust", { placeholder: "title" });
  await valueFrame(s, "V10", "a one-line source change can reshuffle the RTL invisibly; a new XLS release is a leap of faith",
    "none (CI)", "🔴 S each");
  const prs = [["LuGitPullRequest", "On every pull request", ["pkt_engine: stages 3 → 4 (+1)", "area estimate +3%",
      "critical path now pkt_csum.sv:43"], C.background2],
    ["LuShieldCheck", "On every XLS upgrade", ["new xlsynth release vs block corpus", "QoR within threshold on every block",
      "lockstep check passes"], C.accent6]];
  for (let i = 0; i < 2; i++) {
    const x = MX + i * 6.15;
    card(s, x, 2.15, 5.95, 3.95, prs[i][3], "PR " + i);
    await badge(s, x + 0.3, 2.4, 0.8, prs[i][0], HEX.accent1, HEX.lt1, prs[i][1]);
    text(s, prs[i][1], { x: x + 1.3, y: 2.4, w: 4.4, h: 0.8, fontSize: 20, bold: true, valign: "middle" });
    for (let j = 0; j < 3; j++) {
      await icon(s, x + 0.45, 3.55 + j * 0.75, 0.3, "LuChevronRight", HEX.accent1, "Item");
      text(s, prs[i][2][j], { x: x + 0.95, y: 3.48 + j * 0.75, w: 4.8, h: 0.5, fontSize: 16,
        fontFace: i === 0 ? "Courier New" : THEME.bodyFontFace });
    }
  }
  s.addNotes("These remove the two main organizational objections to HLS: changes nobody can " +
    "review, and tool-version risk. The PR comment content is illustrative.");

  // ============================================================ 14. matrix
  pres.addSection({ title: "Plan" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Plan" });
  s.addText("Every item: high value, none or low impact", { placeholder: "title" });
  const hdr = (t) => ({ text: t, options: { bold: true, color: C.background1, fill: { color: C.text1 }, fontSize: 14 } });
  const mrows = [
    ["V1", "Your SV and types are the source", "none", "✅ / 🔴 S logic"],
    ["V2", "In your SoC sim on day one", "none", "🔴 S–M"],
    ["V3", "Timing from XLS's schedule", "none", "🟡 / 🔴 S–M"],
    ["V4", "Fast model proven against RTL", "none", "🔴 S"],
    ["V5", "One test suite, every level", "none", "✅"],
    ["V6", "Honest multi-process models", "none", "✅ / 🔴 M sizing"],
    ["V7", "Debug in your terms", "none–low", "🟡 / 🔴 S–M"],
    ["V8", "Generated verification", "none", "🟡 / 🔴 S–M"],
    ["V9", "See the hardware in your source", "low", "🔴 S–M"],
    ["V10", "Reviewable, safe to upgrade", "none", "🔴 S"],
    ["V11", "RTL that drops into your back end", "none", "🟡 / 🔴 S"],
  ];
  const mt = [[hdr(""), hdr("Value"), hdr("Impact on you"), hdr("Status")]].concat(mrows.map((r, i) =>
    r.map((c, j) => ({ text: c, options: { fontSize: 14, bold: j < 2, color: j === 0 ? C.accent1 : (j === 2 ? C.accent2 : C.text1),
      fill: { color: i % 2 ? C.background1 : C.background2 } } }))));
  s.addTable(mt, { x: MX, y: 1.4, w: CW, colW: [0.9, 5.6, 2.4, 3.23], rowH: 0.43,
    border: { type: "solid", pt: 0.5, color: HEX.lt2 }, valign: "middle", margin: [0.03, 0.15, 0.03, 0.15] });
  s.addNotes("✅ exists · 🟡 partial · 🔴 to build, with effort S/M/L.");

  // ============================================================ 15. ladder
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Plan" });
  s.addText("The value ladder: what to lead with", { placeholder: "title" });
  const rungs = [
    ["1", "Nothing to learn", "V1 · V5", "Exists today"],
    ["2", "It's just a module", "V2 · V11", "S–M"],
    ["3", "Real timing, early", "V3 · V4", "S for functions"],
    ["4", "Debug and verify faster", "V7 · V8", "S–M each"],
    ["5", "Engineering you can manage", "V9 · V10", "S each"],
    ["6", "Multi-process without fear", "V6", "M"],
  ];
  for (let i = 0; i < 6; i++) {
    const w = 1.9, x = MX + i * 2.04, h = 2.0 + i * 0.55, y = 6.25 - h;
    card(s, x, y, w, h, i === 0 ? C.accent6 : (i < 3 ? C.accent4 : C.background2), "Rung " + i);
    text(s, rungs[i][0], { x: x + 0.15, y: y + 0.1, w: 1.6, h: 0.6, fontSize: 30, bold: true, color: C.accent1, fontFace: THEME.headFontFace });
    text(s, rungs[i][1], { x: x + 0.15, y: y + 0.7, w: 1.65, h: 0.75, fontSize: 15, bold: true });
    text(s, rungs[i][2], { x: x + 0.15, y: y + h - 0.75, w: 1.65, h: 0.3, fontSize: 13, color: C.text2 });
    text(s, rungs[i][3], { x: x + 0.15, y: y + h - 0.42, w: 1.65, h: 0.3, fontSize: 13, italic: true, bold: true, color: C.accent1 });
  }
  s.addNotes("Rung 1 is demonstrable today. Rungs 2 and 3 are the next build.");

  // ============================================================ 16. next build
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Plan" });
  s.addText("Next build: rungs 1–3 on a real function", { placeholder: "title" });
  const steps = [
    ["LuPackage", "Ready/valid kit in src/std", "Move it from tests/rv_proto and parameterize it on type T (fixed at 32 bits today)"],
    ["LuPuzzle", "Shell generator", "Struct-typed model shell + XLS RTL wrapper + pin-parity check, from the class and an API→transactor map"],
    ["LuTimer", "Function timing shell + lockstep", "Exact, overlapping timing model; proven pin-by-pin against XLS RTL"],
    ["LuFileText", "Block datasheet", "Ports, latency, II, stages, area estimate, critical path"],
  ];
  for (let i = 0; i < 4; i++) {
    const x = MX + i * 3.07;
    card(s, x, 1.55, 2.87, 4.0, C.background2, "Step " + i);
    await badge(s, x + 0.25, 1.8, 0.8, steps[i][0], HEX.accent1, HEX.lt1, steps[i][1]);
    text(s, String(i + 1), { x: x + 2.0, y: 1.8, w: 0.6, h: 0.8, fontSize: 36, bold: true, color: C.accent3,
      align: "right", fontFace: THEME.headFontFace });
    text(s, steps[i][1], { x: x + 0.25, y: 2.8, w: 2.4, h: 0.85, fontSize: 18, bold: true });
    text(s, steps[i][2], { x: x + 0.25, y: 3.7, w: 2.4, h: 1.7, fontSize: 14, color: C.text2 });
  }
  card(s, MX, 5.8, CW, 0.8, C.accent6, "Demo");
  text(s, [{ text: "The demo: ", options: { bold: true } },
           { text: "an SV function in existing RTL; model ↔ timed ↔ XLS RTL by file list, same tests passing, lockstep green, hand-off ready." }],
    { x: MX + 0.3, y: 5.8, w: CW - 0.6, h: 0.8, fontSize: 16, valign: "middle" });
  s.addNotes("The divergence finder (V7) is the cheapest high-impact follow-on.");

  // ============================================================ 17. audiences
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Plan" });
  s.addText("One line per audience", { placeholder: "title" });
  const aud = [
    ["LuPencilRuler", "Designer", "Keep your SV and your types; XLS pipelines it; you see the hardware in your own source."],
    ["LuTestTube", "DV engineer", "The block is in your environment on day one, with generated checkers, a free reference model, and one test at every level."],
    ["LuGauge", "Architect", "Timing numbers in the SoC sim before RTL, from XLS's own schedule, proven against its RTL."],
    ["LuBriefcase", "Manager", "No retraining, reviewable changes, controlled tool upgrades, and adoption that starts with one function."],
  ];
  for (let i = 0; i < 4; i++) {
    const x = MX + (i % 2) * 6.15, y = 1.5 + Math.floor(i / 2) * 2.6;
    card(s, x, y, 5.95, 2.35, i % 3 === 0 ? C.accent6 : C.accent4, "Audience " + i);
    await badge(s, x + 0.3, y + 0.35, 0.85, aud[i][0], HEX.accent1, HEX.lt1, aud[i][1]);
    text(s, aud[i][1], { x: x + 1.4, y: y + 0.35, w: 4.3, h: 0.5, fontSize: 21, bold: true });
    text(s, aud[i][2], { x: x + 1.4, y: y + 0.95, w: 4.3, h: 1.25, fontSize: 16, color: C.text2 });
  }
  s.addNotes("Close the discussion by audience; each line maps to rungs on the ladder.");

  // ============================================================ 18. closing
  s = pres.addSlide({ masterName: "TITLE_DARK", sectionTitle: "Plan" });
  s.addText("Same XLS QoR. Nothing new to learn. Everything around it automated.", { placeholder: "title" });
  s.addText("SystemVerilog as the low-impact entry point to XLS.", { placeholder: "body" });
  await badge(s, MX, 0.9, 0.9, "LuZap", HEX.accent1, HEX.lt1, "Spark");

  await pres.writeFile({ fileName: OUT });
  if (process.env.APPLY_THEME) {
    const { applyTheme } = require(process.env.APPLY_THEME);
    await applyTheme(OUT, THEME);
  }
  console.log("wrote " + OUT);
}

main().catch((e) => { console.error(e); process.exit(1); });
