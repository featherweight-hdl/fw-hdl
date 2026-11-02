// Builds docs/research/pitch-commercial.pptx from the content of pitch-commercial.md.
//
//   NODE_PATH=<dir with pptxgenjs, react-icons, react, react-dom, sharp>/node_modules \
//     node docs/research/deck/build_pitch.js
//
// Then apply the theme (done at the end of this script via apply_theme.js if APPLY_THEME
// points at the pptx skill's scripts/apply_theme.js).

const path = require("path");
const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const L = require("react-icons/lu");

const OUT = path.join(__dirname, "..", "pitch-commercial.pptx");

const THEME = {
  name: "fw-hdl Copper",
  headFontFace: "Cambria",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "1E2A30", // graphite: text, dark slides
    lt1: "FFFFFF",
    dk2: "34444C", // secondary text
    lt2: "EEF1F2", // cool light tint
    accent1: "C8702E", // copper: the accent
    accent2: "2A7F7A", // teal: "fw-hdl / available"
    accent3: "8A9BA3", // slate: muted
    accent4: "F3DCC6", // light copper tint
    accent5: "A8423A", // brick: gaps / problems
    accent6: "D7ECEA", // light teal tint
    hlink: "2A7F7A",
    folHlink: "8A9BA3",
  },
};
const HEX = THEME.colors;

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5
pres.title = "High-level synthesis for RTL teams: SystemVerilog + fw-hdl + XLS";
pres.author = "Matthew Ballance";
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
const C = pres.SchemeColor;

const W = 13.333;
const MX = 0.6; // side margin
const CW = W - 2 * MX; // content width

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
    { text: { text: "SystemVerilog + fw-hdl + XLS", options: { x: MX, y: 7.0, w: 6, h: 0.3,
        fontSize: 10, color: C.accent3, margin: 0 } } },
  ],
  slideNumber: { x: 12.2, y: 7.0, w: 0.5, h: 0.3, fontSize: 10, color: C.accent3, align: "right" },
});
pres.defineSlideMaster({
  title: "CONTENT_DARK",
  background: { color: C.text1 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: MX, y: 0.35, w: CW, h: 0.9,
        fontSize: 32, bold: true, color: C.background1, valign: "middle", align: "left", margin: 0 }, text: "" } },
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

// Icon in a filled circle: the deck's motif.
async function badge(slide, x, y, d, icon, fill, iconHex, name) {
  slide.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: fill },
    line: { type: "none" }, objectName: name + " circle" });
  const pad = d * 0.24;
  slide.addImage({ data: await iconPng(icon, iconHex), x: x + pad, y: y + pad,
    w: d - 2 * pad, h: d - 2 * pad, altText: name, objectName: name + " icon" });
}

function card(slide, x, y, w, h, fill, name) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.12,
    fill: { color: fill }, line: { type: "none" }, objectName: name });
}

function text(slide, t, opts) {
  slide.addText(t, Object.assign({ isTextBox: true, margin: 0, fontSize: 16,
    color: C.text1, valign: "top" }, opts));
}

function arrow(slide, x1, y1, x2, y2, color, name) {
  slide.addShape(pres.shapes.LINE, { x: Math.min(x1, x2), y: Math.min(y1, y2),
    w: Math.abs(x2 - x1), h: Math.abs(y2 - y1), flipH: x2 < x1, flipV: y2 < y1,
    line: { color, width: 2, endArrowType: "triangle" }, objectName: name });
}

