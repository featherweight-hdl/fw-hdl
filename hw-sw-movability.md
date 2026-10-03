# Moving Between Software Algorithm and Hardware Accelerator

*Status: proposal for review.*

**Companions:** `zuspec-semantics.md` (axes, layers, qualification),
`software-model-taxonomy.md` (concept families), `software-object-models.md`,
`one-model-many-hosts.md` (hosts, bindings, operation models),
`integration-thesis.md` (SPL / HLS / CAG and the design-side story),
`multi-view-rearchitecture.md` (views behind one port).

---

## 0. Summary

1. **A region is movable** when its internals sit in the intersection of a software
   subset and a hardware dialect, **and** its boundary has both a software calling
   convention and a hardware protocol (§1).
2. **Six shapes of computation** range from trivially movable (pure fixed-size functions)
   to not worth moving (pointer-chasing, OS-interacting code) (§2).
3. **Moving is a binding decision, not a rewrite.** A movable region is a component with
   two realizations behind one interface; the partition is chosen at elaboration (§3).
4. **Five calling conventions** cover the boundary. For each, the tools generate both sides
   — the hardware wrapper and the software stub (§4). The operation model is the
   partition-stable API: firmware does not change when the partition does.
5. **Deciding early needs tools, in increasing fidelity** (§5–§6): a movability report from
   qualification; software profiling that counts work *and* data crossing each candidate
   boundary; a cost model with a roofline-style check of compute against transfer
   bandwidth; hardware estimates from the scheduler and delay model; and finally
   measurement in co-simulation. Profiles from every host attach to the same IR elements,
   so evidence accumulates across the project.
6. **First worked case:** the DMA's inline CRC — software post-processing versus inline in
   the engine's data path (§8).

---

## 1. The intersection

### 1.1 Internals

A region's internals are movable when they qualify for both a software target and a
hardware dialect at once. In axis terms (`zuspec-semantics.md` §2):

| Axis | Required | Meaning |
|---|---|---|
| C | `C1` | no creation at run time |
| D | `D0` (HLS, FSM) or `D1` with memories mapped (tier 4) | fixed-width or bounded data |
| M | `M1` | inputs as arguments or channel reads; results as returns or channel writes; no shared mutable state |
| T | `T0` (HLS) or `T1` (SPL-hw) | no absolute time |
| N | `N0` | every choice resolved |

Plus, from the software side (`software-object-models.md`): static types, dispatch resolved
at elaboration, no recursion (or recursion bounded and unrolled), bounded loops, errors as
values, no host I/O.

This intersection is **SPL-hw ∪ HLS seen from software**: a pure function over fixed-size
values, or a latency-insensitive process over channels.

### 1.2 Boundary

The region's interface must map onto a **calling convention** (§4) on the software side and
a **protocol** on the hardware side, with only **values** crossing (no object graphs — the
`M1` rule, and the lesson of the WebAssembly component model).

### 1.3 Movability is a qualification result

Movability is reported by the same machinery as any qualification
(`zuspec-semantics.md` §8): a region's per-axis levels against an "accelerator-eligible"
target, with the blocking constructs and their locations.

---

## 2. Shapes of computation

| Tier | Shape | Examples | Software form | Hardware form | Natural convention | Movability |
|---|---|---|---|---|---|---|
| **1** | Pure function, fixed-size in/out | CRC, checksum, hash or cipher rounds, bit manipulation, encode/decode, fixed-point math, fixed-N sorting networks | function call | combinational or pipelined unit (HLS) | custom instruction (CC1), request/response (CC2) | near free |
| **2** | Streaming kernel | FIR filter, compression stage, packet parsing, framing, matrix-vector over a stream | loop over queues | HLS pipeline, ready/valid | stream + DMA (CC3) | easy; DMA plumbing is the cost |
| **3** | Bounded-state transaction engine | DMA descriptor processing, schedulers, protocol controllers | firmware task, driver | FSM (SPL-hw) | MMIO-programmed (CC2) via the operation model | easy with SPL |
| **4** | Fixed-capacity data structures | bounded hash tables, priority queues of N, LRU caches, lookup tables | collections | explicit memories (SRAM views) with ports | CC2–CC4 | feasible; memory mapping and port scheduling decide performance |
| **5** | Irregular, pointer-chasing | graphs, linked structures, dynamic allocation, recursion | ordinary code | pools and bounded memory, specialized designs | — | rarely worth it |
| **6** | OS-interacting control | protocol stacks with timers, policy code | ordinary code | — | — | stays in software |

