# Automated lifting grounded in existing DV

Draft, 2026-11-15.

**What this note is.** It proposes an automated process that turns existing
RTL into a higher-abstraction fw-hdl description. The process uses the
block's existing verification environment (DV) as its oracle, and produces a
fast software model from the same source.

It builds on:
- `ip-library-focus.md` §0 ("lift, prove, model");
- `research/riscv-ip-inventory.md` (the block inventory);
- `research/ip-market.md` (evidence of model drift).

It is written to be read on its own by an organization considering an
internal pilot.

Confidence tags for claims about other tools:
- **[P]** read from a primary source;
- **[U]** unverified, to be checked.

## 1. The proposal in one paragraph

Most SoC teams own a portfolio of IP with mature UVM environments, and are
under pressure to deliver fast software platforms (QEMU or Renode machines,
virtual prototypes). Today the platform models are written by a separate
team and drift from the RTL. Automated lifting reads a block's RTL *and its
DV*. It proposes a higher-level description that keeps the block's function
separate from its timing, and accepts the result only when three checks
pass:
- formal equivalence where the cycle behaviour is kept;
- the existing DV regression, with coverage parity;
- operation-level equivalence between the fast model and the RTL, under DV
  traffic.

The checks run **in situ**. fw-hdl wraps the original RTL, places the lifted
design or model beside it with operation checkers, and emits the whole thing
as RTL in the original module's footprint. Every existing test, at every
level, becomes an equivalence test with no change to any testbench (§5.5).

The output is:
- a fast model that is register- and interrupt-accurate;
- optionally, a lowered RTL;
- an equivalence record that can be re-run on every RTL release, so drift is
  caught rather than discovered.

## 1a. Why fw-hdl, and what the pilot is really for

**Fast models are the lead payoff. Converting the design process is the
real goal.** A team adopts lifting because it gets a platform model it
can't otherwise afford. The lasting result is a design team that has seen
its own IP expressed at a higher level, proven equivalent and lowered back
to good RTL. That team's next block starts in fw-hdl.

fw-hdl is in the picture for four reasons, not one:

1. **Protocol kits.** `fw-proto-<X>` provides, for each interface:
   - the operation definition;
   - the ordering rules;
   - the transactor;
   - the default equivalence relation.

   Operation-level equivalence (§5) and the harness's replay (§5.5) are
   defined once per protocol, not once per block.
2. **Automation.** The assembly framework builds the in-situ harness
   (§5.5), and the factory selects modes. Lifting stops being a
   per-testbench project.
3. **A proof point for the design path.** A lifted description can be
   lowered to RTL, and that lowering is a free experiment in design
   quality.
   - Show that the lift lowers to **synthesizable, reasonable RTL**: QoR
     close to the original, and readable.
   - Show that it supports **retiming and re-architecture**: a different
     pipeline depth, a wider or narrower datapath, a different FIFO
     arrangement. Each is selected by configuration, checked by
     operation-level equivalence, and measured.

   For the design team this is a **freebie**. A microarchitecture
   exploration of an existing, working block is something no team would
   ever prioritize, because it means a rewrite. Here it comes as a side
   effect of lifting for the model.
4. **A research vehicle.** If lowering *doesn't* produce reasonable RTL,
   the lifted block, the original and the harness form a controlled setting
   to find out why. The cause might be:
   - a missing construct in the RTL subset;
   - a weakness in the Zuspec IR lowering;
   - a timing structure the function/timing split can't express.

   Every failure is a concrete, reproducible case against real IP, not a
   benchmark chosen to flatter the tool. That is the evidence the core
   rewrites (P2) were meant to produce, now generated as a by-product.

**What the pilot reports, in priority order:**
1. **Fast model:** completeness, speed, effort saved. This is what sells
   the next pilot.
2. **Lowered RTL:** QoR against the original (area, Fmax, on a named FPGA
   and with yosys), readability, and SEC or operation equivalence.
3. **Microarchitecture variants:** at least one retimed or re-architected
   variant per block where it makes sense, each with its equivalence result
   and QoR.
4. **Failures and causes:** every block or construct where lifting or
   lowering fell short, and why. This feeds the fw-hdl and Zuspec roadmap.

