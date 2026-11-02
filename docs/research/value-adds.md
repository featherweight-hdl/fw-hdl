# Value-adds around XLS: a catalog

*Brainstorm and review, 2026-11-01. Commercial track: XLS stays the engine (optimize,
schedule, codegen). fw-hdl owns everything a designer touches around it. Builds on:*
- *[designer-ramp-to-xls.md](designer-ramp-to-xls.md): story and plan*
- *[timing-shell.md](timing-shell.md): wrappers and timing shell*
- *[pitch-commercial.md](pitch-commercial.md): pitch*

## 1. The principle

XLS takes IR in and produces RTL plus a few artifacts. Those artifacts are rich, but XLS
does almost nothing *with* them for the designer:
- the signature
- the schedule
- per-node delays and source positions
- block IR
- the area and delay models
- the equivalence and quickcheck provers
- the JIT

fw-hdl sits on both sides of the engine. It knows the SV source: names, structs, classes and
line numbers. It also knows the SV environment: simulator, testbench and the RTL around the
block. So it can **turn XLS's artifacts into designer-facing automation**. Almost every
item below is "read an XLS output and connect it back to the SV source or the SV
environment."

Four platform pieces unlock most of the catalog. Build them once:

| Platform piece | Built from | Unlocks |
|---|---|---|
| **P1. Signature model** | XLS module signature + the SV port and struct types | Wrappers, transactors, UVM agents, SVA, datasheets, IP-XACT, lockstep |
| **P2. Source↔schedule map** | IR `pos=` (fw-hdl already emits it) + schedule (node → stage, delay) + block IR (register names) | Schedule overlay, critical-path view, debug name maps, timing shell, QoR-diff on review |
| **P3. Transaction recorder** | One monitor per channel, the same at every level (model shell, timing shell, RTL, gates) | Divergence finder, replay, Perfetto/waveform transaction views, FIFO sizing, coverage |
| **P4. Variant runner** | dv-flow matrix over XLS options and SV parameters | Design-space sweeps, QoR tracking, XLS-upgrade gating, block variants |

Status legend: ✅ exists · 🟡 partial · 🔴 new. Effort: S / M / L.

## 2. Catalog by stage

### 2.1 Authoring: write the right SV the first time

| # | Value-add | What the designer gets | XLS hook | Status / effort |
|---|---|---|---|---|
| A1 | Accept `logic` as 2-state | No rewrite of house style | — | 🔴 S |
| A2 | "Can this be synthesized?" check, run at edit/sim time | Errors on the SV line, before synthesis | — (slang + static mapper) | 🟡 S: mapper exists, needs a CLI and a dfm task |
| A3 | **Editor integration (LSP via slang)** | Squiggles for unsynthesizable code; hover shows the stage and delay for a line | P2 | 🔴 M |
| A4 | **Schedule overlay on the SV source** | An annotated listing or HTML of the class: each line's pipeline stage, its delay, and the critical path highlighted. "This multiply is what sets your clock." | schedule `timed_nodes` + `pos` | 🔴 M. *Not offered by XLS for DSLX either* |
| A5 | **Width and dead-logic feedback** | "Field `hdr.ttl` never affects an output"; "`count` is declared 32 bits but XLS proved 7 suffice" | Compare pre-opt and post-opt IR (narrowing, DCE) mapped through `pos` | 🔴 M |
| A6 | Coding guide with FSM→class recipes | The on-ramp | — | 🔴 S |
| A7 | **Refactor-safety check** | "Did my cleanup change behavior?" Prove two revisions of a function equivalent | `check_ir_equivalence_main` (functions; procs bounded) | 🔴 S |
| A8 | Parameterized variants | One SV class → N specialized XLS modules (widths, lane counts) with names and wrappers | P4 | 🟡 S: parametric functions work |
| A9 | Reuse XLS's DSLX library blocks | Use the blocks in `xls/modules` from SV designs: RTL via signature (P1), model via XLS JIT/AOT behind DPI | Signature, JIT AOT wrappers | 🔴 M |
| A10 | LLM-friendliness (observation) | Coding assistants know SystemVerilog far better than DSLX. xlsynth needs a dedicated `dslx-llm` repo; we get this for free | — | Positioning, not a build item |

### 2.2 Architecture and performance: answers before RTL

