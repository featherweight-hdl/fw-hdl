# Chisel and XLS — IR and Front-End Capability Assessment

*Status: assessment, for review. Snapshot as of 2026-10. Facts about Chisel/FIRRTL and XLS
come from their docs and source (cited in §10). Facts about our stack come from reading
`packages/*` in this workspace; I did not run the tests. Inferences are marked **[inf]**.*

**Companions:** `integration-thesis.md` (§2.1 XLS survey, §7 "adopt XLS's semantics"),
`ir-primitives.md` (kernel P0–P6), `zuspec-semantics.md` (layers),
`one-model-many-hosts.md` (bindings), `reference/diplomacy-integration.md`.

This document goes further than the XLS notes in `integration-thesis.md`, adds Chisel,
and answers five questions:

1. Can the zuspec IR capture what Chisel/FIRRTL captures? (§2)
2. Can it capture what XLS captures? (§3)
3. Can SystemVerilog (fw-hdl) capture XLS's semantics, and should it be the input
   language? (§4; decision in §4.4)
4. Can the Python DSL (zuspec-dataclasses) capture XLS's and Chisel's semantics? (§5)
5. Could we be "the Chisel/XLS killer", and what are we overlooking? (§6, §7; the
   resulting position is in §6.4)

---

## 0. Summary

1. **Chisel and XLS are not the same kind of thing, so "killing both" needs two different
   arguments.**
   - **Chisel** is a *generator* language. Its value is Scala metaprogramming, and almost
     all of it is erased at elaboration. Its IR, FIRRTL, is a single-edge synchronous RTL
     netlist with verification and metadata side channels (layers, probes, LTL, object
     model, domains).
   - **XLS** is a *semantics plus compiler*: bit-accurate pure functions, CSP procs over
     channels, a timing-driven scheduler with characterized delay models, and one IR
     executed at every level and cross-checked by a fuzzer and SMT.
2. **Semantically, the zuspec IR already covers more ground than either tool**: TLM, procs,
   actions/activities, constraints, coverage, register maps, multiple clock domains, CDC
   primitives, C emission. Neither Chisel nor XLS has anything for transaction-level,
   test-intent or HW/SW concerns.
3. **At the RTL boundary we are behind both.** The gaps are engineering, not semantics:
   - no timing-driven scheduler or delay model;
   - packed aggregates are flattened, and `signed`/enums are not emitted;
   - no width inference or narrowing;
   - user `assert`/`cover`/trace do not survive into RTL;
   - four separate string-based SV emitters;
   - no fuzzer and no formal equivalence;
   - Diplomacy-style negotiation is still a design document.
4. **SystemVerilog can carry XLS's semantics at the class level almost completely.** The
   exceptions are three library additions and four pinned semantic differences (§4). What
   SV lacks is *restriction* (it lets you write things that cannot be synthesized), not
   *expressiveness*. The profile checker is the answer, as `integration-thesis.md` §8.1
   already says.
   - **Decision (§4.4):** XLS-style input is written in SV, in the fw-hdl class subset, so
     the source simulates unchanged in existing flows.
   - For that to hold, **2-state SV semantics are normative** for the synthesizable
     subset. The simulator's answer *is* the defined answer, and XLS-specific behaviour
     such as clamping arrives only through an XLS-IR importer.
5. **The Python DSL captures XLS's model well and Chisel's poorly.** zdc is a *declarative*
   class model with parsed method bodies. It has no imperative generator phase, so the
   thing Chisel users actually come for — arbitrary code that builds hardware — is
   missing. Python is a perfectly good generator language; we just haven't exposed it.
6. **Verdict on "killer":**
   - **XLS: yes, by building on it rather than replacing it (§6.4).** The killer app is
     **an SV user layer with back-end machinery that fills in the detail**:
     - authors write SV classes;
     - analysis produces XLS IR for timing-free compute;
     - XLS schedules and generates the RTL;
     - our automation stitches the result in (transactors, FIFOs, CDC, register blocks,
       glue);
     - the same source simulates as a model in existing flows.

     QoR equals DSLX's by construction, since the back end is the same. The pitch is
     integration effort, and the native scheduler becomes a fallback rather than the
     critical path.
   - **Chisel: no, and it's the wrong goal.** Chisel's moat is the rocket-chip/Chipyard
     ecosystem and CIRCT, not its semantics. The winning move is to make Chisel
     unnecessary for SV-centric teams and to **host** Chisel output (FIRRTL in), not to
     compete with it head-on.
7. **The biggest overlooked opportunities** (§7):
   - (a) use **CIRCT** as a back end and analysis engine instead of maintaining four SV
     emitters;
   - (b) **ingest XLS IR and FIRRTL** as front ends, which makes us the integration layer
     for both ecosystems — "embrace", not "kill";
   - (c) **parameterized SV output**, which neither tool produces;
   - (d) **LLM-native design**: Python/SV hosts plus a checked IR is the most
     agent-friendly hardware stack available, while DSLX and Chisel are low-resource
     languages;
   - (e) an **XLS-style cross-back-end fuzzer**, cheap for us because we already have
     three executors;
   - (f) **typed latency contracts** at component boundaries.

---

## 1. What each tool actually captures

### 1.1 Chisel / FIRRTL

The test of "semantics" in Chisel is: *does it survive into the `.fir`?* The FIRRTL spec
defines itself as the circuit "after all meta-programming has executed".

| Survives into FIRRTL (IR semantics) | Erased at elaboration (generator only) |
|---|---|
| `UInt/SInt/Bool/Clock/Reset/AsyncReset/Analog`, `Vec`, `Bundle` with `flip`, enums, `const`, type aliases | Scala parameters, type parameters, typeclasses |
| width inference (constraint fixpoint), reset inference | Diplomacy / CDE negotiation |
| `wire`, `reg`/`regreset`, `mem` with read/write latency and read-under-write | `Definition`/`Instance` lookups (become plain `inst`) |
| `when`/`else` with **last-connect** semantics; full-initialization check; `invalidate` (DontCare) | Connectable operator variants (`:<>=`, `:#=`, waive/squeeze) |
| `inst`, `extmodule`, public modules, **instance choice** (`instchoice`) | `Decoupled`/`Queue`/`Arbiter` *protocol meaning* (just bundles and modules) |
| **layers** (optional verification logic, bind or ifdef) | `DataView`, `MixedVec`, ChiselEnum behaviour (partially) |
| **probes** (`Probe`/`RWProbe`, force/release → XMRs) | all testbench code (ChiselSim is Scala) |
| assert/assume/cover/printf/stop; LTL via intrinsics; `formal` tests; contracts | |
| **properties / classes / object model** (metadata such as memory maps) | |
| **domains** (2026: clock/reset/power domain kinds, checked crossings) | |

Not captured at all: transactions, channels, processes, untimed behaviour, scheduling,
randomization, constraints, functional coverage. Chisel's whole timing model is "registers
update on the clock edge".

### 1.2 XLS

