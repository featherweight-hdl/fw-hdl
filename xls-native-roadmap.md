# XLS native roadmap: XLS as the implementation now, native zuspec-IR algorithms over time

Status: **plan, parked**. Written 2026-10-03, not scheduled. It refines
`chisel-xls-assessment.md` §6.4 (XLS is the primary back end; the native scheduler is a
fallback) and sits beside `xls-phase2.md` (X2, the SPL → RTL pipeline). Nothing here
changes X2.

> **Reframed by `refinement-views.md` (2026-10-04).** Refining decisions (schedule,
> II, binding, channel depths) must be facts in zuspec IR, because the architecture
> views (CAG, stage TLM) are built from them. XLS may make those decisions but must not
> own them. As a result, W1-1, W1-5 and W4 move up in priority; W4-4 is path (c) there;
> the W6 optimizer question is unaffected.

## 1. Goal and position

- **Near term: XLS is *the* implementation** of HLS/MLS synthesis (optimization,
  scheduling, codegen) for `timing=static` components. We rely on its QoR.
- **We check everything up front.** fw-hdl and zuspec validate the input so that XLS
  is unlikely ever to report an error on user input. An XLS verifier failure or
  `RET_CHECK` is reported as an *internal* error with a reproducer, not as a user
  diagnostic.
- **Over time we grow native HLS/MLS algorithms on zuspec IR.** Reasons:
  - control over diagnostics, and one consistent user experience;
  - the ability to run *part* of a flow (analysis, timing estimate, schedule) during
    development, for fast feedback without a full synthesis run;
  - flexibility XLS's pipeline does not offer.
- **XLS is used as an instrument and an oracle, then becomes optional.** We study what
  each XLS algorithm does on our designs, check native results against it, and switch
  over one algorithm at a time.
- **Retiring XLS as a *requirement* is an outcome we measure, not a milestone we
  schedule.** XLS can remain an opt-in high-effort engine behind the same interface.
- **Solving and SAT-like reasoning come from dv-solve,** not from a solver stack of
  our own.

## 2. Background: what XLS consists of

Measured on the local google/xls checkout (`~/projects/xls/xls`, commit `dff59c1a1`,
April 2025). xlsynth tracks upstream, so its proportions should be similar. Counts are
production `.cc`/`.h` lines with tests excluded.

| Area | Prod C++ | Test C++ | Role for us |
|---|---|---|---|
| `dslx/` (frontend 18K, type_system v1+v2 27K, ir_convert 8.5K, bytecode 7K, fmt, lsp…) | 83K | 49K | front end; bypassed entirely |
| `ir/` | 47K | 26K | core: IR, verifier, parser |
| `passes/` (optimizer: ~60 passes over BDD/range/ternary query engines) | 45K | 45K | core QoR |
| `codegen/` (block conversion 22K, VAST emitter 8K) | 31K | 35K | core |
| `scheduling/` (SDC scheduler ≈1K, mutual exclusion, etc.) | 7K | 4.6K | core, and small |
| `estimators/` | 2K + **41K lines of delay-model textproto** (asap7, sky130, unit) | 1K | data; we can read it directly |
| `solvers/`, `data_structures/` | 9K | 8K | Z3/BDD support |
| `jit/` (LLVM), `interpreter/`, `simulation/`, `fuzzer/` | 33K | 21K | eval and verification infrastructure |
| `noc/`, `contrib/`, `netlist/`, misc | ~60K | | not relevant |

The core path from IR to Verilog is about 130K lines of C++, with a test corpus of the
same size.

**Why XLS's errors are bad.** The front end isn't the cause. The back end is a compiler
built on the assumption that DSLX has already rejected bad input:

- **No warning channel.** `passes/` has 0 warnings, 224 `XLS_RET_CHECK`s and 51
  user-style errors. Across ir, passes, scheduling and codegen there are about 700
  `RET_CHECK`s.