## 2. Why ground the lift in DV

A mature UVM environment already contains most of what lifting needs.

| DV artifact | What lifting uses it for |
|---|---|
| Register model (RAL), or the hjson/SystemRDL/IP-XACT it came from | The register layer, imported directly. Never lifted by hand or by an LLM |
| Scoreboard reference model / predictor | A hand-written functional model of the block: the nearest existing thing to the fast model. It is the main source for separating function from timing |
| Interface agents and monitors | Extract the operation stream on each interface (§5) |
| Sequences and tests | Stimulus for the operation-level checks, run against the original RTL, the lowered lift and the fast model |
| Coverage model | The acceptance bar. The lifted design must reach the same coverage under the same tests |
| Assertions | Carried over as properties on the lifted design's method interfaces |

Two consequences:
- **The DV is what makes the work automatable.** It provides an oracle that
  doesn't depend on trusting the lifter. Without DV, a lift can be checked
  only by formal equivalence, and that is lost as soon as the lift changes
  timing.
- **The automation rate will follow DV maturity.** A block with a complete
  predictor and good coverage lifts well. A block with a thin smoke test
  doesn't. That is a useful filter for choosing pilots.

## 3. The pipeline

```
  RTL + DV (RAL, scoreboard, agents, tests, coverage)
        |
   1. ingest ---- register descriptions -> register classes
        |         interfaces -> fw-proto kits (operation semantics)
        |         predictor -> candidate function model
        v
   2. propose --- rule-based recognizers + LLM-assisted proposer
        |         output: fw-hdl description, function | timing split
        v
   3. lower ----- fw-hdl -> RTL (SV), and -> C fast model
        v
   4. check ----- A. SEC (where state-matchable)
        |         B. DV regression + coverage parity on the lowered RTL
        |         C. operation-level equivalence: model vs original RTL
        |            (and lowered RTL), under DV traffic and formal (§5),
        |            run in situ: shadow harness in the original footprint
        v
   accept ------- or return counterexamples to step 2 and iterate
        v
   5. emit ------ fast model (Renode/QEMU device), lifted RTL (optional),
                  equivalence record re-run in CI on each RTL release
```

### Ingest

- **Registers** come from the generator inputs when they exist (hjson,
  SystemRDL, IP-XACT). Otherwise they come from the RAL model. In OpenTitan
  blocks, generated register code is often most of the line count: about
  2,500 of rv_plic's 2,700 lines in Cheshire's configuration.
- **Interfaces** are matched to fw-proto kits: TL-UL, APB, regbus, AXI,
  interrupts, and so on. A kit supplies the transactor and the operation
  semantics that equivalence is defined over (§5.3).
- **The predictor** is read for its decomposition: what each operation does
  to state, and which outputs it produces.

### Propose

There are three proposers, in order of trust:
1. **Rule-based recognizers.** These handle:
   - register files;
   - FIFOs and counters;
   - valid/ready handshakes;
   - FSMs with explicit state encoding;
   - known library cells (synchronizers, arbiters).

   They are mechanical and their output is predictable.
2. **An LLM-assisted proposer** for control logic the rules don't cover. It
   is given the RTL, the predictor and the kit APIs. It is safe *only*
   because nothing it proposes is accepted without the checks.
3. **Human-guided.** An engineer writes or edits the lift. The same checks
   apply.

Each proposal declares a **target level**:

| Level | What the lift keeps | Primary check |
|---|---|---|
| L1 | The original's cycle behaviour; registers and operations made explicit | A. SEC |
| L2 | The original's operations, but not its timing (a different microarchitecture, or a transaction-level model) | C. operation-level equivalence |
| Model | Function only (the fast model, at every level) | C, model against RTL |

The user's point that lifts need not be cycle-exact makes C the central
technical problem. It gets its own section.

## 4. The three checks

