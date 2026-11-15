# Demo: autonomous traffic generator on a low-cost FPGA

Draft, 2026-11-15. This is a proposal for one of the "cool" demos behind
`pitch.md` (*Who this is for*, item 4: verification engineers on emulation).
The industry research is in `research/emulation-traffic-generators.md`.

## 1. The story in one paragraph

Performance verification on an emulator needs traffic generators. If the host
crosses into the emulator for every transaction, emulation slows to a crawl.
A generator that runs host-built descriptor chains on its own is fast, but it
is a real design project, so few teams build one.

The demo shows a verification engineer:
1. writing such a generator in fw-hdl, using higher-level constructs;
2. choosing scenarios with fw-hdl-dv, which follows PSS semantics;
3. running the same generator three ways: as a class model in simulation, as
   RTL in Verilator, and at speed on a cheap FPGA board;
4. getting synthesizable RTL within about 10% of a hand-written baseline.

## 2. Platform

**Recommended: AMD Kria KV260 (about $250).** The KR260 is an alternative.
- The quad-core Arm processor runs Linux and Python. It plays the
  **host**, so the Python flavor of fw-hdl-dv runs on the board itself.
- The programmable logic plays the **emulator**.
- The boundary between the processor system and the logic (AXI-Lite for
  control, AXI HP/HPC ports for data) stands in for the host-to-emulator link.
  Measure that boundary rather than assuming it behaves like an emulator link
  (see §5, sweep S1).
- The traffic targets DDR4 on the processor side through the HP ports. That
  is a real memory system with real contention, refresh and page effects.
- Vivado 2023.1 and 2024.1 are already installed under `/tools` and support
  the board.

**Fallbacks:**
- *Arty A7-100T* (DDR3, MicroBlaze host). Cheaper, but the host is weak, so
  Python would have to run on a PC over UART or Ethernet.
- *A PCIe card:* LiteFury ($109, often out of stock) or NiteFury ($329), an
  M.2 PCIe x4 Gen2 Artix-7 card that plugs into a PC. This is the closest
  physical analog to an emulator link, but bring-up costs more. Keep it for a
  later phase.

## 3. The design

```
  Arm host (Linux, Python)                     Programmable logic
 ┌──────────────────────────┐    AXI-Lite    ┌───────────────────────────────────┐
 │ fw-hdl-dv (Python flavor)│ ── control ──► │ doorbells, config, stats snapshot │
 │  scenario → solver →     │                │                                   │
 │  descriptor chains       │ ── HP port ──► │ descriptor fetch  ┌─────────────┐ │
 │  (written into DDR)      │                │  per stream ────► │ stream eng. │×N│
 │ reads completions, stats │ ◄─ completion  │                   └──────┬──────┘ │
 └──────────────────────────┘     ring       │      arbiter (QoS) ◄─────┘        │
                                             │          │                        │
                                             │  fw-proto-axi master ── HP port ──┼─► DDR4
                                             │  response tracker, data checker   │
                                             │  stats: counters, latency hist.   │
                                             └───────────────────────────────────┘
```

### 3.1 Descriptors describe patterns, not transactions

This is the key design point. If one descriptor equals one transaction, the
host is still in the loop, just in batches. A descriptor should instead
describe a *pattern* that the hardware expands, so a short chain produces
long, rich traffic. The descriptor fields, roughly fio-style:

| Field | Meaning |
|---|---|
| `op` | read, write, or mix with a read percentage |
| `addr_mode`, `base`, `window`, `stride` | sequential, strided, or random (LFSR) within a window |
| `xfer_size`, `burst_len` | transfer size, and how it splits into AXI bursts |
| `count` | transfers in this descriptor |
| `qdepth` | maximum outstanding transfers (iodepth) |
| `rate` | token-bucket rate limit, or unlimited |
| `think` | idle gap between transfers, fixed or random |
| `seed` | LFSR seed for addresses and data |
| `check` | write a pattern derived from address and seed; check it on read |
| `next`, `loop` | chain pointer, and loop back N times |
| `cpl` | post a completion record, with interrupt coalescing |

A few kilobytes of descriptors can then keep the generator busy for seconds
of full-rate traffic. The demo reports this ratio of *transactions per host
interaction*, because it is what decides emulation speed.

**Align the descriptor model with Arm's AMBA Adaptive Traffic Profiles
(ATP).** The ATP spec describes address patterns (linear, 2-D, random), a FIFO
timing model, rates (peak, constrained peak, average) and synchronization
between profiles. It explicitly calls for "low-gate-count hardware"
generators for emulation and FPGA, but Arm ships only a C++ engine for gem5.
If our descriptors can express ATP profiles, the demo fills a named gap in a
standard rather than inventing a private format. ATP's C++ engine also gives
a reference to compare against.

