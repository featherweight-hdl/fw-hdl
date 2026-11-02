# Low impact, high value: what SV + fw-hdl adds over adopting XLS alone

*2026-11-01. The commercial story, narrowed: **SystemVerilog as a low-impact entry point to
XLS.** Every item answers the same question: "if my team adopted XLS on its own, what
would we *not* get, and what would it cost us?" Detailed designs:*
- *[value-adds.md](value-adds.md): catalog*
- *[shell-generation.md](shell-generation.md)*
- *[timing-shell.md](timing-shell.md)*

*The XLS baseline is as checked in [xls-vs-fw-hdl.md](xls-vs-fw-hdl.md).*

## 1. The baseline: a team that adopts XLS alone

To be fair to XLS, a team adopting it gets a lot:
- an excellent optimizer and scheduler
- ready/valid codegen
- DSLX tests in its interpreter and JIT
- quickcheck proofs and IR equivalence
- SVA asserts and covers, and `$display` traces, in the generated RTL
- a module signature and a schedule as text protos

That team also takes on the following work, every time:
1. **Learn DSLX** and re-express its existing SV types, constants and helper functions in it.
2. **Wait for RTL** before the block can enter the SoC simulation. Otherwise it writes and
   maintains a DPI wrapper over XLS's JIT, which is easy for functions and hard for procs,
   and is untimed either way.
3. **Hand-wire** each generated module into its RTL: flat bit-vector ports, its own
   ready/valid naming, its own FIFO wrapper contract.
