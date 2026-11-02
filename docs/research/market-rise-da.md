# Market check: fw-hdl vs Rise Design Automation (and the HLS field)

*Research note, 2026-11-01, from public sources only. Labels: **[V]** the vendor's own
material, **[3P]** third-party, **[INF]** inference. Rise has published no documentation,
code examples or pricing, so "not found" below means *not claimed publicly*, not
*absent*.*

## 1. Verdict

**On concept, we have not invented something new: Rise DA is a close sibling.** Rise
targets the same audience (RTL and DV engineers) with the same entry point (behavioral
SystemVerilog), and **it uses Google XLS inside**:
- Rise's own company-wiki text: *"Google XLS for our Intermediate Representation (IR) and
  structural optimization"* [V]
- Bernard Murphy, reporting on DVCon 2025: *"they have integrated the Google XLS platform"*
  [3P]

Rise also generates transactors to put RTL back into behavioral simulations, correlates HL
lines to RTL, and reuses UVM from HL through RTL.

**In execution and delivery, we differ, and the differences sit exactly in our "before
synthesis" story:**
- fully open versus a closed commercial suite
- XLS's *own* scheduler versus Rise's proprietary scheduling layer on top of XLS IR [INF]
- multi-view models behind the same pins: a timed TLM back-annotated from the schedule and
  a staged TLM, with lockstep against RTL
- divergence finder and replay
- unit-level SVUnit tests reused unchanged through gate level
- a class/channel coding style

None of these appears in Rise's public material.

**Positioning consequence.** We must **not** claim "first SV-based HLS" or "first SV→XLS".
We *can* claim, as far as public sources show, **the only open SV→XLS flow**. We can also
claim the multi-view, timing-shell and debug capabilities as distinctive. Rise's existence
is good news for the thesis: an ex-Catapult team is betting on SV-entry HLS on top of XLS.

## 2. Rise in brief

| Topic | Finding | Source |
|---|---|---|
| Company | Pleasanton, CA; emerged from stealth around early 2025; founding reportedly 2022 (unconfirmed) | [V] rise-da.com/company; [3P] SemiWiki CEO interview |
| Team | CEO Badru Agarwala, former GM of Mentor's **Calypto** division (Catapult, SLEC). Mike Fingeroff (HLS Blue Book, Catapult). An ex-Catapult team in effect | [V] rise-da.com/company, /lunchandlearn |
| Products | Rise High-Level Platform (HLS, verification, debug, analysis); AI IPCreate and IPTransform (DAC 2026) | [V] rise-da.com/products; [3P] SemiWiki DAC 2026 |
| Inputs | **SystemVerilog** (untimed / loosely timed), **C++, SystemC**, mixed per block. MathWorks models into IPCreate. SV parsed with **Verific** | [V] products; [V-authored] SemiWiki company wiki |
| Engine | Own HLS transforms (unrolling, scheduling, parallelism) plus **XLS IR and structural optimization**. Built-in RTL synthesis within 10% of production tools; .lib; power and clock gating; memory inference | [V] wiki, /rise-agentic-ai; [3P] SemiWiki |
| QoR | "Comparable to hand-coded RTL", no numbers; "10–100× faster synthesis/exploration" | [3P] 2026 Outlook interview |
| AI | Rise.ai advisor (SV, C++, SystemC, UVM generation); agentic propose/evaluate/decide loop; spec→RTL (IPCreate) and RTL→HLS (IPTransform) | [V] products, /rise-agentic-ai |
| Business | Commercial, closed; North America distributor AI Tech Sales (Jan 2026); no public pricing; AI/compute and DSP/vision targets | [3P] 2026 Outlook |

## 3. Stage-by-stage comparison: "before RTL goes to synthesis"

