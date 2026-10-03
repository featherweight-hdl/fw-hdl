# The AI Story — Measuring fw-hdl + XLS Against SV RTL and Plain XLS for AI Agents

*Status: strategy proposal, for review. Snapshot as of 2026-10-03. Facts about our stack
come from this workspace. Facts about published benchmarks are cited in §2 and §11.
Inferences are marked **[inf]**.*

**Companions:**
- `killer-app.md`: the product and its MVP (D1–D3), which this proposal re-orders;
- `chisel-xls-assessment.md` §7.4: "LLM-native hardware design", where AI first appeared
  as a secondary opportunity;
- `xls-phase0.md`: the X0 bring-up this depends on;
- `../fw-wb-dma/llm_benchmark_orchestrator_research.md`: dfm as a benchmark orchestrator,
  with the EEE/Inspect result schemas;
- `../fw-wb-dma-2`: the WB-DMA SPL model, plus a UVM environment that swaps
  RTL / SPL / SPL-RTL views. This is the template for an arm-neutral grader.

---

## 0. Summary

1. **This changes what the MVP is for.** Until now the AI angle was §7.4 of the
   assessment, "cheap to lean into". If the headline is *"an AI agent implementing a spec
   with fw-hdl + XLS was X% better than with SV RTL or with plain XLS"*, then the
   benchmark that produces X is the MVP's acceptance test. D1–D3 remain the engineering
   targets, but they are no longer the proof.
2. **We choose the designs, and we choose them for XLS's sweet spot.** This is a
   demonstration, not a neutral benchmark, and it says so. The designs are deep,
   statically schedulable compute: AES, FIR, GHASH, SHA, IDCT, floating point. Each must
   hit a **clock and throughput target**, and each is wrapped as a **register-programmed
   streaming engine**. That one choice puts every arm on the spot it is weakest:
   - the RTL arm must hand-pipeline a deep datapath to meet the clock, and hand-write
     stall/valid logic through the pipeline;
   - the DSLX arm writes a low-resource language, then hand-integrates CSRs, the bus and
     the top;
   - the fw-hdl arm writes the algorithm as timing-free SV and a register model. XLS
     pipelines it, and the glue is generated.
3. **The claim still needs a mechanism, not just a number.** "Our tool wins on designs we
   picked" is easy to dismiss, because we built both. The claim that survives scrutiny is
   causal and falsifiable:

   > LLMs are good at sequential, timing-free code and bad at cycle-level work: pipeline
   > balancing, valid/stall propagation, handshakes, CSR side effects. fw-hdl + XLS takes
   > all of that out of what the agent writes. So the advantage over RTL should **grow
   > with the clock target and with pipeline depth**, and the advantage over DSLX should
   > **grow with the integration surface**.

   The benchmark is built to show those two slopes, with ablations that attribute them
   to specific mechanisms (§3). Being open about the selection costs us nothing: "on the
   designs XLS is built for, fw-hdl makes AI *X%* better" is exactly the pitch.
4. **Three arms, plus two ablations, on one arm-neutral grader:**
   - **A**: SV RTL, with a strong toolkit (PeakRDL, a FIFO/skid-buffer library, lint, sim);
   - **B**: DSLX + XLS, with hand integration;
   - **C**: fw-hdl SV + XLS + generated glue.

   Every arm delivers the same pin-level top. A hidden testbench grades it at the pins:
   reference model, backpressure, reset, register programming. The QoR flow is shared too.
5. **Quality and efficiency are measured together.**
   - **Quality:** verified at the pins, *and* meets the clock/throughput target. With
     XLS-friendly designs, QoR against the RTL arm becomes a **win to claim** (timing
     closure, area at equal throughput), not merely a guardrail.
   - **Efficiency:** cost per verified design (tokens, $, turns, wall-clock).
   - **The signature chart is a clock-target sweep.** The same AES engine is specified at
     increasing clock targets, and we plot the verified-and-timing-met rate per arm.
     Arm C changes one attribute; arm A re-pipelines by hand **[inf]**.
   - **Change requests:** retarget the clock, change II, add a mode, swap the bus.