| Layer | What it captures |
|---|---|
| **Types** | `bits[N]`, arrays, tuples, `token`; DSLX adds signed views, structs, enums with explicit width, parametrics |
| **Function** | pure, single output, bounded loops (`counted_for`), `map`, `invoke`; **every operation fully defined** (out-of-bounds clamps, shifts saturate, `one_hot_sel` ORs) |
| **Proc** | state + `next` activation; channels as infinite FIFOs; blocking/non-blocking/predicated send and recv; **tokens** give a partial order over effects; `next_value` with mutually exclusive predicates; Kahn determinism unless non-blocking ops are used |
| **Channel** | kind (`streaming`/`single_value`), flow control (`ready_valid`/`valid_data`/`none`), FIFO config (depth, bypass, registered push/pop), flop kind (flop/skid/zero-latency), **strictness** (how several ops on one channel are ordered) |
| **Block** | RTL: ports, registers, instantiations (block, FIFO, delay line, extern) |
| **Compile** | about 90 optimization passes; SDC scheduling under clock period / stages / II / IO constraints; characterized delay and area models (asap7, sky130, unit); combinational or pipeline codegen |
| **Execute and check** | DSLX interpreter, IR interpreter, LLVM JIT/AOT (including cycle-accurate block IR), fuzzer cross-checking all levels plus Verilog sim, Z3/Bitwuzla equivalence, `symex` |

Not captured: multiple clocks or CDC, bus protocols, memory beyond fixed-latency RAM
channel rewrites (experimental), temporal assertions, hand-placed registers.

---

## 2. Can the zuspec IR capture Chisel/FIRRTL?

**Key:** ✔ present · ◐ partial · ✘ absent. "IR" means `zuspec-ir-core`. "RTL" means a
lowering to SV exists today.

| FIRRTL concept | IR | RTL | Notes |
|---|---|---|---|
| `UInt<w>`/`SInt<w>`/`Bool` | ✔ `DataTypeInt(bits, signed)` | ◐ | be-sv never emits `signed`; process locals are emitted as `logic [31:0]` |
| Width inference | ✘ | ✘ | By design (`ir-primitives.md` rule 3: widths explicit). A *front-end* feature for a generator host, not an IR need |
| `Vec` | ✔ `DataTypeArray` | ◐ | emitted as an unpacked array; no Vec-of-Bundle, no multi-dimensional packed arrays |
| `Bundle` with `flip` | ◐ `DataTypeStruct`; direction lives on ports/exports | ◐ | Bundles are flattened to `name_field` ports; there is no directional aggregate type |
| Enums | ✔ `DataTypeEnum` | ✘ | FSM states use `localparam`; no `typedef enum` |
| `Clock`, `Reset`, `AsyncReset` as types | ◐ clock/reset are domains, not values | ◐ | async reset handling is inconsistent across emitters |
| `Analog` / inout | ✘ | ✘ | rare in our domain; low priority |
| `const` types | ◐ `zdc.const` fields | ✔ `parameter` | |
| `reg`/`regreset` | ✔ `Field(is_reg)` + `reset_value` | ✔ | |
| `mem` with latency and read-under-write | ◐ `DataTypeMemory` | ◐ register files only | **no SyncReadMem semantics, no RUW, no SRAM binding** |
| `when` + last-connect | ✔ (imperative `if` in `@comb`/`@sync` bodies has last-assignment semantics, which is what ExpandWhens produces) | ✔ | No full-initialization check: a latch-producing `@comb` is not rejected **[inf]** |
| `invalidate` / DontCare | ✘ | ✘ | Worth adding: an explicit "don't care" lets the optimizer and the formal tools use the freedom |
| `inst`, `extmodule` | ✔ `zdc.inst`, `DataTypeExtern` | ✔ | `ModuleInstance(module: str)` should reference a type (`ir-primitives.md` §8) |
| Instance choice | ◐ fw-hdl multi-view design (`multi-view-rearchitecture.md`) | ✘ | Chisel's `instchoice` validates the multi-view idea |
| Layers | ✘ | ✘ | **Adopt.** Verification code emitted as `bind` modules keeps RTL clean (§7.7) |
| Probes / XMR / force | ✘ | ✘ | P5 `Tap(endpoint)` is the transaction-level analogue; signal probes are cheap to add in P4 |
| assert/assume/cover | ✔ `StmtAssert/Assume/Cover` | ✘ for user code | The synth transformer reads `assert x == y` as a *defining* assignment (`transformer.py:762`); only generated FSM/pipeline properties reach RTL |
| printf | ◐ fw-hdl `fw_dbg` (SV runtime only) | ✘ | P5 `TraceSite` is designed, not built |
| LTL / SVA sequences | ◐ the SV IR has SVA nodes | ◐ generated only | Protocol kits are the natural source of temporal properties |
| `formal` tests, contracts | ◐ `requires`/`ensures` (runtime, be-py) | ◐ sby gen for pipelines | |
| Properties / object model | ✔ richer: MMR register maps, attributes | ✔ regblocks, C headers | We are ahead: the register model *is* an object model with semantics |
| Domains (clock/reset/power, checked crossings) | ✔ richer: `ClockDomain`, `DerivedClockDomain`, `ResetDomain`, `PowerDomain`, `TwoFFSync`, `AsyncFIFO`, `cdc_unchecked` | ◐ `CDCAnalysisPass` reports crossings, inserts nothing | We are ahead on vocabulary, behind on enforcement |
| Diplomacy (generator-level) | ✘ code; ✔ design (`reference/diplomacy-integration.md`) | — | Our design keeps negotiated attributes in the IR; Diplomacy erases them |

**Assessment.** Everything in FIRRTL fits in `ir-primitives.md` P0/P1/P4/P5 without new
concepts. The work is:
- directional aggregates in P4;
- memory read latency and read-under-write;
- `invalidate`;
- layers;
- signal probes;
- user assertions surviving lowering.

The reverse direction is the interesting one. **FIRRTL cannot carry most of what our IR
holds** (P2, P3, P6, constraints, coverage). A FIRRTL *import* is therefore lossless and
cheap, while a FIRRTL *export* is a lowering.

---

## 3. Can the zuspec IR capture XLS?

