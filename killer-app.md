# The Killer App — A SystemVerilog Design Layer over XLS

*Status: proposal, for review. Snapshot as of 2026-10-03.*

**Companions:**
- `chisel-xls-assessment.md` — the analysis this proposal comes from: §4.4 (SV as the
  input language, SV-normative semantics) and §6.4 (the position);
- `integration-thesis.md` — SPL/HLS/CAG, the "one knob", the beachhead;
- `one-model-many-hosts.md` — the IR at the center;
- `ir-primitives.md` — the kernel the emitter targets;
- `multi-view-rearchitecture.md` — swapping the class model for RTL.

---

## 0. One paragraph

Designers write ordinary SystemVerilog classes using the fw-hdl library. That source
simulates as-is, as a model, in the simulators and testbenches they already run. Our
tools analyze it:
- **Timing-free compute** goes to Google XLS as XLS IR. XLS optimizes and schedules it
  into pipelined RTL at a target clock.
- **Control, registers and protocols** go through our own lowerings.

Our automation then stitches the XLS output into the design: protocol transactors, FIFOs,
register blocks, reset and clock adaptation, top-level glue, and a firmware header. The
designer never writes DSLX, never hand-integrates generated RTL, and can switch any block
between "model" and "generated RTL" without touching the testbench. **We supply the user
layer and the integration; XLS supplies the hardest part of the back end.**

Over time the glue grows. With several XLS islands, the logic between them is written at
the transaction level too, and lowered with hand-RTL QoR. Users then *opt into*
restriction one component at a time, because each step pays back in generated RTL. That
is the opposite of the restrict-first bargain HLS languages ask for (§1.4).

---

## 1. Motivation

### 1.1 What organizations evaluating XLS run into

1. **A new language is a hard sell.** DSLX is Rust-flavoured, changes without
   backward-compatibility guarantees (two proc syntaxes, feature-gated generics and traits,
   two type-inference engines in 2026), and comes with a Bazel-centric toolchain. Design
   and verification teams read SV.
2. **It isn't clear which problems XLS applies to.** XLS is excellent at statically
   schedulable compute: datapaths, transforms, streaming kernels. It is weak at control,
   protocols, multi-clock and memory-heavy designs. Adopting a *language* forces that
   question to be answered for a whole team or project, when it is really a per-block
   question.
3. **Integration is left to the user.** XLS's interfaces are ready/valid, valid-only or
   single-value wires. It has one clock per block, RAMs are experimental, and the tests live
   in the DSLX interpreter. Everything around the generated module is hand-written.
   - **Evidence:** XLS's own largest design, the ZSTD decoder (with Antmicro), implements
     its **AXI and CSR interfaces in DSLX** (`axi_csr_accessor.x`, `csr_config.x`,
     `memory/axi_*.x`) and ships a hand-written `xls_fifo_wrapper.sv`. Much of its
     complexity is integration, not compression.

### 1.2 Where XLS's value actually is

In conversations, XLS's creators place its value in **the IR and what can be done to it**:
- a precise, fully defined, bit-accurate IR;
- about 90 optimization passes;
- SDC scheduling under clock-period, throughput and I/O constraints, with characterized
  delay and area models (asap7, sky130, unit);
- JIT/AOT execution;
- SMT-based equivalence checking.

XLS's architecture agrees. DSLX, XLS[cc] (C++) and an MLIR dialect all target the same IR,
and XLS[cc] exists largely because DSLX is a hard sell. **An SV front end is the same move,
not a fight with XLS's design.**

### 1.3 Why this is the killer app

| Stakeholder | What they get |
|---|---|
| Designer | XLS-quality pipelining without learning DSLX; writes SV; picks per block which parts go to XLS |
| Verification | the source *is* a simulatable model in the existing environment (UVM, cocotb, Verilator, commercial); class model vs generated RTL compared in one simulation, with the same tests |
| Integrator | no hand-written wrappers: protocols, FIFOs, registers, resets and top-level wiring are generated |
| Firmware | register map and C header from the same source; class model usable for bring-up before RTL exists |
| Management | QoR equals DSLX's **by construction** (same back end); the pitch is effort and risk, which is measurable |

And for us, it takes the largest item off our roadmap: the timing-driven scheduler and
delay models (`integration-thesis.md` S4/S5) move from "build" to "buy".

### 1.4 The strategy over time: from glue to TLM, with restriction as a pull

XLS input is high level, so **at first our value is glue**: we wrap an XLS island and
connect it to registers, protocols and the testbench. As designs grow, the shape changes.
There are **several XLS islands, and the logic between them grows**:
- sequencers and command decoders;
- register bridges, packetizers, width converters, credit and flow control;
- arbitration between islands.