6. **"Held out" means parameterized, not obscure.** AES and FIR are memorized from
   GitHub, and that memorization helps arm A most. So we keep the famous algorithms, and
   make each instance novel in the things that matter: clock target, II, tap count and
   coefficient width, key size and mode, the register map and command format, the stream
   width. A memorized unpipelined AES does not pass a 1 GHz, II=1, CSR-programmed CTR spec.
7. **Pilot as soon as X1 can run one design end to end.** AES-128 is already in the X0
   corpus (C3/C4). Before the glue generator is done, a **compute-only pilot** on FIR and
   AES (stream in → stream out at a clock target) tests the pipelining slope, the M2 half
   of the claim. The integration half follows with M3.
8. **Our biggest AI-specific risk is that fw-hdl is a low-resource API too.** SV syntax
   is familiar to models, but `fw_port`, `fw_get_if` and `fw_schedule_static` are not in
   any pretraining corpus. The mitigations are an engineering agenda in their own right
   (§6): "guessability" probes, agent-shaped diagnostics, and skill quality.

---

## 1. Review of the current position

What the existing documents get right for an AI story, and what they miss.

**Already right:**
- **No new language.** It matters more when the author is partly a model (§7.4).
  DSLX's churn (two proc syntaxes, feature-gated generics) is precisely what makes
  low-resource languages hard for models: what the model learned may already be stale.
- **The checked subset with source-located diagnostics** (`killer-app.md` §4.3). In an
  agent loop, diagnostic quality *is* the user experience, and here the user is a model.
- **The class model as an executable spec** (`fw_view_diff`). It gives the agent a fast,
  self-checking oracle before any RTL exists.
- **Restriction as a pull, with "next rung" guidance** (§1.4). This reads naturally as
  agent guidance: "to lower this, replace the dynamic queue at line 42".

**Missing or under-weighted:**
1. **No hypothesis about *why* AI should do better.** "SV is high-resource" explains
   C > B, but not C > A, and A is the comparison most people care about. C > A has to
   come from abstraction and generated glue (§3, M2–M4).
2. **The success measures (killer-app §6) are human-effort measures** (lines written,
   steps). They need AI equivalents: pass rate, tokens, turns, wall-clock, $ per verified
   design, escaped bugs.
3. **No baseline-strength story.** A critic's first move is "your RTL arm was a strawman".
   The RTL arm needs the best conventional tooling (register generator, standard IP,
   lint, simulator) and a calibration run on a public benchmark (CVDP), so we can show
   our harness reproduces published numbers.
4. **No contamination story.** D1–D3 come from XLS's own repo and well-known standards.
   They are fine as design *families*, but each benchmark instance must be novel in its
   parameters, clock target and register map (§4.2).
5. **The fw-hdl API's learnability isn't treated as a product requirement.** For the AI
   story, the API's names, shapes and error messages are part of what is being measured.

---

## 2. What the field shows

Literature survey as of 2026-10. Full references are in §11. Numbers marked (u) come
from abstracts or snippets only.

### 2.1 Small RTL benchmarks are saturated; the remaining failures are timing, protocol and glue

- **Saturated benchmarks:**
  - VerilogEval v2: Opus 4.6 gets 90.8% single-shot, and agent systems (MAGE, VerilogCoder)
    get about 95%.
  - NVIDIA's HORIZON agent loop reaches **100%** on VerilogEval, RTLLM, ChipBench and 9
    CVDP categories.

  Its authors conclude that once loops converge, *the metrics that matter are efficiency
  and verification quality*. That is why §5 leads with cost per verified design, not
  raw pass rate.
- **Harder benchmarks still have headroom:**
  - CVDP: best 33.6% pass@1;
  - ChipBench: Opus 4.5 at 30.7%, CPU IP at most 22.2%.
- **Where failures cluster:**
  - CVDP's largest failure clusters are "Clock Domain; Protocol Violations" (55% of
    Claude's spec-to-RTL failures), "Flawed Timing", "Faulty Reset Handling" and missing
    states.
  - **CVDP's module-reuse category** (compose existing modules with glue) tops out at
    **18–25% for every model**. That is almost exactly the work our generated glue
    removes.
- **Nobody has isolated datapath vs control at matched difficulty, and nobody has
  measured how well agents pipeline to a clock target.** Our R1/R2/R3 rungs fill both
  gaps. The baseline curves (P0) are a publishable result in their own right.

