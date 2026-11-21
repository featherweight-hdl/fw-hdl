# Core layer 2: processes (issues and recommendations)

Status: **decisions settled 2026-11-17.** The owner amended decision 5
(processes are pinned to the component's domain and to its interfaces'
domains, §4.4) and left the others as recommended. The plan that
implements them is kept in the work packet like the protocol-kit plan.

This file follows the form of [core-domains.md](core-domains.md): the
issues, what exists, and a recommendation for each.

Inputs:
- [core-protocol-kit-prep.md](core-protocol-kit-prep.md) §14.1: the five
  requirements that transactors and monitors (§6 there) put on layer 2,
  and §3.5, the time a self-timed connection needs.
- [core-layer1.md](core-layer1.md) §1 "Out of scope" and §3.3
  "Layer 2": `read()`/`write()` add methods but change no layer-1
  declaration; values live behind `fw_impl_if`, request-update style.
- [core-domains.md](core-domains.md) §0 items 1 and 5, §9 "Out": a
  process runs in its component's domain; `tick`, `wait`, `in_reset()`,
  the run lifecycle and `reset_state()` were left to layer 2; a domain
  is realized where its API is used.
- The old core's sync layer, which is the reference to port:
  - `docs/methodology/sync-logic.md` (commit, settle, step; write rules;
    reset-force; the pin bridge; lowering);
  - `src/sync/*` (`fw_sync_kernel`, `fw_steppable`, `fw_combinational`,
    the `fw_rv_pin_in`/`fw_rv_pin_out` bridges);
  - `python/fw/hdl/fe/elab/sync*.py` (the lowering to `always_ff` /
    `always_comb`, parameterized per class);
  - fw-proto-axi-new `design-sync-rtl.md` §3.5 (mixing `run()` and
    `step()` in one component).
- `roadmap.md` "Basic RTL (glue logic)": implementing `fw_comb_if` or
  `fw_step_if` is detected automatically; several methods are combined
  through a closure that implements the interface (a macro now, an
  annotation later); a comb/step pair may share plain locals (comb
  settles, then step runs); interacting comb blocks go through
  `fw_signal`; each variable or signal has one writing call chain,
  checked statically.
- `docs/methodology/timing.md`: untimed and timed code. That is the
  synthesis track, and layer 2 does not take it on (§10).

## User benefit

What a user of fw-hdl gets from layer 2:

1. **Clocked logic written as a class, emitted as plain RTL.** A
   component writes `step()` (registers) and `comb()` (wires) against its
   ports and bundles. fe-sv lowers them to `always_ff` and `always_comb`
   in the same parameterized module layer 1 already emits, with no
   per-signal annotation: whether a signal is a register or a wire
   follows from which process writes it (§4).
2. **The same class runs in a simulator, cycle-accurate.** rt-sv runs
   `step()` and `comb()` with the same edge semantics, so a class model
   and its lowered RTL agree cycle for cycle. Conformance checks it.
3. **Procedural models and test code in the same terms.** A `run()` task
   waits on its domain's edges and drives and samples the same ports. A
   transactor is an ordinary component: `run()` on the method side,
   `comb()`/`step()` on the pin side, and only the pin side becomes RTL.
4. **Clocks and resets come from domains, not wiring.** A process runs in
   its component's clock and reset domains, or in those of the interfaces
   it drives. `tick()`, `in_reset()` and
   `reset_state()` go through the domain capability; nothing is
   connected by hand.
5. **Class models run beside wrapped RTL.** A generated pin bridge joins
   class signals and RTL pins in one simulation, with comb paths settled
   in the same time step, so a class-level transactor drives an IP's
   pins with zero added latency.
6. **Fast models keep real time.** A byte-level UART connection takes a
   frame time, from the protocol's configuration (prep §3.5), because
   class code can wait for a time as well as for an edge.

---

## 0. Status