- **Back-end errors fall into three classes:**
  1. **Malformed IR.** Our bug, which we fix by validating before emission (§4, W0).
  2. **Scheduling infeasibility.** User-facing, but XLS reports only "try
     `--clock_period_ps=N`".
  3. **Proc/channel legalization failures.** User-facing; they name bare IR nodes.
- **Source positions (`pos=`) are best-effort through optimization.** The facts are
  recorded in the xls-diagnostics memory and handled in libsynth `xls/diag.py` (BLK-4).

## 3. The per-algorithm lifecycle

Each algorithm (an analysis, the timing estimator, the scheduler, codegen, an
optimization pass) moves through these stages on its own:

| Stage | XLS's role | Native's role | Exit criterion |
|---|---|---|---|
| **S0 Observe** | implementation | none. XLS's result (schedule, per-pass IR, block IR) is imported into zuspec IR and shown to the user | the importer round-trips the corpus |
| **S1 Shadow** | implementation | runs alongside; output compared and discarded | matches XLS on the corpus, or differs only in documented ways |
| **S2 Advisory** | implementation | drives diagnostics and development-time feedback | users rely on it, and it never contradicts XLS |
| **S3 Native-first** | oracle and fallback | emits the result | QoR within an agreed band (§6); translation validation passes |
| **S4 XLS optional** | opt-in engine | default | — |

## 4. Workstreams

### W0 Up-front checking (now, alongside X2)
- ☐ **W0-1** Every semantic check runs in SV/zuspec before XLS IR is emitted: widths,
  types, channel direction and usage, proc state.
- ☐ **W0-2** A zuspec-side structural verifier on the XLS IR we emit, mirroring
  XLS's IR verifier rules.
- ☐ **W0-3** Any XLS verifier failure or `RET_CHECK` is classified as an internal
  error. Package a reproducer: our IR, flags, XLS version.
- ☐ **W0-4** Upstream the cheap fixes: CSE keeping the union of source positions; the
  0-based position off-by-one in codegen annotations.

### W1 Foundations (prerequisites for every later stage)
- ☐ **W1-1 XLS IR → zuspec IR importer.** It covers functions, procs, and later
  blocks; per-pass IR dumps; schedules (`--output_schedule_path`). This is also the
  long-term goal from X2 §3.3. Ops map directly, because zuspec IR already follows
  XLS's 2-state semantics (`sv-normative-semantics`).
- ☐ **W1-2 QoR harness.**
  - The corpus is the AI-benchmark designs (`ai-benchmark-strategy.md`) plus the X2
    corpus.
  - Metrics: area (yosys), timing (delay model; OpenSTA later), pipeline register
    bits, stage count.
  - Tracked over time, so regressions show up.
- ☐ **W1-3 Translation validation.** A miter of the IR before and after each native
  transform, checked with dv-solve's bit-blast + SAT path (`dvs_aig`, `dvs_bitblast`,
  kissat/cadical). The word-level engine caps width at 64 bits (`dvs_bvdom`,
  `dvs_problem`), so wide datapaths must use the bit-blast path.
- ☐ **W1-4 One diagnostic model.** Native analyses and the XLS error mapping
  (libsynth `xls/diag.py`) produce the same diagnostic objects with source positions,
  whichever engine found the problem.
  - Stable codes, severities, secondary locations and notes, suggested fixes,
    suppressible warnings, and documentation per code.
  - Output in two machine-readable forms: LSP diagnostics and SARIF.
- ☐ **W1-5 Provenance model,** richer than `pos=`.
  - Each IR node carries a chain from the source construct (class, field, method,
    statement), through the lowering steps, to the node.
  - When CSE merges nodes, provenance is kept as a *set*. Unrolled loops tag each
    iteration.
  - Through W1-1, the same model applies to imported XLS IR, with `pos=` as the
    lowest-fidelity input.
  - W7 depends on this. Without it, every report falls back to line numbers.

### W2 Analyses (no QoR risk; first native code to reach S2)
- ☐ **W2-1 Known-bits / range analysis on zuspec IR.** Forward abstract
  interpretation over the dataflow DAG, reusing dv-solve's `dvs_bvdom` (ternary) and
  `dvs_bvbounds` (signed/unsigned ranges) as the lattice. Both are bitwuzla ports, the
  same abstraction as XLS's ternary and range query engines. Needed: an adapter. dv-solve
  today is shaped around constraint problems, not dataflow over an IR.