### 3.2 Blocks, and which fw-hdl level each one uses

| Block | Role | fw-hdl level |
|---|---|---|
| Descriptor fetch | Walk the chain through DDR; prefetch the next descriptor | SPL (inferred FSM): sequential control, a natural fit |
| Stream engine (×N, N = 4–8) | Expand a descriptor into transfers: address generator, size split, `qdepth` limit, token bucket | RTL subset for the datapath; SPL for control |
| Arbiter | Weighted round-robin and strict priority across streams | RTL subset; builds on the `examples/rr_merge` work |
| AXI master | Pin-level AXI4 | The `fw-proto-axi` transactor, unchanged |
| Response tracker and checker | Outstanding IDs, latency timestamps, read-data check at full rate | RTL subset; builds on the `examples/resp_tracker` work |
| Stats | Per-stream bytes, transfers, errors; min/max/sum latency; log2 latency histogram; snapshots | RTL subset |
| Completion ring | NVMe-style completion queue in DDR, with coalescing | SPL |

Every block has a method interface, for example
`stream.load(desc)`, `stats.snapshot()` and `cpl.pop()`. The same interface
serves:
- the class model in simulation;
- the RTL in Verilator;
- the host driver on the board, where the Python calls become register and
  memory operations.

### 3.3 Host side

- A **scenario** in fw-hdl-dv (Python flavor; the same semantics in SV):
  - actions are stream profiles ("sequential write, 128 KB, qdepth 32",
    "random read, 4 KB, qdepth 8, rate-limited");
  - activities compose them (parallel streams, phases, repeats);
  - constraints keep streams in disjoint address windows and within the
    bandwidth budget.
- The **solver output becomes descriptor chains**. The scenario is also
  projected to PSS source, to show "author in Python, ship PSS".
- A **driver** writes the chains into DDR, rings the doorbells, then gathers
  completions and stats. A **reporting script** produces the plots and tables
  in §5.
- The **same scenario** runs in simulation against the class model. That gives
  a functional check of the descriptors before anything runs on the board.

### 3.4 A deliberate baseline

To back the "within 10%" claim, hand-write one stream engine (or the whole
data path for a single stream) in plain SystemVerilog. Compare area, Fmax,
throughput and lines of code. Without this, the QoR claim is only a claim.

## 4. What to show off

Each item maps to a pitch claim.

1. **The host-boundary curve.** Throughput against transactions per host
   interaction, from one transaction per doorbell (the host in the loop) up
   to autonomous chains. It should rise steeply and saturate at line rate.
   This picture *is* the emulation argument.
2. **Line rate with no bubbles.** Against an ideal sink (BRAM, or an AXI
   slave that always accepts), the generator sustains 100% of the port's
   theoretical bandwidth across burst sizes. That proves the generator is
   never the bottleneck.
3. **One source, three platforms.** The same generator and scenario run as a
   class model in simulation, as RTL in Verilator, and on the board. Show the
   functional results matching, and the simulated and measured performance
   side by side (the model uses an approximate DDR timing, so expect
   correlation, not equality).
4. **Productivity and QoR.** Lines of code and build time for the generator,
   against the hand-written baseline and against what a fixed-function IP
   can express. AMD's AXI Traffic Generator (PG125) is the comparison point:
   256 register-programmed commands per direction, with no descriptor chains,
   multi-queue semantics or closed-loop rate control. Area and Fmax within
   about 10%.
5. **Scenarios to PSS.** One scenario file selects the traffic. It is
   projected to PSS source and solved into descriptor chains. Change one
   constraint, rerun, and get a new run in seconds with no FPGA rebuild,
   because the bitstream never changes.
6. **At-speed checking.** Data-integrity checks run at full rate on every
   transfer. Inject a fault (for example corrupt one DDR word through the
   host) and show the checker catching it, with the descriptor and stream
   that saw it.
7. **ATP profiles in hardware.** Run Arm ATP profiles on the board, which
   nothing else does today (see §3.1).
8. **Real performance-verification results.** Familiar memory-system curves,
   measured on real hardware with a generator written in days (see §5).

## 5. Sweeps

### S1. The host boundary (the core result)

- **Vary:** transactions per host interaction: 1, 4, 16, … up to fully
  autonomous chains with loops. Also run a mode where Python issues every
  transaction itself through AXI-Lite, as the worst case.
- **Measure:**
  - achieved bandwidth;
  - host CPU time per transaction;
  - the boundary round-trip latency, in logic clock cycles.