| Item | Status |
|---|---|
| This doc | decisions settled 2026-11-17 (§11; decision 5 amended) |
| Plan (L2.2) | written (work packet `layer2-plan.md`) |
| Implementation | not started; gates protocol-kit Part B (K9–K11) |

---

## 1. Requirements

From prep §14.1, numbered as there (R2.n):

| | Requirement | Where here |
|---|---|---|
| R2.1 | `read()`/`write()` on signals and bundle members, with request-update | §3 |
| R2.2 | `comb`/`step` registration; `run()` tied to the component's clock and reset domains, with an edge wait | §4, §5 |
| R2.3 | comb semantics on bundle members, on the effective (mirror-flipped) direction, so a `comb` that writes `ready` settles in the same edge | §4.3 |
| R2.4 | defined visibility of `run()`'s writes: a call drives `valid` and `data` in its own cycle and returns on the handshake edge (prep decision 8) | §5.2 |
| R2.5 | rt-sv: the kernel, settle and the pin bridge; fe-sv: lowering `comb`/`step` (`run()` stays simulation-only) | §6, §7, §8 |

From prep §3.5:

| | Requirement | Where here |
|---|---|---|
| R2.6 | class code can wait for a `time` (the timed channel delays a delivery by `PROTO::xfer_time(...)`) | §9 |

---

## 2. What exists

**In the new core: nothing that runs.**
- The spec's `fw_signal #(T)` has `create`, `connect` and `tie` only.
  `semantics/signals.md` has a "Reserved (layer 2)" paragraph and no
  more.
- rt-sv elaborates and stops: `fw_elab #(T)` builds the tree, checks it
  and prints `fw_elab: ok`. There is no kernel, no value storage and no
  settle.
- fe-sv lowers structure only: components, signals, connections, ties,
  externs, domains (clock and reset ports) and the protocol sockets.
- The domain layer (`fw_domain #(K)`, `fw_clock_domain`,
  `fw_reset_domain`) is done. Its clock `params_t` has derivation fields
  (`div`, `mul`, `phase_deg`) but no period.

**In the old core: a working sync layer** (`sync-logic.md`):
- three process kinds: `step()` (registered by `add_step()` through
  `fw_steppable`), `comb()` (`add_comb()` through `fw_combinational`) and
  the component's `run()` task;
- cur/nxt value holders (`fw_sig_holder`; no request-update by name);
- **per-field** sync/comb marking on struct ports (`set_comb()`), with
  write rules checked by the kernel;
- an edge in three phases: commit, settle (whole passes of every `comb()`,
  bound 64), step; `run()` resumes after the kernel at an edge;
- reset-force: in reset, a peer reads each field's reset value;
- the pin bridges `fw_rv_pin_in`/`fw_rv_pin_out` (`COMB=1` for zero
  latency): an input pin change writes the field and settles at once;
  sync fields go to the pins nonblocking;
- lowering: `step()` to `always_ff`, `comb()` to `always_comb`, sync
  fields to registers, comb fields to wires; one parameterized module
  per class; a settle weaver (static schedule) replaces naive settle.

It is written on old-core types: struct ports, not signals and bundles,
and transaction ports that are now sockets. Its semantics carry over; its
API does not.

---

## 3. Signal values (R2.1)

**Issue.** Layer 1 promised `read()`/`write()` without changing a
layer-1 declaration. They are the signal's own value, not a separate
concern, so the capability-layer rule (core-domains "API pattern") does
not push them off the class: layer 1 already reserved them as methods.

**Recommendation.**
- `fw_signal #(T)` gets `function T read()` and `function void write(T v)`.
  Ports and bundle members inherit them. Bodies are tool-supplied (§4.1
  of layer 1); storage is behind `fw_impl_if`.
- **Read** is legal on every direction. **Write** to an *effective*
  input (after mirror flips) is an error: `FW-E-WRITE-IN`, reported
  statically by fe-sv and at run time by rt-sv.
- **Request-update.** `write()` stores a pending value; the kernel makes
  it visible at the update point that the writer's process kind defines
  (§4). Nobody sees a half-applied edge.