| XLS concept | IR | RTL / execution | Notes |
|---|---|---|---|
| `bits[N]`, explicit `zero_ext`/`sign_ext` | ✔ `ExprZext`/`ExprSext` | ◐ | no explicit `Trunc` node; truncation is a slice or implicit (`ir-primitives.md` wants it explicit) |
| Arrays, tuples, structs, enums | ✔ | ◐ | tuple returns are expanded to `_v0`, `_v1`, … |
| Parametrics | ◐ `DataTypeParameterized`/`Specialized` (PSS path); zdc width **lambdas** | ◐ | Python lambdas in `width_expr` are Python-only IR. They need to become `Param` expressions |
| Pure `Function` | ◐ no purity flag | ✘ | no "pure function → combinational/pipelined block" flow; bodies are inlined |
| **Fully defined op semantics** (OOB, shift ≥ width, div by 0) | ✘ unspecified | — | **Must be pinned** in `zuspec-semantics.md`. This is the foundation of XLS's cross-level checking. The values are SV-aligned, not XLS's (§4.1 D1–D4, §4.4) |
| `counted_for`, `map`, unroll | ✔ `StmtFor` | ◐ | no IR-level unroll pass; unrolling is left to downstream synthesis |
| Proc (state + activation) | ✔ `@zdc.proc` / `Process` | ✔ as FSM (explicit timing) | the *static-scheduled* activation is missing (`integration-thesis.md` §3.5) |
| Channels with depth | ✔ ×5 encodings | ✔ Queue → sync FIFO | consolidation is `ir-primitives.md` §8's first item |
| `send_if`/`recv_if` | ✔ (a channel op under `if`) | ✔ | |
| `recv_non_blocking` | ◐ `DataTypeChannel` docs mention `try_put`; no DSL op found | ✘ | gap S1 in the thesis |
| Tokens / `after_all` | ✘ (program order instead) | — | **semantic choice with a real cost**; see §4.2 |
| `next_value` (predicated, mutually exclusive) | ✔ (assignment to a state field) | ✔ | ours is more permissive (last-assignment-wins) |
| `single_value` channel | ✘ | ✘ | needs a standard interface: a register-like endpoint, not a FIFO |
| Channel strictness | ✘ | ✘ | an endpoint attribute; matters when two branches touch one channel |
| Flow control kind, flop kind, FIFO kind | ◐ `IfProtocolProperties`; `skid_buffer.v`, `fifo_sync.v` templates | ◐ | we generalize this through protocol kits |
| Select (first-ready among channels) | ✔ `SelectStmt`, `zdc.select(priority=…)` | ✔ fixed priority / round-robin | **XLS has no select**; you build it from non-blocking receives. We are ahead |
| SDC scheduling under clock period | ◐ `sdc_schedule.py`, integer latency table | ✘ | `clock_period_ns` is "informational" (`scheduler.py:672`) |
| II / worst-case throughput | ◐ toy modulo scheduler (`sprtl/pipeline.py`) | ◐ | `@zdc.pipeline` with hazards, forwarding and stalls is ahead of XLS for *explicit* pipelines |
| Delay / area model | ✘ | — | XLS's asap7/sky130 data is Apache-2.0 and importable |
| Optimizer (narrowing, BDD, select simplification) | ✘ | — | narrowing is the one pass worth owning; downstream synthesis does the rest |
| Interpreter / JIT | ✔ be-py (asyncio); ✔ be-sw RTL → C (benchmarked against Verilator) | | be-sw is limited to ≤64-bit types; be-bc (the reference interpreter) is **not in this workspace** |
| Fuzzer, equivalence | ✘ | ✘ | `eqy` is vendored but unused |
| assert / cover / trace survive | ◐ IR nodes exist | ✘ | |
| `#[test]`, `#[test_proc]`, quickcheck | ✔ richer: rand + constraints + covergroups, be-py solver | | quickcheck = `rand` + `@constraint`; we already have the stronger tool |

**Assessment.** The IR captures XLS's *model*: procs, channels, state, bounded compute.
Its *rigor* is missing: defined op semantics, explicit effect ordering, channel kinds and
strictness, and the scheduler. Concretely:
- Five semantic additions (§4.1 L1–L3, plus channel strictness and defined op semantics)
  are small.
- Two engineering items are large: the timing-driven scheduler with a delay model, and the
  cross-level checker/fuzzer.
- One item is cheap: user assertions surviving lowering.

---

## 4. Can SystemVerilog capture XLS's semantics?

The question has two halves: the class level (fw-hdl, the behavioural model) and plain RTL.

### 4.1 Concept by concept

