# picorv32 reach: one process-level description, three payoffs

Status: plan (2026-11-26). No code yet.

The aim is to show *reach*: one process-level description of an RV32I core
gives, through a combination of techniques,

1. a fast behavioral model;
2. a range of implementations with measured PPA, connected to their buses
   through generated transactors;
3. verification that is cheaper and more complete than RTL-level practice,
   in particular method-level formal analysis that is smaller and faster
   than riscv-formal, even when the target is the lowered RTL.

picorv32 is the reference point because it is well known, has RVFI, and is
supported by riscv-formal. It is heavily hand-tuned for Fmax and area, so the
claim is *not* "we beat picorv32 at its own design point". The claim is
breadth: from one source we reach several design points, one of which is
competitive, plus a simulation model and formal results that RTL can't give.

## User benefit

- **Architects:** a single description of the core runs at instruction-set
  simulator speed (~17M instr/s measured earlier, ~75× the RTL) and is the
  same description that is implemented and verified. No separate ISS to keep
  in step.
- **Designers:** change the bus (Wishbone, picorv32 native memory, zero-time
  memory) or the micro-architecture without touching the core's description;
  the PPA table shows what each choice costs.
- **Verification engineers:** the instruction-set properties are written once,
  as methods, and proved completely (not to a bound) on the method-level
  model; the RTL is then covered by a refinement proof that the generator sets
  up, instead of ~40 deep BMC runs. The same spec checks third-party RTL
  through an RVFI monitor and serves as the simulation scoreboard.
- **The project:** evidence for the method-level claim on a design people
  recognize, and a concrete driver for the Zuspec formal engine and dv-solve's
  verification direction.

## 0. Status

| Step | What | State |
|------|------|-------|
| A1 | Port the process-level core to the canonical packages; memory through a crossing to `wb_xtor` | not started |
| A2 | Re-establish correctness: rv32ui and RVFI record-for-record against picorv32 | not started |
| A3 | Re-measure simulation speed (class model, behind WB pins, lowered netlist) | not started |
| B1 | Register file in a RAM primitive; re-measure area | not started |
| B2 | Variant table: bus bindings × micro-architectures, vs picorv32 | not started |
| V0 | Baseline: riscv-formal on picorv32 | not started |
| V1 | riscv-formal on the lowered core's RVFI pins | not started |
| E0 | Engine probe: one-step method proof on a small design, bitwuzla backend | not started |
| V2 | Instruction properties on the method-level model (our engine) | not started |
| V2s | Same obligations through sby (attribution run) | not started |
| V3 | Refinement of the lowered core against the method-level model | not started |
| V4 | Method-level spec on picorv32 through an RVFI monitor | not started |
| S | Structure catalogue (§5): ablation measurements per property | not started |
| D | dv-solve: which §5 properties belong inside the solver (§6) | survey done; mapping in §6.2 |

Track A comes first; everything else needs the ported core. V0 and E0 can run
in parallel with A1.

---

## 1. Starting point

From the earlier packets (old `fw-hdl` API, not the canonical packages):

- `~/projects/packets/fw-picorv32`: process-level class model
  (`src/spl/fw_picorv32.svh`, 239 lines), lowered pin top, side-by-side
  benches. 36/36 rv32ui reach TOHOST; directed programs match picorv32
  record-for-record over RVFI.
- `~/projects/packets/fw-picorv32-retiming2`: delay model and schedulers;
  results in `syn/results-step*.md`; open items in `impl-plan.md` §6,
  `sched-plan.md` §7, `lifting-and-collapse.md` §6.