| # | Value-add | What the designer gets | XLS hook | Status / effort |
|---|---|---|---|---|
| B1 | **Exact function-pipeline timing shell** | A drop-in timed model, pin-identical to the RTL | signature `pipeline.latency` | 🟡 S: StageTLM is latency-only |
| B2 | **Proc timing shell** (stage flow control, state-backedge II, flop kinds) | Throughput and back-pressure behavior in the SoC sim before RTL | signature `channel_interfaces[].stage`, `flop_kind`; schedule | 🔴 M (timing-shell.md §4.2) |
| B3 | **Design-space sweep** | One command sweeps clock × stages × II and reports a Pareto table (latency, II, area estimate, min clock period), each point with its own timing shell | P4 + XLS area/delay models + `min_clock_period_ps` | 🔴 S–M |
| B4 | **Budget vs actual** | The architect writes `latency ≤ 4, II = 1` next to the class; every build checks XLS's schedule against it and fails on violation, so the budget is enforced continuously | schedule, signature; can also *drive* `--worst_case_throughput` / `--pipeline_stages` | 🔴 S |
| B5 | **System-requirement → per-block constraints** | "1 packet/cycle at 1 GHz" flows down to per-block II and clock constraints for XLS, and `--io_constraints` from protocol timing | XLS scheduling options | 🔴 M |
| B6 | **FIFO sizing assistant** | Sweeps channel depths over the timing-shell network and reports (a) the minimum depth that avoids deadlock and (b) the depth needed for full throughput | P3 + B2 | 🔴 M. XLS can't do this pre-RTL (#988) |
| B7 | Pipeline occupancy / activation timeline | A Perfetto view of activations moving through stages, with stalls and bubbles | P3, Perfetto format (XLS has `trace_to_perfetto`) | 🔴 S once B2 exists |

### 2.3 Integration: it's just a module

| # | Value-add | What the designer gets | XLS hook | Status / effort |
|---|---|---|---|---|
| C1 | **Struct-typed model shell + RTL wrapper** with layout and pin-parity checks | Instantiate with the designer's own typedefs; swap views by file list | P1 | 🔴 S (timing-shell.md §3) |
| C2 | Per-view file lists and dv-flow filesets | `-f blk_model.f` / `-f blk_rtl.f` / `-f blk_timed.f` | — | 🔴 S |
| C3 | **CSR / configuration integration** | Config registers described once (SystemRDL / fw-hdl `fw_reg`). The generated CSR block drives XLS single-value channels or streaming config. Covers the "MMIO-configured XLS blocks" gap | single-value channels in the signature | 🔴 M. Most real blocks have CSRs |
| C4 | SRAM integration | `fw_mem_if` → XLS RAM channels → a wrapper per memory compiler; behavioral memory on the model side | `--ram_configurations`, signature `rams[]` | 🔴 M–L |
| C5 | Clock-domain crossings | Async FIFOs generated where shells sit in different domains; one clock per XLS block is enforced | — | 🔴 S–M |
| C6 | **Block datasheet** | Generated Markdown/HTML per build: ports with struct types, latency, II, stages, clock, area estimate, critical path, reset behavior | P1 + P2 | 🔴 S |
| C7 | IP-XACT component | SoC assembly tools import the block | P1 | 🔴 S |
| C8 | Idle / clock-gating hook | `--add_idle_output` exposed on the shell, giving the integrator a clock-gate enable; modeled in the timing shell | XLS codegen option | 🔴 S |

### 2.4 Verification: richer, with less effort