| XLS | fw-hdl SV (class level) | Plain SV RTL | Fidelity |
|---|---|---|---|
| `uN[N]`/`sN[N]` | `bit [N-1:0]`, `bit signed [N-1:0]` | same | ✔, but see D1 |
| struct, array, tuple, enum | `typedef struct packed`, packed arrays, `enum logic [k:0]` | same | ✔ (tuple → packed struct) |
| parametric `fn f<N>` | `class C #(int N); static function …` | `module #(parameter N)` / parameterized function in a package | ◐ verbose, but complete. Derived parametrics map to `localparam` |
| pure function | SV `function automatic` | same | ✔ if the profile checker enforces purity |
| `counted_for` | `for` with a constant bound | same | ✔ |
| `match` (exhaustive) | `unique case` / `case … inside` | same | ◐ SV does not enforce exhaustiveness at compile time |
| proc `config` / `spawn` | `build`/`connect` phases, `fw_component` tree | module instances | ✔ fw-hdl is a superset (negotiation) |
| proc `next` activation | one iteration of a `run()` `forever` loop **with no `tick()`** (thesis §3.5) | `fire = &recv_valids & &send_readys` | ✔ by convention |
| proc state, `next_value` | class fields | `always_ff` | ✔ |
| streaming channel (infinite FIFO) | `fw_port #(fw_put_if/fw_get_if)`; mailbox-backed export | ready/valid + FIFO instance | ✔ |
| blocking `recv` / `send` | `get()` / `put()` tasks | — | ✔ |
| `send_if`/`recv_if` | `if (p) out.t.put(v)` | — | ✔ |
| `recv_non_blocking` | **missing** in `fw_std_pkg` → add `try_get`/`can_get` | — | L1 |
| `single_value` channel | **missing** → a `fw_value_if` (read last written, non-destructive) | a wire or register | L2 |
| tokens / `after_all` | statement order (total) | — | ◐ see §4.2 → L3 |
| channel strictness | none | — | add as an endpoint attribute |
| `assert!` / `cover!` / `trace_fmt!` | native `assert`/`cover`/`$display`, `fw_dbg` sites | native, plus **SVA temporal properties** | ✔ SV is *stronger* (XLS has no temporal properties; issue #1350) |
| `#[test_proc]` | an `fw_component` test with an `fw_root` | — | ✔ |
| `#[quickcheck]` | `rand` + constraints | — | ✔ stronger |
| `fail!` (assume unreachable) | `assert (0)` in a `default` branch | `unique case`, or `$fatal` in sim | ◐ synthesis may not exploit it |
| `gate!` (power hint) | — | an attribute or a clock-gate cell | ◐ library |
| `extern_verilog` FFI | trivial: it *is* SV | trivial | ✔ SV wins by construction |

**Library additions (L1–L3):** `try_get`/`try_put`/`can_*`/`peek` on the standard
interfaces; a single-value interface; and the ordering relaxation in §4.2. L1 is
integration-thesis stage S1. L2 and L3 are new.

**Semantic differences the SV front end must pin (D1–D4).** These are the real fidelity
risks. In each case SV is legal but means something different from XLS.

**Decision (§4.4): for the synthesizable subset, 2-state SV semantics are normative.**
The IR adopts what an SV simulator does, not what XLS does. That way, simulating the SV
source in any simulator gives the defined answer. Every operation stays fully defined,
which is XLS's real property; only the chosen values differ. Clamping and other
XLS-specific behaviour become a job for an XLS-IR front end (§7.2), which inserts explicit
clamps on import.

| # | Difference | XLS | SV | Normative rule (SV-aligned) |
|---|---|---|---|---|
| D1 | Expression widths | every op has an explicit result width | **context-determined** widths (operands extended to the widest in the expression, including the LHS) | SV's rules. The front end resolves them (pyslang gives the resolved types) and records explicit `Zext`/`Sext`/`Trunc` (`ir-primitives.md` rule 3) |
| D2 | Out-of-bounds array access | read clamps to the last element; write is a no-op | 2-state read returns 0; write is ignored | **read returns 0, write is a no-op.** Lowering emits the guard unless the index is provably in bounds (cf. XLS's `assumed_in_bounds`) |
| D3 | X / 4-state | 2-state; every value defined | 4-state; X propagates | **the synthesizable profile is 2-state**: `bit`, not `logic`, in synthesizable paths. The profile checker rejects `logic`/`x`/`z` there |
| D4 | Divide by zero | defined result | X (4-state); stored into a 2-state variable it converts to 0 **[verify per simulator]** | **rejected by the profile checker unless the divisor is guarded or provably non-zero.** Avoids picking a value that simulators may disagree on |

### 4.2 Tokens versus program order — the one deep difference

`integration-thesis.md` §3.3 says "SV's sequential semantics provide what XLS needs
explicit tokens for." That is true for **correctness**: program order is a legal
refinement of any token order. It is false for **scheduling freedom**:

- XLS tokens give a *partial* order. Two sends on different channels with no token edge may
  go in the same cycle, or in either order, and the scheduler picks.
- SV statement order is *total*. A scheduler that respects it serializes I/O the author
  never meant to order.
- A scheduler that ignores it may change deadlock behaviour. With `recv(a); send(b);`,
  when b's consumer feeds a, reordering creates a deadlock.

So the IR needs to know which program-order edges are semantic. Options:

1. **Default total order, with an explicit relaxation.** A `par { }` / `fork … join` block,
   or an `@unordered` region, says "these effects may reorder". This is SV-native
   (`fork`/`join` already exists) and keeps "no magic".
2. **Default per-channel order only** (XLS's guarantee), with dependency analysis plus a
   deadlock check deciding the rest. This is more freedom, more surprise, and needs the
   Kahn/latency-sensitive classification to be sound.

**Recommendation:** option 1 everywhere. `fork … join` is the relaxation, and it
*simulates with the same meaning* in any SV simulator, which keeps the source the reference
(§4.4). Option 2 can come later as an opt-in optimization for `timing=static` processes
(which are Kahn by construction), but only behind a deadlock check showing that the
reordering cannot change deadlock-freedom relative to the source. This resolves
`integration-thesis.md` Q5 and `ir-primitives.md` Q2 together.

### 4.3 Verdict

SV at the class level captures XLS's semantics, provided there are three library
additions (L1–L3), four pinned semantic rules (D1–D4), and a profile checker that rejects
everything else. SV RTL captures XLS's *output*, but not its *source*: activations,
tokens and the schedule are compiler concepts that RTL can only show after the fact. SV is
**strictly stronger** in two places that matter to customers: temporal assertions and
Verilog interop.

The thing XLS has that SV fundamentally does not is **restriction**. Every DSLX program is
synthesizable; an SV class may not be. That is the one XLS advantage worth copying in
full: clear, source-located "this cannot be synthesized because…" diagnostics.

### 4.4 Decision: SV classes as the XLS-style input language

Given the library additions, **XLS-style input should be written in SV**, in fw-hdl's
class-level subset. The deciding benefit is that the source *simulates as-is in existing
flows*: commercial simulators and Verilator, under UVM or cocotb. No new language,
interpreter or build system is needed.

**The mapping:**

| XLS (DSLX) | fw-hdl SV |
|---|---|
| `proc` | `fw_component` + `fw_runnable` |
| `config` / `spawn` | build / connect phases |
| `init` + state | class fields + reset values |
| `next` (one activation) | one iteration of `run()`'s `forever` loop, **with no `tick()`** |
| `chan<T>` endpoints | `fw_port #(fw_get_if #(T))` / `fw_port #(fw_put_if #(T))` |
| `recv` / `send` / `*_if` | `get()` / `put()`, inside `if` |
| `recv_non_blocking` | `try_get()` (L1) |
| `single_value` channel | `fw_value_if` (L2) |
| token-free effects | `fork … join` (L3, §4.2) |
| `fn` (pure) | `function automatic` in a package, over packed 2-state types |
| parametric `fn f<N>` | `class C #(int N); static function …` |
| `#[test]`, `#[test_proc]`, `#[quickcheck]` | SV tests over `fw_root`, `rand` + constraints |
| `assert!`, `cover!`, `trace_fmt!` | `assert`, `cover`, `fw_dbg` sites (+ SVA, which XLS lacks) |
| scheduler flags | a component attribute: target clock (from its clock domain) or stages, plus II |

```systemverilog
// Simplified run-length encoder (no end-of-stream flush).
class rle_enc #(int W = 8) extends fw_component implements fw_runnable;
    typedef struct packed { bit [W-1:0] sym; bit [7:0] run; } pkt_t;
    fw_port #(fw_get_if #(bit [W-1:0]))  in;
    fw_port #(fw_put_if #(pkt_t))        out;
    bit [W-1:0] last;  bit [7:0] run;  bit valid;   // proc state

    virtual task run();
        forever begin                    // one activation per iteration, no tick():
            bit [W-1:0] x;               //   eligible for static scheduling
            in.t.get(x);
            if (valid && (x != last || run == 8'hFF)) out.t.put('{last, run});
            run   = (valid && x == last && run != 8'hFF) ? run + 1 : 1;
            last  = x;
            valid = 1;
        end
    endtask
endclass
```

**Evidence it simulates today.** `tests/intf_pc` runs a class-level producer/consumer over
`fw_put_if` on Verilator (`hdlsim.vlt`). The XLS-style subset needs nothing beyond that
machinery, plus L1–L3.

**What makes the "simulates in legacy flows" benefit real:**

1. **The source simulation is the reference.** Hence the SV-aligned rules D1–D4 (§4.1).
   With them, the SV simulator, the IR executors (be-py, be-sw, be-bc) and the lowered RTL
   agree by definition. The cross-back-end fuzzer (§7.5) checks our executors against the
   simulator people already trust, rather than the other way round.
2. **Source and lowered RTL in one simulation.** Both views sit in the same testbench under
   the user's stimulus, and their channels are compared per channel and in order
   (`fw_view_diff`). XLS cannot do this, because its tests live in the DSLX interpreter.

**Accepted costs:**

| Cost | Mitigation |
|---|---|
| SV accepts non-synthesizable code silently | the profile checker (S3) is **mandatory**, with source-located diagnostics |
| Statement order is stricter than tokens, so the scheduler has less freedom | `fork … join` as the explicit relaxation (§4.2) |
| Class-level timing (mailbox handoffs within a time step) is not RTL cycle timing | compare per channel and in order. That is valid only for components using blocking operations. With `try_get`, the class model and RTL may legitimately diverge (as in XLS), and are compared against the legal set instead |
| More verbose than DSLX (parametric functions, tuples as packed structs) | tolerable. Partly offset by language-model fluency in SV (§7.4) |
| Class-based simulation is slow at scale | fine at block level; long regressions run the lowered RTL or the be-sw C model |

**Prototype to validate the decision:**
1. Port two or three XLS examples into the fw-hdl SV subset: one function (CRC or a
   `float32` add) and one proc (the run-length encoder, as above).
2. Simulate them on Verilator against XLS's own test vectors.
3. Record what was awkward to express.

This tests expressiveness and ergonomics cheaply, and it seeds the corpus for both the XLS
back end and the XLS-IR front end.

---

## 5. Can the Python DSL (zuspec-dataclasses) capture XLS and Chisel?

### 5.1 XLS — a good fit

| XLS | zdc | Status |
|---|---|---|
| bits types | `u1..u128`, `s8..s128`, `bv[N]`, `x[hi:lo]`, `concat`, `sext/zext/signed` | ✔ |
| struct / array / enum / tuple | `PackedStruct`, `Array[T]` + `array(depth)`, `@zdc.enum`, `tuple(size)` | ✔ |
| parametrics | `zdc.const`, width lambdas, `kwargs=lambda s: …` | ◐ works, but lambdas are opaque to the IR |
| pure function | plain method | ◐ no purity marker or check |
| proc | `@zdc.proc async def run(self)` with `await` on channels | ✔ |
| channels | `Channel`, `Queue[T]` + `queue(depth)`, `PutIF`/`GetIF`, `ReqRspChannel` | ✔ (too many forms) |
| non-blocking recv | — | ✘ |
| select | `zdc.select(..., priority='round_robin')` | ✔ (ahead of XLS) |
| pipelining | `@zdc.pipeline`, `pipeline.stage(cycles=N)`, hazard locks | ✔ for explicit pipelines; ✘ timing-driven |
| tests / quickcheck | rand, `@constraint`, covergroups; Python test frameworks | ✔ and hypothesis is available |
| reference models | numpy and anything else in Python | ✔ — a real advantage over DSLX |

**Python-specific semantic hazards (P1–P4)** that the front end must pin, the same way D1–D4
pin SV:
- **P1**: unbounded `int` arithmetic, so every result needs an explicit width (the front end
  must type every intermediate, not only fields).
- **P2**: `//` and `%` round toward −∞, whereas XLS, SV and C truncate toward 0. Signed
  division therefore differs.
- **P3**: `>>` on a negative `int` is arithmetic; on an unsigned `bv` it must be logical.
- **P4**: `bool` is an `int`, so `True + True == 2`.

`data_model_factory.py` handles some of these. They belong as normative rules in
`zuspec-semantics.md`, with conformance tests.

### 5.2 Chisel — a poor fit today, and fixable

Chisel users come for **generators**: arbitrary host-language code that runs at
elaboration and builds a circuit (reduction trees from recursion, parameterized
crossbars, Diplomacy graphs). zdc is a **declarative** model:
- structure is class-level fields (`zdc.inst(size=, elem_factory=)`, `kwargs` lambdas,
  `__bind__` returning a dict);
- behaviour is method bodies *parsed from the AST* rather than executed.

So:

| Chisel capability | zdc | Gap |
|---|---|---|
| Imperative generation (loops and recursion that create instances and wires) | ✘ only `size=`/`elem_factory=` | **main gap** |
| Conditional structure from parameters | ◐ via kwargs lambdas | awkward |
| Width inference | ✘ | could live in the front end |
| Directional aggregates (`Bundle` with flip), bulk connect | ◐ `Bundle`, flattened in RTL | |
| `Definition`/`Instance` (elaborate once, instantiate many) | ✔ implicitly, by Python class identity | specialization naming exists only in the `reg_c` path |
| Diplomacy | ✘ (design only) | |
| Layers, probes, instance choice | ✘ | |
| Object model | ✔ MMR | ahead |
| Testbench in the host language | ✔ be-py runtime, asyncio | ahead: ChiselSim only pokes a compiled simulator; zdc *runs the model* |

**The fix is not to make zdc into Amaranth.** Add an **elaboration hook**, in which an
`__elab__(self)` method (or similar) runs as ordinary Python and *calls the builder API*
(add instance, add binding, add port). The C1 creation layer in `zuspec-semantics.md`
already licenses exactly this: objects created only during elaboration. The bodies stay
declarative and parsed, so the behavioural semantics do not change. This gives zdc
Chisel's generator power **while keeping the parameterization visible**, which Chisel
cannot do (§7.3).

### 5.3 Verdict

- **XLS:** zdc already expresses the proc/channel/function model, with better testing.
  It lacks non-blocking ops, a purity check, and P1–P4 rules.
- **Chisel:** zdc expresses everything that survives into FIRRTL except layers, probes and
  memory-latency semantics. It lacks the *generator*, which is the reason people use
  Chisel. One elaboration hook closes most of that.

---

## 6. Could we be the Chisel/XLS killer?

### 6.1 Against XLS — plausible, if three conditions hold

XLS's documented weak points are exactly our strengths:

| XLS weakness | Our answer | Status |
|---|---|---|
| new language (DSLX), syntax churn, two proc syntaxes | SV and Python hosts | ✔ |
| single clock, no CDC | clock-domain tree, `AsyncFIFO`, CDC analysis | ◐ vocabulary exists, insertion doesn't |
| ready/valid only | protocol kits: any protocol through transactors | ◐ ready/valid kit exists |
| verification lives in its own world; no temporal assertions | runs in UVM/cocotb/SBY; SVA | ◐ |
| no select, no arbitration primitive | `select` with policies; CAG | ✔ / design |
| experimental memory | `fw_mem_if` views | ◐ |
| no TLM, no firmware, no test intent | P2/P3/P6, be-sw, PSS | ✔ |

But XLS's *strengths* are where we are weakest, and they are what HLS customers measure:

1. **QoR.** A timing-driven scheduler with a characterized delay model. We have an SDC
   skeleton with integer latencies. *Condition:* either build S4/S5 from the thesis, or
   **ship XLS as a back end** for `timing=static` compute. **Resolved in §6.4:** XLS is the
   primary back end for scheduled compute; the native scheduler is a fallback.
2. **Trust.** XLS's fuzzer and SMT equivalence are why people believe its output.
   *Condition:* a cross-back-end fuzzer (§7.5) and `eqy`/SBY equivalence on lowered pure
   functions.
3. **One clean IR.** XLS has one documented IR; we have five channel encodings and four SV
   emitters. *Condition:* the `ir-primitives.md` §8 consolidation. It is the critical path
   for everything else.

If those hold, the pitch is **"XLS semantics, in the languages and environments you
already use, with clocks, protocols and verification included"**. That is a credible XLS
replacement for the large population that will never adopt DSLX and Bazel.

### 6.2 Against Chisel — no, and it is the wrong goal

- Chisel's moat is **ecosystem and infrastructure**, not semantics: rocket-chip, BOOM,
  Chipyard, XiangShan, Constellation, SiFive's production use, and CIRCT (an
  LLVM-hosted compiler with dozens of dialects and a funded team).
- Its users chose Scala metaprogramming *deliberately*. "No new language" doesn't appeal to
  people who already paid that cost and like it.
- Semantically we are already a superset of what survives into FIRRTL (§2). That is not a
  reason for a Chisel user to switch, because what they value is erased before FIRRTL.

What we *can* credibly claim:
- **For SV-centric teams evaluating Chisel**, everything Chisel would give them except the
  generator ecosystem, without leaving SV or Python, and with verification and TLM that
  Chisel lacks.
- **For Chisel users**, a place to *put* their designs: FIRRTL import (§7.2), so a Chisel
  block gets a class view, a firmware model, protocol-kit verification and multi-host
  integration. That makes us complementary to Chisel, and more useful to its users than a
  replacement would be.

### 6.3 Re-framing

"Killer" invites a fight on the opponent's best ground: QoR for XLS, ecosystem for Chisel.
The defensible position is the one `one-model-many-hosts.md` already reached: **be the
model that every host (and every competing front end) feeds into**. Chisel and XLS then
become two more hosts with strong RTL generation and no integration story, which is the
gap we fill.

### 6.4 The killer app: an SV user layer, with back-end machinery that fills in the detail

*Added after discussion. This section supersedes the "build or borrow" choice in §6.1
condition 1.*

**Context.** Organizations evaluating XLS find it interesting, but they hit two walls:
- a new language is a hard sell;
- it is unclear which problems XLS applies to.

XLS's creators locate its value in **manipulating the IR**, not in DSLX. That suggests:

> **Authors write SV.** Analysis produces XLS IR for the parts XLS is good at. Our
> automation integrates the XLS result as RTL: transactors, FIFOs, clock-domain crossings
> and generated glue. The same SV source simulates as a model, with minimal integration
> effort.

This is the integration thesis made concrete. XLS is not "the" back end. It is the **first
of several detail-filling engines** behind one SV-native design layer.

**Why it holds up.**

1. **XLS's architecture already accepts it.** XLS IR was built as a target: DSLX, XLS[cc]
   (C++) and an MLIR front end all feed it. XLS[cc] exists largely because DSLX was a hard
   sell. An SV front end is the same move, not a fight with XLS's design.
2. **Each layer does what it is good at, and each covers another's gap:**

   | Layer | Does | Covers |
   |---|---|---|
   | SV user layer (fw-hdl) | authoring, class-level simulation, test intent, register model | XLS's new language; XLS tests stuck in the DSLX interpreter |
   | XLS | optimization, scheduling to a clock period, pipelining, delay models | our largest gap (§8: native scheduler) |
   | Our integration machinery | protocol kits, FIFOs, CDC, regblocks, SRAM views, structural glue | XLS's ready/valid-only interfaces, single clock, experimental memory, manual integration |

3. **It answers "what problems does XLS apply to?" per component, not per language.**
   - Timing-free compute loops (`timing=static`) go to XLS. Typical cases are crypto,
     compression, checksums, DSP, floating point and packet transforms.
   - Control, protocol handling and register programming stay as explicitly timed logic
     (`timing=explicit`, zuspec-synth).

   XLS becomes a function-unit generator inside an otherwise ordinary SV design. This is
   the "one knob" from `integration-thesis.md` §3.2, with XLS behind the static setting.
4. **It takes the largest roadmap item off the critical path.** The timing-driven
   scheduler and delay models (thesis S4/S5) move from "build" to "buy". The native
   scheduler becomes optional, kept for transparency and as a hedge.
5. **QoR parity with DSLX by construction.** Both paths use the same back end. The only
   open question is whether our SV → IR conversion yields IR as good as DSLX's
   `ir_converter`, which is measurable: compare post-`opt_main` IR and area for the same
   block. The pitch then rests on **effort**, which is where we win.

**Flow.**

```
SV classes (fw-hdl subset)
  │ pyslang front end + profile checker (§4.4)
  ▼
zuspec IR ── partition by timing class ──┬─ explicit → zuspec-synth (FSM) → RTL
  │                                      └─ static   → XLS IR text
  │                                                     │ opt_main + codegen_main (pinned, prebuilt)
  │                                                     ▼
  │                                        Verilog + codegen signature
  ▼                                        (ports, channels, flow control, RAMs)
structural generator ◄─────────────────────────────────┘
  (protocol kits, FIFO module, CDC, regblocks, SRAM views, top-level wiring)
```

- **Route through zuspec IR, not straight from SV to XLS IR.** It costs a little more, but
  it keeps the C and Python models and the class-vs-RTL comparison. It also keeps XLS a
  replaceable back end rather than a hard dependency.
- **The codegen signature (`--output_signature_path`) is the integration contract.** The
  glue generator reads it and never parses XLS's Verilog.
- **The XLS FIFO is a module we supply** (`--fifo_module`, or per channel via
  `#[channel(fifo_wrapper=…)]` in DSLX). That is our hook for FIFO implementation and
  depth policy. Async FIFOs for clock crossings are a candidate, but the wrapper interface
  has a single `clk`, so this needs investigation.
- **RAM channels** (`--ram_configurations`) map to `fw_mem_if` SRAM views.

**Emitting XLS IR from the SV-normative IR.** This is mechanical, given the §4.4 rules:

| zuspec IR (SV-normative) | XLS IR |
|---|---|
| out-of-bounds array read returns 0 | `sel(in_bounds, {0, array_index(...)})`. XLS's optimizer drops the guard where it proves the index in range, so XLS's clamping never leaks through |
| out-of-bounds write is a no-op | `array_update` (already a no-op when out of bounds in XLS) |
| program order of channel ops | a token chain in program order (conservative, correct) |
| `fork … join` | parallel token chains joined by `after_all` |
| `if (p) get/put` | `receive`/`send` with `predicate=` |
| `try_get` | `receive(blocking=false)` |
| state fields | `state_read` / `next_value` |
| SV file and line | XLS `file_number` table + node `pos=` attributes, so XLS tools point back at the SV source **[verify that positions survive codegen]** |
| division by zero | rejected upstream by the profile checker |

**Simulation: three levels, chosen per component.**

1. **Class model only.** No XLS in the loop. Fastest turnaround, any simulator, any
   existing flow.
2. **Mixed.** Selected components swap to XLS-generated RTL behind transactors, using
   fw-hdl's multi-view mechanism (`multi-view-rearchitecture.md`). The testbench does not
   change.
3. **Full RTL.**

The class model is the reference throughout. Channel-by-channel comparison against the
XLS RTL in the same simulation (`fw_view_diff`) catches both bugs in our conversion and
regressions in XLS. Later option: XLS's ahead-of-time-compiled C++ as a fast
cycle-accurate model behind DPI.

**Risks.**

| Risk | Mitigation |
|---|---|
| SV → XLS IR semantic drift | explicit lowering of D1–D4 (table above); the cross-back-end fuzzer (§7.5) includes the XLS path |
| Debuggability (XLS names like `add_37`) | source positions in XLS IR; schedule report mapped back to SV lines; class-model comparison localizes failures to a channel |
| XLS churn (no semver; codegen versions in flux; proc-scoped channel bugs in 2026) | pin an XLS version; target **XLS IR, not DSLX** (more stable); start with functions and simple procs; class-model comparison acts as a regression detector |
| Users send timing-sensitive control to XLS and get poor results | partitioning is explicit (a component attribute) and explained, never guessed. The profile checker rejects non-blocking or `select` constructs in `timing=static` components unless allowed |
| Equivalence of SV source and XLS output | XLS proves its own optimizations; we cover source → IR with differential simulation, plus SymbiYosys/eqy equivalence for pure functions |
| Dependence on Google's roadmap | zuspec IR stays in the middle. The native scheduler remains a fallback; additional engines can sit behind the same layer |

**Positioning.** Not "an SV front end for XLS", but **an SV-native design layer with
pluggable back-end engines**:
- XLS for scheduled compute;
- zuspec-synth for FSMs;
- the regblock generator for registers;
- protocol kits for pins;
- CDC insertion for clocks.

This survives if XLS stalls, and it reuses the same playbook for future engines. It is
also an easy conversation with the XLS team: another front end feeding their IR, plus the
integration layer they do not want to build. Upstream collaboration is plausible.

**First proof.**
1. Pick a block an organization has already considered for XLS.
2. Write it in the SV subset.
3. Generate XLS IR and run `opt_main` + `codegen_main`.
4. Wrap the result with generated transactors and drop it into the existing simulation
   flow, unchanged.
5. Report:
   - integration effort against the DSLX path;
   - QoR against DSLX-generated IR for the same block;
   - class-model vs RTL agreement under the existing stimulus.

---

## 7. Opportunities we are overlooking

Ordered by leverage ÷ cost.

### 7.1 CIRCT as a back end and analysis engine

We maintain at least four string-based SV emitters (be-sv `generator.py`, the structured
be-sv `ir/`, synth `sprtl/sv_codegen.py`, and the `lines.append` emitters in `mls.py`,
`pipeline.py` and `multiproc.py`). CIRCT's `hw`/`comb`/`seq`/`sv` dialects plus
ExportVerilog are an industrial-strength version of what we're hand-building, and CIRCT
brings much more:

- `ltl`/`verif` → SVA;
- `circt-lec`/`circt-bmc` for equivalence and bounded model checking;
- `arcilator`, a fast compiled RTL simulator with no 64-bit limit;
- `ssp`/`pipeline`/`handshake`/`calyx` (scheduling and dynamic-HLS infrastructure that
  maps directly to our `timing=static` and CAG lowerings);
- `esi` (typed latency-insensitive channels, close to our endpoint model);
- `om` for metadata.

Two caveats:
- **Readability.** firtool output is machine-style. Keep a native readable emitter for the
  transparent SPL path, and use CIRCT for the HLS/CAG path and for analysis.
- **Dependency weight.** Use the Python bindings or the prebuilt `firtool`/`circt-opt`
  binaries rather than building LLVM.

Even used only as a *checker* (lower our P4 to `hw`/`comb`/`seq`, run `circt-lec` against
our own emitted SV), it pays for itself.

### 7.2 Front ends for XLS IR and FIRRTL — embrace, don't kill

Both are documented, text-serialized IRs:
- **XLS IR → zuspec IR:** functions become P0 pure functions; procs become P2 processes;
  channel attributes become endpoint attributes. Where XLS semantics differ from the
  SV-aligned normative rules (D2's clamping, division by zero), the importer inserts the
  XLS behaviour as explicit operations, so imported designs keep their meaning.
- **FIRRTL → zuspec IR:** P4.

Payoff: an XLS or Chisel block immediately gets a Python and SV-class view, firmware C,
protocol kits, UVM/cocotb integration, register-map co-generation and our coverage
derivation. We become the *integration layer for both ecosystems*, which is the
integration thesis applied to competitors. Cost is moderate, and the semantics map cleanly
(§2, §3). The XLS import is also the cleanest way to get a conformance corpus: the XLS
examples (aes, zstd, rle, float32) come with their own tests.

### 7.3 Parameterized SV output

Chisel erases parameters; each specialization becomes a separate FIRRTL module. XLS
monomorphizes. Neither can deliver **`module foo #(parameter W=32, DEPTH=8)`** as
reusable IP. IP vendors and internal IP teams ship parameterized RTL, and that is a
first-order requirement for them.

`ir-primitives.md` rule 5 (type-level IR is first-class) already positions us to do this,
and be-sv already emits `#(parameter …)` for const fields. The job is to make `Param`
expressions real IR (replacing width lambdas) and to keep specialization late. **This is
a capability neither competitor can add without redesigning its IR.** It deserves a line in
the positioning.

### 7.4 LLM-native hardware design

As of 2026 a large share of new RTL is drafted with AI assistance. DSLX and Chisel are
low-resource languages for models; SV and Python are among the highest-resource. A stack
that lets an agent:
- write in SV or Python,
- get **source-located profile diagnostics**,
- run a fast Python/C model,
- lower to RTL with a schedule report, and
- self-check through `fw_view_diff`

is the best agent loop available, and the fw-hdl and zuspec-dataclasses skills already
exist. This changes the adoption argument too. "No new language" matters even more when
the author is partly a model, and a *checked IR with defined semantics* is what makes
agent output trustworthy. Nobody is positioned on this, and it is cheap to lean into:
diagnostics quality, skills, and examples.

### 7.5 A cross-back-end fuzzer (XLS's secret weapon, cheaply)

We have three executors: be-py (asyncio), be-sw (C), and be-sv + Verilator, with be-bc as
the intended reference. A generator of random well-typed P0/P2 programs that cross-checks
all of them (with test-case minimization, like XLS's) would:
- find semantic divergences, especially D1–D4 and P1–P4;
- make `zuspec-semantics.md` executable;
- give the conformance suite in `ir-primitives.md` §6 its engine.

It is perhaps 1–2k LOC on top of what exists. XLS credits its fuzzer with much of its
correctness.

### 7.6 Typed latency contracts at component boundaries

XLS's IO constraints are command-line flags. Chisel has nothing. Filament (timeline types)
and Bluespec (method guards) show that *interfaces carrying timing contracts* enable
compositional scheduling and safe reuse. Our `IfProtocolProperties` already has
`fixed_latency`, `initiation_interval`, `max_outstanding`, `in_order`. Make them:
- **checked:** a protocol-kit formal component proves the implementation meets them;
- **consumed:** the scheduler uses a callee's latency when scheduling the caller, and the
  negotiation kernel propagates them.

That is an HLS system where blocks compose with timing guarantees, which XLS's "flatten
and reschedule" model cannot offer.

### 7.7 Layers, via `bind`

Chisel's layers emit verification logic into separate bound modules, so the design RTL
stays clean and verification stays attached. We generate assertions (`sva_gen.py`,
`verilog_props.py`) and plan `fw_dbg` trace sites and derived coverage. Emitting all of it
as **`bind` files, one layer per concern** (assertions, coverage, trace, protocol
checkers), solves both "assertions don't survive lowering" and "don't pollute the
synthesizable RTL". It uses an SV feature every simulator and formal tool supports.

### 7.8 HLS across clock domains

Neither tool schedules across clocks. XLS is single-clock, and Chisel domains (2026) are
metadata checks. A `timing=static` process whose channels cross domains, with the
negotiation kernel inserting `AsyncFIFO`s and the scheduler treating the crossing as an
IO constraint, is unoccupied ground. It is also exactly what data-movement engines (the
beachhead) need. The vocabulary exists in zdc (`cdc.py`, `CDCAnalysisPass`); insertion is
missing.

### 7.9 Smaller items

- **DontCare / `invalidate`** in P0/P4: cheap, helps optimization and formal.
- **Explicit `Trunc`** and an IR-level **narrowing** pass: XLS's single most valuable
  optimization.
- **`#[extern_verilog]`-style FFI is free for us**: an SV module is already an extern.
  Make it easy from Python (`Extern` + port map) and advertise it.
- **Memory with read latency and read-under-write** in P4, binding to SRAM views through
  `fw_mem_if`. XLS's RAM support is experimental, so this is open ground.
- **Instance choice ↔ views**: Chisel's `instchoice` independently validates
  `multi-view-rearchitecture.md`. Cite it.

---

## 8. Gap list, mapped onto the existing roadmap

| Gap | Kind | Size | Thesis stage / doc |
|---|---|---|---|
| Consolidate channel encodings; one `Process` | IR | M | `ir-primitives.md` §8 — **critical path** |
| Defined op semantics, **SV 2-state aligned** (OOB, shifts, div0, X); D1–D4, P1–P4 normative | spec | S | `zuspec-semantics.md` (new section); §4.4 |
| Port 2–3 XLS examples to the fw-hdl SV subset, run on Verilator against XLS vectors | prototype | S | §4.4 |
| `try_*`/`can_*`/`peek`; single-value interface; channel strictness attribute | IR + `fw_std_pkg` | S | S1 (extended) |
| Effect-ordering relaxation (`par` / unordered) — §4.2 | IR | S | new; closes thesis Q5 / primitives Q2 |
| Explicit `Trunc`; `Param` exprs replace width lambdas | IR | S–M | `ir-primitives.md` P0 |
| Emit `signed`, `typedef enum`, packed structs, directional aggregates | be-sv | S–M | — |
| User assert/cover/trace survive lowering, as `bind` layers | be-sv/synth | M | §7.7 |
| Profile checker on IR for SV and Python sources | tool | M | S3 |
| **XLS back end** for `timing=static` compute: XLS IR emitter, pinned XLS tools, signature-driven glue generator (§6.4) | be + integration | M | S6, promoted to primary |
| Native timing-driven scheduler + delay model | synth | L | S4–S5, now fallback only |
| Cross-back-end fuzzer | test | M | §7.5 |
| FIRRTL and XLS-IR front ends | fe | M each | §7.2 (new) |
| CIRCT back end / checker | be | M | §7.1 (new) |
| Elaboration hook in zdc (generator power) | DSL | M | §5.2 (new) |
| Negotiation kernel (Diplomacy) implementation | IR + runtime | L | `reference/diplomacy-integration.md` |
| Memory latency/RUW + SRAM views | IR + be | M | S11 |
| CDC insertion on domain-crossing channels | synth | M | S11, §7.8 |

**Suggested order** (revised for §6.4):
1. **The §6.4 first proof, as a thin vertical slice:**
   - SV subset, through a minimal zuspec IR path, to the XLS IR emitter;
   - pinned `opt_main`/`codegen_main`;
   - a glue generator driven by the codegen signature;
   - the class model vs the RTL in one simulation.

   It can start before consolidation is finished, as long as the XLS emitter is written
   against the kernel shapes in `ir-primitives.md`.
2. Consolidation and the defined-semantics spec (SV-aligned), which the slice will have
   stress-tested.
3. The fuzzer, with the SV simulator and the XLS path among the executors it checks.
4. The partition rule and profile checker for `timing=static` (what may go to XLS), with
   explained diagnostics.
5. Bind-layer assertions and the be-sv type fixes, which are cheap and visible.
6. The XLS-IR *front end* (import), for corpus and interop.
7. FIRRTL import and the elaboration hook.
8. The native scheduler, only if a gap in XLS demands it.

---

## 9. Open questions

| # | Question |
|---|---|
| Q1 | Is CIRCT an acceptable dependency (Python wheels / prebuilt binaries), or is it analysis-only? |
| Q2 | ~~Do we commit to the XLS back end as a supported path?~~ **Decided (§6.4):** yes, as the primary path for `timing=static` compute. Target XLS **IR** with a pinned XLS version. Open sub-questions: how to distribute the XLS binaries (conda / release tarballs), and the version-bump policy |
| Q7 | Can the `--fifo_module` hook carry an async FIFO for domain-crossing channels, given its single-`clk` interface, or must CDC FIFOs sit outside the XLS block? |
| Q8 | Do XLS IR source positions survive into codegen output (line maps), so that XLS reports point at SV source? |
| Q3 | ~~OOB semantics: XLS clamping or "assume in bounds + assert"?~~ **Decided (§4.1, §4.4):** SV 2-state semantics are normative. A read returns 0 and a write is a no-op. The guard is dropped when the index is provably in bounds. XLS clamping is inserted by the XLS-IR front end on import |
| Q4 | Does the zdc elaboration hook run under be-py only, or must the IR record the generator so that other hosts can re-run it with new parameters? (That is the difference between "parameterized IR" and "monomorphized IR".) |
| Q5 | Where is be-bc? `zuspec-semantics.md` names it as the reference implementation, but it isn't in this workspace, so the fuzzer (§7.5) needs to know its oracle. |
| Q6 | How much of FIRRTL's directional-aggregate model (flip, flow) do we adopt in P4, versus keeping direction only on endpoints? |

---

## 10. Sources

**Chisel / FIRRTL / CIRCT**
- Chisel releases and roadmap: https://github.com/chipsalliance/chisel/releases ,
  https://github.com/chipsalliance/chisel/blob/main/ROADMAP.md (7.0 in Sep 2025; 7.16 in Oct 2026)
- FIRRTL spec: https://github.com/chipsalliance/firrtl-spec (v6.0.0, May 2026)
- Hierarchy API: https://www.chisel-lang.org/docs/cookbooks/hierarchy
- Layers: https://www.chisel-lang.org/docs/explanations/layers
- Probes: https://www.chisel-lang.org/docs/explanations/probes
- Properties / OM: https://www.chisel-lang.org/docs/explanations/properties
- Instance choice: https://www.chisel-lang.org/docs/explanations/instchoice
- Intrinsics: https://www.chisel-lang.org/docs/explanations/intrinsics
- ChiselTest → ChiselSim: https://www.chisel-lang.org/docs/appendix/migrating-from-chiseltest
- CIRCT dialects: https://circt.llvm.org/docs/Dialects/
- Tywaves: https://arxiv.org/abs/2408.10082
- Domains: Chisel source `core/src/main/scala/chisel3/domain/*`, release notes 7.10–7.14

**XLS** (repository at commit 17f5c7a, 2026-10-02)
- IR semantics: https://google.github.io/xls/ir_semantics/
- DSLX reference / std: https://google.github.io/xls/dslx_reference/ ,
  https://google.github.io/xls/dslx_std/
- Procs: https://google.github.io/xls/tutorials/what_is_a_proc/ ,
  https://google.github.io/xls/tutorials/how_to_use_procs/
- Elaboration / proc-scoped channels: https://google.github.io/xls/elaboration/ ,
  https://google.github.io/xls/design_docs/proc_scoped_channels/
- Scheduling: https://google.github.io/xls/scheduling/
- Delay estimation: https://google.github.io/xls/delay_estimation/
- Codegen options: https://google.github.io/xls/codegen_options/
- Fuzzer / solvers / JIT: https://google.github.io/xls/fuzzer/ ,
  https://google.github.io/xls/solvers/ , https://google.github.io/xls/ir_jit/
- XLS[cc]: https://google.github.io/xls/tutorials/xlscc_channels/
- Source: `xls/ir/op_list.h`, `xls/ir/channel.h`, `xls/dslx/frontend/module.h`
- Issues: #1350 (temporal assertions), #2175 (synchronous procs), #4554 (proc-scoped codegen)

**Our stack** (paths relative to `packages/`)
- IR: `zuspec-ir-core/src/zuspec/ir/core/{data_type,expr,stmt,activity,constraint,coverage}.py`
- DSL runtime: `zuspec-be-py/src/zuspec/be/py/model/{types,decorators}.py`
  (`zuspec-dataclasses` re-exports them)
- Scheduler: `zuspec-synth/.../sprtl/scheduler.py` (clock period informational, line ~672),
  `passes/sdc_schedule.py`, `sprtl/pipeline.py`
- Assert-as-definition: `zuspec-synth/.../sprtl/transformer.py:762`
- SV emission: `zuspec-be-sv/.../generator.py`, `zuspec-synth/.../sprtl/sv_codegen.py`
- RTL → C: `zuspec-be-sw/.../passes/rtl/*`, `rtl/type_mapper.py` (≤64-bit)
- CDC: `zuspec-dataclasses/.../cdc.py`, `CDCAnalysisPass`
