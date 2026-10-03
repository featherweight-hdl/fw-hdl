# The Integration Thesis — fw-hdl's Killer App

*Status: position and roadmap, for review. No new implementation implied beyond what is cited.*

> **Refined by `one-model-many-hosts.md`.** The integration argument and the SPL/HLS/CAG
> model below still hold, but the center is now the zuspec IR with SV, Python, PSS and C as
> hosts, and the lead target is the DMA's *operation model*; synthesis (§9–§11 here) is the
> expansion.
>
> **Revised by `chisel-xls-assessment.md` §6.4 (2026-10).** For scheduled compute,
> XLS is now the **primary back end**, not a hedge. Authors write SV, analysis emits XLS
> IR for `timing=static` components, and our automation integrates the generated RTL
> (transactors, FIFOs, CDC, glue). The native scheduler (S4/S5) becomes a fallback.
> Synthesizable semantics are SV 2-state-normative (`chisel-xls-assessment.md` §4.4).

**Companions:**
`actions.md` (actions, buffers, resource claims),
`multi-view-rearchitecture.md` (views, blackboxes, factories),
`dynamic-coverage.md` (derived coverage),
`hw-sw-interaction-patterns.md` (the HW/SW construct catalog),
`reference/diplomacy-integration.md` (negotiation kernel),
`reference/formalizing_protocols_and_roles.md` (SPL↔RTL abstractors),
`python/fw/hdl/CENTRALIZED-LOWERING-DESIGN.md` and `SPL-IR-CONTRACT.md` (the lowering),
`examples/cag-risc/cag_risc_c.svh` (a first CAG sketch).

---

## 0. Summary

1. **The product is integration, not a better compiler.** fw-hdl wins by joining two
   things that are disjoint in every flow today: (a) the *environments* hardware
   teams already run — SV simulators, Verilator, UVM, cocotb, SymbiYosys, yosys, commercial
   synthesis, firmware builds — and (b) the *description methodologies* that are
   currently separate languages, tools and teams: RTL, HLS, transaction-level models,
   test intent (PSS), register specifications, and formal properties.
2. **The three description methods are one model.** SPL (sequential processes with
   explicit timing), HLS (timing-free dataflow scheduled by a compiler), and CAG
   (constrained activity graphs: actions scheduled by data and resource availability) are
   all *actions over channels and resources*. They differ only in **who decides when
   things happen**: the author, a static scheduler, or generated run-time hardware. One
   IR, one knob (§3).
3. **The same description serves design and verification.** An activity graph with its
   nondeterminism left in is a specification of every legal behaviour. Resolved by a
   policy, it is an implementation. Left unresolved, it is stimulus, a coverage space,
   and the reference against which the implementation is checked for refinement (§6).
   No existing tool does all of these from one source — not XLS, not Bluespec, not PSS.
4. **Adopt XLS's semantics, not its language.** Precise channel semantics, timing-driven
   scheduling with characterized delay models, cross-level differential checking, and
   tests/assertions/covers that survive into RTL (§7). Do not adopt DSLX, Bazel, or
   XLS's optimizer.
5. **Bluespec is the precedent and the warning.** It proved that synthesizing a
   scheduler from rules yields good hardware. It failed on adoption: a new language, a
   separate toolchain, and a verification story disconnected from everyone else's.
   Those are exactly the gaps fw-hdl's integration story closes (§2.2).
6. **Beachhead: register-programmed data-movement and offload engines** (DMA,
   descriptor-queue engines, crypto/compression offload). They exercise all three
   methods at once, they are dominated by HW/SW interface and verification cost, and
   fw-hdl already has the MMIO lowering, the HW/SW pattern catalog, and the protocol
   kits aimed at them (§9). Not CPUs first.
7. **Proof point: one DMA engine description** that runs as a firmware bring-up model,
   synthesizes to RTL within a stated QoR budget, generates its own stimulus and
   coverage, and checks itself (class view vs RTL view) inside an unmodified UVM or
   cocotb environment (§10).