Tiers 1–3 should move with little effort. Tier 4 is feasible with work. For tiers 5–6 the
tools should say "not a candidate" and why, rather than attempt it.

---

## 3. Mechanism: partition as binding

- A movable region is a **component behind an interface** (a function interface, an
  operation set, or channels).
- It has two or more **realizations**, as views (`multi-view-rearchitecture.md`):
  - **sw**: runs as code on the processor host (C, or the simulation host);
  - **hw**: an accelerator reached through an abstractor, plus a generated software stub.
- The **partition** is the set of realization choices, made at elaboration by attribute.
  A partition is therefore a configuration, not a branch of the source:
  ```
  partition A: crc=hw, compress=sw
  partition B: crc=sw, compress=hw
  ```
- Both realizations derive from the same IR region: the sw realization is the region
  itself; the hw realization is its lowering (HLS or SPL-hw → RTL). The sw realization is
  automatically the hw realization's reference model.

---

## 4. Calling conventions

Each convention fixes what crosses, the overhead, and what is generated on each side.

| # | Convention | What crosses | Invocation overhead (shape) | Generated: hardware side | Generated: software side | Suits |
|---|---|---|---|---|---|---|
| **CC1** | Custom instruction | operands that fit in registers (e.g. 2 in, 1 out); optional small internal state | a few cycles | functional unit with the core's custom-instruction interface (fixed latency or handshake) | intrinsic / inline-assembly wrapper | tier 1, fine-grained |
| **CC2** | MMIO-programmed | arguments and results via registers; larger data by address | register writes + doorbell + completion (poll or interrupt): tens to thousands of cycles | register block, doorbell, completion logic, wrapper around the core | **operation model** and driver | tiers 1, 3, 4; coarse-grained |
| **CC3** | Stream + DMA | blocks of data | DMA setup, then bandwidth-limited transfer | stream interface, DMA descriptors | buffer management, descriptor setup, completion | tier 2; large data |
| **CC4** | Shared buffer | ownership of a buffer in shared memory | ownership hand-off + accelerator's memory accesses | memory master, ownership protocol | buffer allocation and hand-off (aliasing facet `unique`) | tiers 2, 4 |
| **CC5** | Hardware-to-hardware channel | values on an on-chip channel | handshake latency | channel / FIFO | — | composing accelerators |

Conventions are protocol definitions with method and bundle views and an abstractor
(`zuspec-semantics.md` §7.2). Each convention also has a **cost model** (§6.3).

**The operation model is the partition-stable API.** Under CC2, the software calls an
operation; whether that operation runs as code or programs an accelerator is the binding.
Firmware above the operation model is unchanged by repartitioning.

---

## 5. Making the right decision early: principles

1. **Decide with evidence, at increasing fidelity.** Cheap estimates first, measured
   numbers later; each stage narrows the candidate set before the next, more expensive
   stage runs.
2. **Data movement usually decides.** Most failed accelerators are limited by invocation
   overhead or transfer bandwidth, not by compute. Every tool reports data crossing the
   candidate boundary, not just time spent inside it.
3. **Workloads must be representative.** Test scenarios stress corners; partitioning needs
   typical behaviour. Keep **workload scenarios** — CAG scenarios with realistic
   distributions — separate from verification scenarios.
4. **Profiles attach to IR elements,** by stable ID through the source maps
   (`one-model-many-hosts.md` §5). A profile collected in Python, SV, C on an instruction-set
   simulator, or RTL co-simulation lands on the same element, so evidence accumulates
   across hosts and phases.
5. **Every estimate states its assumptions** (workload, clock, calling convention, memory
   bandwidth), so a later measurement can say which assumption was wrong.

---

## 6. Tools

### 6.1 Overview, by project phase

