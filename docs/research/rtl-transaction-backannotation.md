# Transaction-level back-annotation of XLS-generated RTL

*Design note, 2026-11-01. Supports value V7 ("debug in your terms") in
[sv-value-over-xls.md](sv-value-over-xls.md). XLS facts were checked against google/xls
`main` @ `bc53272`:*
- *`codegen/side_effect_condition_pass.h`*
- *`codegen/conversion_utils.cc` (`PipelineSignalName`)*
- *`codegen/block_stitching_pass.cc` and `clone_nodes_into_block_handler.cc` (FIFO instances)*
- *`codegen/module_signature.proto`*
- *`tools/codegen_flags.cc`*

## 1. Short answer

**Yes.** Transactions can be recovered from XLS RTL at three depths. For each one, the
naming facts come from XLS and fw-hdl generates the monitors:

| Tier | What you see as transactions | How | Exactness |
|---|---|---|---|
| **T1. Block boundary** | Every send/receive on the module's channels | Passive monitors on the pins named in the signature (`<ch>`, `<ch>_vld`, `<ch>_rdy`); a transaction is a cycle with `vld && rdy` | Exact; zero change to the RTL |
| **T2. Internal channels** (between procs) | Every push and pop on every internal channel, plus FIFO occupancy | XLS multi-proc codegen instantiates **`fifo_<channel>`** with push and pop ready/valid/data ports, listed in the signature's `instantiations`. With fw-hdl's `Integrate`, the FIFOs are our own `fw_rv_fifo` | Exact; passive |
| **T3. Inside a proc** | **One record per activation**: values received, state read, state written, values sent | Reconstruct from the pipeline's own control signals and registers, mapped through block IR (passive). Or have fw-hdl insert IR trace ops (instrumented) | Passive: exact for a given codegen version. Instrumented: exact, but see §3.2 |

Every record is decoded with the **SV types** (named struct fields) and labelled with
**SV names** (class property names, SV source lines). That is what makes it
*back-annotation*, not just a protocol monitor.

## 2. Why the alignment works

- **Per-channel order is fixed.** XLS keeps the order of operations on each channel, and
  for blocking designs the value stream on each channel doesn't depend on timing (Kahn
  determinacy). So transaction *k* on channel *c* in the RTL corresponds to transaction *k*
  on *c* in the SV model, the timing shell and the gates.
- **Activations are counted, not timed.** Activation *k* of a proc in the RTL is iteration
  *k* of the class's `forever` loop. XLS starts activations in order, and fw-hdl's subset
  allows one operation per channel per activation.
- **Non-blocking receives (`try_get`)** make streams timing-dependent. Compare those against
  the **timing shell**, which reproduces RTL timing, not against the untimed model.

## 3. Tier 3 in detail: activation records inside a pipeline

### 3.1 Passive reconstruction (preferred)
What XLS codegen gives us (codegen 1.5):
- **Stage occupancy.** Per-stage valid registers are named `p<s>_valid`, and load enables
  `p<s>_load_en` (`block_conversion.cc`). An activation enters stage 0 when stage 0 loads,
  and moves from *s* to *s+1* when `p<s+1>_load_en` fires.
- **Values in flight.** Pipeline registers are named `p<s>_<IR node name>`
  (`PipelineSignalName`). **fw-hdl writes the IR, so it chooses the node names.** If it
  names the nodes after SV variables and class properties (`prev_count`), the registers
  become `p2_prev_count`.