8. **The biggest risks** are constraint semantics in synthesis (defining vs choosing),
   QoR of generated scheduling logic, debuggability of dynamically scheduled RTL, and
   scope — three compilers is three ways to be mediocre (§8).

---

## 1. The problem: every handoff is a rewrite

A typical block today passes through five or more descriptions, each in its own language,
owned by a different group, kept consistent by review and hope:

| Description | Typical language | Owner | What it is for |
|---|---|---|---|
| Architecture / performance model | SystemC, Python, C++ | architects | throughput, sizing, what-if |
| Register specification | SystemRDL, IP-XACT, spreadsheet | design + SW | HW/SW contract |
| RTL | SystemVerilog | designers | the product |
| Datapath (sometimes) | C++ HLS, DSLX, Chisel | designers | productivity on compute |
| Reference model / scoreboard | SV classes, C, Python | verification | the checker |
| Test intent / scenarios | PSS, UVM sequences | verification | stimulus |
| Coverage model | SV covergroups | verification | completeness |
| Formal properties | SVA | formal team | proofs |
| Firmware model / driver | C | software | bring-up before silicon |

Each row is a re-expression of the same behaviour. Each boundary between rows is a
place where the descriptions drift, and most of the effort in a verification schedule is
spent *finding* that drift. The industry's partial answers each integrate one or two rows
and leave the rest:

- **HLS** (XLS, Catapult, Vitis) joins "datapath" to "RTL" — and adds a new language and a
  separate simulation world.
- **PSS** joins "test intent" across platforms — but never touches the design.
- **Chisel/Diplomacy** joins "parameters" across a design — inside a new language, with
  verification bolted on afterwards.
- **UVM** standardizes the verification environment — and nothing else.
- **SystemRDL/IP-XACT** join "registers" to RTL and C headers — and nothing else.

fw-hdl's claim is that a single class-based description, in the language the whole team
already reads, can cover most rows, and that the remaining rows can *consume* it through
tools the team already runs.

---

## 2. What the field teaches

### 2.1 XLS

XLS is Google's HLS toolchain: the DSLX language, a bit-accurate SSA dataflow IR, an
optimizer, a scheduler, and a Verilog code generator. What makes it good is almost
entirely independent of DSLX:

- **Procs and channels (CSP).** A proc is state plus a `next` activation; it interacts
  with the world *only* through channel ops with exact semantics — blocking `recv`,
  `recv_non_blocking`, conditional `send_if`/`recv_if`, and tokens that order side
  effects. State updates are `next_value` nodes with mutually exclusive predicates.
  The docs are explicit that non-blocking ops make a design latency-sensitive, i.e. no
  longer a pure Kahn network.
- **Timing is chosen, not written.** An SDC scheduler (an LP over difference constraints,
  integral by total unimodularity) places ops into stages under `--clock_period_ps` or
  `--pipeline_stages`, a throughput bound (`--worst_case_throughput`), and I/O
  constraints (`--io_constraints`). Delay models (`unit`, `sky130`, `asap7`) are
  characterized by sweeping each op over bit widths and fitting `a·w + b·log2(w) + c`.
- **One IR, executed at every level.** DSLX interpreter, IR interpreter, LLVM JIT, and
  Verilog simulation all run the same design. A fuzzer generates random programs and
  cross-checks all four; Z3 proves optimized IR equivalent to unoptimized
  (`check_ir_equivalence_main`), proves quickchecks (`prove_quickcheck_main`), and
  checks netlists (`lec_main`).
- **Tests are language constructs.** `#[test]`, `#[test_proc]`, `#[quickcheck]`,
  `#[fuzz_test]`; `assert!`, `cover!`, `trace_fmt!` survive into the generated SV.
- **Codegen as knobs.** Channels become `_data/_vld/_rdy` ports; `--flop_inputs/outputs`
  with `flop|skid|zerolatency` kinds; configurable inter-proc FIFOs; reset polarity and
  style; RAM request/response channels rewritten to SRAM ports (`--ram_configurations`).

Where XLS hurts, per its own docs, issues, and user reports:

- **Adoption friction.** "Experimental … not an officially supported Google product";
  DSLX changes without backward compatibility; Bazel builds take hours (binary tarballs
  and conda packages exist).