- ☐ **W2-2 Development-time warnings** built on W2-1: dead high bits, constant
  conditions, unreachable branches, possible overflow and truncation.
- ☐ **W2-3 Optimization remarks from XLS.** Diff the IR before and after `opt_main`
  using source-position mappings. Reports things like "the top 28 bits of `count` were
  removed" or "`table[]` became a 1024-way mux". This needs W1-1 but no native passes.

### W3 Timing estimation
- ☐ **W3-1** A reader for XLS delay-model textprotos (Apache-2.0 data).
- ☐ **W3-2** A native critical-path estimate on zuspec IR, reported with source
  positions. Shadow check: compare with XLS's per-node `path_delay_ps` from
  `--output_schedule_path`.
- ☐ **W3-3** "Timing while you edit": run W3-2 without invoking XLS. This is the first
  case of running part of the flow natively for development-time feedback.

### W4 Scheduling (best first native transform)
- ☐ **W4-1 SDC formulation on zuspec IR,** after XLS `scheduling/sdc_scheduler.cc`.
  - Feasibility is purely difference constraints. dv-solve's `dvs_diffcycle`
    (Bellman-Ford negative cycles) together with `dvs_explain` (LCG explanations) can
    name the exact cycle of constraints that makes a schedule infeasible.
- ☐ **W4-2 Explained infeasibility (S2).** Report errors such as "II=1 is not met: the
  loop `acc → add → acc` (src.sv:L) needs 1.3 ns, the clock is 1.0 ns". This replaces
  "try `--clock_period_ps=N`".
- ☐ **W4-3 Optimal schedules.** XLS minimizes pipeline register bits with an LP
  (GLOP). dv-solve has no LP. Options: a min-cost-flow dual (network simplex), or a
  small LP such as HiGHS. A feasible but non-minimal schedule is acceptable for S1/S2.