- **Report:** the curve from §4 item 1. Also compare the measured boundary
  latency with published emulator host-link figures, so the analogy is stated
  with numbers.

### S2. Generator capability, against an ideal sink

- **Vary:** burst length (1–256 beats), transfer size (64 B to 1 MB), number
  of streams (1–8), `qdepth` (1–64).
- **Measure:** achieved bandwidth as a share of the port's theoretical
  bandwidth.
- **Expect:** 100% once `qdepth` covers the sink latency. Any shortfall is a
  generator defect to fix before measuring DDR.

### S3. Memory-system characterization, against DDR4 through the HP ports

These are classic sweeps that a performance engineer would recognize:
- **Bandwidth against outstanding transactions** (Little's law): find the
  `qdepth` that saturates each port.
- **Latency against offered load:** the hockey-stick curve, with p50, p99 and
  max latency from the hardware histogram.
- **Access pattern:** sequential, strided and random, against transfer size.
  This shows page-hit and bank effects.
- **Read/write mix:** 0–100% reads, which shows bus-turnaround cost.
- **Multiple ports:** one to four HP ports in parallel, to find where the
  memory controller saturates.

### S4. Multi-stream QoS and interference (the NVMe-style story)

- **Setup:** one latency-sensitive stream (small random reads, low rate)
  against N bulk streams (large sequential writes).
- **Vary:** the bulk load, and the arbiter policy (round-robin, weighted,
  strict priority).
- **Measure:**
  - p99 latency of the sensitive stream;
  - bandwidth share per stream compared with the configured weights.

This is the "noisy neighbour" result that performance verification exists to
find.

### S5. Abstraction and QoR

- **Vary:** how the stream engine is implemented: hand-written RTL, the fw-hdl
  RTL subset, and SPL. Optionally add an MLS/HLS engine for the address
  generator.
- **Measure:** LUTs, flip-flops, BRAM, Fmax, S2 throughput, and source lines.
- This doubles as the P4 deliverable in `featherweight-ip-strategy.md` (one
  block on several rungs).

### S6. Model-to-hardware correlation

- **Run:** a subset of S3 and S4 in simulation (the class model plus a
  simple DDR timing model) and on the board.
- **Report:** the error per point, framed with the Ampere metric (share of
  tests within ±10%).
- This ties the demo to the architect path (pitch, item 3): the performance
  model and the hardware come from one source.

## 6. Phases

| Phase | Content | Shows |
|---|---|---|
| 1 | One stream engine, BRAM sink, AXI-Lite control, register-level descriptors | Line rate (S2), first host-boundary curve (S1) |
| 2 | Descriptors in DDR, chains and loops, DDR target, stats and histogram | S1 in full, S3 |
| 3 | N streams, arbiter, completion ring, data checker | S4, at-speed checking |
| 4 | fw-hdl-dv scenarios (Python on the Arm), PSS projection, simulation twin | Scenarios to PSS, S6 |
| 5 | Hand-written baseline and alternative rungs | S5, the QoR claim |

Phases 1–2 give a demonstrable result on their own. Phase 5 is what makes the
"within 10%" claim honest, so do not skip it.

## 7. Risks and open questions

- **The analogy to emulation must be measured.** The processor-to-logic link
  on the KV260 is not an emulator link, so S1 has to report the measured
  boundary latency and compare it with published emulator figures.
- **Dependencies:**
  - SPL maturity, for the descriptor fetch and the completion ring;
  - the `fw-proto-axi` master at about 250 MHz on an UltraScale+ device;
  - the Python flavor of fw-hdl-dv and its solver. Until they exist, a plain
    Python script can emit the descriptor chains, so phases 1–3 do not wait on
    them.
- **What emulators accept.** The demo proves FPGA synthesis. Claims about
  emulator compilers (IXCOM, Veloce, ZeBu) need at least one real emulator
  run, or should be worded as "standard synthesizable RTL".
- **Complement, not replacement.** Storage performance validation has
  standardized on a QEMU virtual host running real drivers and fio
  (VirtuaLAB, ZeBu Virtual Host). Present the generator as what that flow
  lacks (line rate, stress, determinism, low cost), not as a substitute for
  real software.
- **Prior art.** Bluespec pitched high-level synthesizable testbenches around
  2009 (an Ethernet MAC testbench in under 9 person-weeks). Know why it didn't
  spread before presenting this.
- **Scope creep.** NVMe protocol semantics (submission queues, PRPs, an SSD
  model) are out of scope. The demo is NVMe-*style* traffic: queues, depth
  and completion semantics, at the memory interface.