| Phase | Model is at | Tool | Answers | Fidelity |
|---|---|---|---|---|
| Algorithm | software layer | **T1 movability report** | which regions *could* move, and what blocks the rest | structural |
| Algorithm | software layer | **T2 work and data-movement profiler** | how much work each region does, how often it is called, how many bytes cross its boundary | operation counts |
| Algorithm | software layer | **T3 offload estimator** | estimated speedup per region per calling convention; break-even granularity; roofline check | analytical |
| Refinement | SPL / HLS | **T4 hardware estimator** | latency, initiation interval, area of the hw realization | scheduler + delay model |
| Refinement | SPL / HLS | **T5 partition explorer** | ranking of candidate partitions; what-if over conventions and clocks | analytical over T2–T4 |
| Implementation | RTL + processor | **T6 co-simulation measurement** | measured cycles per partition, against the estimates | cycle-accurate |
| Any | any | **T7 differential check** | the two realizations behave identically | functional |

### 6.2 T1 — Movability report

- Runs qualification against the accelerator-eligible target for every region.
- For each region: the tier (§2), the natural conventions (§4), and the blocking
  constructs per axis with locations.
- Groups near-misses: "would be tier 1 except for an unbounded loop at line 88".
- Cheap; runs continuously like a linter.

### 6.3 T2 — Work and data-movement profiler

Executes the software-layer model (be-bc, or a host) on workload scenarios and records,
per candidate region:

| Metric | Why it matters |
|---|---|
| inclusive work (operation counts by kind and width; time where meaningful) | the compute that could move |
| invocation count and size distribution | per-call overhead × calls; granularity |
| **bytes in and out per invocation** | transfer cost under each convention |
| reuse: bytes touched more than once | whether data can stay local to the accelerator |
| caller behaviour: does the caller wait on the result immediately? | whether calls can be overlapped (asynchronous / pipelined) or serialize |
| call-site distribution | whether one convention suits every caller |

Operation counts (adds, multiplies, shifts, memory accesses by width) matter more than
wall-clock time here: host wall-clock time in Python or a simulator says little about a
target CPU, whereas operation counts transfer.

Existing tools that cover parts of this on native code: `perf`, `gprof`, Valgrind's
`callgrind`/`cachegrind`. The difference here is that the profile is attributed to IR
regions and boundaries, and records data crossing the boundary.

### 6.4 T3 — Offload estimator

For a region invoked *n* times:

```
T_sw = n · t_sw
T_hw = n · (t_call(cc) + t_xfer(cc, bytes) + t_lat)                 -- synchronous calls
T_hw ≈ n · max(t_call(cc) + t_xfer(cc, bytes), 1 / throughput)      -- overlapped calls
speedup_region = T_sw / T_hw
speedup_total  = Amdahl(fraction of total time in the region, speedup_region)
```

- `t_sw`: from T2 operation counts × a per-operation cost model of the target processor,
  or measured on an instruction-set simulator.
- `t_call`, `t_xfer`: from the calling convention's cost model (§4) and the platform
  parameters (bus width, DMA setup, interrupt latency).
- `t_lat`, `throughput`: from T4 once available; before that, a coarse estimate from
  operation counts and a nominal clock.

It also reports:
- **break-even granularity**: the minimum work per invocation for which moving pays,
  under each convention;
- a **roofline-style check**: compute per byte crossing the boundary against the
  convention's bandwidth. Regions far below the ridge point are transfer-bound and should
  not move unless their data can stay local.

Precedent: Intel Advisor's offload modeling estimates GPU offload benefit from a CPU
profile in the same spirit; the roofline model (Williams, Waterman, Patterson, 2009) is the
standard compute-versus-bandwidth view.

### 6.5 T4 — Hardware estimator

- For HLS-eligible regions: the scheduler with a characterized delay model gives latency,
  initiation interval and register count at a target clock (`integration-thesis.md` §3.5,
  §7).
- For SPL-hw regions: beat counts per operation give latency in cycles; state and register
  counts give a coarse area.
- Area from a characterized area model (operations by width), with optional synthesis of
  the generated RTL (yosys) for calibration.
- Results feed T3 and are stored against the region, with their assumptions.

### 6.6 T5 — Partition explorer