- **Where each operation happens.** The schedule (and the signature's per-channel `stage`)
  gives the stage of every receive, send, `state_read` and `next_value`.
- **Authoritative mapping.** `--output_block_ir_path` gives the block IR: every register
  and port, by name. `--output_verilog_line_map_path` maps Verilog lines back to IR.

From these, fw-hdl generates a **bind module** (SV `bind` into the XLS module, which works
in every simulator including Verilator, with no hierarchical paths in user code). It tracks
activation tokens stage by stage and emits one record per activation:

```
act 1284  RunLengthEncoder
  recv input_r  {symbol: 'h0000_00a5, last: 0}        @ stage 0, cycle 5121
  state prev_count  2 -> 3                             (rle_pkg.sv:61)
  send output_s {symbol: 'h0000_00a5, count: 2, last: 0} @ stage 1, cycle 5122
```

**The rule:** the bind module is **regenerated from block IR every build**, never written
by hand. If the names change, the generator changes with them. Pin the codegen version
(codegen 2.0 is in progress upstream) and gate upgrades with a self-test: the RTL's
activation records must match the timing shell's.

### 3.2 Instrumented (debug builds only)
fw-hdl can insert IR `trace` ops at each receive, send and state update.
`side_effect_condition_pass` rewrites every side-effecting op's condition to
`stage_valid → cond`, so each trace fires **exactly once per activation per stage**. They
appear in the RTL as structured `$display` lines under `` `ifdef SIMULATION ``, and are
robust to any renaming.

**Caveat:** trace ops keep their operands alive and are ordered side effects in IR. They
can change XLS's optimization and schedule, so the instrumented RTL may not be the
signoff RTL. Use this only for a debug build. Report the QoR and schedule delta against the
clean build, or keep it for when passive reconstruction isn't available.

## 4. What it enables

Use the same record format at every level. For the model, hook `fw_channel` and the
activation boundary.
- **First-divergence finder (E4):** compares per-channel streams (T1/T2) and per-activation
  records (T3) between any two runs, and reports, for example: "channel `output_s`,
  transaction 1,284; first differing field `count`; the activation also wrote
  `prev_count` (rle_pkg.sv:61)."
- **Replay (E5):** captured T1 records from the full-chip RTL sim drive the SV model or
  timing shell standalone.
- **Waveform and transaction views:**
  - a vendor-neutral record log
  - adapters for Verdi/SimVision transaction streams and Perfetto, the last showing an
    activation timeline with stalls and bubbles
  - waveform alias scripts that rename `p2_prev_count` to `RunLengthEncoder.prev_count
    @ stage 2`
- **Coverage on RTL in SV terms:** sample the struct-field coverage (D4) from T1/T2 records
  on the real RTL, not just the model.

## 5. Limits

| Limit | Mitigation |
|---|---|
| **Gate level:** internal names are gone after synthesis | T1 always works. T2 works if the FIFO hierarchy is preserved (dont-touch the `fifo_*` instances). T3 at gates is out of scope; reproduce at RTL or model |
| **Simulator visibility:** Verilator may optimize internal signals away | The bind module reads them structurally. Mark it public / `--public-flat-rw` for those nets in debug runs |
| **Codegen naming isn't a published contract** | Generate from block IR every build; pin the codegen version; self-test the records against the timing shell |
| **Single-value channels and RAM ports** | Single-value: log on change. RAM ports (`rams[]` in the signature) get their own request/response monitors |
| **Polling (`try_get`) designs** | Compare against the timing shell, not the untimed model |

## 6. Build order

| Step | Deliverable | Effort | Depends on |
|---|---|---|---|
| 1 | Record format + `fw_channel` hook (model side) | S | — |
| 2 | T1 pin monitors generated from the signature / `shell.json` | S | shell generator |
| 3 | Divergence finder over T1 streams | S | 1, 2 |
| 4 | T2 FIFO monitors (`fifo_<channel>` / `fw_rv_fifo`) | S | 2 |
| 5 | IR node naming = SV names in the fw-hdl XLS lowering | S–M | — |
| 6 | T3 bind module from block IR + schedule; self-test against the timing shell | M | 5, timing shell |
| 7 | Replay, Perfetto and waveform adapters | S each | 1–3 |

Steps 1–3 already deliver the headline debug story at the block boundary. Step 5 is cheap
and pays off twice: readable RTL register names, and T3 records.
