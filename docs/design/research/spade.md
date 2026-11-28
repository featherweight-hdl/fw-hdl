# Spade: what fw-hdl can learn from it

Researched 2026-11-28. This note compares Spade with the fw-hdl vision and
picks out ideas worth trying. It is not a plan.

**Confidence marks:**
- **[P]** primary source (Spade docs, release notes, or Surfer docs read directly);
- **[U]** unverified, or our inference.

## What it is

Spade is a standalone HDL, written in Rust and in Rust style, that compiles to
SystemVerilog [P].
- It started as Frans Skarman's PhD work at Linköping (thesis August 2025).
  Since 2026-09 it has been maintained at Munich University of Applied
  Sciences, and it moved to Codeberg [P].
- The journal paper is "Spade – A Modern Hardware Description Language", ACM
  TRETS, January 2026, DOI 10.1145/3793550 [P].
- It is under active development:
  - v0.16 (2026-01): compiler more than 10× faster;
  - v0.20 (2026-08): LSP and copy views;
  - v0.21 (2026-11-12): `memory` construct, `gen match` [P].
- Its ecosystem is Swim (build, test, packages, LSP, tool install), a package
  index (reef.spade-lang.org) and the **Surfer** waveform viewer, which was
  built for Spade and is now used well beyond it [P].

Spade is a new language. fw-hdl is hosted in SystemVerilog and Python, and it
ships plain SV. So the lessons are about **semantics, checks and tooling**,
not syntax.

## The ideas, ranked by value to fw-hdl

### 1. Latency as a checked contract (pipelines) — try it

Spade's best idea, and its paper's headline [P]:

```spade
pipeline(4) poly(clk: clock, x: int<18>, c: [int<18>; 4]) -> int<74> { ... reg; ... }
let y = inst(3) mix_streams(clk, [s1, s2], gains);   // depth stated at the call site
```

- `reg;` ends a stage; values defined above it are read as their registered
  copies below it. `reg * N;` adds N empty stages.
- If the stated depth is wrong, the compiler errors:
  "Pipeline depth mismatch. Expected 1 got 3".
- Using a value too early is also an error: "Use of `mix` before it is
  ready", with a hint to add `reg`.
- Deepening a sub-pipeline breaks every caller that depends on its depth,
  recursively and across packages. The designer follows the errors.
- Stallable pipelines (`reg[cond];`, `stage.ready`, `stage.valid`) are
  **experimental, with known soundness issues when nested**.
  `stage.valid` starts out undefined, so reset must be held until it
  settles [P].

**Against fw-hdl.** `process-synthesis.md` §5 covers the *latency-insensitive*
case (E1 ready/valid regions). There the engine is free to change latency,
and the controllers are proven templates (§5.6). Spade covers the
**complementary** case: fixed-latency datapaths with no handshake, where
latency is part of the interface. picorv32-class cores, DSP and address paths
are full of these. fw-hdl doesn't model that case today. A fixed-latency
`step()` chain is just RTL whose latency nobody checks.

**What to try:**
- Make latency a **derived attribute in Zuspec IR**, defined for each
  component's non-E1 output relative to its inputs. Derive it from the sync
  IR (a register-count analysis).
- Have consumers that rely on it declare it. Spade forces the user to write
  the number at every call site. That conflicts with *minimal user
  specification*. Instead, derive it by default, and let a consumer pin it
  only where it relies on it, for example a `fw_latency(N)` annotation on a
  connection. Then a change shows up as an `FW-E-LATENCY` at every pinned
  consumer.
- Let these attributes feed the micro-pipelining engine. Once fixed-latency
  blocks carry a latency, an E1 region can contain one, and the controller
  can be sized from it.

Spade's stall troubles support fw-hdl's choice of **proven controller
templates** over ad-hoc stall syntax. Keep that choice, and make the
templates own reset so that the "undefined valid" pitfall can't happen.

### 2. Outputs are linear: each must be driven exactly once — try it

In Spade an `inv` (output-direction) wire must be `set` **exactly once**.
The compiler reports "Use of consumed resource" when one is set twice, and
"m2.addr is unused … a inv value which must be set" when one is never set.
Setting a wire in both arms of an `if` counts as two sets, so you write
`set w = if c {1} else {2};`. Since v0.21, an `inv` from outside an
`if`/`match` can't be consumed inside it [P].

**Against fw-hdl.** fw-hdl already rejects some of these cases:
- `FW-E-WRITE-IN`: a write to an effective input (after mirror flips).
- `FW-E-WRITE-MULTI`: an output written by two blocks.
- Undriven nets at the netlist level (`core-layer1.md`).

What fw-hdl does **not** say, as far as these docs show [U], is that every
effective output of a `comb()` is written **on every path**. A `comb()` that
writes `ready` in one branch only is a latch in the generated RTL, or a stale
value in the class model.

**What to try:** a Zuspec IR pass (not fe-sv code, per AGENTS.md) that checks
definite assignment of each effective output on every `comb()` path:
`FW-E-COMB-PARTIAL`, naming the member and the path that misses it. It's
cheap, it gives the user a clear message, and it closes a class-model/RTL
mismatch.

**Validation, not new work:** Spade's port bundles are ordinary structs with
`inv` fields, e.g. `struct Rv<T> { data: &T, valid: bool, ready: inv bool }`,
plus `.inspect()` for a read-only view [P]. They map one-to-one onto
`fw_bundle` / `fw_mirror` / `fw_monitor`. Two independent designs arrived at
the same model.

### 3. Type-aware waveforms (Surfer) — try it, highest user-visible win