async function main() {
  // ============================================================ 1. title
  pres.addSection({ title: "Opening" });
  let s = pres.addSlide({ masterName: "TITLE_DARK", sectionTitle: "Opening" });
  s.addText("Keep writing SystemVerilog. Stop hand-pipelining it.", { placeholder: "title" });
  s.addText("High-level synthesis for RTL teams: SystemVerilog + fw-hdl + XLS",
    { placeholder: "body" });
  await badge(s, MX, 0.9, 0.9, "LuCpu", HEX.accent1, HEX.lt1, "Chip");
  s.addNotes("The one-line pitch: your designers keep writing SystemVerilog; Google's XLS " +
    "compiler does the scheduling and pipelining. fw-hdl is what connects the two.");

  // ============================================================ 2. big idea
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Opening" });
  s.addText("Write in SV, instantiate like RTL, let XLS pipeline it",
    { placeholder: "title" });
  text(s, "Write a block's behavior as SystemVerilog classes and instantiate it in your RTL " +
    "like any other module. Simulate and verify it with your own simulator, testbench and " +
    "waves. Then XLS generates the pipelined RTL behind that same module, with the same " +
    "ports, for your synthesis flow.", { x: MX, y: 1.45, w: CW, h: 1.2, fontSize: 18 });
  const stats = [
    ["0", "lines of DSLX, C++ or DPI glue to write"],
    ["1", "test file, unchanged, from model to gates"],
    ["6975 vs 6976", "AES IR nodes: SV is as efficient as hand-written DSLX"],
  ];
  for (let i = 0; i < 3; i++) {
    const x = MX + i * 4.1;
    card(s, x, 3.1, 3.8, 3.3, C.background2, "Stat card " + (i + 1));
    text(s, stats[i][0], { x: x + 0.3, y: 3.4, w: 3.2, h: 1.3, fontSize: i === 2 ? 40 : 66,
      bold: true, color: C.accent1, valign: "middle", fontFace: THEME.headFontFace });
    text(s, stats[i][1], { x: x + 0.3, y: 4.9, w: 3.2, h: 1.2, fontSize: 16, color: C.text2 });
  }
  s.addNotes("Three numbers to remember. No new language and no glue. One test file that " +
    "runs at every level. And the same XLS QoR: on AES the SV port gives XLS 6975 IR nodes " +
    "against 6976 for the hand-written DSLX.");

  // ============================================================ 3. why HLS stalls
  pres.addSection({ title: "The problem" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "The problem" });
  s.addText("HLS stalls in RTL teams for reasons other than QoR", { placeholder: "title" });
  const stalls = [
    ["LuLanguages", "A new language", "C++ with pragmas, or a new DSL. The people who know the micro-architecture aren't fluent in it."],
    ["LuMonitorPlay", "A model that lives elsewhere", "The HLS source runs in its own simulator. Getting it into the SoC testbench means a hand-written DPI wrapper."],
    ["LuBrickWall", "An integration wall", "The block first meets the chip as generated RTL: the slowest sim, and the latest feedback."],
    ["LuBug", "Debug across a seam", "A failure in generated RTL, with mangled names, has to be reproduced in another tool and language."],
  ];
  for (let i = 0; i < 4; i++) {
    const x = MX + (i % 2) * 6.15, y = 1.55 + Math.floor(i / 2) * 2.65;
    card(s, x, y, 5.95, 2.4, C.background2, "Problem card " + (i + 1));
    await badge(s, x + 0.3, y + 0.35, 0.8, stalls[i][0], HEX.accent5, HEX.lt1, stalls[i][1]);
    text(s, stalls[i][1], { x: x + 1.35, y: y + 0.35, w: 4.3, h: 0.5, fontSize: 20, bold: true });
    text(s, stalls[i][2], { x: x + 1.35, y: y + 0.95, w: 4.3, h: 1.3, fontSize: 15, color: C.text2 });
  }
  s.addNotes("Most RTL teams have tried HLS or decided not to. It is rarely the QoR that " +
    "stops them; it is everything around the compiler.");

  // ============================================================ 4. XLS
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "The problem" });
  s.addText("XLS is a great engine, with the same four problems", { placeholder: "title" });
  const good = ["Excellent QoR from a strong optimizer", "Delay-model-driven scheduling and pipelining",
    "Ready/valid codegen, FIFOs, I/O flop options", "Real formal: equivalence and property proving"];
  const gaps = ["Its language is DSLX", "Pre-RTL simulation runs only in XLS's own tools",
    "The only SystemVerilog it emits is final RTL", "No DPI or transaction-level model output, upstream or in xlsynth"];
  const cols = [["What XLS does brilliantly", good, "LuCircleCheck", HEX.accent2, C.accent6],
                ["What it leaves to you", gaps, "LuCircleDashed", HEX.accent5, C.background2]];
  for (let c = 0; c < 2; c++) {
    const x = MX + c * 6.15;
    card(s, x, 1.55, 5.95, 5.1, cols[c][4], "Column " + (c + 1));
    text(s, cols[c][0], { x: x + 0.4, y: 1.8, w: 5.2, h: 0.5, fontSize: 22, bold: true,
      color: c === 0 ? C.accent2 : C.accent5 });
    for (let i = 0; i < 4; i++) {
      const y = 2.6 + i * 0.95;
      s.addImage({ data: await iconPng(cols[c][2], cols[c][3]), x: x + 0.4, y: y + 0.05,
        w: 0.4, h: 0.4, altText: c === 0 ? "Strength" : "Gap", objectName: `c${c} icon ${i}` });
      text(s, cols[c][1][i], { x: x + 1.0, y, w: 4.6, h: 0.8, fontSize: 17 });
    }
  }
  s.addNotes("XLS is Google's open-source medium-level synthesis compiler, and its QoR is " +
    "excellent. But checked against google/xls and the xlsynth fork as of late 2026: the " +
    "only SV it emits is RTL, and there is no DPI or TLM model output. The pre-RTL world is " +
    "all inside XLS's own tools.");

  // ============================================================ 5. the path
  pres.addSection({ title: "The fw-hdl path" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "The fw-hdl path" });
  s.addText("One module, two views, and XLS in the middle", { placeholder: "title" });
  card(s, MX, 1.5, 8.3, 1.75, C.background2, "Your RTL design");
  text(s, "Your RTL design", { x: MX + 0.3, y: 1.6, w: 4, h: 0.35, fontSize: 14, bold: true, color: C.text2 });
  const blocks = [["hand RTL", 0.9, 2.0, C.background1, C.text1],
                  ["my_block", 3.65, 2.4, C.accent1, C.background1],
                  ["hand RTL", 6.8, 2.0, C.background1, C.text1]];
  for (const [t, x, w, f, tc] of blocks) {
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 2.1, w, h: 0.8, rectRadius: 0.08,
      fill: { color: f }, line: { color: HEX.accent3, width: 1 }, objectName: "Block " + t + x });
    text(s, t, { x, y: 2.1, w, h: 0.8, align: "center", valign: "middle", fontSize: 16,
      bold: t === "my_block", color: tc, fontFace: "Courier New" });
  }
  arrow(s, 2.9, 2.5, 3.65, 2.5, HEX.dk2, "Arrow in");
  arrow(s, 6.05, 2.5, 6.8, 2.5, HEX.dk2, "Arrow out");
  arrow(s, 4.4, 2.9, 2.7, 3.85, HEX.accent1, "To model view");
  arrow(s, 5.3, 2.9, 6.7, 3.85, HEX.accent1, "To RTL view");
  const views = [["Model view", "SV classes on the fw-hdl runtime, behind the final pins", 0.9, C.accent6],
                 ["RTL view", "XLS-generated pipelined RTL, behind the same pins", 4.95, C.accent4]];
  for (const [h, b, x, f] of views) {
    card(s, x, 3.9, 3.85, 1.6, f, h);
    text(s, h, { x: x + 0.25, y: 4.05, w: 3.4, h: 0.4, fontSize: 18, bold: true });
    text(s, b, { x: x + 0.25, y: 4.5, w: 3.4, h: 0.9, fontSize: 15, color: C.text2 });
  }
  text(s, "Same module name, same ready/valid pins. Pick a view by file list: the parent RTL " +
    "and the testbench never change.", { x: 0.9, y: 5.75, w: 7.9, h: 0.8, fontSize: 16,
    italic: true, color: C.accent1 });
  const chain = ["SV class", "XLS IR (no DSLX)", "XLS optimize + schedule", "XLS codegen",
    "Fusion / DC / Genus"];
  for (let i = 0; i < chain.length; i++) {
    const y = 1.5 + i * 1.05;
    const last = i === chain.length - 1;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 9.4, y, w: 3.3, h: 0.7, rectRadius: 0.08,
      fill: { color: last ? C.text1 : (i === 0 ? C.accent6 : C.background2) },
      line: { type: "none" }, objectName: "Chain " + i });
    text(s, chain[i], { x: 9.4, y, w: 3.3, h: 0.7, align: "center", valign: "middle",
      fontSize: 16, bold: i === 0 || last, color: last ? C.background1 : C.text1 });
    if (!last) arrow(s, 11.05, y + 0.7, 11.05, y + 1.05, HEX.accent3, "Chain arrow " + i);
  }
  s.addNotes("You write SystemVerilog. fw-hdl translates the classes straight into XLS's " +
    "internal representation; no DSLX in between. XLS does what it's best at. And fw-hdl " +
    "wraps both views behind one module, so integration happens on day 2, not after synthesis. " +
    "Note: the generated module shell is the first roadmap item; see the status slide.");

  // ============================================================ 6. first week
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "The fw-hdl path" });
  s.addText("Your first week", { placeholder: "title" });
  const days = [
    ["LuFileCode", "Write the block", "A class with ports and a forever loop: get, compute, put. Members are registers. No pipeline diagram."],
    ["LuPuzzle", "Drop it into your design", "Instantiate the module shell where the hand-written block would go. Real ready/valid in your waves."],
    ["LuTestTube", "Verify with what you have", "Your SVUnit/UVM env on the same pins. A too-shallow FIFO deadlocks now, with an SV call stack."],
    ["LuGauge", "Is it fast enough?", "Set a clock target. XLS schedules it; you get a report and a timed model of the real latency."],
    ["LuRocket", "Generate the RTL", "XLS RTL behind the same module. Switch the file list, rerun the same tests, hand off to synthesis."],
  ];
  s.addShape(pres.shapes.LINE, { x: MX + 0.5, y: 2.05, w: CW - 1.0, h: 0,
    line: { color: HEX.accent3, width: 1.5, dashType: "dash" }, objectName: "Timeline" });
  for (let i = 0; i < 5; i++) {
    const x = MX + i * 2.45;
    await badge(s, x + 0.65, 1.6, 0.9, days[i][0], HEX.accent1, HEX.lt1, days[i][1]);
    text(s, "Day " + (i + 1), { x, y: 2.7, w: 2.25, h: 0.35, fontSize: 14, bold: true,
      color: C.accent1, align: "center" });
    text(s, days[i][1], { x, y: 3.1, w: 2.25, h: 0.75, fontSize: 18, bold: true, align: "center" });
    card(s, x, 3.95, 2.25, 2.1, C.background2, "Day card " + (i + 1));
    text(s, days[i][2], { x: x + 0.15, y: 4.1, w: 1.95, h: 1.85, fontSize: 14, color: C.text2 });
  }
  s.addNotes("Day 1: pick something you'd normally write as an FSM plus datapath. Day 2: the " +
    "module shell has the exact port list XLS will generate. Day 3: same pins means your " +
    "existing verification connects unchanged. Day 4: change the clock target and rerun; the " +
    "same tests pass at the new latency. Day 5: generated RTL lines point back to your SV lines.");

  // ============================================================ 7. code
  pres.addSection({ title: "Why it's better" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Why it's better" });
  s.addText("The same block, two ways", { placeholder: "title" });
  const dslx = [
    "proc RunLengthEncoder<SW: u32, CW: u32> {",
    "  input_r: chan<EncInData<SW>> in;",
    "  output_s: chan<EncOutData<SW, CW>> out;",
    "  init {( State<SW, CW> { prev_symbol: bits[SW]:0,",
    "          prev_count: bits[CW]:0, prev_last: false } )}",
    "  config (input_r: chan<EncInData<SW>> in,",
    "          output_s: chan<EncOutData<SW, CW>> out)",
    "    {(input_r, output_s)}",
    "  next (state: State<SW, CW>) {",
    "    let (tok, input) = recv_if(join(), input_r,",
    "                        !state.prev_last, zero_input);",
    "    ...",
    "    let tok = send_if(tok, output_s, do_send, data);",
    "    State { prev_symbol: symbol, prev_count: count,",
    "            prev_last: last }",
    "  }",
    "}"].join("\n");
  const sv = [
    "class RunLengthEncoder #(int SW = 32, int CW = 2)",
    "    extends fw_component implements fw_runnable;",
    "  fw_port #(fw_get_if #(EncInData))  input_r;",
    "  fw_port #(fw_put_if #(EncOutData)) output_s;",
    "",
    "  bit [SW-1:0] prev_symbol = '0;   // registers",
    "  bit [CW-1:0] prev_count  = '0;",
    "  bit          prev_last   = 1'b0;",
    "",
    "  task run();",
    "    forever begin",
    "      if (!prev_last) input_r.t.get(in_);",
    "      ...",
    "      if (do_send) output_s.t.put(out_);",
    "      prev_symbol = symbol; prev_count = count;",
    "      prev_last = last;",
    "    end",
    "  endtask",
    "endclass"].join("\n");
  const panes = [["XLS DSLX (original)", dslx, C.background2, C.accent5],
                 ["SystemVerilog with fw-hdl", sv, C.accent6, C.accent2]];
  for (let i = 0; i < 2; i++) {
    const x = MX + i * 6.15;
    text(s, panes[i][0], { x, y: 1.4, w: 5.95, h: 0.4, fontSize: 18, bold: true, color: panes[i][3] });
    card(s, x, 1.9, 5.95, 4.55, panes[i][2], "Code pane " + (i + 1));
    text(s, panes[i][1], { x: x + 0.25, y: 2.05, w: 5.5, h: 4.3, fontSize: 12,
      fontFace: "Courier New", color: C.text1 });
  }
  text(s, "Run-length encoder from the XLS examples, abridged (parameter names shortened). " +
    "Both compile through XLS.", { x: MX, y: 6.55, w: CW, h: 0.35, fontSize: 12, color: C.accent3 });
  s.addNotes("Both versions compile through XLS. Left is the original DSLX from the XLS repo; " +
    "right is the SV port in examples/xls/rle. Point at: state threaded through next() vs " +
    "plain registers; token threading vs get/put under an if.");

  // ============================================================ 8. what designers notice
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Why it's better" });
  s.addText("What an RTL designer notices", { placeholder: "title" });
  const notice = [
    ["LuLayers", "State is just registers", "Class members you assign, not an immutable value threaded through next() with init and config blocks."],
    ["LuCable", "I/O is just I/O", "get and put under an if read the way the hardware behaves. No tokens to thread to order side effects."],
    ["LuNetwork", "Composition is just wiring", "An fw_channel #(T, DEPTH) and two connect() calls, visible in your simulator. Not a spawn inside config."],
    ["LuMonitorPlay", "It runs in your simulator", "Plain IEEE 1800 classes, no preprocessing, next to your RTL. DSLX runs in XLS's interpreter."],
  ];
  for (let i = 0; i < 4; i++) {
    const y = 1.5 + i * 1.3;
    await badge(s, MX, y, 0.85, notice[i][0], HEX.accent2, HEX.lt1, notice[i][1]);
    text(s, notice[i][1], { x: MX + 1.15, y: y - 0.02, w: 6.9, h: 0.45, fontSize: 19, bold: true });
    text(s, notice[i][2], { x: MX + 1.15, y: y + 0.43, w: 6.9, h: 0.8, fontSize: 15, color: C.text2 });
  }
  card(s, 9.0, 1.5, 3.73, 5.05, C.text1, "Result panel");
  text(s, "And the hardware?", { x: 9.3, y: 1.75, w: 3.2, h: 0.45, fontSize: 18, bold: true, color: C.accent4 });
  text(s, "105 vs 144", { x: 9.3, y: 2.4, w: 3.2, h: 0.9, fontSize: 44, bold: true,
    color: C.background1, fontFace: THEME.headFontFace });
  text(s, "flip-flops on iCE40", { x: 9.3, y: 3.3, w: 3.2, h: 0.4, fontSize: 15, color: C.accent4 });
  text(s, "89 vs 95", { x: 9.3, y: 4.0, w: 3.2, h: 0.9, fontSize: 44, bold: true,
    color: C.background1, fontFace: THEME.headFontFace });
  text(s, "XLS IR nodes", { x: 9.3, y: 4.9, w: 3.2, h: 0.4, fontSize: 15, color: C.accent4 });
  text(s, "Run-length encoder: SV port vs DSLX original", { x: 9.3, y: 5.55, w: 3.2, h: 0.8,
    fontSize: 13, italic: true, color: C.accent3 });
  s.addNotes("On the run-length encoder the SV source actually gives XLS a smaller starting " +
    "point. Don't oversell it: on most examples it is the same netlist (next slides).");

  // ============================================================ 9. process networks
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Why it's better" });
  s.addText("Multi-process designs you can actually see", { placeholder: "title" });
  const hdr = (t) => ({ text: t, options: { bold: true, color: C.background1, fill: { color: C.text1 }, fontSize: 16 } });
  const rows = [
    [hdr("Concern"), hdr("DSLX procs behind DPI"), hdr("SV + fw-hdl")],
    ["What your sim sees", "One opaque C++ blob", "Every process and channel as an SV object"],
    ["Notion of time", "None: one activation per tick", "Clock domains, tick(n), timed models"],
    ["FIFO depth before RTL", "Ignored; queues unbounded (XLS #988)", "Honored: an undersized FIFO deadlocks in the model"],
    ["Splice in hand RTL", "Not inside the blob", "Any channel edge, via a transactor"],
    ["Connect to your TB", "Hand-written DPI marshalling", "The module's ready/valid pins"],
  ];
  const body = rows.map((r, i) => i === 0 ? r : r.map((c, j) => ({ text: c, options: {
    fontSize: 15, color: j === 2 ? C.accent2 : C.text1, bold: j === 0,
    fill: { color: i % 2 ? C.background2 : C.background1 } } })));
  s.addTable(body, { x: MX, y: 1.5, w: CW, colW: [2.9, 4.4, 4.83], rowH: 0.62,
    border: { type: "solid", pt: 0.5, color: HEX.lt2 }, valign: "middle", margin: [0.06, 0.15, 0.06, 0.15] });
  text(s, "Real blocks are several processes connected by FIFOs: a parser feeding a lookup " +
    "feeding a rewriter, or a cipher fed by a DMA. That is where the difference is largest.",
    { x: MX, y: 5.55, w: CW, h: 0.8, fontSize: 16, italic: true, color: C.accent1 });
  s.addNotes("This is the decisive case. XLS's proc runtime ignores fifo_depth (open issue " +
    "#988 since 2023), so a deadlock from an undersized FIFO stays hidden until RTL. fw-hdl " +
    "channels block at their depth, in the SV simulator.");

  // ============================================================ 10. performance before RTL
  s = pres.addSlide({ masterName: "CONTENT_DARK", sectionTitle: "Why it's better" });
  s.addText("Performance answers before RTL, from the real compiler", { placeholder: "title" });
  text(s, "fw-hdl reads XLS's actual schedule for your clock target and generates a timed " +
    "model with that latency, so system-level numbers don't drift from the RTL.",
    { x: MX, y: 1.4, w: CW, h: 0.9, fontSize: 18, color: C.accent4 });
  const perf = [
    ["Cycle-exact", "with XLS's RTL on the AES test vectors (32 ops in 128 clocks)"],
    ["2.8–4.7×", "faster to simulate than the RTL it stands in for (Verilator)"],
    ["0.18 s vs 33 s", "simulating 64 idle instances: timed model vs RTL"],
  ];
  for (let i = 0; i < 3; i++) {
    const x = MX + i * 4.1;
    card(s, x, 2.75, 3.8, 3.7, C.text2, "Perf card " + (i + 1));
    text(s, perf[i][0], { x: x + 0.3, y: 3.1, w: 3.2, h: 1.3, fontSize: i === 1 ? 54 : 40,
      bold: true, color: C.accent1, valign: "middle", fontFace: THEME.headFontFace });
    text(s, perf[i][1], { x: x + 0.3, y: 4.6, w: 3.2, h: 1.5, fontSize: 16, color: C.background1 });
  }
  s.addNotes("Architects get credible latency numbers in the SoC sim before RTL exists. Today " +
    "the timed model covers latency for functions (AES demo); throughput (II) for processes " +
    "is on the roadmap.");

  // ============================================================ 11. one test
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Why it's better" });
  s.addText("One test file, every level, your testbench", { placeholder: "title" });
  card(s, MX, 2.85, 3.2, 1.6, C.text1, "Test file");
  s.addImage({ data: await iconPng("LuListChecks", HEX.accent4), x: MX + 0.3, y: 3.25, w: 0.8, h: 0.8,
    altText: "Test file", objectName: "Test icon" });
  text(s, "your_test.sv\nunedited", { x: MX + 1.3, y: 3.1, w: 1.8, h: 1.1, fontSize: 17, bold: true,
    color: C.background1, valign: "middle" });
  const levels = ["SV class model", "XLS RTL", "Generic gates", "iCE40 netlist", "ECP5 netlist"];
  for (let i = 0; i < 5; i++) {
    const y = 1.5 + i * 0.9;
    card(s, 5.1, y, 3.0, 0.7, i === 0 ? C.accent6 : C.background2, "Level " + i);
    text(s, levels[i], { x: 5.1, y, w: 3.0, h: 0.7, fontSize: 16, align: "center", valign: "middle" });
    arrow(s, MX + 3.2, 3.65, 5.1, y + 0.35, HEX.accent3, "Fan " + i);
    s.addImage({ data: await iconPng("LuCircleCheck", HEX.accent2), x: 8.25, y: y + 0.15, w: 0.4, h: 0.4,
      altText: "Pass", objectName: "Pass " + i });
  }
  card(s, 9.0, 1.5, 3.73, 4.4, C.accent4, "Evidence");
  text(s, "11", { x: 9.3, y: 1.7, w: 3.2, h: 1.0, fontSize: 60, bold: true, color: C.accent1,
    fontFace: THEME.headFontFace });
  text(s, "examples ported from the XLS repo pass with a byte-identical test file at every " +
    "level, including SHA-256 at three clock targets.", { x: 9.3, y: 2.75, w: 3.2, h: 1.8, fontSize: 15 });
  text(s, "A gate-level failure reproduces at model level in milliseconds: same test, same message.",
    { x: 9.3, y: 4.5, w: 3.2, h: 1.3, fontSize: 15, italic: true, color: C.text2 });
  s.addNotes("No DPI, and no second testbench for the HLS block. Tests compare streams of " +
    "values, so they hold whatever pipeline depth XLS chose.");

  // ============================================================ 12. QoR chart
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Why it's better" });
  s.addText("SV is as efficient as hand-written DSLX, and sometimes more", { placeholder: "title" });
  const names = ["CRC-32", "Adler-32", "LFSR", "Prefix sum", "FIR dot", "IDCT (Chen)", "SHA-256", "GCD", "Run-length enc."];
  const ratios = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.055, 0.672];
  s.addChart(pres.charts.BAR, [{ name: "SV / DSLX iCE40 cells", labels: names, values: ratios }], {
    x: MX, y: 1.4, w: 7.6, h: 5.3, barDir: "bar", chartColors: [HEX.accent2],
    showTitle: true, title: "iCE40 cells, SV source ÷ DSLX source (1.00 = identical)",
    titleFontSize: 14, titleColor: HEX.dk2, titleFontFace: "+mn-lt",
    showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "0.00",
    dataLabelFontSize: 12, dataLabelColor: HEX.dk1, dataLabelFontFace: "+mn-lt",
    catAxisLabelColor: HEX.dk2, catAxisLabelFontSize: 13, catAxisLabelFontFace: "+mn-lt",
    catAxisOrientation: "maxMin",
    valAxisMinVal: 0, valAxisMaxVal: 1.2, valAxisMajorUnit: 0.2, valAxisLabelFormatCode: "0.0",
    valAxisLabelColor: HEX.accent3, valAxisLabelFontSize: 11, valAxisLabelFontFace: "+mn-lt",
    valGridLine: { color: HEX.lt2, size: 0.75 }, catGridLine: { style: "none" },
    showLegend: false, barGapWidthPct: 60,
  });
  card(s, 8.7, 1.5, 4.03, 5.1, C.background2, "QoR commentary");
  text(s, [
    { text: "Same internal representation", options: { bold: true, fontSize: 18, breakLine: true } },
    { text: "fw-hdl feeds XLS's optimizer, scheduler and codegen exactly what DSLX would.",
      options: { fontSize: 15, color: C.text2, breakLine: true, paraSpaceAfter: 14 } },
    { text: "Identical on 7 of 9", options: { bold: true, fontSize: 18, breakLine: true } },
    { text: "Where it differs, it's a few percent either way: GCD +5.5%, run-length encoder −33%.",
      options: { fontSize: 15, color: C.text2, breakLine: true, paraSpaceAfter: 14 } },
    { text: "AES: 6975 vs 6976 IR nodes", options: { bold: true, fontSize: 18, breakLine: true } },
    { text: "XLS's equivalence checker proves the SV port matches the DSLX original on most functions.",
      options: { fontSize: 15, color: C.text2 } },
  ], { x: 9.0, y: 1.75, w: 3.45, h: 4.7 });
  s.addNotes("From examples/xls/RESULTS.md. SHA-256 is 48255 vs 48260 cells, which rounds to " +
    "1.00. Equivalence: 'equivalent' on CRC, Adler, LFSR, GCD, prefix sum, FIR, IDCT; SHA-256 " +
    "partly proved; AES inconclusive (too large). Procs aren't checked: XLS's checker takes " +
    "functions only.");

  // ============================================================ 13. adoption staircase
  pres.addSection({ title: "Getting started" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Getting started" });
  s.addText("Adopt it one function at a time", { placeholder: "title" });
  const steps = [
    ["LuCode", "One function", "Pull a CRC or round function out of hand RTL. XLS pipelines it; your RTL instantiates it.", "Available today"],
    ["LuBoxes", "One block", "Write a whole FSM-plus-datapath block as a class behind its module shell.", "Flow available; module shell on the roadmap"],
    ["LuWorkflow", "A network of blocks", "Processes and FIFOs, assembled by fw-hdl into one RTL top.", "Available for all-XLS networks"],
  ];
  for (let i = 0; i < 3; i++) {
    const x = MX + i * 4.1, h = 3.0 + i * 0.8, y = 6.6 - h;
    card(s, x, y, 3.8, h, i === 0 ? C.accent4 : (i === 1 ? C.accent6 : C.background2), "Step " + (i + 1));
    await badge(s, x + 0.3, y + 0.3, 0.8, steps[i][0], HEX.accent1, HEX.lt1, steps[i][1]);
    text(s, steps[i][1], { x: x + 1.3, y: y + 0.4, w: 2.3, h: 0.6, fontSize: 20, bold: true, valign: "middle" });
    text(s, steps[i][2], { x: x + 0.3, y: y + 1.3, w: 3.2, h: 1.2, fontSize: 15, color: C.text2 });
    text(s, steps[i][3], { x: x + 0.3, y: y + h - 0.85, w: 3.2, h: 0.6, valign: "bottom", fontSize: 14, bold: true,
      italic: true, color: C.accent1 });
  }
  text(s, "Nothing you wrote at an earlier step needs rewriting.", { x: MX, y: 1.4, w: 7.5, h: 0.45,
    fontSize: 18, italic: true, color: C.accent1 });
  s.addNotes("You don't have to convert a block, let alone a team. The lowest-risk first use " +
    "is one datapath function, and that flow works today.");

  // ============================================================ 14. keep XLS
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Getting started" });
  s.addText("Not instead of XLS: XLS with a front end for RTL teams", { placeholder: "title" });
  const keep = [["fw-hdl adds", C.accent6, C.accent2, [
      "SystemVerilog source, in your repo and code review",
      "The model as a module in your design",
      "Visible processes and FIFOs with real depths",
      "Timed models from XLS's schedule",
      "One test at every level"]],
    ["XLS provides", C.accent4, C.accent1, [
      "Optimizer and scheduler",
      "Delay-model-driven pipelining",
      "Ready/valid codegen, FIFOs, I/O flops",
      "Equivalence and property proving",
      "Continuous improvement from Google and xlsynth"]]];
  for (let c = 0; c < 2; c++) {
    const x = MX + c * 6.15;
    card(s, x, 1.5, 5.95, 4.4, keep[c][1], keep[c][0]);
    text(s, keep[c][0], { x: x + 0.4, y: 1.75, w: 5.2, h: 0.5, fontSize: 22, bold: true, color: keep[c][2] });
    text(s, keep[c][3].map((t, i) => ({ text: t, options: { bullet: true,
      breakLine: i < keep[c][3].length - 1, paraSpaceAfter: 8 } })),
      { x: x + 0.4, y: 2.45, w: 5.2, h: 3.3, fontSize: 17 });
  }
  text(s, "As XLS improves, your blocks improve.", { x: MX, y: 6.15, w: CW, h: 0.5, fontSize: 20,
    bold: true, align: "center", color: C.text1, fontFace: THEME.headFontFace });
  s.addNotes("This is not a competitor to XLS's back end. It's how an RTL team actually uses it.");

  // ============================================================ 15. FAQ
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Getting started" });
  s.addText("Common questions", { placeholder: "title" });
  const faq = [
    ["Isn't class-based SV slow?", "It's a transaction-level model: the timed AES model runs 2.8–4.7× faster than its RTL."],
    ["What SV can I use?", "2-state packed types, structs, functions, if/case, fixed loops, blocking get/put. Errors point at the line."],
    ["How do I trust the RTL?", "SV ↔ XLS IR: equivalence + differential tests. IR ↔ RTL: XLS + your tests. RTL ↔ gates: your LEC."],
    ["Can I mix DSLX or hand RTL?", "Yes. The top is built from block interfaces, so any block with the same ready/valid interface plugs in."],
    ["Which simulators?", "Standard IEEE 1800. Tested on Verilator; VCS, Xcelium and Questa are being qualified."],
    ["Are we locked in?", "Source is SystemVerilog; the engine is open-source XLS. Your models stay plain SV."],
  ];
  for (let i = 0; i < 6; i++) {
    const x = MX + (i % 3) * 4.1, y = 1.5 + Math.floor(i / 3) * 2.6;
    card(s, x, y, 3.8, 2.4, C.background2, "FAQ " + (i + 1));
    s.addImage({ data: await iconPng("LuCircleHelp", HEX.accent1), x: x + 0.25, y: y + 0.27, w: 0.4, h: 0.4,
      altText: "Question", objectName: "FAQ icon " + i });
    text(s, faq[i][0], { x: x + 0.8, y: y + 0.22, w: 2.8, h: 0.55, fontSize: 16, bold: true, valign: "middle" });
    text(s, faq[i][1], { x: x + 0.25, y: y + 0.9, w: 3.35, h: 1.4, fontSize: 14, color: C.text2 });
  }
  s.addNotes("Subset detail: a #delay or a get/put inside a loop is rejected with a located " +
    "error. Accepting 'logic' as 2-state is a near-term roadmap item.");

  // ============================================================ 16. today vs roadmap
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Getting started" });
  s.addText("Available today, and what's next", { placeholder: "title" });
  const avail = ["SV functions and processes → XLS → pipelined RTL, at QoR parity",
    "One test at model, RTL and gate level", "FIFO-depth-accurate multi-process models",
    "All-XLS process networks assembled into one RTL top", "Timed model from the XLS schedule (latency, functions)"];
  const next = ["Module shell with XLS's exact pins (first priority)",
    "Accept 'logic', designer coding guide, early synthesizability check (first priority)",
    "Reset style, I/O flops, throughput targets, SDC hand-off",
    "Timed processes with throughput (II)", "$display / cover / properties into RTL and formal; SRAMs; node delay models"];
  const ar = [["Available", avail, "LuCircleCheck", HEX.accent2, C.accent6, C.accent2],
              ["Roadmap", next, "LuMap", HEX.accent1, C.accent4, C.accent1]];
  for (let c = 0; c < 2; c++) {
    const x = MX + c * 6.15;
    card(s, x, 1.5, 5.95, 5.15, ar[c][4], ar[c][0]);
    text(s, ar[c][0], { x: x + 0.4, y: 1.7, w: 5.2, h: 0.5, fontSize: 22, bold: true, color: ar[c][5] });
    for (let i = 0; i < 5; i++) {
      const y = 2.4 + i * 0.83;
      s.addImage({ data: await iconPng(ar[c][2], ar[c][3]), x: x + 0.4, y: y + 0.05, w: 0.35, h: 0.35,
        altText: ar[c][0], objectName: `${ar[c][0]} icon ${i}` });
      text(s, ar[c][1][i], { x: x + 0.95, y, w: 4.75, h: 0.78, fontSize: 15 });
    }
  }
  s.addNotes("Be straight with the audience: the day-2 module shell and the ASIC hand-off " +
    "are roadmap. The function flow, one-test-every-level and QoR parity are real today.");

  // ============================================================ 17. short version
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Getting started" });
  s.addText("The short version", { placeholder: "title" });
  const sh = [
    [hdr(""), hdr("XLS with DSLX"), hdr("XLS with SV + fw-hdl")],
    ["Language", "Learn DSLX", "The SystemVerilog you already write"],
    ["Pre-RTL model in your SoC sim", "Hand-written DPI, or nothing", "The model is SV, behind the final pins"],
    ["Multi-process debug", "Opaque; FIFO depth ignored", "Every process and FIFO visible"],
    ["Performance before RTL", "Static report", "Timed model from XLS's schedule"],
    ["Tests", "HLS tests + RTL tests", "One test file, every level"],
    ["Adoption", "All in, per block", "One function at a time"],
    ["QoR", "XLS", "XLS"],
  ];
  const shb = sh.map((r, i) => i === 0 ? r : r.map((c, j) => ({ text: c, options: {
    fontSize: 15, bold: j === 0 || j === 2, color: j === 2 ? C.accent2 : C.text1,
    fill: { color: i % 2 ? C.background2 : C.background1 } } })));
  s.addTable(shb, { x: MX, y: 1.5, w: CW, colW: [3.4, 4.0, 4.73], rowH: 0.6,
    border: { type: "solid", pt: 0.5, color: HEX.lt2 }, valign: "middle", margin: [0.06, 0.15, 0.06, 0.15] });
  s.addNotes("If they remember one slide, this is it.");

  // ============================================================ 18. closing
  s = pres.addSlide({ masterName: "TITLE_DARK", sectionTitle: "Getting started" });
  s.addText("XLS is the best open medium-level synthesis engine. fw-hdl is how an RTL team actually uses it.",
    { placeholder: "title" });
  s.addText("Next step: a one-week pilot on one datapath function from your design.",
    { placeholder: "body" });
  await badge(s, MX, 0.9, 0.9, "LuZap", HEX.accent1, HEX.lt1, "Spark");
  s.addNotes("Close on the pilot: lowest risk, works today, and it shows the one-test-every-" +
    "level story on their own code.");

  await pres.writeFile({ fileName: OUT });
  if (process.env.APPLY_THEME) {
    const { applyTheme } = require(process.env.APPLY_THEME);
    await applyTheme(OUT, THEME);
  }
  console.log("wrote " + OUT);
}

main().catch((e) => { console.error(e); process.exit(1); });
