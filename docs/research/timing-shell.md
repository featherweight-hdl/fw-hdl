# Struct-typed wrappers and a timing shell from XLS's outputs

*Design note, 2026-11-01. Companion to [designer-ramp-to-xls.md](designer-ramp-to-xls.md)
(step 2 "module shell", step 4 "timed shell"). The XLS facts below were checked against
google/xls `main` @ `bc53272`:*
- *`xls/codegen/module_signature.proto`*
- *`xls/scheduling/pipeline_schedule.proto`*
- *`xls/codegen/signature_generator.cc`*
- *`xls/codegen/proc_block_conversion.cc`*

## 1. Short answers

- **Does XLS define interfaces as ready/valid? Yes, with one exception.**

  | Kind of interface | What XLS generates |
  |---|---|
  | Streaming channel (procs) | data, `<ch>_vld` and `<ch>_rdy` ports. The suffixes are configurable, and fw-hdl already passes `--streaming_channel_*_suffix` |
  | Single-value channel | A bare data port with no handshake |
  | Function pipeline | Optional `input_valid` / `output_valid`, with **no ready** and no back-pressure. It loads every cycle |

  Each channel's data is one flat bit vector.
- **Can we wrap both sides with struct-typed ports?** Yes, cheaply. fw-hdl lowers an SV
  `struct packed` to a bit vector with the same layout (first field = MSB). So the XLS data
  port *is* the struct's bits, and the RTL wrapper is a cast. The model shell and the RTL
  wrapper can present identical ports typed with the designer's structs, generated from one
  description.
- **Is there enough timing data for a timing shell around the SV class?** Yes:
  - For **function pipelines**, the shell can be **exactly cycle-accurate**, and that's
    trivial to build.
  - For **procs**, the signature plus the schedule give enough to build a stage-level
    flow-control model that should be cycle-accurate. The condition is that we reproduce
    XLS codegen's pipeline flow-control rules, which are documented in the source and
    stable per codegen version.
  - Because the shell and the RTL have identical pins, we can **prove the shell right
    automatically** by running both in lockstep and comparing pins cycle by cycle (§5).

## 2. What XLS gives us, field by field

**Module signature** (`--output_signature_path`; fw-hdl already reads it via
`zuspec.xls.Signature`):

| Field | Use in fw-hdl |
|---|---|
| `clock_name`, `reset{name, asynchronous, active_low, reset_data_path}` | Exact clock and reset pins for both wrappers |
| `data_ports[]{name, direction, width, type}` | Exact port list |
| `channel_interfaces[]{channel_name, direction, kind, flow_control, data/valid/ready port names, type}` | Maps each SV port/channel to its pins. `flow_control` is NONE, READY_VALID or VALID_DATA |
| `channel_interfaces[].stage` | **The pipeline stage in which that send or receive happens** |
| `channel_interfaces[].flop_kind` | I/O buffering per channel: none, flop (+1 cycle, a 1-entry FIFO) or skid buffer (+1 cycle, decoupled ready). Affects latency and ready behavior |
| `pipeline{latency, initiation_interval, pipeline_control}` | Overall latency, including I/O flops, and II. **Caveat:** II is `block->GetInitiationInterval().value_or(1)`, so for a proc with a state feedback it can read 1 when the real throughput is lower. Derive II from the schedule instead (below) |
| `fixed_latency` / `combinational` | Function blocks |
| `type` (TypeProto: bits / tuple / array) | Layout cross-check against the SV struct |
| `rams[]` | Later: SRAM ports |