- **Interfaces.** Streaming ready/valid, single-value wires, and the RAM rewrite. Any
  other protocol is a hand-written adapter.
- **Proc networks.** A fall-2025 Cornell course report describes sparse docs, a systolic
  array that deadlocked at pipeline depth ≥3, a default-FIFO bug, and a golden example
  that would not lower to Verilog. New-style procs had a cluster of IR-lowering bugs in
  2026.
- **Microarchitecture control** is indirect (scheduler flags). Resource sharing via
  mutual exclusion is recent work.
- **Verification is separate.** DSLX tests run in the DSLX world; `cover!` does nothing in
  iverilog; nothing connects to a UVM or cocotb environment except by hand.
- **Single clock** per block; no CDC story found.
- The durable criticism from its 2020 launch still applies: not high-level enough to
  hide timing, not low-level enough to predict it, and hard to map RTL back to source.

### 2.2 Bluespec

Bluespec's guarded atomic rules are, in this document's vocabulary, **actions with
guards and resource claims**, and its compiler synthesizes the scheduler (conflict
analysis, urgency, firing logic). It showed that this produces competitive hardware for
exactly the control-heavy, contention-heavy designs HLS handles poorly. It did not win
broad adoption: a new language (first Haskell-flavoured, then BSV), a separate toolchain,
and a verification flow disconnected from the SV/UVM world. **The technology was right;
the integration was missing.**

### 2.3 PSS

PSS describes legal behaviour as actions with flow objects (buffers, streams, states)
and resource claims, composed into activities, with constraints. Tools solve it into
concrete scenarios for multiple platforms. It is a *verification* language: it never
produces the design. But its model — data- and resource-driven scheduling of actions —
is the same model a dynamically scheduled microarchitecture implements.

### 2.4 Dynamic HLS (Dynamatic and relatives)

Academic work on dynamically scheduled circuits (elastic handshakes, tokens flowing
through a dataflow graph) shows that data-driven scheduling synthesizes well where static
schedules are pessimistic — at the cost of handshake overhead, which a hybrid of static
and dynamic scheduling recovers. That hybrid is exactly the SPL/HLS/CAG split below.

### 2.5 The pattern

| | New language? | Design | Verification | Test intent | Multiple scheduling styles |
|---|---|---|---|---|---|
| XLS | yes (DSLX) | ✔ static | own tests only | — | static only |
| Bluespec | yes (BSV) | ✔ rules | separate | — | dynamic (rules) |
| PSS | yes | — | stimulus | ✔ | — |
| Chisel | yes (Scala) | ✔ structural | bolted on | — | explicit only |
| **fw-hdl (target)** | **no (SV classes)** | ✔ | ✔ same source | ✔ same source | **explicit, static, dynamic** |

---

## 3. The unifying model

### 3.1 One vocabulary

Everything is built from four things fw-hdl already has or has designed:

- **Components** — the `fw_component` tree, elaborated by build → connect (and, per the
  diplomacy design, negotiate).
- **Channels** — `fw_port`/`fw_export` over typed APIs (`fw_put_if`, `fw_get_if`,
  `fw_reqrsp_if`, protocol-kit role APIs).
- **Resources** — claimable, possibly pooled, things: functional units, register file
  ports, buffer slots, bus masters (`resource_pool_c`, `resource_share` in
  `cag_risc_c.svh`; buffer pools in `actions.md`).
- **Actions** — closures over a body, inputs, outputs and claims (`actions.md`).

### 3.2 One knob: who decides when

| Method | Timing decided by | Source shape | Lowers to | Best for |
|---|---|---|---|---|
| **SPL** | the author, explicitly | `run()` with `tick()`, protocol beats | FSM, exactly as written (`zuspec.synth.spl`) | control, sequencing, protocol engines |
| **HLS** | a static scheduler, at compile time | `run()` loop with **no** timing, pure `function`s | pipelined datapath, II and stages chosen | fixed-latency compute |
| **CAG** | generated hardware, at run time | actions with buffer/resource claims, activities | datapaths + synthesized scheduler (guards, arbitration, hazards) | contention, out-of-order, sharing |

