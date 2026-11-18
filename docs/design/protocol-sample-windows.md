# Protocol sample windows: a bug checker and a lifting tool

Status: exploration. Builds on `automated-lifting.md` (§3 Propose, §5
operation-level equivalence) and the protocol kits (`core-protocol-kit-prep.md`).

## User benefit

Once a block's ports are mapped to protocols, the user gets two things without
writing anything more:

- **A bug checker.** It reports every place where the block reads interface
  data outside the window in which the protocol says that data is valid. One
  example is reading `data` on `valid` alone, when it should be read on
  `valid && ready`. These bugs only show up under particular stalls, so tests
  miss them. The structural check finds them without any stimulus.
- **A lifting step.** It splits hand-written RTL into the *per-operation
  function* (what happens to state when a transfer fires) and the *control*
  (when a transfer may fire). That split is the hard part of lifting RTL to
  method-level fw-hdl, and here it falls out of the protocol binding.

Both come from one fact that the protocol kit already knows, and both run as
one Zuspec IR analysis.

## 0. Status

| Step | State |
|---|---|
| P1 Sample predicate on kit roles | not started |
| P2 Window analysis pass (Zuspec IR) | not started |
| P3 Checker: structural report + garbage injection | not started |
| P4 Rule extraction for lifting | not started |
| P5 Guarded evaluation in sim (optional) | not started |

## 1. The idea

Every protocol defines a **sample window** for each payload field: the
cycles in which the receiver may read it. For ready/valid that window is
`fire = valid && ready`. Outside the window the sender may drive anything.

Synthesis already uses *observability don't-cares*, but it can only infer
them from inside the design. A protocol's sample window is an *environmental*
don't-care: it is part of the interface spec, and plain RTL has nowhere to
state it. A protocol binding does state it.

**What follows from that:** a *compliant* block must give the same results
whatever the payload holds outside the window, because a legal sender may put
garbage there. So:

- If the block depends on out-of-window payload, that is a bug (§3).
- If it doesn't, all logic fed by the payload is evaluated only "on fire",
  and the block factors into rules (§4).

Whether the block really ignores the payload is a property of the *block*,
not the protocol. That is why it must be checked, not assumed. The checker
also gates the lifting step: the lift is sound only if the check passes.

## 2. The analysis

### 2.1 Input from the protocol kit

Each payload field of a role gets a **sample predicate** `S(F)`. The kit
supplies it; the user writes nothing.

| Protocol | Fields | `S(F)` | Stability rule |
|---|---|---|---|
| ready/valid | data, last, … | `valid && ready` | optional (AXI: stable while `valid && !ready`) |
| AXI channel | per channel | `xVALID && xREADY` | required |
| Wishbone classic | `dat_i` (read) | `ack` | — |
| fixed latency | `rdata` | `req` delayed N cycles | — |

The stability rule is a separate assertion, and the kit already owns it. The
window is always defined by the *sample* predicate, never by `valid` alone.
Otherwise protocols without a stability rule would be analysed wrongly.

### 2.2 Two independent properties per signal

For each payload input field `F` with window `S`:

1. **Gated:** `F` reaches state only through register enables that imply `S`,
   and reaches output ports only as payload of outputs whose own window
   implies `S`. This is the property the **checker** proves.
2. **Data-only:** `F` doesn't influence any handshake signal (`valid`,
   `ready`, credits) or any state that feeds one. This is the property that
   gives **data independence**, and it is what makes guarded evaluation
   simple.

They are independent. In the example below, `in_last` is gated but not
data-only: it is read only on fire, but it steers control (`full`).

The same holds for **outputs**: a block's output payload is a don't-care to
its consumer outside that output's window. So the logic that computes it
needs to be correct only inside the window. This composes across internal
interfaces when they are protocol-mapped too.

### 2.3 Where it runs

This is a Zuspec IR analysis, not fw-hdl code:

- The kit attaches `S(F)` to the protocol interface type in Zuspec.
- The pass works on the sync/comb IR. Hand-written SV arrives there through
  `zuspec-fe-sv`, and fw-hdl designs arrive directly.
- The pass annotates signals and registers with
  `{window: S, gated: bool, data_only: bool}`, plus the paths that break each
  property.
- Consumers read those annotations: the checker, the lifter, the sim backend
  and formal.

## 3. The checker

Three levels, from cheapest to strongest:

- **C1 Structural (no stimulus).** Using the IR, show that each register
  enable on a path from `F` implies `S`. Implication is a small SAT/BDD query
  over the enable's control logic.
  - A failure is reported as "unproven" together with the path, because
    structure is conservative.
  - In practice most real bugs are already plain here: `if (in_valid)` where
    `if (in_valid && in_ready)` was meant.
- **C2 Garbage injection (simulation).** A bind-on scrambler drives random
  payload (or X) whenever `!S`.
  - Run it in the in-situ harness of `automated-lifting.md` §5.5: the block
    runs twice, with clean and with scrambled inputs.
  - Then compare. Handshake signals must match every cycle, and payload must
    match on each output fire.
  - This uses the existing tests, so no new stimulus is needed. It does need
    a stimulus that opens the window being misused (e.g. stalls).
