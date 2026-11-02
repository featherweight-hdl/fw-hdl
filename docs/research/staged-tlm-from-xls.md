# Intermediate models from XLS: a pipelined ("staged") TLM, and how far tweak-and-continue can go

*Design note, 2026-11-01. This straddles both tracks:*
- *Track A (debug aid on the XLS flow)*
- *Track B (incremental lowering; see §6 of
  [designer-ramp-to-xls.md](designer-ramp-to-xls.md))*

*Related: [timing-shell.md](timing-shell.md) and
[rtl-transaction-backannotation.md](rtl-transaction-backannotation.md). XLS facts were
checked against google/xls `main` @ `bc53272`:*
- *`tools/codegen.cc`, `tools/codegen_main.cc`*
- *`tools/scheduling_options_flags.cc`*
- *`tools/block_to_verilog_main.cc`*

## 1. Short answer

- **Does XLS give us enough to *build* intermediate models? Yes.** Four artifacts
  together fully determine a pipelined model:
  - the schedule (node → stage, delays)
  - the scheduled, optimized IR (the operations)
  - block IR (pipeline registers, state registers, flow control)
  - the signature (stage of each channel operation, I/O flops)

  **This is already demonstrated** for a function pipeline. `synth.xls.Lower`
  (dv-flow-libsynth, branch `wpk/lower`) reads XLS's schedule and scheduled IR for AES A0
  and emits a V4 cycle class plus V5 SV. Two link checks pass:
  - V3↔V4: 500 random ops in simulation
  - V4↔V5: a per-stage Yosys miter
- **Does XLS let us *tweak an intermediate model and continue*? Only partly.** It has two
  re-entry points:
  1. **Constraints → reschedule:** `--pipeline_stages`, `--clock_period_ps`,
     `--worst_case_throughput`, `--io_constraints` and `--scheduling_options_proto`. A
     tweak that can be expressed as a constraint round-trips through XLS.
  2. **Block IR → `block_to_verilog_main` → Verilog:** a tweaked pipelined model emitted as
     block IR comes back from XLS's own Verilog emitter. This bypasses XLS's scheduler and
     optimizer, so proving equivalence is our job.

  What XLS does **not** accept is "here is my schedule". `codegen_main` only *writes* a
  schedule; it has no flag to read one. So "move this operation to stage 2 and continue"
  is a native fw-hdl capability (Track B). XLS can seed it and act as the QoR and
  equivalence oracle, but it can't perform it.
- **Is a pipelined TLM a better debug aid than RTL plus monitors?** For **pipeline-specific
  bugs, yes**: timing, back-pressure, state hazards and wrong values at stage boundaries.
  Functional bugs are still best debugged in the untimed model. Monitors tell you *where*
  RTL diverged; the staged model lets you *step through* it (§4).

## 2. The model ladder XLS's artifacts can populate

Every model below is an fw-hdl SV class behind the same pin shell, so any of them can
replace the RTL in a test or the SoC sim.

| View | What it is | Built from | Status |
|---|---|---|---|
| V1 | The designer's class: untimed, order only | source | ✅ |
| V3 timing shell | V1 wrapped with XLS latency, II and per-channel stage | signature + schedule | 🟡 latency-only; exact function shell 🔴 S |
| **V3.5 staged TLM** *(proposed)* | **One fw-hdl process per pipeline stage**, connected by depth-1 channels. Each carries a **stage-boundary struct**: the values live across that boundary, i.e. the pipeline registers, with SV names. Each stage body is that stage's computation. I/O and state operations sit in their scheduled stage. Each stage advances once per clock with `tick` | schedule + scheduled IR (+ block IR for proc flow control) | 🔴 |
| V4 cycle class | Per-stage combinational functions + named registers + `tick()` | schedule + scheduled IR | ✅ AES A0 only (`synth.xls.Lower`) |
| V5 | RTL: XLS's own, or native from V4 | — | ✅ |

**Why V3.5 sits between V3 and V4.** It is the first view with the pipeline's *structure*:
stages, boundary values, stalls. It is still transaction-level: flow control comes from
blocking channels, not ready/valid wires; there are no per-bit registers or enables; and
each stage-to-stage transfer is one record. It is the "TLM version of scheduling" the
native flow wants.

### Construction rules
- **Stage partition:** read straight from the schedule.
- **Boundary structs:** the values defined in a stage ≤ *s* and used in a stage > *s*. These
  are exactly block IR's `p<s+1>_<name>` registers, which cross-check each other.
- **Names:** emit XLS IR node names from SV variable and property names. This is the same
  step as in the back-annotation note. Optimized nodes keep their source `pos`, so every
  stage-body line carries an `// rle_pkg.sv:61` comment.
- **Stage bodies:** XLS IR ops → SV expressions. `synth.xls.Lower` already does this for V4.
- **Function pipelines:** trivial, with no stalls. The structure follows V4's.
- **Procs:**
  - **Bubble flow control.** XLS's rule is that a stage advances iff the next stage is
    empty or advancing. That is a depth-1 channel that can be drained and refilled in the
    same cycle ("pipelined FIFO"). **Check whether `fw_channel #(T,1)` has those
    same-cycle semantics**; if not, add a variant.
  - **State.** Model each element as a register object written by its `next_value` stage
    and read by its `state_read` stage, with a valid flag. That reproduces XLS's
    "all active states valid" interlock, and so the II.