- Enumerates candidate partitions over the regions T1 marks movable.
- Scores each with T3 (using T4 numbers where available) against objectives: total
  speedup, added area, and a data-movement budget.
- What-if over calling conventions, target clock, and platform parameters.
- Outputs a ranked list with the dominating terms ("transfer-bound under CC2; consider
  CC4"), not just a number.
- Precedent: LegUp's hybrid flow (profile, then move hot functions to hardware) and Xilinx
  SDSoC/Vitis (pragma-selected functions with generated data movers) did the mechanical
  step; their experience is that the value depends on hardware quality and data movement,
  which is why T2–T4 come first.

### 6.7 T6 — Co-simulation measurement

- Runs a chosen partition with the sw realizations on a processor model (instruction-set
  simulator, or an RTL core) and the hw realizations as RTL.
- Measures cycles per region, invocation overhead, and transfer time.
- Reports measured versus estimated per term (`t_call`, `t_xfer`, `t_lat`), so the cost
  models are calibrated for the next decision.

### 6.8 T7 — Differential check

- Runs the same workload against both realizations and compares results per channel
  (the class-vs-RTL comparison generalized). Bit-accurate types make results identical;
  floating point needs a stated tolerance or bit-exact arithmetic.
- Runs at every fidelity: be-bc vs generated RTL in simulation, and on target.

---

## 7. What the IR needs

| Need | IR construct |
|---|---|
| a region with multiple realizations | component views; a `realization` attribute selected at elaboration |
| calling conventions | protocol definitions with method view, bundle view, abstractor, and a cost model |
| platform parameters | attributes on the system (bus width, DMA setup latency, interrupt latency, clocks) |
| workload scenarios | CAG scenarios marked as workloads, with distributions |
| profile and estimate data | records keyed by IR element ID, with metric, value, assumptions, host, fidelity |
| movability | qualification against an accelerator-eligible target (`zuspec-semantics.md` §8) |

Profile and estimate records are **data about the model**, stored alongside it (not inside
the semantic IR), so they never affect behaviour.

---

## 8. Worked case: the DMA's inline CRC

**The region:** `crc32(buffer) → u32`. Tier 1 (pure, fixed-width state, bounded loop per
byte or word); also tier 2 if written as a process over the data stream.

**Two partitions:**

| | Partition SW | Partition HW |
|---|---|---|
| Where the CRC runs | firmware, over the destination buffer after the transfer completes | inline in the DMA engine's data path, during the transfer |
| Convention | none (local call) | CC5 inside the engine; result exposed in a status register (CC2) |
| Operation model | `transfer()` then `crc(buffer)` | `transfer(with_crc=true)` returns the CRC |
| Data movement | the processor reads the whole buffer again | none beyond the transfer itself |

**What the tools would show:**

- T1: `crc32` qualifies as tier 1 and tier 2; no blockers.
- T2: work grows linearly with buffer size; **bytes in = buffer size**; caller waits on the
  result immediately.
- T3: in Partition SW the cost is dominated by re-reading the buffer — a data-movement cost
  the hardware partition removes entirely, because the data is already flowing through the
  engine. The estimator should flag that the decisive term is transfer, not compute.
- T4: a CRC stage at the engine's data width — latency and area of a small pipelined unit.
- T6: measured transfer-plus-CRC time for both partitions across buffer sizes.
- T7: both partitions return identical CRCs on the same workload.

**Why it is a good first case:** one function, two bindings, the same tests, an obvious
data-movement argument, and it slots into the operation-model demo already planned.

---

## 9. Open questions

| # | Question |
|---|---|
| H1 | Is CC1 (custom instructions) in scope, given it requires a processor whose core we can extend? |
| H2 | What is the processor cost model for T3 — operation-count tables per core, or always an instruction-set simulator? |
| H3 | Where do workload scenarios come from in practice — authored, or captured from software traces? |
| H4 | How are floating-point regions handled: bit-exact hardware arithmetic, or a tolerance in T7? |
| H5 | Should T5 search automatically, or only evaluate partitions a person proposes? (Proposal: evaluate first; search later.) |
| H6 | Are profile and estimate records versioned with the model, or kept as CI artifacts? |