| Check | Proves | Doesn't prove | Tools |
|---|---|---|---|
| **A. SEC** | Lowered L1 lift ≡ original, cycle for cycle | Anything about the model; L2 lifts | Open: yosys `eqy`, SymbiYosys. Commercial: Jasper SEC, VC Formal SEQ, Questa SLEC [U for current product names] |
| **B. DV regression with coverage parity** | The lowered RTL passes the original's tests and reaches the same coverage | Behaviour outside the tests | The existing simulator flow |
| **C. Operation-level equivalence** | Model and RTL (or L2 and original) perform the same operations with the same effects, within declared timing freedom | Timing beyond that freedom (by design) | To be built (§5); reuses DV agents and fw-proto kits |

The checks are complementary:
- A is complete but rigid.
- B is flexible but bounded by the tests.
- C is what makes a non-cycle-exact lift, and the model itself, checkable at
  all.

## 5. Operation-level equivalence

### 5.1 The problem

A lift at L2, or any fast model, differs from the original in timing:
- it accepts a request a cycle earlier;
- it raises an interrupt three cycles later;
- it completes a burst in one step instead of sixteen;
- a model has no cycles at all.

Cycle-level comparison then fails on designs that are correct for every
purpose that matters. We need an equivalence that compares **what each
design did**, not **when it did it**, while staying strict about the timing
that software or a neighbouring block can observe.

### 5.2 Operations and observables

- An **operation** is one complete exchange at an interface, together with
  its effect: a register read or write, a bus burst, a DMA descriptor's
  execution, an interrupt raised or cleared, a byte sent on a serial line.
  In fw-hdl these are method calls on interface ports, so the operation
  boundaries are already explicit in the lifted design. In the original RTL
  they are recovered by the DV agents' monitors, or by the observability
  kit's bind-on monitors (`wedge-assessment.md` §4b): the same monitors serve
  both purposes.
- An **observable** is what the environment can see of an operation:
  - the data returned;
  - the order relative to other operations;
  - the time, if the environment can see time.

  Equivalence is defined over observables, so the first job is to declare,
  for each interface, which of these are observable.

### 5.3 A ladder of equivalence relations

Each interface declares the strictest relation it needs. The relations come
from the protocol and the platform's needs, not from the design.

| Relation | Same | Free to differ | Typical use |
|---|---|---|---|
| E0 cycle-exact | everything, every cycle | nothing | L1 lifts (SEC) |
| E1 latency-tolerant, in order | the operation sequence and data on each interface | when each operation happens (with optional latency bounds) | valid/ready streams, register buses |
| E2 per-interface order, free interleaving | the sequence on each interface | the interleaving *across* interfaces, within declared causal constraints | interrupt vs register read; DMA writes vs status |
| E3 protocol reordering | the operation multiset, within the protocol's ordering rules | order where the protocol allows it (e.g. AXI responses with different IDs) | AXI masters and slaves, multi-queue engines |
| E4 effect-level | final architectural state (memory, registers) at defined sync points | intermediate operations | DMA results, accelerators, the fast model at a software sync point |

Timing-dependent function (timers, baud rates, timeouts) is handled by a
**time map**. The model keeps virtual time, and equivalence compares
operations against time under that map, with a declared tolerance. A timer
interrupt must fire at the programmed count in time units, not in a
particular clock cycle.

**Causal constraints are what keep E2 and E3 honest.** "Free interleaving"
must not allow orders that software could tell apart and that the original
could never produce. For example, the status register must not read
"complete" before the completion interrupt's cause is visible. The
constraints say which cross-interface orders are guaranteed. They come from
the protocol kit (ordering rules) and from the block's operation contracts
(§5.5).

**The direction of the relation matters:**
- **For a lifted L2 RTL that replaces the original,** use equivalence: each
  behaves as the other could, within the declared freedom.
- **For a fast model,** use refinement. Every behaviour of the model must be
  one the original RTL *could* exhibit under some legal timing of its
  environment. The model picks one; it need not cover them all. This is what
  a software platform needs: whatever the model does, real hardware could
  have done it too.
- **For verification soundness (using the model to predict the RTL),** the
  direction reverses: the model must cover all of the RTL's legal behaviours.
  A DV predictor needs this, and a platform model doesn't. Keep the two uses
  apart.

### 5.4 Techniques