### 2.2 Language matters more than model, and interfaces are where HLS dies

- **"The Representation Bottleneck"** (Fu et al., Apr 2026) is the closest prior work. It
  ran 202 tasks in 6 languages on 3 frontier models, with repair and synthesis:

  | Language | Simulation pass rate |
  |---|---|
  | Verilog | 83–88% |
  | Chisel | 70–85% |
  | Bluespec | 66–80% |
  | **HLS C** | **3–10%** |

  - The language effect is larger than the model effect (models within 1.25×).
  - **HLS C fails because of the interface, not the computation**: Bambu converts 98.7%
    of the C, but the start/done and memory ports don't match the testbench.
  - That is our thesis seen from the other side. The authors' recommended control,
    *the same interface wrapper for all arms*, is built into our rungs: R1/R2 grade every
    arm at plain ready/valid ports, and R3 makes integration an explicit, separately
    measured burden.
- **HDLAgent** (UCSC, Dec 2024) has the only quantitative DSLX numbers:
  - DSLX is about 3% with no help, and 64% on GPT-4 with a language summary, examples and
    a compiler loop (Verilog: 76%).
  - **For DSLX, the quality of the language description mattered more than compiler
    feedback.** Calling DSLX "like Rust" made results worse.
  - Over 10% of DSLX failures never recovered.
  - DSLX produced the best gate counts.
  - Implication: arm B's documentation decides arm B's score, so documentation parity
    (§4.1) is the fairness control critics will check first.
- **ReChisel** (DAC'25): zero-shot Chisel trails Verilog by 30–48 points, mostly on
  syntax. A reflection loop closes most of the gap. Low-resource penalties are real but
  recoverable with scaffolding, so we must measure **cost**, not just eventual success.

### 2.3 XLS + LLMs: one strong qualitative signal, no numbers

- **OpenAI's Jalapeño** compute die was "XLS plus Verilog" (IEEE Spectrum, Sep 2026).
  Chris Leary, who started XLS: *"the AI was much better at software-looking things. XLS
  in some ways looks like software, so it got that benefit."* No numbers were published.
  - This is the strongest public support for the thesis, and it frames our contribution
    precisely: **keep the "software-looking" benefit, drop the low-resource language,
    generate the Verilog half.**
  - We would be the first to quantify it.
- **`xlsynth/dslx-llm`** provides DSLX system prompts, problems and evaluation scripts
  (including procs). **Use its prompt as arm B's documentation baseline.** It is the XLS
  community's own best effort, which neutralizes "you crippled DSLX".

### 2.4 Methodology precedents

- MultiPL-E / MultiPL-T: one problem set, translated across languages, graded by the same
  tests. The Representation Bottleneck paper is the hardware version.
- "AI Agents That Matter": cost/accuracy Pareto plots, a simple retry baseline, held-out
  sets.
- ChipBench reports **cost per pass**, which varies up to 275× between models.
- **Contamination:** VeriContaminated finds signals close to 100% for older models on
  VerilogEval and RTLLM. New specs are mandatory.
- **Test adequacy:** RTLLM's testbenches are weak (72% kill fewer than 95% of injected
  mutants; GateTruth, Aug 2026). **The hidden grader must reach a mutation kill rate of
  at least 95% on the reference design.**
- **Error taxonomy:** NVIDIA's L1 syntax / L2 semantic / L3S (solvable with more
  samples) / L3U (unsolved by any sample). This is adopted in §5.4.

### 2.5 What makes hardware agent loops work

- **Simulation with structured state or waveform tracing is the strongest lever** (MAGE,
  VerilogCoder). Raw VCD pasted into the prompt helped only 8 of 21 models in ChipBench.
  Our `fw_view_diff` / per-channel comparison is exactly the structured form: "channel
  `ctxt`, transaction 17, expected X, got Y".
- **LLM-written testbenches are weak** (CVDP checker generation 0–25%). This is an
  argument for the **class model as the agent's oracle** (M4): in arm C, the agent's own
  executable model is the reference the RTL is checked against, so the agent never has to
  write a cycle-accurate checker.
- **Scaffolding narrows model-size gaps** (small models gain 30–140% on CVDP from task
  decomposition). This supports the "smaller model + fw-hdl" result (§4.4).