- `~/projects/zuspec/zuspec-example-mls-riscv-sav/zpicorv32`: line-for-line
  RTL port in Zuspec; within 3.1% of picorv32 LUTs on iCE40 (the "lift RTL
  up" rung).

Measured (yosys `synth_lattice` + nextpnr-ecp5, LFE5U-85F speed 6; Verilator
5.052 for speed):

| | fw, as written | picorv32 |
|---|---|---|
| Sim speed (class model) | ~17M instr/s | ~0.22M instr/s (RTL) |
| LUT4 | 5,119 | 1,437 + 32 DPR16X4 |
| Fmax | 55.9 MHz | 94.7 MHz |
| CPI | 3.13 | 6.58 |
| ns / instruction | 56 | 69 |

The area gap is mostly the register file in flops and muxes. The delay
scheduler met its clock targets but added cycles on every instruction's path,
so ns/instruction got worse; it is kept off this plan's critical path.

What is new since then: sync crossings and generated transactors. The core's
process code no longer runs into the bus pins; it talks to a transactor
through a ready/valid crossing, which is a register boundary (timing) and a
binding point (flexibility, and formal decomposition).

## 2. Track A: the core on the canonical packages

- **A1.** Re-express the process-level core with `fw-hdl-spec`:
  - one `step()` per instruction (fetch, decode, execute, retire);
  - memory through an API port, bound to a sync crossing whose other side is
    the generated `wb_initiator` transactor (`examples/wb_xtor`);
  - RVFI as a method-level API port (one call per retirement), with a
    generated transactor to the RVFI pins for RTL benches and riscv-formal.
- **A2.** rv32ui and the directed programs, compared record-for-record with
  picorv32 over RVFI. The fast bench binds the memory port to a zero-time
  class memory; the pin bench uses the transactor.
- **A3.** Simulation speed for: class model; class model behind WB pins;
  lowered netlist; picorv32 RTL. Same program, same Verilator.

Location: `examples/picorv32/` in this repo, with picorv32's `picorv32.v`
taken from the fw-picorv32 repo (see open question Q1).

## 3. Track B: implementation points

- **B1.** Register file in a RAM primitive (2R1W, or two 1R1W copies). Target:
  area within ~1.5× picorv32. Without this no PPA statement holds up.
- **B2.** From one core description, a table of variants:
  - bus: Wishbone, picorv32 native memory interface, (later) AXI-lite;
  - micro-architecture: multicycle as written; fetch overlapped with execute
    through a deeper fetch crossing.

  Columns: LUT4, FF, RAM, Fmax, CPI on the rv32ui mix and a Dhrystone-like
  program, ns/instruction. picorv32 in every table, including where we lose.
- Later (not on the critical path): a calibrated delay model and SRAM mapping
  feed back into the scheduler work in fw-picorv32-retiming2.

## 4. Track C: formal

### 4.1 Why riscv-formal is expensive

RVFI is already a transaction (one record per retired instruction), and
riscv-formal's per-instruction spec modules are effectively methods. The cost
is in how they are checked:

- one BMC run per check: ~40 instruction checks for RV32I, plus `reg`,
  `pc_fwd`, `pc_bwd`, `causal`, `unique`, `liveness`;
- each run unrolls the whole RTL from reset until a retirement lands on the
  trigger cycle (15–30+ cycles on a multicycle core);
- the result is bounded; a full proof needs hand-written invariants;
- the consistency checks exist because the RTL hides architectural state
  across cycles and they rebuild it from RVFI over time.

### 4.2 The method-level alternative

- **V2, instruction properties on the model.** Collapse `step()` into one
  transition; memory results are free inputs. Prove
  `∀ state, mem results: rvfi(step(state)) ⊨ spec`. No unrolling, complete.
  `reg`, `pc_fwd`, `causal` and `unique` hold by construction or reduce to
  the next-state PC.
- **V3, refinement of the lowered RTL.** The lowering knows the state
  encoding, which FSM state is the method boundary, and where architectural
  state lives. It emits that correspondence with the netlist; the engine
  proves that every retirement in the netlist matches a `step()` (1-inductive
  given the emitted invariants). Instruction semantics are never re-checked
  on RTL.
- **V4, third-party RTL.** The method-level spec, bound to picorv32's RVFI
  pins through a generated monitor transactor. On sby this is still BMC on the
  whole RTL: the gain is authoring size and reuse, not solver time. Later the
  RTL can be lifted into IR and run on our engine.

### 4.3 Experiments and fairness

| ID | Run | Engine | Reports |
|----|-----|--------|---------|
| V0 | riscv-formal on picorv32 | sby | checks, depth, total solver time |
| V1 | riscv-formal on lowered core | sby | same |
| V2 | instruction properties, method level | ours (bitwuzla) | time, complete?, spec lines |
| V2s | V2's obligations as a combinational module | sby | separates *method-level* gain from *engine* gain |
| V3 | lowered core refines model | ours | time, complete? |
| V4 | our spec on picorv32 via RVFI monitor | sby | spec size vs V0, time |

Claim to test: V2 + V3 are complete, smaller and much faster than V1; V2 vs
V2s shows how much the engine adds on top of the abstraction.

### 4.4 The engine

- Works on Zuspec IR, not on Verilog; lives on the Zuspec side (fw-hdl is a
  front end). Candidate home: a Zuspec formal package, reusing what fits from
  `~/projects/zuspec/zuspec-be-fv-simplify` (early, Dec 2025).
- Solvers are peers behind an engine interface: bitwuzla first, z3 for
  cross-checks, dv-solve as it gains the capabilities in §6. No solver is
  central.
- Starts from off-the-shelf solvers. Everything in §5 that can be done as
  preprocessing or query decomposition is done in the engine, so it works
  with any backend; what needs solver-internal support is listed for dv-solve
  (§6).
- Reference only (old front end): `python/fw/hdl/formal/` (SMT-LIB QF_BV);
  zuspec-synth netlist k-induction miters.

## 5. Structure a method-level description exposes

This is the central question of the formal track: which properties of a
method-level description allow algorithms that a generic solver, given a
flattened netlist or a monolithic SMT query, can't use. Each is measured by
ablation (turn it off, re-run V2/V3).

| # | Property of the description | Algorithm it enables | Why generic solvers miss it |
|---|------|------|------|
| M1 | **Method granularity.** A method call is an atomic transition; awaits occur only at port calls. | One-step obligations; induction at method boundaries; no design-level unrolling. Loops inside a method are bounded and unrolled locally. | A netlist only has clock cycles; the boundary between transactions must be rediscovered as an invariant. |
| M2 | **Explicit, typed architectural state.** Register file and memory are arrays with known index ranges; PC is a field. | Array theory with lazy read-over-write lemmas, instantiated only for the ≤2 reads and 1 write a step touches. | After lowering, the register file is 1024 flops and mux trees; bit-blasting it dominates the query. |
| M3 | **Ports as boundaries.** A port call's result is constrained only by the port's protocol contract. | Assume-guarantee per port; callee abstraction; transactors proved once and reused across designs. | No notion of a component boundary or contract; everything is one cone. |
| M4 | **Pure functions shared by spec and implementation** (ALU ops, immediate decode). | Uninterpreted-function abstraction with congruence: equal calls on equal args give equal results, no bit-blasting of adders, shifters or comparators. Word-level structural hashing before any bit-blasting. | The sharing is lost when both sides are flattened to bit-level gates. |
| M5 | **Top-level case structure from the source** (decode `match` on opcode/funct). | Split into independent per-case queries along the source's own structure; run in parallel; share the common prefix incrementally. | Cube-and-conquer has to guess split variables; they rarely match the decode structure. |
| M6 | **Data independence and symmetry.** Control depends on register indices, not values; registers x1..x31 are interchangeable. | Symmetry reduction (prove for one symbolic register); data abstraction; width reduction where control is width-independent. | Symmetry is not visible in a netlist; riscv-formal's `reg` check does this reduction by hand. |
| M7 | **Known refinement map from lowering.** The generator knows state correspondence and the method-boundary state. | Translation validation per lowering pass; 1-inductive refinement with emitted invariants; no invariant search. | For hand-written RTL the map must be supplied by a person or found by IC3/PDR. |
| M8 | **Query families.** Many near-identical obligations: per instruction, per variant, per bus binding. | Incremental solving; lemma and learned-clause reuse across the family; caching proved obligations so a variant re-proves only what changed (e.g. only the crossing refinement when the bus binding changes). | Each sby run starts cold; nothing is shared between checks or between design variants. |
| M9 | **Declared refinement relations on connections** (E0–E4 in `docs/design/automated-lifting.md`). | Choose the weakest relation that a connection needs (e.g. in-order, latency-tolerant) and check that, not cycle equivalence. | Equivalence checkers only know cycle-exact (or sequential with a fixed latency). |

Which side each belongs on:

- **Engine (preprocessing / decomposition, works with any solver):** M1, M3,
  M5, M6, M7, M9, and the caching part of M8.
- **Benefit from solver-internal support:** M2 (array lemma strategy tuned
  to bounded per-step access), M4 (word-level reasoning with UF before
  bit-blasting), M8 (lemma reuse across a query family, beyond push/pop),
  M5 (shared-prefix incremental scheduling). These are dv-solve's targets
  (§6).

## 6. dv-solve

dv-solve's current focus is producing good random solutions; its purpose is
optimizing for verification problems, including method-level formal. The
formal track gives it a concrete benchmark family (V2/V3 obligations, in
SMT-LIB and in its own problem format) and a ranked list of capabilities from
§5.

### 6.1 What exists (survey, 2026-11-26)

- **Main** (`~/projects/fvutils/dv-solve`, C core, ctypes Python, SMT-LIB2
  executable `dv-solve-smt2`):
  - own word-level CDCL (interval/bound literals, lazy clause generation,
    difference-cycle and GF(2) passes) and a bit-blast path (bitwuzla-derived
    AIG with structural hashing; kissat one-shot, CaDiCaL incremental);
  - QF_BV, QF_UFBV, QF_ABV, QF_AUFBV; small arrays become mux forests,
    lemmas-on-demand arrays are opt-in (`DV_ARRAY=1`,
    `docs/word_level_array_lazy.md`);
  - incremental sessions keep learned clauses across `pop` (selector
    literals; `docs/fw_hdl_property_session.md`);
  - vs others: ~1.55× slower than bitwuzla and ~15% faster than z3 on
    perfcompare tiers 1–3; on the fw-hdl affine-proof scorecard 107/108 vs
    bitwuzla 73.
- **`~/projects/fvutils/dv-solve-formal`** (branch `mballance/formal`,
  6afa6b8, 2026-10-24, not merged; uncommitted native-SVA work):
  - `dv_solve.formal`: transition-system model (inputs, clocks, state and
    array state, constraints) with checked or trusted hints (Enum, OneHot,
    Fsm, Counter, PipelineGroup, Handshake, Invariant, Equiv); SVA-style
    property IR v1;
  - BMC and k-induction on CaDiCaL; traces replayed, proofs re-checked by
    certificate;
  - phase-1 results (`docs/formal_phase1_results.md`): 3,626/3,626 verdicts
    match on wb2axip and sby examples; 7.2× faster than yosys-smtbmc by
    geomean; memories are expanded to registers (the sby `memory` example is
    slower than sby);
  - zuspec-be-fv has a dv-solve back end (`zuspec.be.fv.dvsolve`, branch
    `formal-z1`, uncommitted) that matched 37/37 directives.
- **Planned, not built:** IC3/PDR (incl. interval-cube generalization),
  BTOR2, CEGAR localization, UF datapath abstraction, symmetry
  (IC3PO-style), Houdini, a shared word/bit learning core, and a formal
  engine working directly on Zuspec IR
  (`docs/formal_benchmark_design.md` §6.4,
  `docs/formal_engines_for_tl_specs.md`,
  `dv-solve-formal/docs/formal_pivot_research_2026-10-24.md`). Related
  fw-hdl specs: `~/projects/featherweight-hdl/fw-hdl/` `tl-formal-spec.md`,
  `spl-formal.md`.
- **No method-level formal engine exists yet.**

### 6.2 Mapping §5 onto dv-solve

| § 5 | dv-solve today | What this plan asks of it |
|-----|----------------|---------------------------|
| M1 | transition-system model; BMC/k-ind | a *method-step* model: obligations over one transition, no unrolling; the engine supplies them |
| M2 | lemmas-on-demand arrays in main (opt-in); formal expands memories | lazy arrays in the formal path, bounded per-step access as a hint |
| M3 | Handshake hint | port contracts as assumptions; transactor proofs cached and reused |
| M4 | QF_UFBV accepted; UF datapath abstraction planned | UF for shared pure functions, refined lazily (CEGAR) only where needed |
| M5 | cube-and-conquer engine | cubes taken from the source's case structure, shared prefix kept incremental |
| M6 | symmetry planned (`formal_engines_for_tl_specs.md`) | register-file symmetry as a declared hint (one symbolic register) |
| M7 | Equiv / Invariant hints (checked or trusted) | the lowering emits these; 1-inductive refinement |
| M8 | session keeps learned clauses across `pop` | reuse across a query family and across design variants (proof cache keyed on IR hashes) |
| M9 | — | relation-specific refinement checks (E1–E4), engine side |

### 6.3 Approach

- The engine (on Zuspec IR) does the decomposition and emits each obligation
  to bitwuzla and to dv-solve, through the same decomposition, so
  differences are the solver's alone. The dv-solve route goes through
  `dv_solve.formal` / its C API, not only SMT-LIB2, so hints (M2, M6, M7)
  reach it.
- V2/V3 obligations become a benchmark family in dv-solve's corpus.
- Order for dv-solve work, by expected payoff on V2/V3: M7 hints and M8
  reuse (already partly there), then M2 lazy arrays in the formal path, then
  M4 UF abstraction, then M6 symmetry.

## 7. Risks

- **V3 depends on the lowering emitting its correspondence.** New work in the
  lowering; probe it on a small design (E0) before picorv32.
- **picorv32 Fmax.** Not a safe headline; ns/instruction and breadth are.
- **Scheduler work.** Stalled before; kept off the critical path.
- **Fair comparison.** riscv-formal is a mature, general tool; V2s exists so
  the engine's contribution and the abstraction's contribution are reported
  separately. Report V4 honestly: little or no solver-time gain on
  third-party RTL.
- **Scope creep into IP/VIP.** The WB transactor is used, not extended.

## 8. Open questions

- **Q1.** Where the ported core lives: `examples/picorv32/` here
  (recommended while the canonical packages move), or the fw-picorv32 repo.
- **Q2.** Engine home: a new Zuspec package, or `zuspec-be-fv` (it already
  has a dv-solve back end on branch `formal-z1`, uncommitted). Recommended:
  `zuspec-be-fv`, once `formal-z1` and dv-solve's `mballance/formal` are
  committed and merged.
- **Q3.** Property surface for the instruction spec: Python (zuspec
  dataclasses) or SV (fw-hdl-spec), or both lowered to the same IR. See
  `docs/design/lean-positioning.md` §8 for the spec-layer direction.
- **Q4.** Whether to import riscv-formal's `insns` generator as the source of
  the per-instruction spec, so V2 and V0 check literally the same semantics.