1. **Simulation: transaction comparison under shared stimulus,** delivered
   through the in-situ harness of §5.5, so the DV environment is unchanged.
   - Run the original and the lift (or the model) under the same DV
     sequences.
   - Extract the operation streams with monitors.
   - Compare them with a matcher configured by the relation:
     - in-order queues for E1;
     - per-interface queues plus causal checks for E2;
     - ID-keyed matching for E3;
     - state comparison at sync points for E4.

   Stimulus must respond to timing rather than fix it (drivers wait on
   ready/valid instead of counting cycles), or the timing difference
   appears as a stimulus difference. Well-built UVM agents mostly already
   work this way. This is the first technique to build, because it reuses
   everything and finds most problems.
2. **Lockstep model and RTL comparison.** The fast model runs beside the RTL
   in the same harness (§5.5), fed the same input operations. It is checked operation by
   operation, and resynchronized at sync points. This is cheap, and catches
   model bugs early.
3. **Formal: a transaction miter.**
   - Both designs are driven through the same fw-proto transactors.
   - Their output operations go into queues, which are compared under the
     relation.
   - Bounded proofs come first. Unbounded proofs need invariants relating the
     two designs' states.

   This is the formal analogue of technique 1, and it is how commercial
   transaction-level and C-to-RTL equivalence tools are understood to work
   [U: check SLEC, C2RTL, DPV/Hector].
4. **Spec-centric: both refine one operation spec.** Rather than comparing
   two designs pairwise, prove that each refines the **operation spec**:
   - the lifted function;
   - pre- and post-conditions on each method;
   - ordering and causal constraints.

   Equivalence then follows through the spec. This scales better than
   pairwise miters, because each proof is local to one design. It also
   leaves behind reusable assets: the spec's properties are protocol and
   block checks written the new SVA way, which feeds the observability kit
   directly. Classical techniques apply here:
   - refinement maps;
   - stuttering simulation;
   - Burch–Dill flushing for pipelined blocks.

**Recommended order:**
- Techniques 1 and 2 first, through the harness: they are cheap, reuse the
  DV unchanged, and catch most errors.
- Technique 4 for the blocks where a proof matters.
- Technique 3 where a direct pairwise proof is wanted.

### 5.5 The in-situ harness: side by side, in the original footprint