These are not three front ends. They are three *binding times* for the same decision
over the same IR. A single component may mix them: a CAG orchestrates actions whose
bodies are HLS-scheduled functions, triggered by an SPL register-programming front end.

### 3.3 The channel contract (from XLS)

Every lowering, checker and transactor depends on channel semantics, so they are pinned
first and written into the SPL IR contract:

- **Operations:** blocking `put`/`get` (exist), plus non-blocking `try_put`/`try_get`,
  `can_put`/`can_get`, and `peek`. Today `fw_std_pkg` has only the blocking forms — this
  is a concrete gap.
- **Attributes on the endpoint:** depth (0 = rendezvous/zero-latency, N = FIFO),
  flow-control class (streaming / single-value), and ordering guarantees.
- **Ordering:** program order within a process is the token order. SV's sequential
  semantics provide what XLS needs explicit tokens for.
- **Determinism class:** a component using only blocking ops is latency-insensitive
  (Kahn); one using non-blocking ops is marked latency-sensitive. The class is visible to
  the scheduler, the differential checker (§6.2), and the deadlock analysis.

### 3.4 SPL — explicit timing

What exists: `run()` coroutines of awaited beats lower to FSMs through the transparent,
no-magic lowering now centralized in `zuspec.synth.spl`; register-driven FSMs (MMIO
Phase A) lower with a register block and a structural top. Timing the author writes is
kept exactly. This remains the default.

### 3.5 HLS — the timing-free activation rule

The key adoption from XLS, stated as a rule on existing source:

> A `run()` loop whose body contains channel operations and computation but **no explicit
> timing** (`tick()` or timed beats) is one *activation*. It is a candidate for static
> scheduling into a pipeline with a declared throughput.

```systemverilog
virtual task run();
    forever begin
        in.t.get(x);          // channel op: activation boundary
        y = f(x);             // pure SV function over packed types
        out.t.put(y);         // channel op
    end
endtask
```

Rules that keep the "no magic" commitment intact:

- Scheduling is **opt-in per component** (an attribute: target clock or stages, target
  II). Without it, the loop lowers through the transparent FSM path as today.
- The scheduler **always emits a readable schedule report** — which op landed in which
  stage, the critical path, register count — in the spirit of XLS's `benchmark_main`
  and IR visualizer.
- **The clock period comes from the design**, not a command-line flag: the component's
  clock domain carries a period attribute, propagated by the negotiation kernel.
- Pure SV `function`s over packed types are the HLS unit of computation. They must be
  checked against a synthesizable profile (§8.1).

What exists: `zuspec-synth` has an SDC scheduling pass (`passes/sdc_schedule.py`), hazard
analysis, forwarding and stall generation — but its clock period is "used only for
informational" purposes and there is no delay model. The scheduler is present; timing is
not driving it.

### 3.6 CAG — data- and resource-driven timing

An action fires when its inputs are available (buffers), its claims can be granted
(resources), and its guard holds. A CAG's activities compose actions sequentially, in
parallel, by selection, and by repetition. Synthesis produces:

- **datapaths** for the action bodies (via SPL or HLS lowering),
- **readiness logic** from buffer occupancy and claim availability,
- **arbitration** where several actions compete for a resource,
- **hazard/ordering logic** where actions share state (`state_c` in `cag_risc_c.svh`).

The unresolved heart of CAG-for-synthesis is constraints. In `cag_risc_c.svh` two kinds
are mixed:

| Kind | Example | Synthesis meaning | Verification meaning |
|---|---|---|---|
| **Defining** | `out.rd == in.t[3:0]` | a function: compile to logic | a checker |
| **Choosing** | which instance of `regs` to claim; which ready action to fire | a **policy**: priority, round-robin, age, … | a stimulus dimension and coverage axis |

A constraint that is neither functionally determined nor a declared choice point is a
synthesis error. This split must be **decidable and explained by the tool** before CAG is a
design language rather than a test-generation language (§8).

### 3.7 One IR