- A connected net has one value: `read()` on any member of the net reads
  it. A tie reads as its constant.
- No masked or per-field writes: a packed struct is written whole
  (`signals.md` raised the question; keep it out until a design needs it).

---

## 4. `comb` and `step` (R2.2, R2.3)

### 4.1 Registration

**Issue.** The old core registered processes by calling `add_step(this)`
/ `add_comb(this)` after implementing an interface class. The call is
redundant: the interface already says it. And `comb()`/`step()` as
virtual methods of `fw_component` would grow the core class.

**Recommendation.** Interface classes, with registration derived:
- `interface class fw_step_if; pure virtual function void step(); endclass`
- `interface class fw_comb_if; pure virtual function void comb(); endclass`
- A component `implements` one or both. Elaboration finds them by
  `$cast`; there is no `add_*` call (roadmap "Basic RTL").
- **Several blocks in one component** (roadmap: "combined through a
  closure"): a macro, `` `fw_comb(name) `` / `` `fw_step(name) ``,
  declares a small class that implements the interface and calls
  `name()` on its parent, so a component may have several `comb`
  methods without one method doing everything. Each becomes its own
  `always_comb`/`always_ff` (§7). A later sv-weave annotation can
  replace the macro with no change in meaning.
- Both are **functions**: they cannot wait. Waiting belongs to `run()`.

### 4.2 Register or wire follows from the writer

**Issue.** The old core marked each port field sync or comb with
`set_comb()`. That is a declaration the user must keep consistent with
the code, and the kernel then checks that they did.

**Recommendation.** No marking. A signal's kind is derived:
- written by `step()` or `run()`: a **register** (visible after the
  edge, NBA-like);
- written by `comb()`: a **wire** (visible at once, settled);
- written by both, or by two blocks: `FW-E-WRITE-MULTI` (the roadmap's
  one writing call chain per signal);
- written by nobody in the class tree: driven from outside (a port
  input, an extern pin, a tie), as in layer 1.

fe-sv finds the writers statically; rt-sv learns them on the first write
and reports the same error. A protocol's bundle needs no
sync/comb annotation either: for rv, a target that computes `ready` in
`comb()` makes it a wire; one that registers it in `step()` makes it a
register.

### 4.3 Bundles: the effective direction

**Recommendation.** Bundle members are signals; §3 and §4.2 apply to them
on their effective direction. A mirror's `comb()` may write `ready` (out
for it) and read `valid` and `data` (in for it); the settle (§6) runs it
in the same edge, which is R2.3. Writing `valid` from the mirror is
`FW-E-WRITE-IN`.

### 4.4 Domain of a process