**The problem with changing the DV environment.** A natural way to compare
a model with the RTL is to edit the testbench: add the model, fan the
stimulus to it, and compare in the scoreboard. It works, but has to be
redone for every environment (block DV, subsystem, SoC, software-driven
tests). It also gets less reliable as the environment gets further from the
block. Earlier experiments along these lines (the user's own) ran into
exactly this.

**The fw-hdl approach: change the design, not the testbench.** fw-hdl is an
assembly framework, and the same machinery that builds an SoC from blocks
builds a harness around one block:

```
  original footprint (same module name, ports, parameters)
  +-------------------------------------------------------------+
  |  input ops --+--> [ primary: original RTL (wrapped) ] --+--> outputs
  |  (monitors)  |                                         |
  |              +--> [ shadow: lifted design / model ] -- |--+
  |                     (driven by replay transactors)     |  |
  |                                                        v  v
  |                         [ operation checkers: matcher (E0-E4),
  |                           causal constraints, time map ]
  |                                  |
  |                         mismatch reports, operation trace
  +-------------------------------------------------------------+
```

- **The wrapper keeps the original footprint:** the same module name, ports
  and parameters. It drops into every environment that instantiated the
  original, with no DV change.
- **The primary drives the outputs.** The environment sees exactly the
  behaviour it saw before, so every existing test still means what it meant.
- **The shadow** (the lowered lift, or the fast model through DPI) receives
  the same input operations, and its outputs go only to the checkers.
- **Checkers compare operations** under the declared relation (§5.3). They
  use the protocol kits' monitors, the same ones the observability kit uses,
  so a mismatch is reported as an operation ("write 0x40 to CTRL completed
  on primary, missing on shadow"), not as a waveform difference.
- **The mode is set by the factory at elaboration:**

  | Mode | Primary | Shadow | Use |
  |---|---|---|---|
  | `orig` | original | — | baseline |
  | `shadow` | original | lift or model | check the lift without risk |
  | `swap` | lift | original | prove the lift carries the environment |
  | `lift` | lift | — | the lifted design alone |
  | `model` | model | — | fast model in an RTL simulation (hybrid runs) |

  Running `shadow` and then `swap` over the same regression is a strong,
  cheap result. In `shadow`, the lift sees every operation the real
  environment produced. In `swap`, the environment reacts to the lift's
  timing and still passes.

**Feeding a shadow that is not cycle-exact.** With an L1 lift, inputs fan
out wire for wire. With an L2 lift or a model, the shadow runs at its own
pace, so the harness feeds it at the operation level:
- **Input operations** observed on the primary's interfaces are queued and
  replayed to the shadow by fw-proto transactors, at the shadow's pace.
- **Responses the environment gave the primary** (read data returned to a
  DMA master, for example) are recorded. They are replayed when the shadow
  issues the matching request. A shadow request with no matching primary
  request is itself a mismatch, unless the relation allows it (E4 with a
  mirrored memory model).
- **Back-pressure** the environment applied to the primary is not replayed.
  The shadow's own timing is what is being freed.

This is where the protocol kits earn their place. Replay needs a transactor
and an operation definition for every interface, and `fw-proto-<X>` already
owns both.

**Where it runs.** The wrapper is RTL produced by fw-hdl, so it runs in any
simulator, including Verilator.
- If the shadow is RTL (an L1 or L2 lift) and the checkers are
  synthesizable, the harness also runs on an emulator or FPGA. That gives
  at-speed equivalence checking under real software and real traffic, which
  connects to the testbed story.
- The C model runs only in simulation, through DPI.

**What it gives the pilot:**
- Every existing test at every level becomes an equivalence test, with no
  change to any testbench. That includes SoC-level and software-driven
  tests, which no block-level comparison reaches.
- The organization's environments stay untouched. Only the RTL file list
  changes, and the change is undone by switching back to `orig`.
- Mismatches arrive with an operation-level trace, which is the debug view
  the observability kit sells.

**Mechanics to settle:**
- **Same module name.** The wrapper takes the original's name and the
  original is compiled under a renamed copy. Ways to do this: a generated
  renamed copy, SV `config` and library mapping, or simulator-specific
  options. The generated copy is the portable choice.
- **Generating the wrapper.** Derive it from the original's port list plus
  an interface-to-kit mapping, inferred where possible and declared
  otherwise. Unmapped ports fan out as plain wires and are compared cycle
  by cycle.
- **Hierarchical references.** Testbenches that probe inside the original
  (backdoor register access, `bind`s, internal signal checks) must still
  find it. Keep the original's instance path stable inside the wrapper, or
  emit an adjustment for the testbench's hierarchy references.
- **Reset and clock** pass straight through. Multi-clock blocks are out of
  scope for the first pilot (§11).

### 5.6 Where fw-hdl helps, and what must be built

**What fw-hdl provides:**
- **The assembly framework that makes the process tractable.** Beyond a
  vocabulary and method for lifting, fw-hdl builds the in-situ harness of
  §5.5. It wraps the original RTL, places the shadow beside it, adds the
  checkers, selects the mode by factory, and emits the result as RTL in the
  original's footprint. Without that framework, each comparison means
  editing a testbench.
- **Operations are explicit** in a fw-hdl design: method calls on ports. The
  lifted side needs no reverse engineering.
- **Operation semantics belong in the protocol kit.** `fw-proto-<X>` already
  owns the protocol spec and transactor. It should also own:
  - the operation definition (fields, start and end events);
  - the ordering rules;
  - the default equivalence relation.

  Equivalence is then defined once per protocol, not once per block.
- **Method-level properties** (the "properties on method interfaces" planned
  for fw-hdl-dv) are the operation contracts that technique 4 needs.

**What must be built:**
- an operation matcher library, configured by relation, for simulation;
- operation monitors for the original RTL, shared with the observability
  kit;
- a time-map facility for timing-dependent function;
- a way to state causal constraints per block;
- a transaction-miter generator for formal;
- refinement-proof scaffolding for technique 4.

### 5.7 Open problems

- **Choosing the relation is a design decision.** Making it too loose hides
  real bugs; making it too strict rejects good lifts. The relation should be
  reviewed like an interface spec, and defaults should come from the kit.
- **Timing that software does depend on.** Busy-wait loops, polling with
  timeouts, and races in drivers can make a timing difference observable.
  The model should expose its timing choices (a deterministic schedule, a
  seed) so such issues reproduce.
- **Blocks whose function *is* timing** (PWM, pattern generators, serial
  PHYs) need the time map to be exact. Treat them as E0/E1 with the time map,
  not as E4.
- **Unbounded formal proofs between designs with different state** need
  invariants. Generating them automatically from the lift (the lifter knows
  how its state relates to the original's) is an opportunity, but unproven.

## 6. What the fast model is

- **What it is:**
  - register- and interrupt-accurate;
  - functionally complete;
  - untimed or loosely timed, with virtual time for timing-dependent
    function;
  - lowered to C and hosted as a Renode peripheral (first) or a QEMU device;
  - checked against the original RTL by refinement (§5.3).
- **What it is not:** cycle-accurate. Cycle-accurate needs are served by the
  RTL itself, in Verilator or on FPGA.
- **The bar:** Linux boots at QEMU-class speed, at least 100x Verilator on
  the original RTL. Otherwise the model offers nothing that compiled RTL
  doesn't.

## 7. Metrics for a pilot

| Metric | What it shows |
|---|---|
| Fraction of lines lifted automatically; engineer-hours per block | Whether the automation is real |
| SEC closure (L1); operation-equivalence pass rate and relation used (L2) | Proof strength |
| DV regression pass rate and coverage parity on the lowered RTL | That the original DV accepts the lift |
| Model speed against Verilator on the original; Linux boot time | The value of the fast model |
| Model completeness against the existing hand-written model, if there is one | Fidelity |
| Engineer-hours against writing the model by hand | Return on investment |
| Drift detections when re-run on later RTL releases | Value over time |
| QoR of the lowered lift against the original (area, Fmax; named FPGA and yosys) | Whether the design path is credible |
| Retimed or re-architected variants produced, each with its equivalence result and QoR | The design-exploration freebie (§1a) |
| Lowering failures, with their causes | Research input to the fw-hdl and Zuspec roadmap |
| Readability of the lifted description (lines, reviewer survey) | Maintainability |

## 8. Public pilot: OpenTitan

OpenTitan is the right public stand-in:
- its DV is industrial-grade UVM, with a `dv/env` for every block [P];
- its registers come from reggen hjson [P];
- lowRISC's hand-written QEMU models grade themselves from "near-complete" to
  "dummy", which gives a baseline to beat [P];
- its blocks are in a taped-out, Linux-capable SoC (Cheshire) through PULP
  ports [P];
- its scoreboards are understood to contain reference predictors [U: check
  each block's `*_scoreboard.sv`].

Pin the OpenTitan revision. The QEMU fork targets `earlgrey_1.0.0`, and HEAD
has moved on [P].

| Order | Block | Why | Target |
|---|---|---|---|
| 1 | rv_timer (797 lines, 638 of them registers) | Smallest; proves the path from reggen to register classes; timing-dependent function exercises the time map | L1 + model |
| 2 | uart | A model to compare against (the fork's "near-complete" lacks RX timeout and break); timing via the baud rate | L1 + model; an L2 variant to exercise E1 |
| 3 | gpio | Small logic, input filters | L1 + model |
| 4 | spi_host | Command FIFOs; used by Cheshire's Linux for the SD card | L1 + model, then L2 |
| 5 | rv_plic | Mostly generated registers; claim/complete side effects test E2 causal constraints | L1 + model |

**Exit for the public pilot:**
- The UART and timer lift with at least 80% automation.
- SEC closes at L1.
- OpenTitan DV passes with coverage parity.
- The generated Renode models boot a Zephyr or Linux image.
- One L2 lift passes operation-level equivalence (E1) where cycle comparison
  fails.

That last item is the demonstration that §5 works.

## 9. Internal pilot proposal

**Selecting blocks.** Pick 2–3 blocks with:
- mature UVM: a predictor, coverage closure, and RAL from a generator;
- software visibility: a driver exists or is planned;
- a platform-model need: the platform team models them by hand today, or
  wants to;
- one clock domain and no analog;
- 1–10k lines.

Include one block where an L2 lift is attractive (a DMA-like engine). That
tests operation-level equivalence on the organization's own IP.

**Phases:**
1. **Ingest and baseline.** Import the registers and kits, and run the
   existing DV against the original RTL. Measure the current model effort,
   if a model exists.
2. **L1 lift and SEC.** Lift, lower, prove, and run DV parity. Then run the
   harness in `shadow` and `swap` modes in every environment that
   instantiates the block, with no testbench changes.
3. **Model generation.** Produce the fast model, run it as the shadow in the
   in-situ harness (§5.5) across the existing regressions, including
   subsystem and SoC-level tests, and boot the platform software.
4. **L2 lift** for the DMA-like block, using operation-level equivalence.
5. **Drift run.** Re-run against the next internal RTL release.

**Deliverables:**
- the metrics in §7;
- lifted descriptions;
- fast models;
- equivalence records;
- a report of where automation failed and why.

**Constraints:**
- **Confidentiality.** Internal RTL and DV can't go to an external LLM
  service. The proposer must run on an on-premises model, or with rule-based
  recognizers only. The pilot should report automation rates *with and
  without* the LLM proposer, so the value of each is clear.
- **Open versus internal.** The method, tools, matcher library and protocol
  kits can be open, while the lifted IP and its models stay internal. Agree
  the boundary before any code is shared.
- **Tooling.** The organization's commercial SEC tool can stand in for, or
  supplement, the open flow. Results should be reproducible on at least one.

## 10. Dependencies on fw-hdl

These are what has to exist before an honest pilot:

| Dependency | State on 2026-11-15 |
|---|---|
| A function/timing separation in the fw-hdl description | Concept (`ip-library-focus.md` §0); needs design |
| C lowering of the class model (from Zuspec IR) | Not implemented: `python/fw/hdl/emit/` has SV and register-block emitters only |
| Register-class import from hjson/SystemRDL | `regblock.py` emitter exists; check import paths |
| fw-proto kits with operation semantics | `fw-proto-axi` and others exist; operation definitions and ordering rules need adding |
| Operation monitors and matcher library | Not started; shared with the observability kit |
| In-situ harness generator (wrapper in the original footprint, replay transactors, modes) | Not started; uses the existing factory and wrapping of legacy RTL |
| SEC flow (eqy/SBY) in dfm | Not started |
| Renode peripheral wrapper for generated C models | Not started |

## 11. Risks

1. **Reference models are often incomplete or tied to timing.** The
   automation rate will vary widely. Report it per block, and don't promise
   a portfolio-wide number from a pilot.
2. **SEC scalability** on larger blocks and on L1 lifts that restructure
   state. Fall back to operation-level equivalence and say so.
3. **Relation choice hides bugs** (§5.7). Review relations like specs.
4. **LLM proposer quality and confidentiality.** Rely on rules first; treat
   the LLM as an accelerator, not a dependency.
5. **Readability of lifted descriptions.** A lift that passes every check but
   that no one can maintain will be rejected. Include a review step and
   readability metrics.
6. **The C view and the function/timing split are not built.** They are on
   the critical path for the model half of the value. SEC plus DV parity can
   be shown without them, but that is only half the story.
7. **Scope creep** into multi-clock, analog or large blocks. Hold the
   selection criteria.

## 12. Related work to check

- **Commercial transaction-level and C-to-RTL equivalence:** Siemens Catapult
  SLEC, Cadence Jasper C2RTL, Synopsys VC Formal DPV (formerly Hector). How
  do they define transactions and handle latency? [U]
- **Academic:**
  - refinement mapping and stuttering bisimulation;
  - Burch–Dill pipeline verification;
  - latency-insensitive design equivalence;
  - Kami and Bluespec-style refinement proofs;
  - recent work on LLM-based RTL translation and lifting, checked with
    equivalence. [U]
- **The OpenTitan precedent:** the old apb_uart's Formality VHDL-to-SV
  equivalence script (`util/equiv_check.fm.tcl`) is a small instance of the
  L1 flow [P].
- **lowRISC's QEMU tooling** (`autoreg.py`, `checkregs.py`, `verilate.py`):
  what it automates today, and what a lifted model would replace [P].