4. **Maintain two test suites:** DSLX tests in XLS-land, and SV tests against the RTL.
5. **Debug generated RTL** with mangled state names (XLS #2042), no source-level coverage
   (#1126, #2139), and proc models whose FIFOs have no depth (#988).
6. **Work out timing by hand:** reading the schedule textproto keyed by IR node names,
   with no timed model.
7. **Build the hand-off:** SDC, file lists and documentation are all on the team.

fw-hdl's value is removing items 1–7 **without changing how the team works**. "Low impact"
means it adds nothing to the team's practice except the XLS binaries.

## 2. The value, item by item

Impact on the user is how much of their practice changes: **none**, **low** (a new file
or command) or **some** (a new habit). Status: ✅ exists · 🟡 partial · 🔴 to build
(S/M/L).

### V1. Your existing SV is the source, including the types you already have
- **XLS alone:** re-express structs, enums, constants and helper functions in DSLX.
  xlsynth's `dslx2sv-types` goes the *other* way (DSLX → SV packages), so DSLX becomes the
  source of truth for types the RTL already owns.
- **With fw-hdl:**
  - The block imports the team's **existing SV packages**: the same `typedef struct
    packed`, the same `localparam`s, the same `function automatic` helpers.
  - A CRC function already in a package can go to XLS **unchanged** (the `examples/xls`
    functions are exactly this).
  - Types have one source of truth, shared by RTL, testbench and the XLS block.
- **Worth:** no translation layer, no type drift between RTL and the HLS block, and code
  review by the people who already own the RTL.
- **Impact:** none. **Status:** ✅ functions and packed structs; 🔴 S to accept `logic`.

### V2. The block is in the SoC simulation on day one
- **XLS alone:** nothing runs in the SV simulator until RTL exists, unless the team builds
  DPI glue.
- **With fw-hdl:** the SV class *is* the model. A generated **shell module** with the final
  pins (shell-generation.md) drops it into the RTL design where the block will live.
  Interface, protocol and integration bugs show up when the block is first written, not
  after synthesis.
- **Worth:** the integration wall moves from the end of the block schedule to the start.
- **Impact:** none: the RTL instantiates a module, as usual. **Status:** 🟡 bind machinery
  ✅; generator 🔴 S–M; ready/valid kit needs to move into `src/std`.

### V3. Timing you can simulate, from XLS's own schedule
- **XLS alone:** a static schedule report. Cycle-accurate execution exists only as the
  block JIT in C++, after scheduling.
- **With fw-hdl:**
  - A **timing shell** around the SV class, back-annotated from the XLS signature and
    schedule: latency, II, per-channel stage, I/O flop kinds.
  - It has the same pins as the RTL, runs in the SV simulator, and is several times faster
    than RTL.
  - Function pipelines are exact. Procs get a stage-level flow-control model.
- **Worth:** architects get throughput, back-pressure and FIFO-occupancy numbers in the SoC
  sim before RTL, and the numbers come from the tool that will build the RTL.
- **Impact:** none: a different file list. **Status:** 🟡 latency-only StageTLM ✅; exact
  function shell 🔴 S; proc shell 🔴 M.

### V4. Proof that the fast model matches the RTL, every build
- **XLS alone:** not applicable, since there is no fast model.
- **With fw-hdl:**
  - Same pins, so a generated **lockstep check** runs the timing shell and the XLS RTL side
    by side under random valid/ready throttling and compares every pin every cycle.
  - It is also a regression guard when XLS is upgraded.
- **Worth:** "cycle-accurate" becomes a test result, not a claim, so architects can trust
  the pre-RTL numbers.
- **Impact:** none: CI runs it. **Status:** 🔴 S once the shells exist.

### V5. One test suite, every level
- **XLS alone:** DSLX tests and RTL tests are separate artifacts in separate languages.
- **With fw-hdl:** one unedited SV test runs against:
  - the class model
  - the timing shell
  - XLS RTL
  - gates
  
  It works with SVUnit today and with the team's own UVM env through the shell's pins.
- **Worth:** no duplicated test effort. A failure at gates reproduces at model level in
  milliseconds.
- **Impact:** none. **Status:** ✅ SVUnit, 11 XLS examples; UVM via shell 🔴 (follows V2).

### V6. Multi-process designs that are honest before RTL
- **XLS alone:** the proc runtime ignores FIFO depth (#988), so a deadlock or throughput
  collapse from an undersized FIFO appears first in RTL.
- **With fw-hdl:**
  - Channels block at their declared depth in the SV model, so the deadlock happens in the
    model with an SV call stack.
  - With timing shells, a **FIFO sizing sweep** reports the minimum depth that avoids
    deadlock and the depth needed for full throughput.
- **Worth:** the most expensive class of late HLS bug, found at the cheapest point.
- **Impact:** none. **Status:** ✅ depth-accurate model; sizing sweep 🔴 M.

### V7. Debug in the designer's own terms
- **XLS alone:** generated RTL with mangled state names; traces and channel views only in
  XLS's own tools.
- **With fw-hdl:**
  - **SV-line annotations** in the generated RTL.
  - **Waveform alias scripts** that map XLS registers back to SV variables and stages.
  - **Transaction recording** on every channel, the same at every level.
  - A **first-divergence finder** that compares per-channel transaction streams between any
    two runs and reports the first mismatch. Exact for blocking designs, because results
    don't depend on timing.
  - **Replay:** capture a block's traffic in the full-chip sim and reproduce the failure
    in the SV model in milliseconds.
- **Worth:** this is where HLS teams lose the most time. It turns "bisect generated RTL"
  into "jump to the transaction and SV line."
- **Impact:** none to low (a plusarg, a script). **Status:** 🟡 annotation wired, verify;
  the rest 🔴 S–M.

### V8. Verification collateral generated, with the class as the reference model
- **XLS alone:** asserts and covers carried into RTL, and nothing else for the testbench.
- **With fw-hdl:** from the pin contract:
  - **ready/valid protocol SVA** bound on every channel
  - **typed UVM agents** (or SVUnit APIs, which exist today)
  - **functional coverage** of struct fields and branches
  - a scoreboard that predicts from **the SV class itself**
- **Worth:** DV starts with a working environment and a free reference model. It also
  closes XLS's coverage gap.
- **Impact:** none: generated files the DV team may adopt. **Status:** 🟡 SVUnit API ✅;
  SVA 🔴 S; UVM and coverage 🔴 M.

### V9. See the hardware in your source
- **XLS alone:** schedule and delays keyed by IR node names; nothing maps back to source for
  the user.
- **With fw-hdl:**
  - A **schedule overlay** on the SV class: each line's stage and delay, with the critical
    path highlighted.
  - **Width and dead-logic feedback:** "`ttl` never reaches an output"; "`count` needs 7 of
    its 32 bits".
  - **Budget checks:** `latency ≤ 4, II = 1` written next to the class and enforced every
    build.
- **Worth:** the designer keeps micro-architectural judgment ("why 5 stages?") without
  hand-pipelining. Budgets stop silent regressions.
- **Impact:** low (an optional annotation). **Status:** 🔴 S–M. *XLS doesn't offer this
  even for DSLX.*

### V10. HLS changes you can review, XLS upgrades you can trust
- **XLS alone:** a one-line source change can reshuffle the RTL invisibly, and moving to a
  new XLS release is a leap of faith.
- **With fw-hdl:**
  - A **schedule and QoR diff on every PR** ("+1 stage, +3% area, critical path now
    line 84").
  - An **XLS-upgrade gate:** a corpus with QoR thresholds plus the lockstep check.
- **Worth:** removes the two main *organizational* objections to HLS: review and
  tool-version risk.
- **Impact:** none: CI. **Status:** 🔴 S.

### V11. RTL that drops into your back end
- **XLS alone:** RTL plus a signature proto. Reset style, constraints and documentation are
  the team's job.
- **With fw-hdl:**
  - the house reset and flop profile
  - a **struct-typed RTL wrapper** with the same pins as the model
  - an **SDC stub** from the scheduled clock and I/O delays
  - file lists
  - a **block datasheet** (ports, latency, II, area estimate)
  - IP-XACT
- **Worth:** XLS output becomes a deliverable the physical-design and integration teams
  accept without hand edits.
- **Impact:** none. **Status:** 🟡 reset options partly wired; the rest 🔴 S.

## 3. The value ladder: what to lead with

| Rung | Message | Items | Effort to show |
|---|---|---|---|
| 1. "Nothing to learn" | Your SV, your types, your simulator. Same XLS QoR | V1, V5 | **Exists today** |
| 2. "It's just a module" | In your SoC sim on day one, with the final pins | V2, V11 | S–M (shell generator) |
| 3. "Real timing, early" | A timed model from XLS's schedule, proven against the RTL | V3, V4 | S for functions |
| 4. "Debug and verify faster" | Divergence finder, replay, generated SVA, UVM, coverage | V7, V8 | S–M each |
| 5. "Engineering you can manage" | Source overlay, budgets, PR diffs, upgrade gate | V9, V10 | S each |
| 6. "Multi-process without fear" | Depth-accurate networks, FIFO sizing | V6 | M |

**Recommended next build**, which gets rungs 1–3 demonstrable on a real function:
1. The ready/valid kit in `src/std`, parameterized on `type T`.
2. The shell generator: struct-typed model shell + XLS RTL wrapper + pin-parity check.
3. The exact function timing shell plus the lockstep check.
4. The block datasheet.

V7's divergence finder is the cheapest high-impact follow-on.

## 4. One line per audience

- **Designer:** keep your SV and your types; XLS pipelines it; you see the hardware in your
  own source.
- **DV engineer:** the block is in your environment on day one, with generated checkers and
  a free reference model, and one test at every level.
- **Architect:** timing numbers in the SoC sim before RTL, from XLS's own schedule, proven
  against its RTL.
- **Manager:** no retraining, reviewable changes, controlled tool upgrades, and an adoption
  path that starts with one function.