The SPL IR contract (`SPL-IR-CONTRACT.md`) extends rather than forks:

- channel endpoints carry the §3.3 attributes;
- processes carry a **scheduling class**: `explicit` (today), `static` (§3.5), `dynamic`
  (§3.6);
- actions, flow objects and resource claims become IR nodes. `zuspec-ir-core`'s
  concurrency primitives (`SpawnStmt`, `SelectStmt`, `CompletionSetStmt`, queue ops) are
  the starting vocabulary, per `REUSE-AUDIT.md`;
- choice points are explicit nodes with an optional bound policy.

One IR means one set of back ends: be-sv for RTL, be-sw/be-py for executable models, and
the same IR feeding checker and coverage generation.

---

## 4. Integration axis 1: description methodologies

What "integrated" means concretely, pair by pair:

- **SPL ↔ HLS.** One `run()` may hold both: explicit beats for protocol handling around a
  timing-free compute loop. The lowering partitions at timing statements.
- **CAG ↔ HLS/SPL.** Action bodies are SPL or HLS code. The CAG decides *when* an action
  runs; the body's lowering decides *how*.
- **Registers ↔ everything.** The register model (`fw_reg_block`, `fw_reg_set`) is the
  HW/SW contract. MMIO lowering already turns `wait_change`/`update` into register-block
  ports. The same model produces firmware headers and drives CAG activities
  (a doorbell write launches an activity).
- **TLM model ↔ RTL.** The class view *is* the transaction-level model. It runs in the SV
  simulator directly, with no clocks per transaction where the channels are bound
  class-to-class. There is no separate architectural model to keep in sync.
- **Test intent ↔ design.** The CAG's choice points are test intent (§6.3).
- **Parameters ↔ structure.** The negotiation kernel (`reference/diplomacy-integration.md`)
  propagates widths, address maps, clock domains (and hence clock periods for the
  scheduler), and inserts adapters. XLS's `config`/`spawn` elaboration does a strict subset.

---

## 5. Integration axis 2: environments

| Environment | How fw-hdl plugs in | Status |
|---|---|---|
| SV simulators (commercial, Verilator) | the source *is* SV; class views run natively | exists |
| UVM | fw components live beside or inside UVM envs; ports bind to sequencers/monitors | pattern exists; kit to build |
| cocotb | generated RTL is plain SV; transactors bind the same channels | to build |
| Formal (SymbiYosys, EQY) | protocol kits ship back-to-back formal components; `tests/formal/` | exists for kits |
| Synthesis (yosys/nextpnr, commercial) | generated RTL is lint-clean plain SV, readable | exists (blinky, MMIO) |
| Firmware | register model → headers; be-sw → C model of the block | partial |
| Build / flow | pip + pyslang; DV Flow Manager tasks; IVPM packages | exists |
| Pin protocols | protocol kits map a channel to ready/valid, Wishbone, AXI, … | ready/valid kit exists |
| Multiple clocks | clock-domain tree; a channel crossing domains gets an async FIFO inserted at negotiation | domains exist; insertion designed |
| Memories | `fw_mem_if` + a view that selects an SRAM macro | interface exists |

Each row is a place XLS stops at its own boundary. The two rows most worth emphasizing:

- **Protocol kits generalize XLS codegen.** XLS turns a channel into ready/valid. fw-hdl
  turns a channel into whatever a registered transactor implements, and inserts an
  SPL↔RTL abstractor where a class view meets an RTL view
  (`reference/formalizing_protocols_and_roles.md`).
- **No new language.** Everyone on the team can read the source. Adoption is one block at a
  time, and the output is a normal SV module that can be dropped into an existing design.

---

## 6. The verification duality

This is the part no existing tool offers.

### 6.1 One source, five roles

| Role | Derived from |
|---|---|
| Design | the CAG + policies, lowered (SPL/HLS/CAG) |
| Reference model | the same classes, executed as the class view |
| Stimulus | the CAG's unresolved choice points, solved by randomization |
| Coverage | the actions, claims, buffers, choice points and debug sites (`dynamic-coverage.md` M1–M8) |
| Checker | refinement: every observed RTL behaviour must be a legal CAG behaviour |