That logic is control-dominated and timing-explicit, which XLS handles poorly. Today it is
written as bare RTL.

**Proposal: write the glue at the transaction level too, and lower it with the same QoR as
hand-written RTL.** The glue is exactly what the explicit-timing (SPL) lowering is for.
SPL lowering is *transparent* — one awaited beat is one state is one cycle, with no
scheduler choosing — so its QoR is determined by the structure the author writes, as with
hand RTL. A whole subsystem then lives in one transaction-level SV model:
- XLS fills in the compute islands;
- SPL fills in the glue;
- regblock and protocol kits fill in the edges.

The model simulates as-is from day one.

**This inverts the usual adoption story for HLS.**

| | DSLX / classic HLS | This layer |
|---|---|---|
| Starting point | a restricted language: everything must be synthesizable from line one | unrestricted SV classes: models, testbench components, firmware models, which teams already write |
| Restriction | imposed up front, before any value | **opted into per component, each step paid back by generated RTL** |
| Value arrives | after the design is complete enough to synthesize | immediately (a simulatable model), then incrementally (RTL per component) |

Restriction stops being a cost the tool demands and becomes something the user *asks
for*: "restrict this component, and you get its RTL for free". The steps are already
defined, as the axes in `zuspec-semantics.md` §2 (creation, data bounds, communication,
time, determinism):

| Rung | Restrictions accepted | What you get | Engine |
|---|---|---|---|
| **Model** | none (the P6 host layer) | executable spec, reference model, firmware bring-up, testbench | any SV simulator |
| **Explicit timing** | bounded data (D1/D0), communication only through endpoints (M1), time in cycles (T1), structure created only at elaboration (C1) | RTL with the timing you wrote: glue, control, protocols | SPL → FSM |
| **Static** | as above, plus no timing (T0), blocking ops only (Kahn), pure functions | pipelined RTL at the clock you target | XLS |