**Decision (2026-11-17, owner's amendment).** A component's processes are
pinned to its resolved domain (`fw_clock_domain::get(this)`, and the
reset domain likewise) **and** to every further domain its interfaces
resolve to (core-domains §2 `set(intf, dom)`). A component whose
interfaces are in two clocks (the cdc_fifo of core-domains §2) writes its
crossing logic itself; it does not need children for it. So:
- **A `step` block runs in one clock domain**, derived from what it
  writes (no marking, as §4.2): the domain of the interfaces whose
  signals it writes; with none (only component state), the component's
  domain. A block that writes signals of two clock domains is
  `FW-E-STEP-DOMAINS`; the user splits it with `` `fw_step(name) ``.
  Component fields written by a block belong to its domain; a field
  written by blocks in two domains is `FW-E-WRITE-MULTI`.
- **Reset** of a block's registers is the reset domain of the same
  interfaces (or the component's); `reset_state()` is split per domain by
  what it writes, in fe-sv and rt-sv alike.
- **`run()`** may wait on any of the component's domains: the domain
  operations (§5.1) are keyed by the component *or* one of its
  interfaces, e.g. `fw_clock_domain::tick(rd_port)`. Keying by another
  component's interface is `FW-E-DOM-OBJ`.
- A block that **reads** an interface in another domain than its own is a
  crossing inside the component: the component is the crossing element
  (core-domains §6), so it is allowed; it is listed in the netlist like
  the connection crossings.

Using a domain this way *realizes* it (core-domains §0 item 5), so the
emitted module gets that domain's clock and reset ports.

`comb()` has no domain of its own: it runs in every settle of a domain
whose signals it reads (§6).

---

## 5. `run()` (R2.2, R2.4)

### 5.1 Shape

**Recommendation.**
- `interface class fw_run_if; pure virtual task run(); endclass`, found
  by `$cast` like §4.1. The kernel forks every `run()` after elaboration.
- Domain operations are static functions of the domain capability, keyed
  by the component or one of its interfaces (§4.4), not methods on
  `fw_component`:
  - `fw_clock_domain::tick(this, n = 1)`: wait for `n` edges;
  - `fw_reset_domain::in_reset(this)`; `fw_reset_domain::wait_reset_done(this)`;
  - `fw_reset_domain::wait_assert(this)` (optional; for models that
    restart on reset).
- **Reset of state:** a component that implements `fw_reset_state_if`
  (`function void reset_state()`) has it called while its reset domain is
  asserted, before any `step()`. fe-sv lowers it to the reset branch of
  the `always_ff`. Without it, `step()` sees `in_reset()` and handles
  reset itself.

### 5.2 Visibility of `run()`'s writes (R2.4)

*Superseded (2026-11-21) by [`sync-task-domains.md`](sync-task-domains.md)
and the spec, `fw-hdl-spec/semantics/processes.md` ("The edge",
"Crossings"):* an edge is evaluate, update, settle, then release, so
`run()` resumes after the update. A signal `run()` touches is a crossing
port: a read at edge *k* returns the value from before *k* (C2), and a write
takes effect at once, so comb logic settles on it and `step()` reads it
from *k*+1 (C3). The rv timing below is unchanged; the original text
follows.

**Recommendation.** `run()` writes are register writes, exactly like
`step()`'s:
- `run()` resumes at an edge *after* that edge's commit and settle, and
  after every `step()`. It reads the values `step()` read.
- What it writes is committed at the next edge's commit phase, so peers
  see it during the cycle that follows, as with an NBA.

For the rv transactor (prep §6, decision 8) this gives:
1. `put(t)` is called in `run()` at edge *k*: it writes `valid=1`,
   `data=t`;
2. the target sees them in cycle *k*→*k+1*; its `comb()` drives `ready`;
3. at edge *k+1* the transactor's `run()` reads `valid && ready`, and
   `put()` returns; a back-to-back `put()` keeps `valid` high.

"Drives `valid` in its own cycle" is the cycle after the edge at which
the call is made; nothing is buffered and no cycle is added.

### 5.3 `run()` with `step()` in one component

*Amended (2026-11-21), see the spec's "Crossings":* a signal written by a
`step` block and the task code of the same component is no longer
`FW-E-WRITE-MULTI`: the block's write is the default and a task write at
the same edge overrides it (C5). With release after the update, shared
component state is ordered by the edge, not by process order. The
original text follows.

Allowed (fw-proto-axi-new §3.5's case). Both write registers; a signal
written by both is `FW-E-WRITE-MULTI`. Their
order at an edge is fixed (`step()` first, §6), so a value they share
through component state is deterministic.

---

## 6. The rt-sv kernel (R2.5)

**Recommendation: port the old kernel.** One edge loop per realized
clock domain:
1. **Commit:** pending register writes become visible.
2. **Settle:** run the domain's `comb()`s in whole passes until no wire
   changes; bound 64, then `FW-E-COMB-LOOP` naming the changing signals.
3. **Step:** `reset_state()` (in reset) or each `step` block pinned to
   this domain (§4.4), any order.
4. **Run:** resume `run()`s waiting on this edge.

Reset-force (the peer of a component in reset reads `valid`/`ready` as 0)
is not ported as a kernel feature: it was there for struct ports. In the
new core, a component in reset that drives a protocol is responsible for
its outputs through `reset_state()`, as RTL is. (Decision 7.)

The settle weaver (static schedule) is a later optimization; naive settle
is the reference.

---

## 7. fe-sv lowering (R2.5)

**Recommendation.**
- each `step` block → an `always_ff @(posedge clk ...)`, with the
  `reset_state()` body as the reset branch (polarity and style from the
  reset domain).
- each `comb` block → an `always_comb`.
- registers and wires from §4.2; reads and writes of signals become
  references to the nets; component fields read and written in `step()`
  become registers, in `comb()` locals.
- the interpreter is the M3/M6 one (`zuspec.fe.sv.interp`), with
  procedural bodies mapped to Zuspec IR processes (a new Z item, as Z5/Z6
  were); be-sv emits them. Parameterized emission (layer 1 §6.6) carries
  over: one module per class.
- **`run()` is not lowered.** A class with `run()` is simulation-only:
  fe-sv reports `FW-E-EMIT-RUN` if it is asked to emit one, and the
  testbench generator (K10) is what places it. The emission of a
  transactor is therefore the lowered `comb`/`step` pin core; the
  `run()` side stays in the testbench (prep §6).
- The old `sync*.py` lowering is the reference to port.

---

## 8. Pin bridge to RTL (R2.5)

**Issue.** The old bridges are per protocol (`fw_rv_pin_in/out`). With
§4.2 a bridge needs no protocol knowledge: it moves a value between a
class signal and a module pin.

**Recommendation.** A generic `fw_pin_bridge #(type T)` SV module in
rt-sv, bound to a class signal by path:
- **RTL → class** (the signal is an effective input of the class tree):
  on a pin change, `write()` and settle the signal's domain at once, so a
  class `comb()` that depends on it updates in the same time step.
- **class → RTL:** wires drive the pin continuously after each settle;
  registers drive it with NBA semantics, so RTL at edge *k* sees what the
  class tree sees after commit *k*.
- **RTL clock → class clock** (the path names a clock domain): each
  posedge of the pin is an edge of the domain. Its step blocks run in the
  active region; its register writes commit, and the comb blocks settle,
  after the NBA region of that time step. A register then changes when an
  RTL flop at the same edge would, so both bridge directions follow from
  the "wires after each settle" rule and edges number as in all-RTL. The
  edge loop does not tick a bridged domain. *Done in rt-sv (P4.1b);
  checked mid-cycle against an all-RTL model.*
- The testbench and bind-module generators (K10) instantiate one per
  pin, from the elaborated netlist; a user writes none.

---

## 9. Time (R2.6, prep §3.5)

**Issue.** A self-timed connection delays a delivery by a `time`
(`PROTO::xfer_time(cfg, t)`). A pure class model (two UART models, no
RTL) may have no clock at all. Layer 2's edges come from clock domains;
the channel needs simulation time.

**Recommendation.**
- **Time is SV simulation time.** `run()` is simulation-only, so a delay
  is `#d` in rt-sv. The capability is `fw_time`:
  `fw_time::now()` and `fw_time::delay(time d)`, static, so fe-sv can
  reject it in anything it lowers (`FW-E-EMIT-TIME`).
- **`fw_timed_channel #(PROTO)`** (std, K9) is a `run()` component: it
  samples the sender's configuration, calls `fw_time::delay(xfer_time)`,
  then delivers. It needs no clock domain.
- **Clocks in a pure class model.** A root clock domain with no extern
  pin and no driver has no edges. Layer 2 adds an optional `period` to
  the clock kind's root params (the property core-domains §9 reserved);
  with it, rt-sv ticks the domain itself. Derived domains tick from
  their source by `div`/`mul`. With no period and no driver, a `tick()`
  is `FW-E-CLOCK-NONE`.
- **Timescale.** `time` values follow the compilation unit's timescale;
  std and rt-sv set `` `timescale 1ns/1ps``. A protocol's `xfer_time`
  should compute in a unit-safe way (multiply by `1ns`).

---

## 10. Scope

In:
- `read()`/`write()`, `fw_step_if`, `fw_comb_if`, `fw_run_if`,
  `fw_reset_state_if`, `fw_time`, and the domain operations of §5.1;
- derived register/wire kinds and their write rules;
- the rt-sv kernel and `fw_pin_bridge`;
- fe-sv lowering of `step`/`comb`/`reset_state` through a new Zuspec IR
  item, parameterized per class;
- conformance: scenarios with an expected **trace** (signal values per
  cycle), run in rt-sv and on fe-sv's lowered Verilog in Verilator, which
  must agree;
- the acceptance: the zero-latency rv transactor and monitor of prep §6,
  in a b2b test against RTL.

Out:
- untimed code and the synthesis engines of `timing.md` (a later layer
  may lower `run()` through them);
- a single `step` block in two clocks (split it, §4.4); reset-force;
- the settle weaver;
- the Python binding.

---

## 11. Decisions

| # | Decision | Decision |
|---|---|---|
| 1 | Where `read()`/`write()` live | *Decided 2026-11-17.* Methods on `fw_signal #(T)`, as layer 1 reserved; not a capability class (§3) |
| 2 | How processes are registered | *Decided 2026-11-17.* `fw_step_if`/`fw_comb_if`/`fw_run_if` interface classes, found by `$cast`; no `add_*` call; several blocks per component through `` `fw_comb(name) ``/`` `fw_step(name) `` (§4.1, §5.1) |
| 3 | Register or wire | *Decided 2026-11-17.* Derived from the writing process; no `set_comb()`; one writer per signal, checked (§4.2) |
| 4 | Visibility of `run()` writes | *Decided 2026-11-17.* Register writes, committed at the next edge; `run()` resumes after `step()` (§5.2) |
| 5 | Domain of a component's processes | *Decided 2026-11-17, amended by the owner.* The component's resolved domain and every domain its interfaces resolve to; a `step` block runs in the one clock domain of the interfaces it writes (component's if none), two is `FW-E-STEP-DOMAINS`; `run()` ticks any of them; the component is the crossing element (§4.4) |
| 6 | Domain operations | *Decided 2026-11-17.* Static on the domain capability: `fw_clock_domain::tick(this, n)`, `fw_reset_domain::in_reset(this)`, `wait_reset_done`; nothing on `fw_component` (§5.1) |
| 7 | Reset | *Decided 2026-11-17.* `fw_reset_state_if::reset_state()`, lowered to the reset branch; drop the old reset-force (§5.1, §6) |
| 8 | `run()` in emission | *Decided 2026-11-17.* Simulation-only; fe-sv refuses it (`FW-E-EMIT-RUN`); placed by the K10 testbench generator (§7) |
| 9 | Pin bridge | *Decided 2026-11-17.* One generic `fw_pin_bridge #(T)` per pin, generated; no per-protocol bridges (§8) |
| 10 | Time | *Decided 2026-11-17.* SV simulation time through `fw_time::delay/now`; optional `period` on root clocks so a class-only model ticks (§9) |
| 11 | Conformance | *Decided 2026-11-17.* Expected per-cycle traces, rt-sv versus lowered Verilog in Verilator (§10) |

## 12. Risks

- **Verilator timing.** rt-sv's kernel and `run()` need `--timing`
  (class tasks that wait on events and `#d`, `fork`). Verilator 5.055
  already needed a workaround in M2. A probe comes first in the plan.
- **Static writer analysis.** Deriving register/wire (§4.2) needs fe-sv to
  find every write through helper functions and bundle handles; a write
  it cannot attribute must be an error, not a guess.
- **Settle cost.** Naive settle runs every `comb()` per pass; large class
  trees may be slow until the weaver is ported.