- **Link checks**, generated every build:
  - **V1 ↔ V3.5:** equal per-channel transaction streams (functional).
  - **V3.5 ↔ XLS RTL:** pin lockstep (timing).

## 3. A sketch

```systemverilog
// Generated from XLS schedule (2 stages) for RunLengthEncoder. Do not edit (Track A).
typedef struct packed { bit [31:0] symbol; bit [1:0] count; bit last;
                        bit do_send; } rle_s0_s1_t;        // p1_* registers

class RunLengthEncoder_staged extends fw_component implements fw_runnable;
  fw_port #(fw_get_if #(EncInData))  input_r;    // stage 0 (signature)
  fw_port #(fw_put_if #(EncOutData)) output_s;   // stage 1 (signature)
  fw_channel #(rle_s0_s1_t, 1) s0_s1;            // pipeline register, stage 0 -> 1
  fw_state #(bit [1:0]) prev_count;              // read s0, written s1 (gives the II)
  ...
  task stage0();  forever begin
      // rle_pkg.sv:44  if (!prev_last) input_r.t.get(input_);
      ...  s0_s1.put(b);  tick(1);
  end endtask
  task stage1();  forever begin
      s0_s1.get(b);
      // rle_pkg.sv:61  if (do_send) output_s.t.put(...)
      ...  prev_count.write(b.count);  tick(1);
  end endtask
endclass
```

## 4. Debug: the staged model vs RTL with monitors

| | XLS RTL + generated monitors | Staged TLM (V3.5) |
|---|---|---|
| What you read | RTL nets and bind-module records | SV class code, one task per stage, with SV-named boundary structs |
| Stepping | Waveforms | **SV debugger:** breakpoints in `stage1()`, watch `b.count` |
| Stage-boundary transactions | Reconstructed by a bind module from block IR | **Native:** every `s0_s1` transfer *is* the record |
| Back-pressure and stalls | Visible as ready/valid and load enables | Visible as blocked `put`/`get`, with an SV call stack |
| State hazards and II | Inferred from register enables | Explicit `fw_state` read/write events |
| Fidelity | Ground truth | As good as its link checks (lockstep with the RTL every build) |
| Fits in the SoC sim | Yes | Yes: same pin shell |
| Readability limit | Mangled names unless IR naming is fixed | Post-optimization code (folded, CSE'd), annotated with source lines |

**Triage ladder.** It falls out of the link checks:
1. **V1 ≠ V3.5:** the problem is in optimization or scheduling, or in what the designer
   thinks the source means. Debug in V1 or V3.5.
2. **V3.5 ≠ XLS RTL:** the problem is in codegen or flow control. That localizes a
   potential XLS codegen bug, or a mismatch in our model of XLS's flow-control rules.
3. **V3.5 = RTL, but the SoC fails:** the problem is in integration or protocol. Debug with
   the staged model in the SoC sim, at TLM speed, with the SV debugger.

**Verdict.** Use both. Monitors on the real RTL find the failing transaction. The staged
model is where you *step through* it. It's worth building first for procs, where stalls
and state hazards are hardest to read in RTL.

## 5. Tweak-and-continue: what's possible with XLS, and what's native

| Tweak | Route | Engine |
|---|---|---|
| "Use 3 stages / this clock / II = 2 / these I/O timings" | Constraint → XLS reschedules → regenerate V3.5/V4 | **XLS** (today) |
| "Move this operation to stage 2", "add a register here", "share this multiplier" | Edit V3.5/V4 → native lowering continues → V5 | **Native** (Track B). Needs V3.5/V4 parsers; `reentry.md` notes there's no V4 parser today |
| Same edits, but keep XLS as the RTL emitter | Edited V4 → **block IR** emitter → `block_to_verilog_main` | **XLS codegen** for the last step only. Equivalence is ours: per-stage miter as in fw-aes, or xlsynth's `ir-equiv-blocks` (to verify for sequential blocks) |
| Any edit: is the result still as good as XLS? | XLS's own schedule and RTL for the unedited design | **XLS as oracle** for QoR and equivalence |

The Zuspec "tweak intermediate models and keep lowering" vision is therefore a Track B
capability. XLS supplies the initial intermediate models: they're derived from its
schedule, so they start at XLS QoR. It also supplies a codegen back end through block IR,
and a reference. The ~5% native QoR gap (`synth.xls.Lower` vs XLS on A0) is what the
block-IR route would avoid while native lowering closes it.

## 6. Plan

| Step | Deliverable | Effort | Notes |
|---|---|---|---|
| 1 | IR node names = SV names in the fw-hdl XLS lowering | S–M | Shared with back-annotation; also readable RTL |
| 2 | Staged TLM emitter for **function** pipelines, reusing `synth.xls.Lower`'s stage split and expression emission | S–M | Land/push `wpk/lower` first (currently unpushed) |
| 3 | Generated link checks: V1↔V3.5 streams, V3.5↔RTL lockstep | S | Reuse the lockstep harness |
| 4 | Check `fw_channel #(T,1)` same-cycle drain-and-refill semantics; add `fw_state` (state with read/write stages) | S | Prerequisite for procs |
| 5 | Staged TLM for **procs**: bubble flow control, state interlock, flop kinds | M–L | Start with `rle`, then `lfsr_proc` |
| 6 | Block-IR emitter from V4 → `block_to_verilog_main` | M (research) | Track B bridge; check that the block IR text format is stable enough |
| 7 | V3.5/V4 parsers for tweak-and-continue | L | Track B proper |