The profile checker becomes a **guide**, not a gate. It tells the user what stands
between a component and the next rung ("to lower this to RTL, replace the dynamic queue at
line 42 with a bounded channel").

**Arc:**
1. **Glue around one island.** Value is integration; the MVP (§5).
2. **Islands plus TLM glue.** Value is a whole subsystem in one model. Showcase: AES-GCM as
   an XLS AES-CTR island and an XLS GHASH island, with TLM sequencing and tag assembly
   between them (§5.2, D4).
3. **The model is the design.** Restriction is a per-component knob, and
   `integration-thesis.md`'s SPL/HLS/(CAG) "one knob" becomes how teams work rather than
   a compiler feature.

**What has to be true:** glue lowered from TLM must match hand-written RTL on area and
timing, and its output must be readable. That is a measurable claim, and the MVP measures
it (§6).

---

## 2. Scope

### 2.1 Positioning

**An SV-native design layer with pluggable back-end engines that fill in the detail.**
XLS is the first engine, for scheduled compute. The others already exist or are planned:

| Engine | Fills in | Status |
|---|---|---|
| **XLS** | pipelined datapaths for `timing=static` components | **new (this proposal)** |
| zuspec-synth SPL | FSMs for explicitly timed components (protocol beats, command handling) | exists |
| fw-hdl MMIO / regblock | register blocks, register-driven FSMs, C headers | exists (Phase A) |
| protocol kits | channel ↔ pin protocol (ready/valid, Wishbone, …) | ready/valid exists; Wishbone in `fw-proto-wb` |
| structural generator | top-level wiring, module instances | exists (`emit/structural.py`) |
| CDC insertion | crossings between clock domains | designed, not built |

Framed this way, the approach survives if XLS stalls, and the next engine slots in the same
way. It is also an easy conversation with the XLS team: another front end feeding their
IR, plus the integration layer they do not want to build.

### 2.2 In scope (the product)

- An **SV input subset** for XLS-bound components: procs, channels, state, pure functions,
  packed types, bounded loops, parameters. It simulates natively.
- A **`timing=static` attribute** on a component that routes it to XLS, together with a
  **profile checker** that explains why something cannot go to XLS.
- An **XLS IR emitter** from zuspec IR.
- **XLS tool integration**: pinned binaries; options derived from the design (clock
  period, reset style, flop kinds); outputs captured (Verilog, signature, schedule report).
- A **glue generator** driven by XLS's codegen signature.
- **Multi-view simulation**: the class model and the XLS RTL are swappable per component,
  and their channels are compared.
- **Reports**: schedule (which operation in which stage), critical path, and the mapping
  back to SV lines.

### 2.3 Out of scope (for now)

| Item | Why deferred |
|---|---|
| Non-blocking channel ops, `select`, latency-sensitive procs on the XLS path | breaks Kahn determinism; not needed by the MVP designs |
| Multi-proc XLS packages (XLS-side proc networks) | **We** compose proc networks with our own FIFOs and structure, and each XLS invocation is a single proc (§4.4). This avoids XLS's churning proc-scoped-channel and multi-proc codegen paths |
| Clock-domain crossings inside an XLS block | XLS is single-clock. Crossings sit outside, in our glue (open question Q2) |
| XLS RAM rewrites / SRAM binding | experimental in XLS; later, via `fw_mem_if` views |
| AXI | Wishbone and ready/valid first; AXI kit later |
| Importing existing DSLX/XLS IR designs | valuable ("host the XLS ecosystem"), but a separate track (`chisel-xls-assessment.md` §7.2) |
| Python (zuspec-dataclasses) as XLS input | nearly free once the emitter works on zuspec IR, but not needed to prove the point |
| Native scheduler | fallback only |
| CAG / dynamic scheduling | separate track |

---

## 3. Feature match

**Key:** ✔ exists · ◐ partial · ✘ missing. **MVP** marks whether a row is needed for the
MVP designs (§5).

### 3.1 XLS features → SV user layer

| XLS (DSLX / IR) | SV user layer | Today | Enhancement required | MVP |
|---|---|---|---|---|
| `uN`/`sN`/`bits[N]` | `bit [N-1:0]`, `bit signed [N-1:0]` | ◐ FE maps scalars | width rules pinned (SV context widths → explicit ext/trunc in IR) | ✔ |
| struct | `typedef struct packed` | ✘ FE (`type_mapper.py` is 46 LOC) | packed struct mapping in FE; layout contract (§4.6) | ✔ |
| array | packed / fixed unpacked arrays | ✘ FE | array mapping, indexing with SV-normative OOB (§4.3) | ✔ |
| enum (explicit width) | `typedef enum bit [k:0]` | ✘ FE | enum mapping | ✔ |
| tuple | packed struct | ✘ | via struct | — |
| parametric `<N: u32>` | parameterized class `#(int W)` | ◐ | specialize at elaboration (MVP); keep `Param` in IR later | ✔ |
| pure `fn` | `function automatic` (class static or package) | ◐ FE has `func_mapper` (25 LOC) | purity check; call → XLS `invoke` (or inline) | ✔ |
| `for` (bounded) → `counted_for` | `for` with constant bound | ✘ FE (only `forever`) | bounded-loop mapping | ✔ |
| `match` | `case` / `unique case` | ✘ | case mapping → `sel` / `priority_sel` | ✔ |
| `proc` + `config` + `spawn` | `fw_component` + `build`/`connect` | ✔ | — | ✔ |
| proc state (`init`, `next_value`) | class fields + reset values | ◐ | state extraction for `timing=static` | ✔ |
| `next` activation | one iteration of `run()`'s `forever`, with **no `tick()`** | ◐ (the SPL path treats `forever` as beats) | the timing-free activation rule (thesis §3.5) | ✔ |
| `recv` / `send` | `in.t.get(x)` / `out.t.put(v)` | ◐ `fw_get_if`/`fw_put_if` exist; FE handles `put` | FE handles `get`; maps to `receive`/`send` | ✔ |
| `recv_if` / `send_if` | the op under `if (p)` | ✘ | predicate extraction | ✔ |
| tokens / `after_all` | program order (total); `fork…join` relaxes | — | program-order token chain (MVP); `fork…join` later | ◐ |
| `recv_non_blocking` | `try_get` | ✘ in `fw_std_pkg` | add to the std interfaces | — |
| `single_value` channel | `fw_value_if` | ✘ | new std interface | — |
| `assert!` / `cover!` / `trace_fmt!` | `assert` / `cover` / `fw_dbg` | ◐ | map to XLS `assert`/`cover`/`trace` so they survive into the XLS RTL | ◐ (assert) |
| `#[test]`, `#[test_proc]` | SV test over `fw_root` | ✔ | — | ✔ |
| `#[quickcheck]` | `rand` + constraints | ✔ (SV native) | — | — |
| `--clock_period_ps`, `--pipeline_stages` | from the component's **clock domain** + `timing=static` attribute | ◐ (`fw_clock_domain` exists) | attribute syntax (§4.1); period attribute on the domain | ✔ |
| `--worst_case_throughput` (II) | attribute | ✘ | attribute | ✔ |
| `--io_constraints` | attribute (later: typed latency contracts) | ✘ | — | — |
| `--flop_inputs/outputs[_kind]` | chosen by the glue generator per protocol kit | ✘ | policy in glue | ✔ |
| `--reset*` | from the component's **reset domain** | ◐ | mapping | ✔ |
| `--fifo_module` | **our** FIFO module (for the future multi-proc case) | ✘ | — | — |
| source positions | SV file/line → XLS `file_number` + `pos=` | ✘ | emitter support; verify they survive codegen (Q3) | ◐ |
| JIT / interpreter | class model in any SV simulator; be-py / be-sw | ✔ | — | ✔ |
| fuzzer / equivalence | differential sim, class vs RTL; SymbiYosys/eqy for functions | ◐ | minimal channel comparison (§4.7) | ✔ |

### 3.2 Integration features XLS lacks → what the layer provides

| Need | XLS alone | This layer | Today | MVP |
|---|---|---|---|---|
| Pin protocol other than ready/valid | hand-written | protocol kit transactor bound to the channel | ◐ ready/valid kit; Wishbone kit in `fw-proto-wb` | ✔ (ready/valid + register bus) |
| Software-programmed configuration (CSRs) | hand-written in DSLX (ZSTD) | register model → regblock RTL + C header; register-to-channel bridge (§4.5) | ✔ regblock; ✘ bridge | ✔ |
| Mixing control (FSM) with compute | everything in DSLX | SPL component (FSM) + `timing=static` component (XLS) in one design | ✔ SPL; ✘ partition | ✔ |
| Reset polarity and sync/async matching | flags | from the reset domain | ◐ | ✔ |
| Multiple clocks | ✘ | clock-domain tree; CDC FIFOs in glue | ◐ vocabulary | — |
| Model ↔ RTL swap without testbench changes | ✘ | multi-view | ◐ design | ✔ (minimal) |
| Verification in the user's environment | ✘ (DSLX interpreter) | the source runs in their simulator; same tests on both views | ✔ | ✔ |
| Firmware bring-up model | ✘ | class model + register model + C header | ◐ | ◐ (header) |
| SVA temporal properties | ✘ (issue #1350) | protocol-kit checkers bound to the XLS RTL | ◐ | — |

---

## 4. Required enhancements

Grouped by component. Sizes: S ≈ days, M ≈ 1–3 weeks, L ≈ more.

### 4.1 SV library and attribute (S)
- **`timing=static` attribute** on a component, carrying the target clock (default: from
  the component's clock domain), the stage count (optional), and II. Syntax to be decided
  with `reference/attaching_metadata.md`. A macro such as
  `` `fw_schedule_static(.ii(1)) `` or a parameter on the component class are both
  candidates.
- **A clock-period attribute** on `fw_clock_domain`.
- Later (not MVP): `try_get`/`try_put`/`can_*`/`peek`, `fw_value_if`, endpoint depth and
  strictness attributes.

### 4.2 SV front end (M–L, **the largest item**)
The pyslang front end (`python/fw/hdl/fe`, about 1.7k LOC) covers `forever`/`put`/`tick`
beats and the MMIO/register paths. For the XLS subset it needs:
- types: packed structs, arrays, enums, signed, parameterized classes (specialized at
  elaboration);
- statements: bounded `for`, `if`/`case` → predication, local variables, `get`, `put` under
  predicates;
- functions: `function automatic` calls (class-static and package), with a purity check;
- state extraction: class fields written in `run()` become proc state;
- SV width rules resolved to explicit `Zext`/`Sext`/`Trunc` (pyslang supplies the resolved
  types; see `pyslang11-ast-notes` for its AST quirks).

### 4.3 Profile checker for `timing=static` (M)
Source-located, explained errors. It rejects:
- `tick()` or other timing;
- non-blocking ops and `select` (MVP);
- 4-state types (`logic`), `x`/`z`;
- dynamic containers, class handles in the datapath;
- unbounded loops;
- unguarded division;
- calls to non-pure functions;
- channel ops on non-port objects.

This is the counterpart of "every DSLX program is synthesizable", and the quality of these
messages *is* the user experience.

### 4.4 IR subset and partition (S–M)
- The `ir-primitives.md` P0 + P2 subset only: no need to finish the whole consolidation
  first.
- **Partition rule:** a component with `timing=static` becomes one XLS package containing
  one proc. All other components stay on existing paths. Proc networks are composed by
  *our* structural layer, not inside XLS.
  - **Trade-off:** we lose cross-proc optimization.
  - **Gain:** we avoid XLS's least stable area, and each XLS block is independently
    testable and swappable.
- **Normative semantics** for this subset (SV 2-state, `chisel-xls-assessment.md` §4.1
  D1–D4), written into `zuspec-semantics.md`.

### 4.5 XLS IR emitter (M)
zuspec IR (P0 + P2 subset) → XLS IR text:

| zuspec IR | XLS IR |
|---|---|
| bits, struct, array, enum | `bits[N]`, tuple, array, `bits[k]` |
| `Zext`/`Sext`/slice | `zero_ext`/`sign_ext`/`bit_slice` |
| array read (SV OOB → 0) | `sel(in_bounds, cases=[literal 0, array_index(...)])`; XLS drops the guard when it proves the index in range |
| array write (OOB no-op) | `array_update` (already a no-op when out of bounds) |
| bounded `for` | `counted_for` (or unrolled) |
| `if`/`case` | `sel` / `priority_sel` |
| pure function call | `invoke` |
| state fields | `state_read` / `next_value` |
| `get` / `put` (predicated) | `receive` / `send` with `predicate=`, chained by tokens in program order |
| `assert` | `assert` |
| SV file and line | `file_number` table + `pos=` |

Plus the **register-to-channel bridge** pattern for configuration: a doorbell write
assembles a command struct from registers and puts it to a channel. This is an SPL
component, written by the user or generated from the register model.

### 4.6 XLS tool integration (S–M)
- **Pinned XLS release** (binary tarball or conda, never a Bazel build), recorded in the
  project. A DV Flow Manager task wraps `opt_main` and `codegen_main`.
- **Options derived from the design:**
  - `--clock_period_ps` (clock domain) and/or `--pipeline_stages`;
  - `--worst_case_throughput` (II);
  - `--reset`, `--reset_active_low`, `--reset_asynchronous` (reset domain);
  - `--module_name`;
  - `--generator=pipeline` or `combinational`;
  - `--use_system_verilog`;
  - flop kinds (glue policy).
- **Outputs captured:** Verilog, `--output_signature_path` (the integration contract), the
  schedule, and the block IR, for reports.
- **Data-layout contract:** XLS flattens tuples with element 0 in the MSBs (matching SV
  packed-struct order) and arrays with element 0 in the LSBs (matching `[N-1:0]` packed
  arrays). Pin this, and test it with a layout round-trip.

### 4.7 Glue generator (M)
Reads the signature (`xls/codegen/module_signature.proto`) and generates an SV wrapper
module plus `fw_root` bindings:
- each channel's `<ch>`, `<ch>_vld`, `<ch>_rdy` ports → the protocol kit's transactor for
  that endpoint;
- packed-struct casts at the boundary;
- reset and clock adaptation;
- instantiation in the structural top next to the regblock and SPL FSMs (extends
  `emit/structural.py`).

### 4.8 Multi-view and channel comparison (M)
- A per-component view selection: class model or XLS RTL behind transactors. This is a
  minimal subset of `multi-view-rearchitecture.md`.
- **Minimal `fw_view_diff`:** a splitter on the input channels, then per-channel, in-order
  comparison of the output channels. Valid because the MVP components are Kahn (blocking
  ops only).

### 4.9 Reports (S)
- Schedule report: stage per operation, mapped to SV lines.
- Pipeline depth and register bits.
- Critical path from XLS's delay model.
- Area from yosys (generic or ice40) for the comparisons in §6.

---

## 5. MVP

### 5.1 Goal

Show, on public designs with public reference vectors, that:
1. a designer can write an XLS-class block **in SV**, simulate it as a model in an existing
   flow, and get **XLS-generated pipelined RTL integrated automatically**;
2. the **QoR matches** the DSLX version of the same design under the same XLS version;
3. **integration effort** (hand-written lines, steps) is a fraction of the DSLX path;
4. the **class model and the generated RTL agree** under the same tests.

### 5.2 Target designs

Chosen from XLS's own repository (`google/xls`, Apache-2.0). Each has a DSLX version for
parity, tests or reference vectors, and a distinct job in the demonstration.

| # | Design | XLS source | Kind | What it proves | Reference |
|---|---|---|---|---|---|
| **D1** | **CRC-32, streaming** | `xls/examples/crc32/crc32.x` (byte function, table-less, 8-round loop) | pure function + a small stateful proc (running CRC, `last` flag) | the plumbing end to end; function path (`counted_for`, `invoke`); proc state; clock-period-driven pipelining of the 8-round loop | check value: CRC-32("123456789") = `0xCBF43926`; `crc32_reference.cc` |
| **D2** | **Run-length encoder** | `xls/modules/rle/rle_enc.x` (parametric proc, `recv_if`/`send_if`, struct state, `last` flag) | single proc | the proc path, predicated I/O, parameterized class → specialization; **QoR parity vs DSLX** on a design XLS itself showcases | DSLX tests `rle_enc_small_test.x` / `rle_enc_large_test.x` |
| **D3** | **AES-128-CTR offload engine** (headline) | `xls/modules/aes/aes_ctr.x` + `aes.x` (`Command` struct on a channel, IDLE/PROCESSING state, block streams) | register-programmed engine: **SPL + XLS + regblock + protocol kits** | the integration claim. Firmware programs key, IV, length and start through registers; the bridge sends `Command`; the XLS-pipelined AES core streams blocks over ready/valid; status/done is visible to firmware; a C header is generated. Model ↔ RTL swap under one test | NIST SP 800-38A F.5.1 (CTR-AES128) vectors; XLS `aes_ctr_test.cc` |

**Why these three:**
- They form a ladder: plumbing → proc semantics and parity → full integration.
- D3 sits squarely in the beachhead domain (`integration-thesis.md` §9: offload engines),
  and it is the design where the XLS-only path needs the most hand-written integration.
- None needs non-blocking ops, multi-proc XLS packages, RAMs or multiple clocks, so the MVP
  avoids every XLS area flagged as unstable.

**Candidates for later**, with the reason each was deferred:

| Design | XLS source | Kind | Why later |
|---|---|---|---|
| SHA-256 | `xls/examples/sha256.x` | pure function, 64-round loop over `bits[512]` | good loop-scheduling showcase; overlaps D1 and D3 |
| JPEG IDCT (Chen) | `xls/examples/jpeg/idct_chen.x` | large pure function over `s32[64]` | strong pure-compute QoR benchmark; Go golden reference |
| FP32 add (dual-path) / `fp32_fmac` | `xls/modules/add_dual_path/`, `xls/examples/fp32_fmac.x` | parametric float function | "XLS's sweet spot" benchmark; needs a large parametric front-end surface |
| FIR filter, dot product | `xls/examples/fir_filter.x`, `dot_product.x` | parametric functions over arrays | DSP demo; trivial once D1/D2 work |
| Reorder queue | `xls/examples/reorder_queue/reorder_queue.x` | latency-sensitive proc, buffer state | needs non-blocking semantics (phase 2) |
| 4×4 systolic matmul | `xls/examples/matmul_4x4/matmul_4x4.x` | proc network (node procs) | showcases *our* proc-network composition with our own FIFOs, where XLS users have hit deadlock and lowering issues |
| **D4: AES-GCM as islands + TLM glue** (phase-2 headline) | `xls/modules/aes/aes_gcm.x`, `ghash.x`, `aes_ctr.x` | 11 procs in DSLX; in our version, two XLS islands (AES-CTR, GHASH) plus TLM glue (command sequencing, AAD/length handling, tag assembly), lowered via SPL | the §1.4 arc. Direct comparison: everything-in-DSLX vs islands + TLM glue, on QoR and on lines written. NIST GCM test vectors |
| ZSTD decoder (import, not rewrite) | `xls/modules/zstd/` | large multi-proc, AXI/CSR in DSLX | the **import track** demo: wrap an existing XLS design and replace its DSLX AXI/CSR procs with our regblock and protocol kits |

### 5.3 D3 in outline (SV user layer)

```systemverilog
// Configuration: register model (regblock RTL + C header generated)
class aes_ctr_regs extends fw_reg_block;      // key[4], iv[3], msg_bytes, ctrl.start, status.busy/done
  ...
endclass

// Control: explicitly timed (SPL → FSM). Doorbell → Command on a channel.
class aes_ctr_ctrl extends fw_component implements fw_runnable;
  fw_port #(fw_put_if #(aes_cmd_t)) cmd;
  virtual task run();
    forever begin
      regs.ctrl.start.wait_set();             // MMIO pattern: doorbell
      cmd.t.put(aes_cmd_t'{key: regs.key_value(), iv: regs.iv_value(),
                           msg_bytes: regs.msg_bytes.get(), initial_ctr: 0, ctr_stride: 1});
      regs.status.busy.set(1);
      ...
    end
  endtask
endclass

// Compute: timing-free → XLS (pipelined to the clock domain's period, II=1)
class aes_ctr_core extends fw_component implements fw_runnable;
  `fw_schedule_static(.ii(1))                 // proposed syntax (§4.1)
  fw_port #(fw_get_if #(aes_cmd_t)) cmd;
  fw_port #(fw_get_if #(block_t))   ptxt;
  fw_port #(fw_put_if #(block_t))   ctxt;
  bit busy; aes_cmd_t c; bit [31:0] ctr, blocks_left;   // proc state

  virtual task run();
    forever begin                             // one activation; no tick()
      block_t p;
      if (!busy) begin cmd.t.get(c); ctr = c.initial_ctr; blocks_left = (c.msg_bytes + 15) >> 4; end
      ptxt.t.get(p);
      ctxt.t.put(aes_pkg::encrypt(c.key, {c.iv, ctr}) ^ p);   // pure function automatic
      ctr += c.ctr_stride;  blocks_left -= 1;  busy = (blocks_left != 0);
    end
  endtask
endclass
```

This is sketch-level, and the exact fw-hdl register API is elided. Note that the source
contains **no XLS, no pipeline registers, no ready/valid wiring, and no wrapper**. The same
classes simulate as the model, and the tools produce:
- the regblock RTL;
- the control FSM;
- the XLS AES pipeline;
- transactors and the top;
- the C header.

### 5.4 Milestones

| M | Content | Exit criterion |
|---|---|---|
| **M0 — Plumbing** (de-risk integration first) | pinned XLS in a DFM task; a *hand-written* XLS IR for CRC-32 → `codegen_main` → signature → glue generator → wrapper in an fw-hdl top → Verilator | generated RTL passes the CRC check-value test inside an fw-hdl testbench, with no hand-written glue; Q1/Q3 answered |
| **M1 — D1 from SV** | FE: scalars, `for`, functions, `get`/`put`, state; profile checker (first rules); emitter (P0 + basic P2) | CRC-32 written in SV → XLS RTL; class model and RTL agree on random byte streams; schedule report produced |
| **M2 — D2 + parity** | FE: packed structs, parameterized classes, predicated I/O; `fw_view_diff` minimal | RLE encoder from SV passes XLS's RLE test vectors on both views; **parity**: post-opt IR node count, pipeline register bits and yosys area within ±5% of the DSLX version, same XLS version, same flags |
| **M3 — D3 integration** | register-to-channel bridge; regblock + SPL control + XLS core + ready/valid kit + structural top; C header | NIST CTR-AES128 vectors pass with firmware-style register programming, on the class model, mixed views, and full RTL, **with the same test**. **Glue QoR:** the SPL-lowered control and bridge are within ±10% area/Fmax of a hand-written RTL equivalent (§1.4) |
| **M4 — Report** | the measurements in §6, written up | review-ready comparison vs the DSLX path |

M0 deliberately starts at the integration end, so the riskiest assumptions (the signature
contract, the layout, reset/flop policy, XLS packaging) are tested before front-end work
begins.

**Phase X0** runs in parallel with M0 and needs no XLS install. It covers the semantics
matrix, the front-end and IR work, the `zuspec-be-xls` emitter, and the
Verilator-vs-interpreter conformance tests. It is tracked in `xls-phase0.md`.

---

## 6. Success measures

| Measure | How | Target |
|---|---|---|
| **QoR parity** | same XLS version and flags; SV-path IR vs DSLX-path IR: post-`opt_main` node count, pipeline register bits, XLS delay estimate, yosys area | within ±5% on D1–D3 |
| **Integration effort** | hand-written lines and manual steps from "compute written" to "integrated, simulating RTL with register programming", SV path vs DSLX path (for D3, count what the DSLX path needs: a CSR block, protocol wrappers, a top, a testbench) | ≥ 5× fewer hand-written integration lines **[target to agree]** |
| **Glue QoR** (§1.4) | D3's TLM control + bridge lowered via SPL vs a hand-written RTL equivalent; yosys area, Fmax, and a readability review | within ±10%; readable enough that a reviewer can map RTL states to SV beats |
| **Model/RTL agreement** | `fw_view_diff` on all MVP tests | 100% channel-trace agreement |
| **Time to first simulation** | from SV source to running in an existing testbench | class model: immediate; RTL: one command |
| **Diagnostics** | every profile-checker rejection in the test suite names the SV line and the reason | 100% |
| **Usability signal** | one engineer outside the project writes a small block (e.g. Adler-32 or FIR) from docs alone | done without help from the authors |

**Kill / rethink criteria:**
- **Parity misses by more than 15%** on D2 after reasonable emitter work. That means our
  IR shape is fighting XLS's optimizer; investigate before continuing.
- **The signature + glue cannot integrate D3 without hand edits.** That means XLS's
  outputs are not a stable integration contract; reconsider which XLS version we pin, or
  the depth of integration.
- **Glue lowered from TLM misses hand RTL by more than 20%**, or is unreadable. The
  §1.4 arc then stalls at "glue around one island": still valuable, but not the long-term
  story. Fix the SPL lowering before promoting phase 2.
- **The profile checker rejects natural SV code** in D1–D3 often enough that users fight
  it. That means the subset is too narrow; revisit the semantics before scaling.

---

## 7. Risks

| Risk | Mitigation |
|---|---|
| SV → XLS IR semantic drift | SV-normative rules (D1–D4) emitted explicitly; class-model comparison on every test; later the cross-back-end fuzzer (`chisel-xls-assessment.md` §7.5) |
| XLS churn (no semver; codegen v1/1.5/2; proc-scoped channels) | pin a version; target XLS **IR** (not DSLX); single-proc packages; parity tests as a regression gate on XLS upgrades |
| Debuggability of XLS output (`add_37`) | source positions in the IR; schedule report mapped to SV; class-model comparison localizes a failure to a channel and beat |
| Users route control logic to XLS | `timing=static` is explicit, never inferred, and the profile checker explains its rejections |
| Front-end scope creep (SV is large) | the subset is defined by D1–D3 first; everything else is rejected with a message |
| Dependency on Google | zuspec IR in the middle; the native scheduler as fallback; the engine positioning (§2.1) |
| "Just another HLS" perception | lead with D3 (integration, firmware, verification), not with QoR |

---

## 8. Open questions

| # | Question |
|---|---|
| Q1 | XLS distribution: release tarball vs conda (litex-hub)? Version-bump policy (parity tests as the gate)? |
| Q2 | Can `--fifo_module` carry an async FIFO (its interface has a single `clk`), or must all CDC sit outside XLS blocks? (Not MVP.) |
| Q3 | Do XLS IR source positions survive into codegen's line map, so that reports and lint point at SV source? |
| Q4 | Attribute syntax for `timing=static`: macro, class parameter, or the metadata mechanism in `reference/attaching_metadata.md`? |
| Q5 | Function calls: emit `invoke` (keeps structure, XLS inlines anyway) or inline in our emitter (simpler)? |
| Q6 | Parity methodology: which flags are held fixed (clock period, `--pipeline_stages`, flop kinds), and which yosys flow defines "area"? |
| Q7 | Should we talk to the XLS team early (upstream contact, signature stability, a possible SV front-end mention in their docs)? |
| Q8 | For D3, is the register-to-channel bridge user-written SPL (shows the mix) or generated from the register model (shows automation)? Possibly both, as two variants. |
| Q9 | What glue vocabulary must SPL lowering cover for phase 2 — sequencer, packetizer/depacketizer, width converter, credit counter, arbiter (MMIO Phase B), FIFO? Which are lowered, and which are library components with RTL views? |
| Q10 | Where does the profile checker's "next rung" guidance live: CI, editor (LSP), or both? It is the user-facing form of the §1.4 strategy |

---

## 9. Sources

- XLS repository and docs: https://github.com/google/xls , https://google.github.io/xls/
  - IR semantics: https://google.github.io/xls/ir_semantics/
  - codegen options (signature, reset, flop kinds, FIFO module):
    https://google.github.io/xls/codegen_options/
  - scheduling: https://google.github.io/xls/scheduling/
  - procs: https://google.github.io/xls/tutorials/what_is_a_proc/
- Target designs (paths in `google/xls`):
  - `xls/examples/crc32/crc32.x`, `xls/modules/rle/rle_enc.x`;
  - `xls/modules/aes/{aes,aes_ctr,aes_gcm,ghash}.x`;
  - `xls/examples/{sha256,fir_filter,dot_product,fp32_fmac}.x`;
  - `xls/examples/jpeg/idct_chen.x`, `xls/examples/reorder_queue/reorder_queue.x`,
    `xls/examples/matmul_4x4/matmul_4x4.x`;
  - `xls/modules/add_dual_path/`, `xls/modules/zstd/` (README: CSR/AXI interfaces in DSLX;
    `rtl/xls_fifo_wrapper.sv`).
- Signature schema: `xls/codegen/module_signature.proto`.
- NIST SP 800-38A (block cipher modes; CTR-AES128 test vectors in Appendix F.5.1).
- CRC-32 check value: the standard `"123456789"` → `0xCBF43926` (CRC catalogue, CRC-32/ISO-HDLC).
- Our stack:
  - `python/fw/hdl/fe/*` (current front end);
  - `python/fw/hdl/emit/{regblock,structural,be_sv}.py`;
  - `src/std/fw_{get,put}_if.svh`;
  - `tests/intf_pc` (class model on Verilator);
  - `chisel-xls-assessment.md` §3, §4, §6.4, §8.