### 6.2 Class view vs RTL view (`fw_view_diff`)

XLS's fuzzer checks XLS against itself. fw-hdl can check the design against itself
**inside the user's own environment, under the user's own stimulus**:

- every boundary is an `fw_port`, so a harness can place the class view and the RTL view
  behind a splitter on the input channels;
- output channels are compared **per channel, in order, independent of cycle timing**
  (valid for latency-insensitive components, §3.3); latency-sensitive components are
  compared against the CAG's legal set instead of a single trace;
- the same comparison runs as a bounded proof with SymbiYosys/EQY, reusing the protocol
  kits' formal components on both sides.

### 6.3 Nondeterminism as a feature

A specification CAG deliberately leaves choices open ("any ready descriptor may be
serviced next"). The implementation binds a policy. Verification then has a principled
target: **drive the specification's choice space as stimulus, measure it as coverage,
and check that the implementation's behaviour is always one of the legal ones.** Swapping
the policy (round-robin → priority) re-runs the same tests against the same
specification unchanged.

### 6.4 Property tests and proofs, in SV

- `rand` + constraints over a pure function's inputs is XLS's `#[quickcheck]`.
- Emitting that function as a combinational module and running `sby prove` against a
  specification function is `prove_quickcheck`.
- SV `assert`/`cover` in class code, and `fw_dbg` sites, carry into generated RTL as
  `assert`/`cover`/`$display`, so the coverage model in `dynamic-coverage.md` measures the
  same things in both views.

---

## 7. What to adopt from XLS, and where it lands

| Adopt | fw-hdl home | Effort |
|---|---|---|
| Precise channel semantics; non-blocking ops; depth attribute | `fw_std_pkg`, SPL IR contract | small |
| Timing-free activation → static schedule (§3.5) | `zuspec.synth` scheduling class, opt-in | medium |
| Characterized delay models (width sweep + curve fit, via yosys/ABC or OpenSTA); import XLS's Apache-2.0 sky130/asap7 data to start | zuspec-synth | medium |
| Throughput (II) and I/O constraints as component attributes | negotiation attributes | small |
| Schedule report and critical-path view | zuspec-synth + docs | small |
| Cross-level differential checking | `fw_view_diff` (§6.2) | medium |
| quickcheck / prove-quickcheck | SV `rand` + SBY | small |
| assert/cover/trace survive lowering | be-sv + `fw_dbg` | small–medium |
| Codegen knobs (flop in/out kinds, FIFO kinds, reset style) | lowering config + transactor choice | small |
| Bit-width narrowing | lowering pass | small |
| RAM channel rewrite | `fw_mem_if` views | medium |

**A hedge worth a prototype: XLS as a back end.** *(Superseded: this is now the primary path for scheduled compute; see `chisel-xls-assessment.md` §6.4.)* Emit XLS IR from Zuspec IR for pure
functions and statically scheduled loops, run `opt_main` + `codegen_main` from XLS's
prebuilt binaries, and wrap the result in fw-hdl transactors. This buys XLS-grade
datapaths immediately, gives the native scheduler a benchmark to beat, and fits the
"many back ends behind one IR" architecture. Long term, the native scheduler stays so the
transparency and schedule-report commitments hold.

**Do not adopt:**

- **DSLX** or any other new surface language.
- **XLS's optimizer wholesale** *(for our own lowerings; on the XLS back-end path, `opt_main` runs as part of XLS — `chisel-xls-assessment.md` §6.4)*. Gate-level cleanup belongs to yosys/commercial synthesis
  downstream. Narrowing is the one IR-level pass that pays for itself.
- **Bazel** or any build requirement beyond pip.
- **XLS's single-protocol codegen** as the user-facing interface. Channels map to pins through transactors; on the XLS path, generated glue wraps XLS's ready/valid ports, driven by its codegen signature.

**Do adopt XLS's one real advantage, differently:** everything written in DSLX is
synthesizable by construction; SV lets people write things that are not. fw-hdl needs a
strict synthesizable-profile checker with clear, source-located errors — run in CI and
ideally the editor. zuspec-dataclasses' profile checker is the model.

---

## 8. Risks and kill criteria

| # | Risk | Why it matters | What retires it |
|---|---|---|---|
| R1 | **Constraint semantics** (§3.6) | Until defining vs choosing is decidable, CAG cannot be a design language | A classifier over the `cag_risc_c` and DMA constraints with zero unclassified cases and tool-explained errors |
| R2 | **QoR of generated scheduling logic** | Designers abandon tools that cost area or frequency | DMA proof point within the §10 budget against a hand-written reference |
| R3 | **Scope: three compilers** | Three half-finished lowerings is worse than one good one | The single IR (§3.7); ship SPL → HLS → CAG in order, each usable alone |
| R4 | **Debuggability** | Dynamically scheduled RTL is opaque | Action/site names carried into RTL signal names and `fw_dbg` records; schedule reports |
| R5 | **Audience** | PSS is a verification vocabulary; designers do not know it | Incremental on-ramp: SPL alone is useful; CAG appears only where contention exists |
| R6 | **Synthesizable subset** (§8.1) | SV permits non-synthesizable code silently | The profile checker |
| R7 | **Dual elaboration drift** | The SV kernel and the Python static elaborator must agree (diplomacy O-D5) | The differential oracle extended to negotiated attributes |
| R8 | **Differential checking of latency-sensitive designs** | Timing-independent stream comparison does not apply | Refinement against the CAG's legal set rather than a single trace |

**Kill criterion for the CAG leg specifically:** if R1 cannot be closed for the DMA
engine, CAG remains a verification-modeling feature (still valuable: stimulus and coverage
from the design's own structure) and the design-side claim is dropped. SPL + HLS + the
integration story still stands without it.

### 8.1 The synthesizable profile

A short, enforced list: packed types only in synthesizable paths; no dynamic allocation
after elaboration; loops bounded at elaboration; `function`s pure; channel ops only
through ports; class handles resolved at elaboration. Violations are reported at the
source line with the reason, not as a lowering failure deep in the IR.

---

## 9. Beachhead: data-movement and offload engines

**Why this domain:**

- It uses all three methods in one block: SPL for register programming and command
  handling (the MMIO work), HLS for the transform datapath (checksum, crypto round,
  compression), CAG for contention between channels, buffers and bus ports.
- Cost is dominated by the HW/SW interface and by verification — exactly where
  integration pays — not by the last few percent of area.
- fw-hdl already has the pieces: MMIO FSM lowering (Phase A done; Phase B targets
  arbiters), `hw-sw-interaction-patterns.md` (doorbell, queue, interrupt, lifecycle),
  protocol kits, derived coverage.
- It is universally re-built. Every SoC has several.

**Why not CPUs first:** crowded, judged almost purely on PPA, and a mature hand-written
open ecosystem to compare against. `cag-risc` stays a useful stress test of the CAG
semantics, not a product claim.

---

## 10. The proof point

**One description of a multi-channel DMA engine** — register block, descriptor fetch,
per-channel state, a shared bus master, an optional inline transform — that:

1. **Runs as a firmware bring-up model:** the class view, bound class-to-class, drives a
   C driver through the register model with no RTL in the loop.
2. **Synthesizes to RTL** through SPL (registers, commands), HLS (transform), and CAG
   (channel arbitration, bus-master sharing). Target: within **15% area and 10% Fmax**
   of a hand-written reference on the same flow; stated before measuring, not fitted
   after.
3. **Generates its own verification content:** stimulus from the CAG's choice points
   (channel interleavings, descriptor shapes), coverage from actions/claims/choices/debug
   sites.
4. **Checks itself in an unmodified environment:** `fw_view_diff` in an existing UVM
   testbench and in cocotb; a bounded formal refinement check on the arbitration.
5. **Swaps policy without touching tests:** round-robin → priority arbitration re-runs
   the same suite against the same specification.

**Headline metric:** total design + verification effort (source lines owned, testbench
lines written, weeks to coverage closure) against the conventional flow for the same
engine. Area/frequency is a gate, not the pitch.

---

## 11. Roadmap

Ordered by dependency; each stage is useful on its own.

| Stage | Content | Depends on | Exercised by |
|---|---|---|---|
| **S1** | Channel contract: non-blocking ops, depth, determinism class, into `fw_std_pkg` and the SPL IR contract | — | `tests/intf_pc`, protocol kits |
| **S2** | `fw_view_diff` for latency-insensitive components | S1, existing lowering | blinky, MMIO tests, rv kit |
| **S3** | Synthesizable profile checker | — | all lowering tests |
| **S4** | Timing-free activation rule + schedule report, unit delay model | S1, S3 | a pipelined transform block |
| **S5** | Characterized delay models; clock period from the clock-domain attribute | S4, negotiation kernel | same, ice40 + one ASIC library |
| **S6** | XLS-IR back-end prototype (benchmark) — **promoted: primary path, first vertical slice; no longer depends on S4** (`chisel-xls-assessment.md` §6.4, §8) | S1, S3 | same block, both back ends |
| **S7** | CAG constraint classifier (defining vs choosing) | — | `cag_risc_c`, DMA sketch |
| **S8** | CAG lowering: readiness, arbitration policies, hazards | S7, lowering C5 (fork/join/select) | MMIO Phase B arbiter, DMA |
| **S9** | CAG-derived stimulus + coverage; refinement checking | S7, dynamic coverage | DMA |
| **S10** | DMA proof point (§10) | S2, S5, S8, S9 | — |
| **S11** | Automatic CDC FIFO insertion; SRAM views | negotiation kernel | DMA with a second clock |

S1–S3 are small and immediately make the existing flow more credible. S2 is the most
visible demonstration of the integration claim and should come early.

---

## 12. Open questions

| # | Question |
|---|---|
| Q1 | Is the defining/choosing split (§3.6) always syntactically visible, or does it need an explicit annotation on choice points? |
| Q2 | What is the minimum policy vocabulary (priority, round-robin, age, weighted) that covers real engines without becoming a language of its own? |
| Q3 | Do actions need to be first-class in the SV kernel, or can they be a library over `fw_component` + `fw_runnable` (as `actions.md` sketches)? |
| Q4 | Where does refinement checking run — in the simulator (online, against the class view), in formal, or both? What is the latency-sensitive fallback? |
| Q5 | Is a static schedule ever allowed to change observable channel timing of a latency-sensitive component, or must scheduling be restricted to Kahn components? |
| Q6 | ~~XLS back end: prototype only, or a supported option for teams that want XLS QoR?~~ **Decided:** primary path for `timing=static` compute (`chisel-xls-assessment.md` §6.4) |
| Q7 | How much of PSS's surface (activities, `select`, `schedule`, flow objects) do we mirror by name, so PSS-literate verification engineers recognize it? |

---

## 13. Sources

- XLS documentation: https://google.github.io/xls/ — DSLX reference, `dslx_std`, procs
  tutorials, IR semantics, passes list, scheduling, codegen options, delay estimation,
  tools, solvers, fuzzer, IR visualization, proc-scoped channels design doc.
- XLS repository, releases and issues: https://github.com/google/xls (issues #4925–#4927,
  #4932; PR #4952).
- XLS[cc]: https://github.com/google/xls/blob/main/xls/contrib/xlscc/README.md
- Cornell CS6120 (fall 2025), Allo → XLS back end report:
  https://www.cs.cornell.edu/courses/cs6120/2025fa/blog/allo-xls-backend/
- Antmicro, "Accelerating digital block design with Google's XLS" (2023):
  https://antmicro.com/blog/2023/09/accelerating-digital-block-design-with-googles-xls
- Hacker News discussion at XLS launch (2020): https://news.ycombinator.com/item?id=24354083
- Bluespec: guarded atomic actions and scheduler synthesis (BSV/Bluespec compiler, now
  open source as `bsc`).
- Accellera Portable Test and Stimulus Standard (PSS).
- Dynamatic: dynamically scheduled HLS (Josipović et al.).