| Stage | Rise (public claims) | fw-hdl (status) | Edge |
|---|---|---|---|
| **Engine** | Proprietary HLS layer + XLS IR/opt + own RTL synthesis estimates | XLS's own optimizer, **scheduler** and codegen, unmodified | Different bets. Ours: "XLS as is". Theirs: "XLS as a component" |
| **Authoring language** | SV (loosely timed, handshake I/O); C++/SystemC; mixed | SV classes + `fw_channel`, Kahn-style; functions | Rise is broader (C++/SystemC). Our class/channel style is distinct (Rise's SV subset is unpublished) |
| **Early behavioral testing** | Behavioral sim 30–1000× faster than RTL; UVM reuse; AI-generated testbenches | SVUnit at task/function level ✅; one unedited test at model, RTL and gates ✅ | Overlap on reuse. **Unit-level SVUnit and gate-level reuse are ours** |
| **Connection to signal level** | "Automatically generated adapters" / RTL instrumented with transactors | Shell generator from an API→transactor map (planned); bind machinery ✅ | **Overlap.** Ours is open and kit-extensible |
| **Reports back to source** | Cross-probing; HL↔RTL line correlation; critical-path analysis | SV `pos` in XLS IR ✅; schedule overlay, width/dead-logic feedback, PR QoR diff (planned) | Overlap on correlation. Overlay, budgets and PR diffs not claimed by Rise |
| **Multiple views behind the same pins** | "Mixed-language, mixed-abstraction simulation" (HL blocks next to RTL blocks) | Untimed / **timed TLM from the XLS schedule** / **staged TLM** / RTL, with a **lockstep** check | **Ours.** No public Rise equivalent of schedule-back-annotated timed models |
| **RTL debug** | `$display` support; line-number annotations; transaction-level waveforms; channel capture; HL-vs-RTL comparison; synthesized assertions and coverage | Generated monitors at boundary / internal-FIFO / per-activation level; **divergence finder; replay**; SV-named registers (planned); assert ✅, trace/cover planned | Overlap on monitors and waveforms. **Divergence finder and replay are ours.** Rise is ahead on shipped polish (assertions, coverage, IDE) |
| **Formal** | None claimed | XLS equivalence for functions ✅; SBY contract proofs (prototype) | Slight edge to us if matured |
| **Delivery** | Closed VS Code-based suite; commercial support; claims of silicon validation | Open source; dv-flow tasks; any simulator (Verilator today) | **Open vs closed** is the structural difference |

## 4. What Rise has that we don't, and whether it matters for our angle

| Rise capability | Matters for "curated XLS adoption for SV engineers"? | Action |
|---|---|---|
| `$display` support, synthesized assertions and coverage carried into RTL | **Yes.** Cheap and expected | Do it: map `$display`→`trace_fmt!`, `cover`→`cover!` (value-adds D9) |
| Polished IDE with cross-probing | Yes, eventually | Schedule overlay + LSP (A3/A4). There is also a zuspec langserver to build on |
| C++/SystemC input | No: off-angle | Skip (the Python/zuspec path is the parked equivalent) |
| AI advisor / agentic flows | Not core | Note: SV is LLM-friendly for free. Revisit later |
| Built-in RTL synthesis with .lib correlation, power and clock gating | Partly. It's "after XLS" but informs scheduling | Delay-model characterization (F4) and the sweep (B3) cover our need |
| Commercial support and silicon references | Yes, for enterprise buyers | Not ours to match. Lean on openness and community instead |

## 5. Rest of the field (brief)

| Tool | Entry | Aimed at SV engineers? | Notes |
|---|---|---|---|
| Siemens Catapult | C++ / SystemC | No | SCVerify (testbench reuse), SLEC-HLS (formal), Catapult Coverage |
| Cadence Stratus | SystemC / C++ / MATLAB | No | TLM-to-gates flow; Jasper equivalence |
| AMD Vitis HLS | C/C++ | No (FPGA) | C/RTL co-simulation |
| Bluespec | BSV / BH (open bsc) | Loosely | A new language; rule-based, not HLS-scheduled |
| Chisel / CIRCT | Scala generators | No | CIRCT's `circt-verilog` (slang → MLIR) is a possible SV front end |
| PipelineC | C-like HDL | No | Auto-pipelining; little verification tooling |
| XLS / xlsynth | DSLX, xlscc | No | No SV front end; xlsynth has `slang-rs`, bedrock-rtl, topstitch, but no SV→IR path |

**Open SV→XLS flows other than fw-hdl:** none found.

## 6. Recommended positioning

**Lead with:**
1. **The open SV→XLS adoption path:** your SV in, XLS's own scheduler and codegen,
   everything inspectable, no license.
2. **Multiple views behind the same pins:** timed TLM from the XLS schedule replacing RTL
   at subsystem level, proven by lockstep.
3. **RTL debug you can automate:** generated monitors, divergence finder, replay.
4. **Unit tests that survive to gates:** SVUnit at task/function level, unchanged at every
   level.
5. **Class-based composition**: connect-time binding, interface-class APIs, pin-free channels. Rise's public material shows module-style entry (§6a). Speed from classes is to be benchmarked before claiming it.
6. **An open flow** (dv-flow) that fits existing CI.

**Avoid:** "first SV-based HLS", "first XLS-based HLS", "only HLS with HL↔RTL
correlation or generated transactors". Rise claims all of these too.

**Watch:**
- whether Rise publishes timed/cycle-approximate models or HL-vs-RTL lockstep
- its SV subset (classes?)
- formal equivalence
- any open-sourcing

Also watch XLS upstream and xlsynth for an SV front end (slang-rs makes one plausible).

## 6a. Design-entry style: modules vs classes (follow-up check)

**Public evidence:**
- Rise describes its SV only as "untimed or loosely-timed" [V]. Its control-logic webinar
  covers loops, conditionals, non-blocking I/O, handshakes, FSMs and concurrency [V].
- **No construct is ever named.** Searches found nothing on `module`, `class`,
  `interface`, `@(posedge clk)` or a channel-library name.
- **No public code at all:** no GitHub, patents, DVCon papers or code screenshots. Detail
  sits behind webinar registration.
- **Classes:** no public statement either way. Verific can *parse* classes; whether they
  are synthesizable input for Rise is unknown.

**Other indications:**
- Our own observation of Rise material is that it is **mostly module-based**.
- Inference supports this. In HLS practice, "loosely timed" usually means clocked
  processes in a module. Swapping HL and RTL models under the same testbench implies
  pin- or interface-compatible module boundaries.
- Treat "Rise is module-based" as likely, but say "as publicly shown", not "Rise cannot".

**Differentiator 1: composition.** This holds on its own merits.

fw-hdl composes with:
- ports and exports bound at `connect()`
- API interface classes, so polymorphic implementations sit behind one contract
- parameterized types
- pin-free transaction-level connections
- structural components whose channels *are* the architecture, which `spl.Partition`
  and `Integrate` read directly

Module composition fixes connectivity at elaboration through signal or SV-interface
ports. Swapping an implementation or protocol variant means rewiring. If Rise uses SV
interfaces with tasks, part of the pin-free benefit exists there too, but without
connect-time polymorphic binding.

The cost on our side: object graphs must be statically resolvable for synthesis, with no
post-elaboration allocation or handle aliasing. The static mapper must enforce that.

**Differentiator 2: execution speed.** Plausible, **unproven**.
- **Why it's plausible:** class-based TLM processes that block on channel put/get and skip
  idle clocks generate far fewer scheduler events than a module model that waits on
  `posedge clk` every cycle.
- **What we've measured:** only against RTL (timing shell 2.8–4.7×; 0.18 s vs 33 s at 64
  instances).