- No controlled ablation of formal vs simulation feedback exists (u).

## 3. The hypothesis, decomposed into mechanisms

Each mechanism gets a measurement or an ablation, so the result explains itself.

| # | Mechanism | Predicts | How it is isolated |
|---|---|---|---|
| M1 | **Familiar syntax.** SV is high-resource; DSLX is low-resource and churning | C and A have fewer syntax/type errors per turn than B | count compile/parse errors per turn in each arm |
| M2 | **Timing-free compute.** Writing `get → compute → put` with no cycles removes pipeline balancing and stall logic from the agent's job; XLS schedules | C ≈ B > A, with the gap rising with the clock target and pipeline depth | rung R1 vs R2 (§4.2); clock sweep on F1/F2 |
| M3 | **Generated glue.** Transactors, CSR bridge, FIFOs, top-level wiring are correct by construction | C > B, with the gap rising with the integration surface; A's and B's failures cluster in handshake, CSR and reset logic | rung R2 vs R3; failure taxonomy (§5.4) |
| M4 | **Executable spec / fast oracle.** The class model simulates in the agent's loop before RTL exists, and `fw_view_diff` checks the lowering | fewer turns to first passing design; fewer bugs escaping to the hidden grader | tokens and turns to first pass; escaped-bug rate; ablation C\no-model (no class-level test harness provided) |
| M5 | **Agent-shaped diagnostics.** The profile checker names the line and the next rung | fewer turns stuck on toolchain errors | ablation C\diag: generic messages only |
| M6 | **Separation of concerns.** Clock target, protocol and register map are attributes or generated, not hand-coded | change requests succeed more often and much more cheaply in C | rung R4 change requests |

**Expected shape [inf]:**
- **At a relaxed clock** (no pipelining needed), a bare stream-in/stream-out kernel: A
  and C are roughly at parity, and B is behind on syntax. Saying so up front is part of
  the credibility, and it is the left edge of the chart.
- **As the clock target rises:** A falls off, and C ≈ B, because both get XLS
  scheduling (M2).
- **As the register/bus surface is added:** B falls off, and A pays twice (M3).
- **Change requests:** C's cost stays flat, and A's and B's do not (M6).

The two headline charts are *pass rate vs clock target* and *pass rate vs integration
surface*. Slopes are robust to model progress: better models move the curves, but the
structural reason for the gap remains.

---

## 4. Benchmark design

### 4.1 Arms

| Arm | Agent writes | Tools available | Deliverable |
|---|---|---|---|
| **A: SV RTL (strong)** | synthesizable SV modules + top | Verilator lint/sim, yosys, PeakRDL-regblock, a small vetted IP library (sync FIFO, skid buffer, ready/valid register slice), cocotb or SV testbench scaffolding | pin-level top |
| **B: DSLX + XLS** | DSLX for compute; hand-written SV for CSRs, wrappers and top | pinned xlsynth tools (`ir_converter_main`, `opt_main`, `codegen_main`), DSLX interpreter/tests, plus all of A's tools for integration | pin-level top |
| **C: fw-hdl + XLS** | fw-hdl SV classes (compute with `timing=static`, control as SPL, register model) | fw-hdl flow (one command to RTL), class-level simulation, profile checker, schedule report, `fw_view_diff` | the generated pin-level top |
| C⁻ (ablation) | as C, but compute is written with explicit timing (SPL, no XLS) | as C | as C; isolates what XLS scheduling contributes to timing closure and area |
| C\diag (ablation) | as C | profile checker with generic error text | as C |

**Fairness rules:**
- The same model, agent harness (Claude Code headless or Inspect), turn/token/wall-clock
  budget, and machine.
- **Documentation parity:** each arm gets a skill of comparable size and quality. Arm B
  gets a curated DSLX guide pinned to the same xlsynth version. Arm A gets RTL
  guidelines and the IP library docs. Skill sizes are reported.
- Every arm may write its own tests; none sees the hidden grader.
- The arm-specific prompts are published.

### 4.2 Design selection: XLS's sweet spot, wrapped as real engines

**Selection rule.** We choose designs that are:
1. **deep, statically schedulable compute**, where XLS's scheduler does the work an RTL
   author would otherwise do by hand;