- **C3 Formal.** The same miter with payload left free outside `S`, proved in
  SymbiYosys. This turns C1's "unproven" results into proofs or
  counterexamples. The protocol kits already ship a back-to-back sby
  component, and this is a second miter beside it.

**Bugs it targets:**
- reading data on `valid` without `ready`;
- pre-decoding a header before `valid`;
- side logic (counters, parity checks) that samples every cycle;
- output payload that is right only by coincidence of the current stimulus.

## 4. Lifting

For a gated block, the IR annotations give the lift directly:

- **Operations.** Each input window `S(P)` is an operation on port `P`. Its
  payload fields become the method's arguments.
- **Rule bodies.** Registers whose enable implies `S(P)` are updated by
  operation `P`. Their next-state logic, with `S(P)` set true, is the rule
  body `state' = f_P(state, payload)`.
- **Guards.** The control cones (what drives `ready`, or `valid` on outputs)
  become method guards, or the blocking condition of a method call.
- **Output operations.** An output's payload logic, evaluated at its window,
  gives the return value or argument of the output operation.
- **Remainder.** Registers updated outside any window (free-running counters,
  timers) and registers written by more than one operation in the same cycle
  are left as an explicit internal process. The lifter does not guess.

The lifted design is compared with the original under **E1** (in-order and
latency-tolerant, `automated-lifting.md` §5.3). This is the natural relation,
because payload is compared only at fire. E0 is still possible when the lift
keeps cycle timing.

**Precondition:** C1 or C3 must pass. If the block reads payload outside the
window, the rule extraction is wrong. That is the bug, and the checker has
found it.

## 5. Worked example

```systemverilog
module acc (
  input  logic        clk, rst,
  input  logic        in_valid,  output logic in_ready,
  input  logic [31:0] in_data,   input  logic in_last,
  output logic        out_valid, input  logic out_ready,
  output logic [31:0] out_data);

  logic [31:0] sum;
  logic        full;
  wire in_fire  = in_valid  && in_ready;
  wire out_fire = out_valid && out_ready;

  assign in_ready  = !full;
  assign out_valid = full;
  assign out_data  = sum;

  always_ff @(posedge clk)
    if (rst) begin sum <= '0; full <= 1'b0; end
    else begin
      if (in_fire)  begin sum <= sum + in_data; if (in_last) full <= 1'b1; end
      if (out_fire) begin sum <= '0; full <= 1'b0; end
    end
endmodule
```

**Analysis:**

| Signal | Window | Gated | Data-only | Role |
|---|---|---|---|---|
| `in_data` | `in_fire` | yes | yes | payload |
| `in_last` | `in_fire` | yes | **no** (→ `full` → `in_ready`, `out_valid`) | payload that steers control |
| `full` | — | — | — | control state |
| `sum` | written under `in_fire`, `out_fire` | — | — | operation state |
| `out_data` | `out_fire` | — | — | output payload |

**Lifted (sketch, not final fw-hdl syntax):**

```
in.put(data, last)   guard !full :  sum += data; if last: full = 1
out.get() -> r       guard  full :  r = sum; sum = 0; full = 0
```

**The bug the checker catches:** change the first branch to
`if (in_valid)`. Then whenever `full` holds and the sender keeps `valid` high,
`sum` keeps adding stalled beats.
- **C1** reports it at once: the enable on `in_data → sum` is `in_valid`,
  which does not imply `in_fire`.
- **C2** catches it only if a test stalls the input while full. This is
  exactly why such bugs escape testing.

## 6. Also: guarded evaluation in simulation

With the same annotations, a backend can wrap gated, data-only cones in
`if (S)`.
- **The gain** is roughly the idle fraction of each window. It is large for
  wide datapaths at low utilisation and near zero at full throughput, where
  the guard is pure overhead. A cost model should decide.
- **Waveforms** then show stale payload outside windows. Make guarding a
  switch, and turn it off for debug runs and glitch-power runs.

This is a side benefit, not the reason to build the analysis.

## 7. Open questions

- **Windows that aren't one cycle wide:** burst protocols, credits, and
  fixed-latency responses. These need temporal predicates (a delayed `req`, a
  beat counter). Can the kit express them in Zuspec without a general
  temporal logic?
- **Partial gating.** Some fields of a bus are gated and others are not
  (e.g. a sideband sampled every cycle by design). The kit must be able to
  mark a field as "always sampled" so it isn't reported.
- **Deep sequential paths.** Payload captured into a FIFO and read later is
  gated at capture. After capture, the FIFO's contents are state, not
  payload. The analysis should stop at the first gated register and not try
  to follow the data through the FIFO.
- **Is C1 precise enough on real RTL?** Enables built from FSM state may
  imply `fire` only under a state invariant. That case needs C3, or a
  user-supplied invariant.
- **Prior art to check:** ODC-based clock gating, latency-insensitive and
  elastic design (Carloni; Cortadella), Bluespec rule extraction, data
  independence (Wolper), and X-injection checking.

## 8. Next steps

1. P1: add the sample predicate (and the "always sampled" mark) to the
   ready/valid reference kit's role definitions.
2. P2: write the window pass over Zuspec IR. Test it on the example above and
   on `rr_merge`.
3. P3: C1 report, then C2 scrambler in the Verilator in-situ harness, then
   the C3 sby miter.
4. P4: rule extraction on `acc`, checked against the original under E1.