- ☐ **W4-4 Feeding our schedule to XLS (S3 while XLS still does codegen).**
  `codegen_main` has no CLI flag for an external schedule (`lec_main` and
  `delay_info_main` read one; codegen doesn't). Options: the libxls API, or asking
  xlsynth for a flag (they're already a channel for the `eval_ir_main` request), or W5.

### W5 Codegen / block conversion
- ☐ **W5-1** Converge zuspec-synth's SV emission (`pipeline_sv_emit`, sprtl) on XLS's
  block model: pipeline registers, valid/ready flow control, FIFOs. The
  integrate-by-signature path (X2 step C) stays unchanged.
- ☐ **W5-2** Native codegen at S3 for blocks with a native schedule. XLS codegen
  remains the oracle.

### W6 Optimization (last, selective, data-driven)
- ☐ **W6-1 Pass ablation study** on the W1-2 corpus, using XLS's own instruments:
  - `opt_main --skip_passes` / `--passes_textproto`: QoR contribution of each pass;
  - `--pipeline_metrics_proto`: per-pass change counts, a cheap first ranking;
  - `--ir_dump_path`: IR after each pass, imported via W1-1, so we can see what each
    pass did to *our* designs. This is the "inspiration" channel;
  - `--passes_bisect_limit`: find the pass responsible when results diverge.
- ☐ **W6-2** Port only the passes that W6-1 shows carry most of the QoR on our corpus.
  Hypothesis to test: about 10 of roughly 60 passes. Restate them in terms of zuspec
  IR and dv-solve; don't transliterate.
- ☐ **W6-3** Replace BDD-based passes (`BddSimplification`, `BddCse`) with SAT
  sweeping / fraiging on dv-solve's AIG. dv-solve has no BDD engine, and SAT sweeping
  is the current state of the art. It is also a dv-solve showcase.
- ☐ **W6-4** Native-only passes that use knowledge XLS doesn't have (SV-level intent,
  narrowing across blocks), run as zuspec IR passes *before* XLS from S0 onward.

### W7 Reporting and analysis beyond XLS
**What XLS offers today:**
- block metrics (`codegen/xls_metrics.proto`): flop count; reg-to-reg, input-to-reg,
  reg-to-output and feedthrough delays; a per-op bill of materials, where each BOM
  entry carries source locations;
- `delay_info_main` and `sched_printer`: per-stage critical paths;
- `visualization/ir_viz`: a web viewer for the IR graph with the critical path
  highlighted;
- an area model, and per-pass pipeline metrics.

This is real analysis, but it is written for XLS engineers: IR-level and run after the
fact as a batch. It doesn't explain anything to the person who wrote the source.

**Where we have structural advantages:**
- source-level vocabulary (W1-5);
- proof-backed explanations (dv-solve);
- fast native estimates (W3, W4);
- the whole composition, not one block (X2 integration);
- a simulatable model of the same source.

**Reporting is mostly separate from implementation.** W7-1, W7-2 and W7-6 work at
stage S0, on top of XLS outputs brought in through W1-1 and W1-5. They can be the
roadmap's first visible payoff, before any native transform exists.

- ☐ **W7-1 QoR attributed to the source (S0).** Aggregate XLS's BOM and flops per
  class, method and field. Example: "412 flops; 256 come from pipelining the `mul`
  on line 30". Show stage assignment per source statement.
- ☐ **W7-2 Diagnostics with source vocabulary (S0).** Re-express mapped XLS errors
  and optimization remarks (W2-3) in terms of fields, methods, loop iterations and
  channel transactions, not IR nodes.
- ☐ **W7-3 Proof-backed explanations (needs W2, W4).** Use dv-solve explanations to
  report *why*, not just *what*:
  - the minimal set of constraints that makes a schedule infeasible;
  - the chain of reasoning that proves a bit constant;
  - why a value could not be narrowed (missed-optimization remarks, in the style of
    LLVM `-Rpass-missed`).
- ☐ **W7-4 What-if and sensitivity analysis (needs W3, W4).** Examples:
  - a curve of clock period against stages and flops ("at 800 ps: 4 stages, about
    1.3× the flops");
  - slack per source statement;
  - "making line 42 200 ps faster removes a stage".

  XLS needs a full rerun per point; a native estimator makes this interactive.
- ☐ **W7-5 System-level analysis across the composition (X2 step C).** XLS can't do
  this because it sees one block at a time:
  - throughput mismatch between channels (a producer at II=1 into a consumer at II=2);
  - required FIFO depths;
  - potential deadlock;
  - end-to-end latency per transaction path.

  dv-solve's `scheduling_graph.py` (conflict detection over mixed
  sequential/concurrent/mutex graphs) may be a starting point. This is likely the
  biggest differentiator.
- ☐ **W7-6 Correlating the model with the implementation (S0+).**
  - Annotate model simulation traces with pipeline stages, and predict latency from a
    model run.
  - Map RTL behaviour back to model events through the debug domain (structured
    observable events).
- ☐ **W7-7 Feedback in the editor (needs W2, W3).** Show as LSP diagnostics or
  inlay hints:
  - stage assignments;
  - estimated delay per statement;
  - inferred widths and dead bits.
- ☐ **W7-8 Agent-friendly output.** Structured diagnostics with suggested fixes
  (W1-4) are what lets an AI agent's edit loop converge. Measure the effect in the AI
  benchmark (`ai-benchmark-strategy.md`): better reporting should show up as fewer
  iterations and higher pass rates.

## 5. dv-solve: what it provides and what is missing

| Need | dv-solve today (`~/projects/fvutils/dv-solve`) | Gap |
|---|---|---|
| Known-bits / ternary analysis | `dvs_bvdom` (bitwuzla port) | width ≤ 64; needs an adapter for dataflow over an IR (W2-1) |
| Range analysis | `dvs_bvbounds` (bitwuzla port) | same |
| Difference constraints / schedule feasibility | `dvs_diffcycle`, with explanations | — |
| Explanations / unsat cores | `dvs_explain`, LCG, `dvs_contradiction` | map back to IR nodes and source positions |
| Equivalence / SAT sweeping | `dvs_aig`, `dvs_bitblast`, kissat/cadical, `bvsat.py` | a miter builder; a sweeping loop |
| LP / min-cost flow | none | W4-3 |
| BDDs | none | not needed if SAT sweeping replaces them (W6-3) |

These gaps belong in dv-solve's own plan when the work starts. They are not dv-solve
work in fw-hdl.

## 6. Exit criteria for S3 (native-first)

Per algorithm, on the W1-2 corpus:

- **Correctness:** translation validation (W1-3) passes on every design. The existing
  simulation tests match bit-exactly against the XLS path.
- **QoR band:** to be decided when W1-2 exists. Placeholder: area within 5% of XLS,
  timing met wherever XLS meets it, and pipeline register bits within 10%.
- **Diagnostics:** every failure the native path reports has a source position and a
  cause. That's the reason for doing this at all.

"XLS optional" (S4) needs the scheduler and codegen at S3, plus W6 at S3 for the
passes W6-1 identifies.

## 7. Suggested order

1. W0, alongside X2.
2. W1-1 importer and W1-5 provenance; XLS schedule imported and displayed (W4 at S0).
   Then W7-1/W7-2 QoR attribution and source-vocabulary diagnostics, the first
   visible payoff.
3. W3 delay-model reader and native timing estimate (S2).
4. W2-1/W2-2 known-bits/range analysis and warnings (S2); W2-3 optimization remarks.
5. W1-2 QoR harness and W1-3 translation validation.
6. W4 shadow scheduler with explained infeasibility (S1 → S2).
7. W6-1 ablation study. This decides how much of the optimizer is ever worth porting.
8. W4 + W5 at S3, with XLS still doing optimization.

After step 8, the only dependency on XLS is the optimizer, and the W6-1 data says how
much of it would have to be replaced.

## 8. Risks and guardrails

- **Starting early.** Don't start native transforms (S3) before the XLS-based product
  is proven. S0–S2 work adds value right away, and the optimizer at S3 is a 2027+
  question.
- **Transliteration.** Port algorithms (Apache-2.0, with attribution), restated in
  terms of zuspec IR and dv-solve. Copying XLS's structure would bring back the
  diagnostic-hostile design we are trying to escape.
- **Semantic drift.** Native and XLS must agree bit-exactly on 2-state semantics, or
  the oracle comparison breaks down. W1-3 enforces this.
- **Chasing upstream.** XLS changes often. Pin versions (xlsynth release), and re-run
  the W6-1 ablation when upgrading, rather than tracking every pass change.
- **Messaging.** The pitch is "XLS QoR today, more control over time". Don't publicly
  promise to deprecate XLS: the user's company is evaluating it, and "we build on XLS"
  is the stronger message.

## 9. Open questions

- The QoR band values for S3 (§6).
- LP for W4-3: a native network simplex, or an external dependency (HiGHS)?
- Does the dv-solve width ceiling of 64 bits matter for W2 analyses on wide datapaths
  (CRC, AES), or is a fallback to unknown/top for wide values acceptable?
- Is W4-4 done via libxls, or by asking xlsynth for an external-schedule flag?
- Where do native HLS algorithms live: zuspec-synth (existing sprtl scheduler,
  optimizer) or a new package?
- Where does provenance (W1-5) live: in zuspec-ir-core, as a node attribute every
  front end fills in, or as a side table?
- Which report surface comes first for W7: CLI text, an HTML report, or the LSP?

## 10. Log

- 2026-10-03: written from a design discussion. XLS sizes measured on google/xls
  `dff59c1a1`; dv-solve capabilities checked at `10e8bdc`. Parked.
- 2026-10-03: added W1-5 (provenance) and W7 (reporting and analysis beyond XLS).
- 2026-10-04: reframed by `refinement-views.md` (architecture views; refining decisions
  live in zuspec IR).