2. **specified at a clock and throughput target** that forces pipelining (II=1 at a
   clock where the unpipelined datapath fails timing);
3. **delivered as an engine**: CSR-programmed (key, coefficients, mode, length, start),
   streaming over ready/valid, with status and interrupt. That is the integration
   surface DSLX leaves to the user;
4. **backed by public reference vectors** (NIST, FIPS) or a trivial golden model
   (numpy), so the grader is unarguable.

We are explicit that the selection favours XLS. The comparison is fair *within* the
selection: every arm gets the same spec, budget and grader.

**Design families.**

| Family | Compute (XLS's job) | Engine wrapper (glue) | Parameters per instance | Reference | Status in our stack |
|---|---|---|---|---|---|
| **F1 FIR / polyphase decimator** | N-tap MAC tree, symmetric-coefficient folding, decimation by M | coefficient RAM/regs loaded over CSR; sample stream in/out; overflow status | taps 8–64, data and coefficient widths, M, rounding/saturation, clock, II | numpy | new (XLS `fir_filter.x` exists for parity) |
| **F2 AES block engine** | AES-128/256 rounds (S-box, MixColumns), key expansion | key/IV regs, mode (ECB/CTR), length, start/done/IRQ, block streams | key size, mode, unroll vs II, clock | FIPS-197, SP 800-38A | X0 corpus C3/C4; `killer-app.md` D3 |
| **F3 GHASH / AES-GCM** | GF(2¹²⁸) multiply (Karatsuba or a 4-bit table) + AES-CTR | AAD/length handling, tag compare, two islands + sequencing glue | multiplier architecture, clock, II | SP 800-38D vectors | phase 2 showcase (D4) |
| **F4 SHA-256 / SHA-3 engine** | 64-round compression or Keccak-f | message padding/length, digest readback, multi-block chaining | algorithm, rounds per cycle, clock | FIPS-180-4 / 202 | `sha256.x` exists for parity |
| **F5 8×8 IDCT / DCT** | Chen/Loeffler butterfly network over s16/s32 | block stream, quantization table in CSRs | precision, transform direction, clock | numpy / JPEG reference | `idct_chen.x` exists |
| **F6 FP32 multiply-add / dot product** | IEEE-754 FMA (denormals flushed or kept), vector dot | vector length and accumulate mode in CSRs, result stream | rounding mode, vector length, denormal handling, clock | softfloat / numpy | `fp32_fmac.x` exists |
| **F7 Streaming CRC-64 / checksum, wide** | 256–512-bit-per-cycle parallel CRC (the matrix form) | polynomial and init in CSRs, frame boundaries | width, polynomial, reflection, bytes per cycle | crcmod | X0 C1 |

**Suite structure:** each family is run at three "rungs", so that each family yields
both slopes.

| Rung | Spec asks for | Separates |
|---|---|---|
| R1 **kernel, relaxed clock** | stream in → stream out, no CSRs, a clock low enough that no pipelining is needed | the baseline: familiarity and algorithm correctness (M1) |
| R2 **kernel, aggressive clock** | the same, at a clock target that needs a deep pipeline at II=1 | pipelining (M2): A must re-pipeline, B and C get XLS |
| R3 **full engine** | R2 + CSR bus (Wishbone or APB-lite), register map, command, status, IRQ | integration (M3): B must hand-integrate, C generates |
| R4 **change requests** on a passing R3 | (a) clock ×1.5; (b) II 1 → 4 to save area; (c) add a mode (CTR → CBC, add decimation); (d) swap the bus | maintainability (M6) |

Sizing: 7 families × 2 parameter instances × R1–R3, plus 2 change requests per R3
instance. That is about 70 task instances. A **clock sweep** on F1 and F2 (4–5 clock
targets at R3) produces the signature chart.

**Contamination controls.** The algorithms are famous by design, and memorization helps
arm A most, so it biases *against* us. The instances are novel where it counts:
- parameters (widths, taps, II, clock, key size, mode) drawn per instance;
- bespoke register maps and command formats;
- spec text paraphrased per instance;
- a canary check: if a model recites a public AES/FIR core verbatim, log it. It will
  still fail R2/R3 unless it adapts the core.

### 4.3 The grader (arm-neutral, hidden)

- **The spec fixes the pin interface:** clock, reset, a CSR bus, and the stream ports.
  Every arm's deliverable is graded through the same pins, exactly as the WB-DMA
  environment swaps RTL/SPL/SPL-RTL behind one UVM bench.
- **Functional checks:**
  - reference model (Python or C) plus scoreboard;
  - directed vectors (the standard ones where they exist);
  - constrained-random traffic **with random backpressure and idle cycles**;
  - mid-stream reset;
  - register read-back and side effects;
  - a throughput check (sustained II at the specified rate).
- **Formal, where cheap:** protocol checkers (the ready/valid assertions from
  `fw-proto-kit`) bound to the ports; SymbiYosys BMC for a bounded depth.
- **QoR:** a shared yosys flow (generic or a fixed liberty), area at the target
  frequency, Fmax via OpenSTA or nextpnr on a fixed FPGA target, plus register bits.
- **Lint:** Verilator `-Wall` warnings.

- **Adequacy:** a mutation kill rate of at least 95% on the reference design for every
  family. Below that, the grader is not trusted (§2.4).

The grader is written and frozen **before** any arm is run.

### 4.4 Models

- At least three models across capability tiers (e.g. Opus, Sonnet, Haiku), plus one
  open-weights model.
- This supports a second, very quotable result **[inf]**: *a smaller model with fw-hdl
  matches a larger model on RTL*. That claim is about cost, and it is the one that
  resonates with engineering management.

---

## 5. Metrics and analysis

### 5.1 Headline metrics (pre-registered)

| Metric | Definition |
|---|---|
| **Verified rate** | fraction of (task, seed) runs whose deliverable passes the full hidden grader within budget (pass@1; pass@k reported too) |
| **Cost per verified design** | total tokens (and $ at list price) over all attempts ÷ verified designs |
| **Change-request success** | R4 verified rate, and tokens per successful change |
| **Timing met** | the deliverable closes timing at the specified clock with the specified II (shared synthesis + STA flow) |
| **QoR** | area at equal clock and throughput. **vs A: a claimed win** (XLS pipelining vs agent hand-pipelining). **vs B: parity** (same back end, within ±5%) |

### 5.2 Secondary metrics

- turns and wall-clock to the first passing design;
- lines written by the agent, split into compute and glue;
- self-reported pass vs hidden pass: **escaped bugs**, i.e. the agent says "done" and
  the grader disagrees. This is the AI-trust metric;
- toolchain-error turns (M1, M5);
- lint warnings.

### 5.3 Statistics

- At least 5 seeds per (task instance × arm × model).
- Paired by task instance.
- Report verified rate with bootstrap 95% CIs. Use a mixed-effects logistic regression
  (arm as a fixed effect; task family and model as random effects) for the headline
  "X% better".
- Test the slope claims as interactions: arm × clock target (M2), and arm × rung R2→R3 (M3).
- Write the analysis script before the run.

### 5.4 Failure taxonomy

Use two axes:
- NVIDIA's levels (L1 syntax, L2 semantic, L3S solvable by more samples, L3U unsolved);
- a hardware cause:
  - syntax/type;
  - toolchain misuse;
  - functional (compute);
  - pipeline (valid/stall misalignment);
  - handshake/backpressure;
  - CSR/side effect;
  - reset;
  - timing not met;
  - throughput;
  - incomplete (budget exhausted).

Classification is automatic where possible (the grader knows which checker fired), and
otherwise done by an LLM judge spot-checked by a human. The taxonomy chart *is* the
mechanism story: A fails in handshake/CSR/reset, B fails in syntax/toolchain and
integration, C fails in … (we need to know, and to fix it).

### 5.5 What the headline will say (template)

> On N spec instances drawn from seven XLS-class designs (AES, GCM, FIR, SHA, IDCT, FP,
> wide CRC), Claude agents using fw-hdl + XLS delivered verified, timing-closed engines in
> a% of attempts, vs b% with SystemVerilog RTL and c% with DSLX + XLS, at k× lower cost
> per verified design. At 1 GHz the RTL arm closed timing in d% of attempts, vs e% for
> fw-hdl, with x% less area. Change requests (clock retargeting, II, bus swaps) succeeded
> f% vs g%.

Only claim what the numbers show; publish the harness, prompts, tasks and logs.

---

## 6. Engineering agenda implied by the AI story

These are now product requirements, not polish.

1. **One command, spec to pin-level RTL**, with machine-readable output (JSON
   diagnostics, a pass/fail summary). Agents waste turns on multi-step flows.
2. **Agent-shaped diagnostics.** Every profile-checker rejection gives the SV line, the
   rule, and a concrete rewrite. Measure them with C\diag.
3. **API guessability probes.** Ask models to write fw-hdl components *without docs*
   from a short description, and record what they guess: names, import paths, port
   idioms. Where a model's guess is reasonable, add an alias or rename to match. Re-run
   the probes after each API change. This is cheap, and it directly attacks the
   "fw-hdl is low-resource too" risk.
4. **Skill quality.** The `fw-hdl` skill becomes a measured artifact. Track its size and
   the agent-error rate against its revisions.
5. **Fast class-model simulation in the loop.** The agent needs a seconds-scale
   "run my tests" step. Verilator class+timing, or be-py, whichever is faster for
   block-level tests.
6. **Templates for the spec shapes in §4.2:** a register-programmed engine skeleton, a
   stream proc skeleton.
7. **Stability.** Every flow bug costs arm C a run. The task families define the subset
   that must be solid, which aligns with `killer-app.md`'s "the subset is defined by
   D1–D3 first".

---

## 7. Infrastructure

- **Orchestration:** dfm, as already researched (`llm_benchmark_orchestrator_research.md`).
  Generation runs as an `llm_api` resource class; scoring as `sim`/`formal` classes.
- **Results:** Inspect-style per-run logs (token stats, reductions over seeds), exported
  to the EEE schema, with a lockfile (model IDs, prompt revisions, tool versions,
  container digest).
- **Calibration:** run arm A's harness on a CVDP subset (non-commercial categories) and
  on ChipBench (VerilogEval is saturated), and check that it reproduces the published pass rates for the same
  models. That defends against "the RTL agent was set up to fail".
- **Isolation:** one container image per arm, with tools pinned (xlsynth version as in
  `xls-phase0.md` §7) and no network access.

---

## 8. Phasing

| Phase | Content | Needs | Exit |
|---|---|---|---|
| **P0 — Harness + baselines** (now) | dfm harness; grader and reference models for F1 (FIR) and F2 (AES); run arms A and B only at R1/R2, with 1 model and 5 seeds; CVDP calibration of arm A; guessability probes for the fw-hdl API | nothing from the XLS path. Arms A and B need only Verilator, yosys and xlsynth | baseline curves for A and B on the clock sweep. **These are publishable on their own** ("how well do agents pipeline?") and tell us how much room there is |
| **P1 — Compute pilot** | arm C on F1/F2 at R1/R2 (stream in → stream out; the wrapper is the plain XLS ready/valid ports, so no glue generator is needed) | X0 exit; X1 checks; M0 plumbing | the M2 slope (A falls off with the clock, C does not) is visible, or we know why not |
| **P2 — Full suite** | F1–F7 at R1–R4; 3+ models; ablations C⁻ and C\diag | M3 (register bridge, glue generator); F3–F7 front-end coverage | pre-registered analysis run; draft headline |
| **P3 — External credibility** | publish harness and tasks; invite a third party (the XLS team is a natural fit) to re-run or add a family; write-up | — | independent replication of at least the direction of the result |

**Kill / rethink criteria:**
- **P0 shows arm A closing timing at aggressive clocks about as often as at relaxed
  ones.** Frontier agents then pipeline well, and M2 is weak. Lead with integration (M3)
  and cost instead, and re-check the clock targets: are they really aggressive?
- **P1 shows arm C failing R2 for reasons other than API misuse.** XLS or our front end
  is then the bottleneck. Fix the toolchain before P2.
- **C's failures are dominated by fw-hdl toolchain or API misuse after two rounds of
  skill and diagnostic work.** The low-resource problem then dominates; fix the API
  before scaling the benchmark.
- **The gap disappears with the strongest model.** The story then becomes cost (the
  smaller-model result) rather than capability. Decide which headline to lead with.

---

## 9. Risks to the story

| Risk | Mitigation |
|---|---|
| "You built both the tool and the benchmark", "you picked XLS-friendly designs" | state the scope openly: XLS-class designs are the market XLS addresses. Then pre-registration, a frozen hidden grader, a strong arm A calibrated on CVDP/ChipBench, a relaxed-clock rung where we expect parity, a published harness, and third-party replication |
| Contamination inflates whichever arm has public implementations | parameterized families, novel variants, canary recitation checks |
| fw-hdl is unfamiliar to models | guessability probes, aliases, skill quality (§6) |
| Tool immaturity sinks arm C | P0 on the mature SPL path first; the task families define what must be solid |
| Arm B looks bad because of DSLX churn rather than an inherent cost | pin a version, give a version-matched DSLX guide, and report syntax errors separately (M1) so readers can discount them |
| Model progress erodes the gap | lead with the slope (gap vs glue) and change requests; those are structural |
| QoR loss undercuts "quality" | QoR is a guardrail metric; arm C's compute comes from the same XLS back end as arm B |

---

## 10. Open questions

| # | Question |
|---|---|
| Q1 | Is the audience the user's company (internal XLS evaluation), the public, or both? Internal: use their own blocks as one task family. Public: everything must be releasable |
| Q2 | Does arm B get our generated glue (a "B+" arm: DSLX compute + fw-hdl integration via the XLS-IR import track)? It isolates "language" from "glue" cleanly, but needs the importer |
| Q3 | Should a human-expert arm be timed on a few tasks, for an absolute reference ("the agent with fw-hdl was N× faster than an engineer")? |
| Q4 | Which agent harness: Claude Code headless (realistic, what users run) or Inspect (cleaner instrumentation)? Possibly Claude Code inside Inspect's sandbox |
| Q5 | Budget: about 70 instances × 5 arms × 5 seeds × 3–4 models ≈ 5–7k agent runs. What spend is acceptable, and does P0 use a smaller matrix? |

---

## 11. Sources

- **Benchmarks:**
  - VerilogEval v2: https://arxiv.org/abs/2408.11053
  - NVIDIA error taxonomy (Opus 4.6 at 90.8%): https://arxiv.org/abs/2606.19347
  - CVDP: https://arxiv.org/abs/2506.14074
  - ChipBench: https://arxiv.org/abs/2601.21448
  - HORIZON: https://arxiv.org/abs/2606.28279
  - ResBench: https://arxiv.org/abs/2503.08823
  - RTL-Repo: https://arxiv.org/abs/2405.17378
  - GateTruth (RTLLM mutation adequacy): https://arxiv.org/abs/2608.12635
  - Open-model Verilog flows: https://arxiv.org/abs/2607.22759
- **Agents:**
  - VerilogCoder: https://arxiv.org/abs/2408.08927
  - MAGE: https://arxiv.org/abs/2412.07822
  - CorrectBench: https://arxiv.org/abs/2411.08510
  - CVDP task decomposition: https://arxiv.org/abs/2512.05073
- **Languages:**
  - The Representation Bottleneck: https://arxiv.org/abs/2604.17097
  - HDLAgent (DSLX): https://arxiv.org/abs/2501.00642
  - ReChisel: https://arxiv.org/abs/2505.19734
  - HLS-Eval: https://github.com/sharc-lab/hls-eval
  - Agentic HLS: https://arxiv.org/abs/2609.09526
  - "Are LLMs any good for HLS?": https://arxiv.org/abs/2408.10428
- **XLS:**
  - xlsynth/dslx-llm: https://github.com/xlsynth/dslx-llm
  - IEEE Spectrum on Jalapeño: https://spectrum.ieee.org/llms-for-chip-design
  - Hot Chips summary: https://taekim.substack.com/p/hot-chips-openai-jalapeno-presentation
- **Methodology:**
  - MultiPL-E: https://arxiv.org/abs/2208.08227
  - MultiPL-T: https://arxiv.org/abs/2308.09895
  - AI Agents That Matter: https://arxiv.org/abs/2407.01502
  - Type-constrained decoding: https://arxiv.org/abs/2504.09246
  - VeriContaminated: https://arxiv.org/abs/2503.13572
- **Internal:**
  - `../fw-wb-dma/llm_benchmark_orchestrator_research.md` (dfm orchestration, EEE/Inspect
    schemas)
  - `../fw-wb-dma-2/tests/uvm` (a multi-view grader pattern)