Surfer translates raw bits back into language values: enums by name, structs
by field, `Option` as `Some(x)`/`None`. It also reads FTR **transaction
streams**, has a headless server mode, accepts scripted command files, and
can be driven externally through WCP (`--wcp-initiate`; the protocol details
are unconfirmed [U]) [P].

**Against fw-hdl.** Lowering flattens classes into one parameterized module
per class, and bundles into prefixed pins. The user's view of the design (the
bundle, its role, its payload type, the transaction) is lost in the VCD/FST.
That is the gap a class-based user feels first when debugging generated RTL.

**What to try:**
- Have lowering emit a **sidecar type map** that maps each net to its Zuspec
  type, bundle, role, and field. It is a by-product of the IR, so it costs
  little.
- Use the map to drive a Surfer translator, or a plain signal-grouping
  script. Each bundle then appears as a group with its payload decoded.
- Have monitors (`fw_monitor`, the protocol-kit monitors) record
  **transactions to FTR**, so Surfer shows them as transaction streams above
  the pins. Writing FTR from SV needs a DPI writer [U: effort not yet
  checked].
- Later: on a scoreboard mismatch, use WCP to open the waveform at the
  failing time.

This helps every user of the IP library and fw-hdl-dv, and it's tool-neutral
(VCD/FST, Verilator).

### 4. No implicit width changes — a lint, not a semantics change

In Spade, `+` grows the result by a bit and can't overflow, while `+.` wraps
at the same width. `trunc`, `sext` and `zext` are explicit: "Spade never
implicitly casts integer widths". Widths can be type-level expressions, such
as `int<{N + 1}>` and `uint<{uint::bits_for(C)}>` [P].

fw-hdl can't change SV's context-determined widths in user source. But
truncation in sync code is a classic source of bugs, and the IR knows both
widths.
- **Try:** an IR lint that warns on implicit truncation in sync assignments,
  silenced by an explicit cast. It would be more precise than Verilator's
  `WIDTH` warnings, because it runs before parameterization blurs the widths.
- On the Python (zdc) side, which has its own semantics: consider adopting
  "grow by default, wrap explicitly" for arithmetic [U: a Zuspec-wide
  decision, not an fw-hdl one].

### 5. Tests that speak the design's types — small, fits existing work

Spade's cocotb integration uses values written in Spade syntax:
`s.i.a = "Some(5)"` and `s.o.sum.assert_eq("5")` [P].

fw-hdl's rule is *no string references* in its Python DSLs. Spade's strings
are values, not references, but the same lesson applies through typed
objects. The **cocotb bridge flavor** (`wb_xtor`) should give and take the
protocol kit's payload types as generated Python dataclasses, decoded from
bits, never as raw integers. This matches the transactor bridge contract
already in place.

### 6. Smaller points

- **Clocks aren't data.** In Spade, `clock` is its own type, and it can't be
  muxed or registered. `Copy`/`Data` traits gate what may go in a register
  [P]. fw-hdl could reject clock-as-data in sync IR with an error such as
  `FW-E-CLOCK-DATA`, if it doesn't already [U].
- **Errors with a fix.** Spade's messages point to the source and suggest the
  fix ("add more `reg` statements"). This is worth copying for fw-hdl's
  `FW-E-*` messages, which today name the problem but rarely the remedy [U].
- **One-command experience.** `swim test`, `swim build` and
  `swim install-tools` [P]. fw-hdl has ivpm and dfm. The lesson is that new
  users should have one documented entry point per action.

## Where fw-hdl is already ahead (don't copy)

- **Clock domains and crossings.** Spade has no clock-domain typing and no
  CDC checks [P: none found]. fw-hdl's sync/task domains and checked
  crossings (`sync-task-domains.md`) go further.
- **Verification.** Spade has no formal features. Its `assert` is "silently
  ignored when simulating with Verilator". Generic units can't be tested
  directly; you wrap them in a concrete harness [P]. fw-hdl has equivalence
  and BMC in its flow, a DV library, and parameterized modules per class.
- **Interop.** Spade leaves struct packing undefined, so a `#[no_mangle]`
  extern can't return a struct [P]. fw-hdl has a defined packed layout and
  plain-SV output (`core-layer1.md` M8(b)). That is a real advantage for
  shipping IP.
- **Adoption.** A new language has to win users before it can win designs.
  fw-hdl's SV hosting, plus its plain-SV output, avoids that hurdle.

## Suggested follow-ups

1. Write up idea 1 (latency attribute plus pinned checks) as a design note
   next to `process-synthesis.md` §5. It's the most novel idea, and it feeds
   the picorv32 reach plan.
2. Prototype idea 2 (definite assignment of `comb()` outputs) as a Zuspec IR
   pass. It's small and stands alone.
3. Spike idea 3: emit the type sidecar from one example (`rr_merge` or
   `wb_xtor`) and get a Surfer view with decoded bundles.
4. Research **Filament** (Nigam et al., PLDI 2023). It takes Spade's latency
   idea to full *timeline types*, which check when every signal is valid.
   It's the strongest prior work for idea 1 [U: not yet read].

## Sources

- spade-lang.org; docs.spade-lang.org: pipelines, dynamic pipelines, stage
  references, wires and `inv`, copy views, the type system, registers,
  generics, type-level operations, simulation, external Verilog.
- blog.spade-lang.org: release notes for v0.16, v0.20, v0.21.
- surfer-project.org; docs.surfer-project.org/book.
- F. Skarman, O. Gustafsson, "Spade – A Modern Hardware Description
  Language", ACM TRETS, 2026, DOI 10.1145/3793550 (not read in full).