- **Why Rise's figures can't serve as a baseline:** they vary between 30× and 1000×
  "vs RTL", with no published methodology.
- **What could cut against us:** class dispatch and handle indirection cost something in
  commercial simulators.

**Benchmark needed before claiming speed.** Write the same design three ways:
1. RTL
2. a module-based, loosely timed SV model in the conventional style (`always` processes
   with `@(posedge clk)`, handshake signals)
3. an fw-hdl class model, untimed and with a timing shell

Run all three on the same simulators (Verilator, and one commercial simulator). Measure
wall-clock per transaction, at 1 instance and at N instances. Candidates: AES A0 (we have
RTL and class views) and `rle_loop` (multi-process).

Until then, pitch composition as the differentiator and speed as "expected, being
measured".

## 7. Confidence and gaps

- **XLS inside Rise:** high confidence (first-person company text plus a third-party
  report). The split between Rise's scheduling and XLS's is our inference.
- **Funding, investors, headcount, customers:** unconfirmed.
- **Rise's SV subset** (classes, interfaces, channel API): unpublished; no public code found anywhere. Module-based is likely (our observation plus inference), not confirmed (§6a).
- **Rise's timed models, formal, gate-level reuse, SVUnit:** no public evidence either way.
- **Comparison-set entries** come from vendor pages, not deep dives.

*Key URLs:*
- rise-da.com/products, /company, /rise-agentic-ai
- semiwiki.com/wikis/company-wikis/rise-design-automation/
- semiwiki.com/eda/rise-design-automation/353600-an-imaginative-approach-to-ai-based-design/
- semiwiki.com/eda/rise-design-automation/361724-rise-da-webinar-systemverilog-at-the-core-scalable-verification-and-debug-in-hls/
- semiwiki.com/eda/372254-rise-design-automation-at-dac-2026/
- semiwiki.com/eda/rise-design-automation/365630-2026-outlook-with-badru-agarwala-of-rise-design-automation-rda/