**Schedule** (`PackageScheduleProto`; fw-hdl's StageTLM already reads it):
- For each function or proc: `stages[]{stage, timed_nodes[]{node, node_delay_ps, path_delay_ps}}`,
  plus `length`, `min_clock_period_ps` and `target_clock_period_ps`.
- Every IR node, including `receive`, `send`, `state_read` and `next_value`, has a stage
  number and a delay.
- With the scheduled IR, that gives us:
  - the **stage of every channel operation**
  - the **stage that reads each state element**
  - the **stage that writes it back**
  - each node's **critical-path slack**, useful for reports

**Flow-control rules** (`proc_block_conversion.cc`, codegen 1.5):
- The proc pipeline uses **bubble flow control**. A stage advances when its own inputs are
  valid, its sends are accepted, and the next stage is empty or advancing. So bubbles
  collapse when the output stalls.
- State registers are written only when the writing stage is active and valid.
- A stage that reads state waits until that state is valid ("`all_active_states_valid`").
- Together these determine II: if state is read in stage *r* and written in stage *w*, the
  next activation can't use it until *w − r + 1* cycles later.

## 3. Struct-typed wrappers (the automation)

From one description (the SV class's ports plus the XLS signature), fw-hdl generates three
pieces:

1. **`<blk>_pkg`**: the designer's own struct typedefs, re-exported, plus a per-block port
   bundle if wanted.
2. **The model shell** `module <blk>`: struct-typed ports
   (`input in_t in, input in_vld, output in_rdy, …`) wrapping `fw_root` and ready/valid
   transactors around the SV class.
3. **The RTL wrapper**, also named `module <blk>`, with identical struct-typed ports. It
   instantiates XLS's module and casts: `.in(in)` becomes `.in(in_t'(in))`, which is a
   no-op on bits.

Generated checks:
- **Layout:** `$bits(in_t)` equals the signature port width. When the TypeProto is a tuple
  or array, the element order is checked against the struct's field order. A mismatch fails
  the build.
- **Pin parity:** both wrappers expose exactly the same port list. A mismatch fails the
  build.

Optional: emit an SV `interface` per channel (`fw_rv_if #(type T)`) for teams that wire
with interfaces, plus modports.

Effort is small. `comp_api.xls_binding_sv` already generates `<module>_xtor_if` from
signatures, and the ready/valid transactors exist in `tests/rv_proto/`.

## 4. The timing shell

### 4.1 Function pipelines: exact
A function pipeline has a fixed latency *L* (from the signature, including I/O flops),
II = 1 and no back-pressure. The shell does the following:
- It samples the input every cycle that `input_valid` is high.
- It calls the SV function at zero time.
- It pushes the result into an *L*-deep delay line that drives the output and
  `output_valid`.

This is pin-for-pin identical to XLS RTL by construction. It extends today's StageTLM,
which is latency-only and blocks one op for the full latency, so it allows ops to overlap
the way the real pipeline does.

### 4.2 Procs: a stage-level flow-control model
The shell treats each activation of the class's `forever` loop as a token moving through
*L* stages. It runs the RTL's rules, not the class's timing:

| Rule | Source |
|---|---|
| A receive on channel *c* completes in the cycle when the activation is in `stage(c)`, the stage can advance, and `c_vld` is high | signature `stage`, flow control |
| A send on *c* presents `c_vld` when the activation is in `stage(c)`, and completes on `c_rdy` | same |
| A predicated (`if`) send or receive that is false takes no cycle on that channel | schedule plus the class's own control flow |
| `try_get` (non-blocking receive) samples `c_vld` in that exact cycle | so the polling model becomes **timing-faithful**, not merely determinate |
| A stage advances iff its operations are done and the next stage is empty or advancing (bubble collapse) | `proc_block_conversion.cc` |
| An activation can't enter the stage that reads state *x* until the previous activation has written *x* | `state_read` / `next_value` stages, which give II |
| I/O flop, skid and zero-latency buffers add their latency and buffering | `flop_kind` |

**How the class and the shell cooperate:**
- The class computes the *values*; the shell decides *when* each one appears on the pins.
- The class runs ahead functionally:
  - Its `get` blocks until the shell completes that receive for its activation.
  - Its `put` is captured immediately and released to the pins when the activation
    reaches the send's stage.
- Because fw-hdl channels are blocking and XLS keeps per-channel order, the value streams
  are the same as the RTL's, and the shell supplies the cycle timing.

**Activation boundaries.** The shell must know when one iteration of `forever` ends.
There are two ways to get this:
- **Preferred:** fw-hdl's front end already has the AST of the lowerable `run()`. It
  emits a timed copy of the class with a hook at the top of the loop. That is the same
  kind of generation StageTLM already does.
- **Fallback:** a no-op `activation()` marker call that the coding guide asks for and the
  lowering ignores.

The static subset helps here: one operation per channel per activation, and no channel
operations inside loops.

**Composition.** A network of shells connected by `fw_rv_fifo` (whose timing we own)
reproduces network-level throughput, back-pressure and FIFO occupancy. That is the
architect's question, answered before RTL.

### 4.3 Fidelity limits (state them up front)
- **The shell's timing is XLS's opinion.** Stage counts come from XLS's delay model, and on
  a commercial node without a characterized model the RTL's *schedule* is a guess too. The
  shell matches the RTL that XLS generates; it doesn't predict the post-synthesis timing.
- **The codegen version matters.** The rules above are codegen 1.5. Codegen 2.0 is in
  progress, so pin the version and gate it with the lockstep check (§5).
- **Multi-proc tops built by XLS** (`--multi_proc`) add FIFO instantiations. Model those
  from the signature's `instantiations` / `fifo_config`, or keep fw-hdl's `Integrate` for
  composition.
- **The signature's II can be wrong for procs** (`value_or(1)`), so always derive II from
  the schedule.

## 5. Automatic proof that the shell is right

Both wrappers have the same struct-typed pins, so fw-hdl can generate a **lockstep
harness**:
- Instantiate the timing shell and the XLS RTL.
- Drive both from the same randomized ready/valid stimulus, with random valid and ready
  throttling on every channel.
- Compare every output pin every cycle.

A mismatch names the channel, the cycle and the activation. This turns "cycle-accurate"
from a claim into a regression test, and it catches drift when XLS changes. The existing
`vectors-run-fid` check (32 ops in 128 clocks on AES) is the function-pipeline version of
this, done by hand.

## 6. What exists and what to build

| Piece | Status |
|---|---|
| Reading the XLS signature | ✅ `zuspec.xls.Signature`, `comp_api.xls_binding_sv` |
| Reading the XLS schedule | ✅ `fw.hdl.xls.StageTLM` (`stage_tlm.py`) |
| Ready/valid transactors | 🟡 `tests/rv_proto/`; move to `src/std` |
| Struct-typed model shell + RTL wrapper + layout and pin-parity checks | 🔴 small |
| Function-pipeline timing shell (exact, overlapping) | 🔴 small: extends StageTLM |
| Proc timing shell (stage and flow-control model, state-backedge II, flop kinds) | 🔴 medium: needs scheduled IR → per-op stage map, and the activation hook |
| Lockstep shell-vs-RTL harness | 🔴 small once the wrappers exist |
| Pass `--output_scheduled_ir_path` / block IR through `synth.xls.Codegen` | 🔴 trivial (dv-flow-libsynth) |

**Suggested order:**
1. Struct-typed wrappers with their checks.
2. The function-pipeline shell.
3. The lockstep harness.
4. The proc shell.

The lockstep harness should come before the proc shell, so every proc-shell rule is
developed against the RTL from day one.