| # | Value-add | What the DV engineer gets | XLS hook | Status / effort |
|---|---|---|---|---|
| D1 | One test at every level | Same SVUnit file at model, RTL and gates | — | ✅ |
| D2 | **Generated UVM agents and env** per block | Typed ready/valid agents (driver, monitor, sequencer) using the struct types, with a scoreboard predicting from the SV class model itself | P1 | 🔴 M. The class is the reference model for free |
| D3 | **Ready/valid protocol SVA** bound on every channel | Valid holds until ready, data stable, no X. Bound to the model shell and the RTL, so both are checked | P1 | 🔴 S |
| D4 | **Generated functional coverage** | Covergroups per channel struct field (enums, flags, ranges); branch coverage of the class's `if`/`case`, also emitted as XLS `cover!` so it survives into RTL | P1, `pos` | 🔴 M. Closes XLS's coverage gaps (#1126, #2139) |
| D5 | Back-pressure stress built in | Every generated test can randomize valid and ready throttling on every channel | P3 | 🟡 S: `tests/xls/test_compose.py` does this for one case |
| D6 | **Lockstep shell-vs-RTL check** | The timing shell proved cycle-accurate against XLS RTL on every build | P1 | 🔴 S (timing-shell.md §5) |
| D7 | **Model ↔ XLS IR differential check** | Every block, every build: the same vectors through the SV model and the XLS JIT/interpreter. This is the trust story for our translation | `eval_ir_main` / `eval_proc_main` | 🟡 S: suites exist in `tests/xls/` |
| D8 | SV properties → XLS proofs | `function bit prop_*` proved over all inputs | `prove_quickcheck_main` | 🔴 S |
| D9 | `$display` / `assert` / `cover` carried into RTL | Same messages and checks in model and RTL | `trace_fmt!`, `assert!`, `cover!` codegen | 🟡 S: assert mapped; trace and cover not yet |
| D10 | Contracts → SBY proofs | Environment assumptions proved on transactors | — | 🟡 AES-specific (cosynth) |
| D11 | Front-end fuzzing | Random SV in the subset, model vs XLS JIT. Internal QA, and part of the trust story | XLS fuzzer patterns | 🔴 M |

### 2.5 Debug: fast, in the designer's terms

| # | Value-add | What the designer gets | XLS hook | Status / effort |
|---|---|---|---|---|
| E1 | **SV-line annotations in RTL** | Every generated RTL line points to its SV line | `--source_annotation_strategy`, `pos` | 🟡 S: wired; verify end to end |
| E2 | **Debug name map + waveform alias scripts** | XLS's flattened signals are renamed and grouped by SV variable and stage in Verdi, SimVision and GTKWave (`p2_state_17` becomes `RunLengthEncoder.prev_count @ stage 2`) | P2 + block IR register names | 🔴 M. Fixes the #2042 pain |
| E3 | **Transaction views at every level** | Channel traffic recorded as transactions, the same at model, timed, RTL and gates | P3 | 🔴 S–M |
| E4 | **First-divergence finder** | Compares the per-channel transaction streams of two runs (model vs RTL, RTL vs gates, before vs after a change) and reports the first mismatching transaction and its activation number. Exact for blocking designs, because Kahn determinacy makes per-channel streams comparable regardless of timing | P3 | 🔴 S. *High value per line of code* |
| E5 | **Replay from SoC sim** | Capture a block's channel traffic in the full-chip RTL sim, then replay it into the SV model standalone and reproduce the failure in milliseconds, with the SV debugger | P3 + model shell | 🔴 S–M |
| E6 | Stage-aware RTL debug | From a failing RTL cycle, show which activation occupies each stage and which SV lines that stage computes | P2 + P3 | 🔴 M |

### 2.6 Back-end hand-off: RTL that signoff accepts

| # | Value-add | What the designer gets | XLS hook | Status / effort |
|---|---|---|---|---|
| F1 | House reset, flop and naming style | `--reset_asynchronous`, `--reset_data_path`, `--flop_*_kind`, suffixes from a team profile | codegen options | 🟡 S: some wired |
| F2 | **SDC + hand-off bundle** | RTL, an SDC stub (clock at the scheduled period, I/O delays used by the scheduler), file list, signature, datasheet, schedule report | schedule + options | 🔴 S |
| F3 | Synthesis scripts for Fusion / DC / Genus / Yosys | Turnkey per-block synthesis trial | — | 🟡 Yosys ✅; commercial 🔴 S |
| F4 | **Delay model characterization** for the customer's node | A schedule that holds in *their* library: a one-time per-node task driving their synthesis tool, using XLS's characterization flow | XLS delay-model tooling | 🔴 L. *Gating for "validated QoR" on commercial nodes* |
| F5 | Timing feedback loop | Read the synthesis timing report, then adjust `--clock_margin_percent` or per-block clock and reschedule. Or use XLS's FDO (yosys/OpenSTA) where possible | XLS FDO | 🔴 M |
| F6 | Lint/CDC gate on generated RTL | Generated RTL runs the house lint in CI, with standard waivers for XLS idioms | — | 🔴 S |
| F7 | RTL stability report | How much of the RTL changed for a small source change. This matters for ECO-minded teams | diff of block IR | 🔴 S |

### 2.7 Team process: richer reviews, safe upgrades

| # | Value-add | What the team gets | XLS hook | Status / effort |
|---|---|---|---|---|
| G1 | **QoR/schedule diff on every PR** | "This change: +1 stage, +3% area estimate, critical path moved to line 84", posted on the review | P2 + P4 | 🔴 S. Makes HLS changes *reviewable* |
| G2 | QoR trend dashboard | Area, latency and min-period history per block | P4 | 🔴 S |
| G3 | **XLS-upgrade gate** | A new xlsynth release must pass the block corpus with no QoR regression beyond a threshold and no lockstep failure before the team moves | P4 + D6 | 🔴 S. Takes the risk out of tracking XLS |
| G4 | CI templates (dv-flow) | One-line adoption of the whole set in a repo | — | 🟡 S |
| G5 | Prebuilt XLS via xlsynth | No Bazel for anyone | xlsynth releases | 🟡 S: missing `eval_proc_main` |

## 3. Review of what we've already planned

- **Keep.** Module shell (C1), timing shell (B1/B2), coding guide (A6), `logic` (A1),
  hand-off (F1/F2), debug annotations (E1), SRAM (C4), delay model (F4) and contracts are
  all in the catalog and still right.
- **Consolidate.** The module shell, timing shell, lockstep harness, UVM agents, SVA,
  datasheet and IP-XACT are all generated from the **same signature model (P1)**. Build P1
  as one library with emitters, not as one generator per artifact.
  `comp_api.xls_binding_sv` and `zuspec.xls.Signature` are the seeds.
- **Re-rank.** Earlier plans led with synthesis-side items. The catalog shows the
  **debug and verification items** (E4, E5, D3, D6, G1) are mostly small, and they're
  what designers feel every day. They should come earlier.
- **Gap we hadn't named.** CSR/configuration (C3). Almost every commercial block has
  registers. fw-hdl already has `fw_reg` / MMIO work, but "XLS block + CSRs" is out of
  scope today. It belongs on the commercial path.
- **Gap we hadn't named.** Making HLS changes reviewable (G1, F7). Teams resist HLS partly
  because a one-line source change can reshuffle the RTL invisibly. A schedule and QoR diff
  on the PR fixes the social problem as well as the technical one.

## 4. Top picks

Ranked by value to an RTL team relative to effort, assuming XLS stays the engine:

| Rank | Item | Why |
|---|---|---|
| 1 | **C1 struct-typed wrappers (on P1)** | The keystone. Everything else plugs into it |
| 2 | **B1 + D6 exact function timing shell + lockstep** | A cycle-accurate pre-RTL model that is *proven* against XLS RTL. Small effort |
| 3 | **A4 schedule overlay on SV source** | The "aha" demo: the designer sees the hardware in their own code. XLS doesn't offer it even for DSLX |
| 4 | **E4 + E5 divergence finder and replay (on P3)** | The fastest debug loop in HLS, enabled by Kahn determinacy |
| 5 | **B3 + B4 sweep and budgets** | Architects get numbers, and the budget is enforced continuously |
| 6 | **D2–D4 generated UVM agents, SVA, coverage** | DV gets a ready-made environment with the class as reference model |
| 7 | **G1 + G3 PR QoR diff and XLS-upgrade gate** | Makes HLS reviewable and makes XLS-version risk manageable |
| 8 | **B2 + B6 proc timing shell and FIFO sizing** | The multi-process story nobody else has |
| 9 | **F2 + F1 hand-off bundle** | Gets RTL into Fusion without hand edits |
| 10 | **C3 CSR integration** | Needed for real blocks |
| Strategic | **F4 delay model for the target node** | Large, but without it "validated QoR" on a commercial node is only XLS's estimate |

**A demo that shows most of this in 10 minutes:**
1. Edit one SV class.
2. Show the schedule overlay (A4) and the PR diff (G1).
3. Run the sweep (B3).
4. Drop the timed shell into an SoC bench.
5. Show the lockstep pass (D6).
6. Inject a bug and let the divergence finder (E4) point at the transaction and SV line.
7. Replay it in the model (E5).
