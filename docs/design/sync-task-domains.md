# Sync and task domains, and the crossing between them

The plan for separating fw-hdl's two kinds of execution, and for the one
construct that connects them:
- **sync**: `step()` and `comb()`, communicating through signals and
  functions;
- **task**: `run()` and blocking method calls.

It replaces `sync-kernel-two-phase.md` (2026-11-21, removed), which tried to make the
kernel order the two. It amends `core-layer2.md` §5.2 and decision 4. It
was prompted by G4 (`micro-pipelining-feasibility.md` §0.1), and
micro-pipelining D1 waits for it. Pick up from **§0 Status**.

## User benefit

1. **Class models match their RTL cycle for cycle**, at the pins and
   everywhere else. G4 (comb logic after a register reaching a pin one edge
   late) goes away. Pipelined designs, and most datapaths, depend on that.
2. **One bench for classes and RTL.** A bench that samples like RTL gets the
   same answers from both, whatever order the simulator runs processes in.
3. **One timing rule for task code, independent of scheduling order.** What
   a transactor or BFM sees, and when its drives land, follows from the time
   at which it acts, not from which process the simulator happened to run
   first. "Wait for the ack, then send the next request" in the same cycle
   (fwvip-wb's initiator) works by construction.
4. **Transactor cores written once.** In the recommended pattern (§5.1) a
   transactor's protocol timing lives in a sync class. That class lowers to
   the Verilog core, as fwvip-wb's `wb_initiator_xtor_core` is written by
   hand today, and runs as a class in class-only sims. The task side is a
   generic crossing that is written and checked once.
5. **A clean contract for optimized execution.** An optimized subtree
   injected by factory override lives in the sync domain. It implements
   plain RTL timing (§2.3) and never sees task-side scheduling.

## 0. Status

| Step | Status | Notes |
|---|---|---|
| Plan (this doc) | **draft**, 2026-11-21 | Q1, Q3, Q4, Q7, Q8 decided (Q3 revised by Q8); Q2, Q5, Q6 open (§9); clock design in §6.5; derived endpoints in §6.6 |
| X0 Probes | **done** 2026-11-21 | findings in §8.1; probes in `docs/design/probes/sync-domains-x0/`. `rr_merge_pipe`'s class sim passes, cycle-identical to its RTL |
| X1 Semantics written down | **done** 2026-11-21 | spec, conformance and IR (§8.2) |
| X2 Kernel: two-phase edge | **done** 2026-11-21 | `src/` §8.3, rt-sv §8.4. Root suite: 865 passed, 3 skipped, 1 xfailed; the root flow's 35 SV sim tasks pass (`rundir/log/x2-*`) |
| X2a Edge drivers and groups (§6.5) | **done** 2026-11-21 | `src/` (`div` only) §8.3; rt-sv (all derivations) §8.4. `phase` edges start at *j* = 1 (user, 2026-11-21) |
| X3 Crossing ports in the kernel | **done** 2026-11-21 | `src/` and rt-sv §8.5. Root suite 866 passed, 3 skipped, 1 xfailed; 35 SV sim tasks pass (`rundir/log/x3-*`); rt-sv conformance 103/0/13. Follow-up §8.6 (std rv transactors; C5 undo rule): rt-sv pytest 25 passed, root suite and SV tasks unchanged |
| X4 Generic ready/valid crossings (put/get) | **done** 2026-11-21 | re-scoped under §6.6; results §8.7. Root suite 867 passed, 3 skipped, 1 xfailed; 35 SV sim tasks rc=0; rt-sv pytest 26 passed (`rundir/log/x4-*`) |
| X5 Pin bridges | **done** 2026-11-21 | inputs to `cur`, outputs `<=` in both runtimes (§8.3, §8.4); `comb_pins` removed (§8.8; user chose A). Root suite 867 passed, 3 skipped, 1 xfailed; 35 SV sim tasks rc=0; rt-sv pytest 26 passed (`rundir/log/x5-*`) |
| X6 Enforcement and migration | **in progress** 2026-11-21 | §8.9: task blocks, `check_xing` in fe-sv, be-sv rejects task blocks; survey: nothing to migrate. Package suites running |
| X7 Examples, WB walkthrough, docs | not started | `rr_merge_pipe`'s class sim already passes (G4 closed, §8.3); left: the WB initiator, docs |

Nothing is committed by these steps. The user commits.

## 1. The problem

Today a `run()` may read and write sync fields directly. The kernel then has
to decide, at each edge, whether the `run()`s or the `step()`s go first, and
which values each sees. Three mechanisms do that:

- **The lazy commit.** `do_edge()` commits the previous edge's writes at the
  next edge (`fw_sync_kernel.svh:109-131`).
- **`after_tick`.** Every `run()` that ticks yields `#0` so that it resumes
  after the kernel (`fw_sync_kernel.svh:101-107`;
  `fw_clock_xtor_bridge.svh:25`, `fw_clock_period_xtor_bridge.svh:24`).
- **The early-write guard.** A `run()` write that came before the kernel at
  an edge is held back (`fw_sig_holder.svh:157-167`).

Inside the tree these work. At the boundary they don't:

- **G4.** The lazy commit puts register values, and comb logic computed
  from them, in `cur` one edge late. The pin bridge corrects for that only
  for sync fields (`fw_rv_pin.svh:119-133`), so comb logic after a register
  reaches a pin one edge late.
- **The ordering is fragile.** `#0` is one delta. A `run()` that waits with
  a raw `@(posedge)` or `#d` bypasses it.

Fixing G4 in the kernel alone means making the kernel order `run()`s against
an edge it can't see the end of (the replaced plan's §4.2). The root
cause is that two kinds of execution share fields with no defined order. So
the fix is to stop sharing.

## 2. The model

### 2.1 Two domains

| | Sync domain | Task domain |
|---|---|---|
| Code | `step()`, `comb()`, functions they call | `run()`, tasks, blocking method calls |
| Communicates through | signals: struct-port fields, sync and comb | method ports, exports, channels |
| Time | the edges of its clock domain | simulation time; `tick()` and delays |
| Semantics | evaluate, update, settle at each edge (§2.2) | threads, as today |
| Lowered to RTL | yes | no (simulation only; `core-layer2.md` decision 8) |

**The rule:** task code never reads or writes a sync field directly. It
interacts with the sync domain only through a **crossing endpoint**
(§3), seated in one clock domain.

This is the clock-domain-crossing idea applied to two models of execution.
A crossing is the only place where the two meet, and it has a defined
latency. The domains model of `core-domains.md` §6 already makes the
component that owns interfaces in two domains the crossing element; here
the endpoint is that element.

### 2.2 The sync domain: one edge

At each edge of a clock domain, with no task code involved:

1. **Evaluate.** Each `step()` reads the values from before the edge
   (`cur`) and writes next values (`nxt`). Order among `step()`s doesn't
   matter, because none sees another's writes.
2. **Update.** `cur = nxt` for every sync field of the domain.
3. **Settle.** Run the `comb()`s on the new values until none changes.

After the edge, registers and the comb logic computed from them both show
the new values, as in RTL. Between edges, a comb input that changes (a pin,
or a crossing write, §3) settles the domain at once. This is SystemC's
evaluate/update split with settle as the comb delta loop. It needs no
`after_tick` and no early-write guard, and it doesn't depend on SV
scheduling regions.

### 2.3 The override contract

A sync subtree replaced through the factory with an optimized
implementation must, at each edge of its domain:
- read its inputs as they were before the edge;
- compute and commit its next state;
- settle its outputs;

and settle its comb outputs when a comb input changes between edges. A
compiled model, or a Verilated module of the generated RTL, does exactly
this.

## 3. The crossing

### 3.1 What it is

A **crossing endpoint** is an object seated in one clock domain (and its
reset domain), through `set_domain`/`fw_domain`, as any interface is. It has:
- **A sync side:** struct-port fields, which sync logic reads and writes as
  it would any peer's.
- **A task side:** methods that task code calls. They are blocking
  (`put()`, `get()`, `wait_cycles()`) or non-blocking (`sample()`,
  `drive()`, `try_put()`).

Every task-side operation happens **at an edge of the endpoint's clock**,
and has RTL register timing with respect to that edge.

### 3.2 The rules

- **C1 Alignment.** A task-side operation acts at an edge *k* of the
  endpoint's clock. If it's called when the current time isn't the time of
  an edge of that clock, it first waits for the next edge. Entering the
  clock domain from the task domain synchronizes to its clock, as a CDC
  synchronizer does.
- **C2 Sample.** A read at edge *k* returns the value just before *k*: what
  the `step()`s at *k* read. That includes comb values, as they were settled
  before *k*.
- **C3 Drive.** A write at edge *k* is visible to the sync domain just after
  *k*. Comb logic settles on it at once, and the `step()`s sample it at
  *k*+1. That is the timing of a register written at *k*.
- **C4 Order independence.** C2 and C3 hold whether the task runs before or
  after the kernel's evaluate at *k*, and after any zero-time detour. The
  edge is identified by time, not by process order (§6.2).
- **C5 Drives per output per edge** (*decided 2026-11-21*). Per output and
  per edge there is at most one *default*, set by the endpoint's
  implementation, and at most one *explicit drive*, from task code. The
  explicit drive wins. A second explicit drive of the same output at the
  same edge is an error (`FW-E-XING-DRIVE-TWICE`): it would be two values in
  one cycle, for example two `put()`s, which is two beats in one cycle.
  *Refined 2026-11-21 (user, §8.6):* the one exception is an **undo**, a
  write by the same thread in the same time step that restores the value
  from before the last one. It cancels that write, so comb logic may run
  across the method API within a time step. A second write that changes
  the value again is still an error.

  Defaults are of two kinds:
  - **hold**: register behaviour, no action;
  - **pulse**: a change the endpoint makes itself, such as dropping `valid`
    after the handshake, or `ready` after taking a beat.

  Only the endpoint sets defaults. The generic put/get endpoints fix them in
  the library. A cycle view (§5.2) may let the user declare one per output
  (`set_default(valid, 0)`). This is the RTL idiom of a default at the top
  of an `always_ff`, overridden later in the same block:

  ```systemverilog
  always_ff @(posedge clk) begin
      if (fire) valid <= 0;            // the endpoint's default
      if (next) begin                  // the task's explicit drive (put(B))
          valid <= 1;
          data  <= b;
      end
  end
  ```

  Why it is needed: when `put(A)` returns at its handshake edge, the
  endpoint can't know whether the caller will `put(B)` at the same edge (a
  sequencer may hand over B in zero time). The alternatives all fail:
  - with no defaults, every caller must remember `idle()`, or a beat is
    duplicated;
  - with notice in advance (`put(A, .more(1))`), the caller carries the
    burden;
  - deciding at the end of the time step needs the host scheduler.

  Cost: if the kernel has already updated at the edge, comb logic sees the
  default and then the explicit value within one time step. Nothing samples
  in between, so the design can't see it; a class trace may show a
  zero-width glitch (§10).
- **C6 Read and write at one edge.** A task may read a port and drive it,
  or drive another port of the same endpoint, at the same edge. That is
  "receive the ack, send the next request" (§4).
- **C7 Blocking operations return at an edge.** `put()` returns at its
  handshake edge, `get()` at the edge where it took a beat, and
  `wait_cycles(n)` *n* edges later. Code after the return is still at that
  edge until it consumes time. A zero-time detour (an untimed channel, a
  sequencer that has the next item ready) stays at the edge. A detour that
  consumes time leaves it, and the next operation re-aligns (C1). That costs
  a bubble, and the bubble is real.
- **C8 Reset.** While the endpoint's reset domain is asserted, its outputs
  hold their reset values and blocking operations wait for reset to end, as
  the WB core's `req_ready` does (`wb_initiator_xtor_core.sv`, the
  `!reset` gate).

C2, C3 and C7 make `core-layer2.md` R2.4 hold exactly: "a call drives
`valid` and `data` in its own cycle and returns on the handshake edge".

### 3.3 What changes from `core-layer2.md` §5.2

| | Decision 4 (2026-11-17) | Here |
|---|---|---|
| Who may touch sync fields | `run()`, directly | only crossing endpoints |
| When a task write is seen | committed at the next edge's commit | just after the edge it's made at (C3); the same observable cycle for peers, with RTL timing for comb |
| What makes reads consistent | `run()` resumes after the kernel (`after_tick`) | the edge is identified by time (C4) |
| `run()` and `step()` in one component (§5.3) | allowed, sharing signals | allowed, but they may not share signals (§9 Q3); they communicate only through endpoints |

## 4. Walkthrough: fwvip-wb's initiator

fwvip-wb's initiator is a sync core (`wb_initiator_xtor_core`, in
fw-proto-wb) with two ready/valid channels to the task side:

- a **request** channel: the task side drives `req_valid`/`req_dat`, and the
  core drives `req_ready = (state == 0)`;
- a **response** channel: the core drives
  `rsp_valid = (ack || err) && state == 1`, and the task side drives
  `rsp_ready`.

`access()` is `request()` then `response()`. The SV task interface
(`wb_initiator_xtor_if.sv`) does that with `<=` drives at `posedge`.

In this model the task side is two generic endpoints: a put endpoint `Ereq`
and a get endpoint `Ersp` (§5.1). A sequence of two accesses, A then B,
with a target that acks in the first bus cycle:

| Edge | Sampled before the edge (C2) | Task side, at the edge | Core `step()` at the edge | Visible after the edge |
|---|---|---|---|---|
| k0 | — | `Ereq.put(A)`: drive `req_valid=1`, `req_dat=A` (C3) | state 0 | `req_valid=1`, `req_ready=1` |
| k1 | `req_valid && req_ready` | `put` returns (C7); `Ereq` default drops `req_valid`. `Ersp.get()`: drive `rsp_ready=1` | latch A, state 1 | `stb=cyc=1`; ack, so `rsp_valid=1` |
| k2 | `rsp_valid && rsp_ready` | `get` returns A's response; `Ersp` default drops `rsp_ready`. `access()` returns; the sequence's next item is ready (zero time, C7); `Ereq.put(B)`: drive `req_valid=1` | term, so state 0 | `req_valid=1`, `req_ready=1` |
| k3 | `req_valid && req_ready` | `put(B)` returns; `Ersp.get()`: `rsp_ready=1` | latch B, state 1 | … |

At k2 the task reads the response channel and drives the request channel
at the same edge (C6). Each output is driven explicitly at most once per
edge (C5): `rsp_ready`'s drop is a default, and `req_valid=1` is the one
explicit drive of `req_valid`. B is accepted at k3, one edge after A's
ack. That is the same timing as the SV interface, and the only gap is
the core's own state-0 cycle, which frames WB phases.

The same table holds if the task happens to run before the kernel at k1 or
k2 (C4). If fetching B took time, B would re-align to a later edge (C1), and
the delay would be real.

## 5. Where the developer takes part

### 5.1 Pattern 1 (recommended): sync core, generic crossings

The developer splits a transactor in two, as fwvip-wb already does:

- **A sync core:** a `step()`/`comb()` class with all the protocol's
  timing: the WB FSM, the bus signals, `req_ready`, `rsp_valid`. It is
  ordinary sync code, so:
  - it lowers to the Verilog core, the hand-written
    `wb_initiator_xtor_core` today;
  - it runs as a class in class-only sims;
  - it can be checked formally like any sync block.
- **A task side** made only of library crossings: a **put endpoint** and a
  **get endpoint** over ready/valid. Their timing is fixed by §3.2:
  - `put(t)` drives `valid`/`data` in its own cycle and returns at the
    handshake edge;
  - `get()` drives `ready` and returns at the edge it takes a beat;
  - back-to-back calls keep the signal high.

  The developer writes `access()` as `req.put(r); rsp.get(p);`, with no
  timing.

Only the generic endpoints know about the crossing. They are written once,
with C1–C8 checked by tests and an SBY proof. This is where developer
participation helps most: by putting protocol timing in sync code, the
developer leaves the crossing nothing protocol-specific to get right. It is
also the process-synthesis view: the core is R1, `access()` is R2, and the
endpoints are a connection between them (`process-synthesis.md` §4, S1).

### 5.2 Pattern 2: a cycle view (the escape hatch)

For BFM-style code that genuinely sequences signals in a task, an endpoint
can offer a cycle view of a port: `sample()`, `drive()`, `wait_cycles(n)`,
`wait_until(cond)`. It has the same rules as above. This is a clocking
block for class code. It is allowed and checked, but the catalog should
steer protocol timing to Pattern 1, because Pattern 2 code doesn't lower
and isn't checked formally.

### 5.3 Pattern 3: declaring the seating

The developer seats each endpoint in a clock domain (the component's by
default; `set_domain` for others), so the crossing check
(`fw_crossing_check.svh`, `core-domains.md` §6) covers it. A component with
endpoints in two clock domains is a CDC element, and is declared as one.

### 5.4 What the developer doesn't do

- order processes;
- think about delta cycles;
- call `after_tick`;
- know whether their task ran before or after the kernel.

## 6. The SV binding

### 6.1 Kernel

`do_edge()` becomes evaluate (`step()`s), update, settle (§2.2). The lazy
commit, `after_tick` and the early-write guard are removed. Crossing
endpoints take part as sync participants (§6.2). The kernel knows nothing
about tasks.

### 6.2 Crossing endpoint

*Superseded in part by §6.5:* tasks are released after the update, and C1
is decided by release count, so only the "kernel has processed" column
below remains. The original text follows.

The endpoint is a sync participant with two hooks, plus a task API. The
edge is identified by time:
- the clock domain records the time of each edge as it happens, whichever
  process sees it first;
- the endpoint compares `$realtime` with that time.

Within one time step:

| | The kernel hasn't processed edge *k* yet | The kernel has |
|---|---|---|
| A task read at *k* (C2) | `cur` is still the value before *k* | the endpoint's sample, taken in its evaluate hook at *k* |
| A task write at *k* (C3) | held, and applied in the endpoint's update hook at *k* | written to `cur` at once, and the domain settled (`settle_now`) |

Either way, the read sees the value before *k* and the write is seen just
after *k*. That is C4.

The endpoint also:
- counts explicit drives per output per edge (C5);
- applies its own defaults at its update hook, unless an explicit drive at
  the same edge overrides them;
- re-aligns off-edge calls with the domain's `tick()` (C1).

This is the one place the old early-write guard's idea survives, scoped to
an endpoint and turned around: a write at the edge lands at that edge, not
the next one.

### 6.3 Pin bridges

They drive module-side outputs from `cur` through `<=` after update and
settle, and settle on input changes as today. The `nxt` view goes. This is
the only place SV scheduling regions appear.

### 6.4 Enforcement

`fw_sig_holder::m_wr` already checks phases (`fw_sig_holder.svh:148-155`).
Add:
- a `get_*`/`set_*` on a sync port from the RUN phase that doesn't come
  through an endpoint is an error: `FW-E-RUN-SYNC-ACCESS`;
- a drive from a `step()`/`comb()` of a field an endpoint owns is an error,
  as writing a peer's output is today;
- a lint flags a component member written by `run()` and read by `step()`/
  `comb()` (Q3), unless it is written only before the run phase.

Test-harness code (phase NONE, around a manual `do_edge()`) stays allowed.

### 6.5 Edges and clocks (final, after the X0.2 review)

X0.2 found that derived and period domains had no fixed edges. The probe's
fix was a time-based `edge_index()`, counted by "whoever sees the edge
first". It worked on the probe, but a review found holes, and the
spec runtime (`fw-hdl-rt-sv`, `__fw_rt_kern`) already has a better
structure. This is the final version. It is stated at the spec level
(`fw-hdl-spec/semantics/processes.md`, "The edge" and "Time"), per Q7. Both
SV runtimes bind it, and a Python runtime can too.

**Holes in the probe's version:**

| # | Hole | Effect |
|---|---|---|
| H1 | A process woken at an edge by something other than the clock (an event, or a `delay` ending at the edge time) reads `edge_index()` before any recorder has run | it sees the previous edge; the result depends on order |
| H2 | "Is now an edge of *this* domain?" (C1) can't be read from an index; a derived domain has no edge time | C1 undecidable for derived domains |
| H3 | `posedge` counts 0→X and X→1 | a clock that starts at X counts its first edge twice; every derived phase shifts |
| H4 | Period edges from floating `$floor(t / period)` | a non-integral ratio can round to a zero wait, which gives a double edge |
| H5 | Counting starts when someone first ticks, or (rt-sv's pin bridge) when elaboration ends | derived phase depends on when elaboration finished |
| H6 | Edges of related domains at one time run as separate groups in some order (both kernels today) | a ÷2 domain's `step()` can read its source's registers after their update. Lazy commit hid this; two-phase exposes it |
| H7 | `edge_index()` is a new pure method on `fw_clock_domain_if` | every implementer outside the repo breaks |
| H8 | A derived domain driven by an RTL divider (`pin_out`) has a phase set by that divider's reset, not by a count from time 0 | the class model and RTL disagree on which edges are the ÷2 edges |
| H9 | `mul` > 1, and `gated`/`muxed` derivations, can't be computed from the source's edge index alone | not covered |

**The final version: one edge driver per root, edges in groups, tasks
released after.**

1. **Edge driver.** Each root clock domain has one edge driver. It is the
   only thing that observes the root's edges.
   - A clock from module code: one `always @(posedge clk) if (clk === 1)`
     in the clock's interface or bridge module (H3), counting from time 0
     whether or not the tree is elaborated yet (H5).
   - A `period` root: the edge loop, in integer `time` (`nxt += period`;
     first edge at `period`, as the spec says), as rt-sv does today (H4).
   - The driver keeps `edges`, the root's edge count, starting at 1.
2. **The group.** At each root edge the driver forms the group: the root,
   plus each modelled derived domain whose edge falls here.
   - `derived(div)` with phase *p* (source edges, from `phase_deg`): edge
     when `(edges − p) mod div == 0`, so the first is at source edge `div`.
   - `gated`: when its enable, read as a pre-edge value, is 1.
   - `mul` > 1 needs a `period` root (period × div / mul; a non-integral
     result is `FW-E-CLOCK-PERIOD`). From a clock in module code it is
     `FW-E-CLOCK-MUL`. `muxed` waits for a driver (H9).
   - Derived of derived nests: a derived domain's count is the edges at
     which it fired.
3. **The edge, for the whole group:** evaluate every `step()` of every
   domain in the group, then update them all, then settle. Related domains
   at one time thus behave like flops on one clock tree (H6).
4. **Release.** Each domain in the group bumps `released` (its edge count)
   and records the edge number. Then the waiting tasks resume. `tick(n)`
   waits until `released ≥ start + n`, as rt-sv's `dedges` does: by count,
   never by time.
5. **C1 by count, not by time (H1, H2).** A crossing operation is at an edge
   if domain *d* has released an edge in this time step. Otherwise it waits
   for *d*'s next release. A process that arrives at an edge time just
   before the group runs waits for that group's release, so it lands at
   the same edge either way, and the outcome doesn't depend on order. A
   time with no edge of *d* waits for *d*'s next edge.
6. **Endpoints simplify.** Every crossing operation now runs after its
   edge's update:
   - a write goes to `cur` and settles (§6.2's "kernel has processed" column
     only);
   - a read returns the hook's pre-edge sample, keyed by edge number, not
     time.

   The probe's either-order code is not needed.
7. **A domain whose net comes from an RTL driver** (a divider wrapper's
   `pin_out`) is a root for edges (H8): its edges are its net's. It stays
   *related* to its source for crossing checks, and an optional run-time
   check compares its edges with the declared derivation (`FW-W-DOM-DERIV`).
   Its group runs after its source's at a shared time, because the divider's
   output rises after the NBA that changed it. RTL simulation of the
   same design does the same.
8. **No API change (H7).** The group is formed inside the kernel or edge
   driver from what the domain API already gives: the chain
   `domain_src()` up to the root, and `root_ticks(1)` for the divisor.
   `fw_clock_domain_if` keeps its methods. `tick()` on a root bridge waits
   for a release once a kernel or driver owns that root.
9. **Pin outputs** are driven with `<=` after settle (§6.3), so RTL flops
   at that edge sample pre-edge values. rt-sv's NBA-toggle commit
   (`fw_pin_bridge.sv`) goes, and no SV region is part of the semantics.
   Pin inputs that RTL flops drive change in the NBA region, after the
   group. A pin driven by a blocking assignment at the edge is a race,
   as in RTL.

**What it changes for users:**
- `tick(n)` on a derived domain waits for the *n*-th edge of that domain,
  phase fixed from time 0. It no longer waits *n* × div source edges from
  the call, so the first can come sooner (rt-sv already behaves this way).
  `clock_domain_tb`'s span check is restated.
- `run()` resumes after the update, not between step and commit. Code
  that reads sync values from `run()` sees post-edge values; reading
  through an endpoint gives pre-edge values. §6.4 makes the former an error.
- Two root clocks with edges at the same time are unrelated. Their groups
  run in some order, and a crossing between them is a CDC, checked as one
  (`FW-E-DOM-CROSS` unless synchronized or waived). A task in one that
  ticks the other at such a time gets an order-dependent answer, as
  RTL would.

**Rejected:**
- **Time-based edge identity with a first-seer recorder** (the probe): H1 and H2.
- **Ordering by SV regions** (`#0`, NBA toggles): ties the semantics to SV
  scheduling (§2.2).
- **Ticking the source `n × div` times from the call** (today): no fixed edges.

### 6.6 Derived endpoints (decided 2026-11-21, Q8)

With §6.5 every task operation runs after its edge's update, so an
explicit endpoint object is no longer needed for correctness. The user
chose **derived** endpoints: nothing declares one.

- A signal that task code reads or writes is a **crossing port**, in the
  domains of its interface. The component whose code touches it is the
  crossing element, as for any interface pair in two domains.
- Task code is *at edge k* of a domain when that domain released edge *k*
  in the current time step, and *between edges* otherwise.
- `read()` at edge *k* returns the value from before *k* (C2), even after
  a write at *k*; between edges, the current value.
- `write()` takes effect at once (C3): the signal takes the value and comb
  logic settles. `step()`s read it from the next edge.
- A `step` block of the same component that writes the same signal gives
  its **default** (C5); a task write at the same edge overrides it. A
  second task write sampled by the same edge is `FW-E-XING-DRIVE-TWICE`,
  unless the same thread makes it in the same time step and it restores the
  value from before the first (an undo; §8.6).
- `FW-E-RUN-SYNC-ACCESS` narrows to task code touching a signal that is
  not its component's own or a direct child's port. It is static (a run-time
  implementation can't attribute code to a component in general).
- `FW-E-WRITE-MULTI` no longer covers one `step` block plus task code of
  the same component; `comb` plus task code is still an error (Q4).

What it changes in this plan:
- §3.2's rules hold as written, stated per signal instead of per endpoint
  object; C1 doesn't make `read()`/`write()` wait (they are functions).
  Blocking operations align with `tick`.
- §6.2's endpoint class is gone. The kernel keeps, per signal task code
  reads, the value from before the current edge (saved on the signal's
  first change after the edge starts, keyed by edge number), and counts
  task writes per sampling edge (X3).
- §6.4: the run-phase check becomes the static scope check above; the
  shared-field lint is dropped (fields are ordered by the edge now).
- Q3 is revised: a `step` and the `run()` of one component may share a
  signal, as default and drive.
- X4's put/get endpoints stay, as library components for Pattern 1 (§5.1),
  not as the gate. Q6 (naming) applies only to them.
- Users write nothing new. Existing spec scenarios (`proc_run_put`,
  `proc_time`, `proto_timed`) keep their traces.

## 7. Effects on existing code and decisions

- **`core-layer2.md`:** §5.2 and decision 4 amended (§3.3). §5.3 amended,
  pending §9 Q3. R2.4 is kept and made exact.
- **`tests/sync/fw_sync_kernel_unit_test.sv`:**
  - `k_mix` (:118-123), the only `run()` that touches sync fields, is
    rewritten with an endpoint;
  - `clocked_root_run_and_step` (:294-) and the early-write test (:309) are
    replaced by endpoint tests for C1–C7.
- **Clock bridges:** `tick()` loses `after_tick`.
- **Pin-level transactors** (`fw_put_to_rv_bridge`, `fw_get_from_rv_bridge`
  in `src/std/rv/`) are unaffected; they don't touch sync fields.
- **`fw_channel`** is unaffected (task domain only). Its per-edge
  accounting (`fw_channel.svh:143-226`) is checked in X0.

## 8. Steps

Run as for the repo (`direnv exec .`). Logs go to `rundir/log/`, not the
terminal.

### X0 Probes (throwaway, scratch copies)

1. **Kernel.** Two-phase `do_edge` and `<=` pin bridges, with `after_tick`
   still in place:
   - `examples/rr_merge` `sim`;
   - `examples/rr_merge_pipe` `sim` (expect a pass);
   - `tests/sync` (expect `k_mix` and the guard tests to change).

   List every change.
2. **Edge identification.** Check that a clock domain can record the edge
   time before any process woken by that edge reads it, for both a root
   clock from a module (`fw_clock_xtor_if`) and a derived domain. If not,
   find the fix.
3. **`rr_merge_tb` sampling.** Run it with a clocking block, on today's
   kernel, to confirm or refute its dependence on scheduling order.
4. **A minimal endpoint.** A put endpoint over `fw_rv_sp_out` with the §6.2
   table. Test it with the task before and after the kernel at an edge
   (force each order) and with a zero-time detour.

*Exit:* findings recorded here; §9 questions answered with the user.

### 8.1 X0 findings (2026-11-21)

The probes ran on a scratch mirror; `docs/design/probes/sync-domains-x0/`
has the patches, the probe sources and how to rerun them.

**X0.1 Kernel.** Two-phase `do_edge` (evaluate, update, settle), with
`after_tick` kept, on `rr_merge`, `rr_merge_pipe` and `tests/sync`:

| Target | Today | X0 kernel |
|---|---|---|
| `examples/rr_merge` `sim` | pass, 1528 beats | pass, 1528 beats |
| `examples/rr_merge_pipe` `sim` | fail (G4: double beats, data changing under a stall) | pass, latency 1, as the RTL |
| the same, sink = 0, stream seed fixed (`+s0`) | | 1707 beats, and the order of the first 200 packets is **identical** to the generated RTL's |
| `tests/sync` SVUnit | 23/23 | 23/23 after the changes below |
| `tests/clock_domain`, `reset_domain`, `crossing` (with X0.2's clocks) | pass | pass, except one span check (below) |

It took four changes, not two:
1. **`do_edge`:** the `step()`s, then `commit()`, then settle.
2. **Pin bridges, outputs:** drive `cur` through `<=`, for comb and sync
   fields alike. The `_c`/`_s` pair and the `nxt` view go.
3. **Pin bridges, inputs (new):** a sync field the pins drive must land in
   `cur` at once (and settle), not in `nxt`. Once the commit moved after the
   `step()`s, a pin value written to `nxt` after edge *k* reached the tree's
   `step()` at *k + 2*, one edge late (`fw_rv_slice_ut` caught it). A pin is
   an input from outside the domain. The input side of a pin bridge
   is the same rule as an endpoint write (§6.2), with the pin process as the
   writer.
4. **The early-write guard is not needed (new).** A write at edge *k* by a
   process that runs before the kernel lands in `nxt`, and the commit at
   *k* moves it. That is just what the guard did by hand. Left in,
   the guard delayed such a write a further edge. With `commit()` always
   unkept, `clocked_root_run_and_step`'s early-write case (`lg2`) gives its
   old values back (`99 + k`).

What changed in the tests (`x0-tests.patch`):
- `comb_chain_settles_in_one_edge`: the comb output reflects the register
  that edge's `step()` wrote (`valid` 0 then 1, was 1 then 0). That is
  the intended change (§2.2).
- `forbidden_writes_detected`: both errors are still counted; the last one
  is now the comb error, because settle runs after the `step()`s.
- `clocked_root_run_and_step`: `run()` now reads the value after the edge
  (`rn[k] = k + 1`, was `k`), because `after_tick` resumes it after update.
  This is the race of §1 moved, not fixed. It goes in X6 with an endpoint,
  as planned. The `run()` write still lands where it did (`lg` unchanged).

**X0.2 Edge identification.** The plan's assumption fails as the code
stands. `edge_phase.sv` ticks each clock from two processes that start one
root cycle (or 3 time units) apart:
- a divide-by-2 domain gives edges at 15/35/55 to one and 25/45/65 to the
  other: `fw_clock_domain::tick(n)` is `src.tick(n * div)`, counted from the
  call;
- a period clock gives 10/20/30 and 13/23/33: `fw_clock_period_xtor_if::
  tick` is `#(count * period)` from the call.

So a domain's edges depend on who ticks it, and no endpoint can know the
kernel's edge. The fix (in `x0-kernel.patch`):
- `fw_clock_domain_if::edge_index()`: the edges so far, from time 0;
- the root `fw_clock_xtor_if` counts edges, recorded by whichever process sees
  the edge first (an `always` and every `tick()` call the same idempotent
  update);
- a period clock's edges fall at multiples of the period;
- a derived domain's edges are its source's edges whose index is a multiple
  of the divisor.

Both processes then see the same edges. Costs:
- `edge_index()` is a new pure method on an interface class, so every
  implementer must add it (`tests/clock_domain/cd_root2.svh` did; so must
  any outside the repo);
- `tick(n)` on a derived domain now means "to the *n*-th edge of this
  domain", so the first can come sooner. `clock_domain_tb`'s check
  "÷6 span = 6 × root span" fails (200 vs 240) and must be restated.

Edge identification for an endpoint is simpler than §6.2 assumed. After
C1 the task is at an edge, so the only question is whether the kernel has
processed it, and the endpoint's own evaluate hook stamps that. The
clock-level index is needed for C1 (is now an edge?) and to make derived and
period domains have edges at all.

**X0.3 `rr_merge_tb` sampling, today's kernel.** All three ways of sampling
pass with the same 1528 beats: as written, through a `#1step`
clocking block, and after `#0`. A monitor finds no sample that differs from
the `#1step` value (9276 samples). The reason is Verilator's order: at
every posedge the testbench's `always` ran before the kernel (it had
committed the edge in 0 of 2319 cases), and after `#0` the kernel had run
(2319 of 2319). The pins, which wake on `gen`, ran after that. So the old
blocking drives of comb pins (`ready_c`) are safe only because of this
order. Another simulator may order them differently. The X0 kernel's `<=`
drives remove the dependence by construction. `rr_merge_tb` should still move to a clocking block
(X7), as `pipe_bench` did.

**X0.4 A minimal put endpoint.** `put_ep.sv`: the endpoint's `step()`
samples the pre-edge `valid`/`ready` and applies the pulse default unless
the task drove `valid` at this edge. A task-side drive writes `nxt` if the
kernel hasn't processed the edge, else `cur` and settles. A sync
consumer stalls at three edges. The program has six back-to-back puts
through the stalls, a put, a zero-time detour (`#0`), a put, a gap, five
more back-to-back puts, and two drives at one edge.
- Task before the kernel at every edge, and after it: the **same** log,
  `2:1 3:2 5:3 6:4 7:5 10:6 11:10 12:11 15:20 … 19:24`. There's no bubble
  between back-to-back puts or across the detour, and the double drive is
  flagged (C5) both ways.
- Negative control: the same endpoint writing `nxt` always, as a `run()`
  write is today. Kernel-first gives one beat every two edges
  (`3:1 5:2 7:3 …`), the G4 shape.

**What this means for X1–X7:**
- X2 takes changes 1 and 4. X5 takes changes 2 and 3, with change 3
  stated as an endpoint write. `after_tick` goes in X2 as planned (it
  now does harm: it puts `run()` after update).
- X0.2's clock fix was reviewed and replaced by §6.5 (edge driver per
  root, groups, release by count; no `edge_index()` API). It is step X2a.
- X3's endpoint is the simpler form §6.5 item 6 allows: always after the
  update. `put_ep.sv`'s either-order handling was needed only because the
  probe's tasks could run before the kernel.

### X1 Semantics (in the IR and the spec, per Q7)

- **Zuspec IR** (`zuspec-ir-core`), restated by §6.6: task code is a
  `ProcBlock` of kind `TASK` with read and write sets; crossing ports are a
  derived result node, `XingPort` (path, read, written, the default's
  `step` block, clock and reset). A pass in `zuspec-synth` derives them and
  reports `FW-E-RUN-SYNC-ACCESS` and `FW-E-WRITE-MULTI` (`comb` plus task
  code). C5's drive count is a run-time rule.
- **Spec** (`fw-hdl-spec/semantics/processes.md`):
  - "The edge" becomes evaluate, update, settle, then release, over a group
    (§2.2, §6.5);
  - "Domain operations" and "Time" take §6.5;
  - a new "Crossings" section states C1–C8 by edge number, not by SV time.
- **This repo:** `core-layer2.md` §5 is amended to point at the spec.
  `fw-proto-axi-new/docs/design-sync-rtl.md` (`/packets/featherweight-ip/
  fw-proto-axi-new`) §3.3 and §3.5 get a note that the spec supersedes them.
- **A conformance case per rule**, in the IR plus a per-edge trace, under
  `fw-hdl-spec/conformance/`. Both SV runtimes and the lowered RTL run them.

### X2 Kernel

Two-phase `do_edge`. Remove the lazy commit, `after_tick` and the
early-write guard. Update the kernel and holder header comments.

### X2a Edge drivers and groups (§6.5)

In `fw-hdl-spec` (the semantics), `fw-hdl-rt-sv` and this repo's `src/`:
- one edge driver per root (module clock: counting from time 0, `=== 1`;
  period: integer time);
- groups of root plus modelled derived domains (`div`, phase, `gated`;
  `mul` on period roots), two-phase over the group;
- release by count;
- C1 by release;
- domains driven from an RTL net as roots.

Tests:
- `edge_phase.sv` restated against releases;
- two tasks on a ÷2 domain started a cycle apart (same edges);
- a ÷2 `step()` reading its source's register at a shared edge (pre-edge
  value);
- a clock starting at X (one edge);
- a period of 3.3 ns at 1 ps (no double edge);
- derived phase independent of elaboration time;
- a `delay` ending at an edge time, then a crossing operation (same edge,
  either order);
- `clock_domain_tb`'s span check restated.

### X3 Crossing ports in the kernel (§6.6)

In `fw-hdl-rt-sv` and `src/`: the pre-edge value of each signal task code
reads (saved on first change after the edge starts, keyed by edge number),
the at-edge/between-edges position per domain, task writes to `cur` with a
settle, drive counting per sampling edge (`FW-E-XING-DRIVE-TWICE`), and
step-block-plus-task-code writers as default and drive. Exit: the spec's
`xing_*` scenarios pass on rt-sv (§8.2).

### X4 Generic ready/valid crossings

`fw_rv_put_ep #(T)` (task `put()` → `valid`/`data`, reads `ready`) and
`fw_rv_get_ep #(T)` (task `get()` → `ready`, reads `valid`/`data`). Also
`try_put`/`try_get`, and the cycle view of §5.2 on the base. SBY proofs of
C2, C3, C5 and C7 for each, with a mutant each.
*Re-scoped 2026-11-21 under §6.6 (§8.7):* a put and a get endpoint in
both runtimes, checked by random-gap simulation with a mutant each. Not
built: `try_put`/`try_get`, the cycle view (task code already reads and
writes signals directly), and SBY proofs (the endpoints are task code,
which doesn't lower).

### X5 Pin bridges

`fw_rv_pin` getters return `cur`; `fw_rv_pin_in/out` drive their outputs with
`<=`.

### X6 Enforcement and migration

The phase checks of §6.4. The tests of §7 are rewritten. Every example and
test with a `run()` is checked against the new rule.

### X7 Examples, walkthrough, docs

- `examples/rr_merge_pipe`: `dfm run sim` passes (G4 closed).
- A WB initiator in Pattern 1:
  - the core as a sync class, lowered and checked equivalent to fw-proto-wb's
    `wb_initiator_xtor_core`;
  - the task side as `fw_rv_put_ep`/`fw_rv_get_ep`;
  - the §4 table reproduced in a test, including back-to-back accesses.

  The example lives in this repo, with a note to fw-proto-wb.
- Docs:
  - `micro-pipelining-feasibility.md` G4 closed;
  - `process-synthesis.md` §4/§14 point at the endpoint as the
    simulation-side connection;
  - the override contract (§2.3) placed where the factory-override design
    will live.

*Exit:* the root suite green (unit and svunit); every example's class sim
green; G4 closed.

### 8.2 X1 results (2026-11-21)

Nothing committed. Files are in the shared packages' working trees (all
on their `mballance/core-layer1` branches, next to the user's own
uncommitted edits there).

**Spec (`packages/fw-hdl-spec`):**
- `semantics/processes.md`:
  - new "Edges": numbering from time 0, net edges on a rise to 1, period
    edges exact, derived edges (`div` fixed from time 0, `gated`, `mul`
    and `phase` from a period, `muxed` none), driven derived domains;
  - "The edge" rewritten: groups, then evaluate, update, settle, release;
    order between groups;
  - "Domain operations": at an edge or between edges; `tick` by count;
  - new "Crossings": derived crossing ports, C1–C8,
    `FW-E-RUN-SYNC-ACCESS`;
  - "Time": exact edge times;
  - "Register or wire" and "Request-update": task writes, and one `step`
    block plus task code as default and drive.
- `semantics/diagnostics.md`: `FW-E-WRITE-MULTI` and `FW-E-CLOCK-NONE`
  restated; new `FW-E-CLOCK-PERIOD`, `FW-E-RUN-SYNC-ACCESS`,
  `FW-E-XING-DRIVE-TWICE`.
- `bindings/sv`: the doc comments of `fw_run_if` and `tick`.
- `conformance/`: nine new scenarios, `xing_sample_drive`,
  `xing_rv_default`, `xing_drive_twice`, `xing_edge_time`,
  `xing_zero_time`, `xing_write_multi`, `xing_access` (static only),
  `edge_div` and `edge_period_bad`; the README's trace definition and
  table; `proc_cdc`'s comment. No existing expectation changed.
- `dfm run tests` passes: all 116 scenarios compile, and the schema check
  passes (`rundir/log/x1-tests.log`).

**Today's rt-sv on the process scenarios** (baseline for X2, X2a and X3):
all 12 `proc_*` scenarios pass. So do `xing_sample_drive` and
`xing_zero_time`, whose rows don't tell the old order from the new one,
and `edge_div`, since rt-sv already phases derived domains from time 0.
`xing_access` is skipped (static only). These five fail as expected:

| Scenario | rt-sv today | Fixed by |
|---|---|---|
| `xing_edge_time` | the delay to 30 runs before the edge, so the write lands at edge 3, not 4 | X2a (C4) |
| `xing_rv_default` | `FW-E-WRITE-MULTI` on `valid`; the default doesn't apply after the last beat | X3 |
| `xing_drive_twice` | no diagnostic; the second write wins | X3 |
| `xing_write_multi` | `comb` plus `run()` isn't detected | X3 |
| `edge_period_bad` | no `FW-E-CLOCK-PERIOD` | X2a |

The static front end (`fw-hdl-fe-sv`) needs to report
`FW-E-RUN-SYNC-ACCESS` for `xing_access`: in X6.

**IR:**
- `zuspec-ir-core` `proc_block.py`: `ProcKind.TASK`, `ProcBlock.reads`,
  and the `XingPort` node; exported, round-trip tested, CHANGELOG entry.
  The ir-core suite passes: 244 passed, 3 skipped.
- `zuspec-synth` `passes/domains/xing.py`: `check_xing(res)` returns the
  crossing ports per instance, with `FW-E-RUN-SYNC-ACCESS` and
  `FW-E-WRITE-MULTI`. It tells a child component from a bundle through
  `Resolution`'s instance tree. Its tests (`tests/test_xing_pass.py`)
  mirror `xing_access` and `xing_write_multi`; 14 pass with the domain
  passes.
- No front end produces `TASK` blocks yet. `zuspec-be-sv`'s
  `proc_emit.py:50` treats every non-`COMB` block as a `step` block, so it
  needs an explicit rejection of `TASK` blocks when one does (X6).

**Repo docs:** `core-layer2.md` §5.2 and §5.3 carry supersede notes.
So do `design-sync-rtl.md` §3.3 and §3.5, in
`/packets/featherweight-ip/fw-proto-axi-new`.

### 8.3 X2 and X2a results, `src/` (2026-11-21)

Nothing committed. X2 and X2a went in together, with X5's pin changes,
since X0 showed the tests don't pass without them.

**Kernel (X2)** (`src/sync/fw_sync_kernel.svh`):
- `do_group(ds)`: every `step()` of the group, then every commit, then
  each domain's settle. `do_edge(d)` is a group of one (the unit tests
  call it).
- `launch()` groups the domains by their root's edge driver and runs one
  process per root: wait for root edge *k*, run the domains whose divisor
  divides *k*, release *k*. A domain whose root has no edge driver (a
  root bridge outside fw-hdl, e.g. `tests/clock_domain/cd_root2.svh`)
  keeps a loop of its own.
- Removed: `after_tick`, `m_live`/`m_procs`, the early-write guard
  (`fw_sig_holder::wr_t`/`edge_t`, `m_keep`, the `*_kept` values).

**Edge drivers (X2a)** (`src/fw_edge_driver.svh`, new):
- `fw_edge_driver`: `released`, `owned`, `own()`, `release_edge(k)`,
  `tick(div, n)` by count; `of(domain, div)` walks to the root.
  `fw_edge_source` is a new interface class the two root bridges
  implement, so `fw_clock_domain_if` keeps its methods (H7).
- Net roots: `fw_clock_xtor_if.n_edges`, counted from time 0 on a rise to
  1 (`=== 1`, H3, H5); `fw_edge_driver_net`.
- Period roots: `fw_clock_period_xtor_if.edges()`/`wait_edge(k)`, edge *k*
  at *k* × period computed from the time, not a loop (no event per edge;
  H4). Its `tick()` now lands on edges too. An edge due now counts as
  passed (C4: a computed edge comes before a delay at its time).
- `fw_clock_domain::tick` (÷n): the *n*-th edge of the domain, edges at
  root edges *j* × `root_ticks(1)`, from time 0.
- The root bridges tick through the driver only once a kernel owns the
  root. Before that they call `vif.tick(n)` as before, because the
  elaborator (`fe/elab`) inlines the bridge's `tick()` into synthesized
  processes; with the driver code there, `test_elab_random` lowered
  differently. `fw_component_root` launches the kernel before any `run()`
  starts, so tasks never straddle the hand-over. A task already waiting
  when a kernel takes a root over waits for the edge's release too.
- Not in `src/` (only `div` exists here): `phase`, `gated`, `mul`,
  `FW-E-CLOCK-PERIOD`, domains edged by an RTL net. rt-sv has them.

**Pin bridges (X5, early)**: a pin value lands in `cur` at once and
settles (sync fields too); `fw_rv_pin_in/out` drive every output from
`cur` with `<=`. `fw_rv_pin`'s comment flags whether `comb_pins` is still
needed as open (X5).

**Tests:**
- `tests/sync` SVUnit 23/23, after X0's three re-baselines
  (`comb_chain_settles_in_one_edge`, `forbidden_writes_detected`,
  `clocked_root_run_and_step`: `run()` reads *k* + 1 until X3 makes it *k*);
  the `fw_sync_kernel::m_live = 0` lines removed (also in the two examples'
  benches).
- New `tests/edges/edges_tb.sv` (`tests/python/system/test_edges_sim.py`):
  ÷2 phase from three starts, the group edge (a ÷2 `step()` reads its
  source's register from before the edge), release after update, a kernel
  launched between edges, period edges from two starts, 3.3 ns at 1 ps
  (30 edges, none twice), a delay ending at an owned period edge, a clock
  starting at X and a 0 → X → 1 rise. Passes.
- `clock_domain_tb`: the span is now measured from each leaf's first edge
  (`cd_leaf.svh`); the ÷6 check was 200 vs 240 before.
- `examples/rr_merge` `sim`: pass, 1528 beats. `examples/rr_merge_pipe`
  `sim`: **pass**, latency 1, as the RTL (G4 closed in the class sim).
- Full root suite (`rundir/x2-regress.sh`, 8 shards): 865 passed, 3
  skipped, 1 xfailed. The root flow's 35 SV sim tasks (all of `dfm run
  tests` but the pytest and XLS tasks): pass, with no FAIL line in any
  sim log.

### 8.4 X2 and X2a results, `fw-hdl-rt-sv` (2026-11-21)

Nothing committed; in the package's working tree next to the user's
edits. Logs: `packages/fw-hdl-rt-sv/rundir/log/x2-*`.

- Conformance: 98 pass / 5 fail / 13 skip before, **100 / 3 / 13** after.
  `xing_edge_time` and `edge_period_bad` now pass; the 12 `proc_*`,
  `xing_sample_drive`, `xing_zero_time` and `edge_div` still pass. Left
  for X3: `xing_drive_twice`, `xing_rv_default`, `xing_write_multi`.
  rt-sv's own pytest suite: 24 passed before and after.
- `sv/fw_rt_kern.svh` rewritten: `plan()` computes each clock's edges (net
  roots count edges; `div`/`gated` from them; period roots in whole ticks
  of the precision with `div`/`mul`/`phase`; `muxed` none);
  `check_edges()` reports `FW-E-CLOCK-PERIOD`; `form_groups()` by root;
  `group()` evaluates, updates, settles and releases a group;
  `tick()` reports `FW-E-CLOCK-NONE`; `gen_edges()` gives C4 for a delay
  ending at a generated edge.
- `sv/fw_pin_bridge.sv` is the edge driver of a bridged root
  (`always @(posedge i) if (i === 1)`, from time 0); its NBA-toggle commit
  is gone and outputs are driven with `<=`.
- **Part of X3 came early:** `xing_edge_time` needs it. Task reads at an
  edge return the pre-edge value (`fw_rt_val.svh`: a cell's value before
  its first change in each group), and a `run()` write lands at once and
  settles (`write_now`). Drive counting and default-plus-drive are still
  X3.
- Departures and limits:
  - `gated` uses the source's edges, as the spec says (the enable isn't
    modelled), not the pre-edge enable of §6.5 item 2.
  - `phase` edges start at *j* = 1 (first 90° edge at 1.25 × P). The spec
    didn't say where *j* starts. *Decided 2026-11-21 (user):* keep
    *j* = 1 for now; now stated in the spec (Edges).
  - `FW-E-CLOCK-PERIOD` is checked before pin bridges register, so a
    bridged root with a `period` is checked as if generated.
  - C4 covers a delay only; another arrival at an edge time (a mailbox
    from another root) is order dependent, as the spec allows.
  - Pre-edge values are kept per group, not per domain (only a CDC can
    tell).
  - Not done: edges for a clock driven from a class net (as before),
    `FW-W-DOM-DERIV`, SV unit tests for X2a (covered in `src/` by
    `tests/edges`; rt-sv's `period` is a 1 ns `time`, so 3.3 ns can't be
    expressed).

### 8.5 X3 results (2026-11-21)

Nothing committed.

**`src/`:**
- `fw_sync_dom` records each domain's edge count and the time of its last
  edge; `do_group()` sets them before the `step()`s.
- `fw_sig_holder`: task code (phase RUN) is *at an edge* of a holder's
  domain when that domain ran an edge in the current time step
  (`m_at_edge`). `commit()` saves each field's value from before the edge
  (`pre`); at an edge, task reads return it, between edges `cur` (C2).
- A task write lands at once in `cur` and `nxt` and settles the domain
  (C3). At an edge it comes after the update, so it overrides a `step()`'s
  write there (the default, C5). It counts against the edge that samples
  it (the domain's next); a second one is `FW-E-XING-DRIVE-TWICE` (through
  `m_rule`, fatal unless `fatal_on_rule = 0`) and is ignored.
- Pin bridges write sync fields in phase NONE now: they aren't task code.
- `comb` plus task code is already an error in `src/` (a comb field
  written from `run()`).
- Tests:
  - `clocked_root_run_and_step` re-baselined: `run()` reads *k*; the
    test's own write at the rising clock is between edges, so that edge's
    `step()`s read it (100 + *k*, was 99 + *k* a cycle later).
  - New `tests/xing/xing_tb.sv` (`tests/python/system/test_xing_sim.py`):
    sample, drive, drive twice and default plus drive, after the spec's
    `xing_drive_twice` and `xing_rv_default`.
- Results: root pytest 866 passed, 3 skipped, 1 xfailed (865 + the new
  test); the 35 root-flow SV sim tasks pass with no FAIL line; sync SVUnit
  23/23; `rr_merge` PASS (1528 beats), `rr_merge_pipe` class sim PASS
  (latency 1). Script: `rundir/x3-regress.sh`.

**`fw-hdl-rt-sv`** (logs `packages/fw-hdl-rt-sv/rundir/log/x3-*`):
- Conformance 100/3/13 before, **103/0/13** after.
- `fw_rt_val.svh` keeps per net its `run()` writer and the edge that
  samples its last task write. `fw_rt_proc.svh`: one block writer plus the
  `run()` of a `step` writer's own component is default and drive; any
  other second writer (`comb` plus `run()` too) is `FW-E-WRITE-MULTI`. A
  second task write for one edge is `FW-E-XING-DRIVE-TWICE`, reported once
  per net, and ignored.
- `fw-hdl-spec/conformance/xing_write_multi/expect.json` gained a trace
  (`edges: 4`): without one the runner never runs the kernel, so the
  run-time error can't appear (`proc_write_multi` has one for the same
  reason).
- **rt-sv pytest: 22 passed, 3 failed** (`test_pin_bridge_rv`,
  `test_pin_bridge_rv_tgt`, `test_protocols::test_rv_b2b`). The spec
  package's `std/fw_rv_xtor.svh` transactors write a pin twice for one
  edge, which C5 now rejects:
  - `fw_rv_initiator::run()` writes `valid = 0` after the handshake and
    `valid = 1` for the next item in zero time. Fix: a `step` block that
    drops `valid` after the handshake (the default), as in
    `xing_rv_default`, and no `write(0)` in `run()`.
  - `fw_rv_target::run()` writes `ready = 0`, `put`s, then `ready = 1`;
    when `put` returns at once both are sampled by one edge. There is no
    fix that keeps zero latency without knowing whether `put` will block:
    **to decide** (X4 territory). *Resolved in §8.6.*

### 8.6 X3 follow-up: the std rv transactors (2026-11-21)

Nothing committed.

- **Initiator:** `fw_rv_initiator` gained a `step()` that drops `valid`
  after a handshake (the default); `run()` only raises it, and a
  back-to-back `put` at that edge overrides the drop.
- **Target:** `fw_rv_target` writes `ready = 0`, `put`s, then writes
  `ready = 1`; when the `put` returns at once, both writes are sampled by
  one edge.
  - Rejected: `try_put` on `fw_put_if`. The kit generates a proxy,
    listener and txn for every API method, so every put sink would have
    had to write it.
  - First tried: a same-thread, same-time-step write *replaces* the last
    one. Withdrawn by the user: it silently loses a value, so a `put` that
    writes `data` twice without waiting (two beats in one cycle) would go
    unreported. That is the bug C5 exists to catch.
  - **Decided (user): undo only.** A second task write sampled by the same
    edge, by the same thread in the same time step, that restores the
    value from before the first write cancels that write. The edge then
    has no task write of the port, and a later one is the first. The user
    describes this as allowing comb logic across the method API: within a
    time step, a call's writes settle, and only a net change is a drive.
    Any other second write is still `FW-E-XING-DRIVE-TWICE`: another
    thread; a later time step (case b of `xing_drive_twice`: edge 3, then
    35); or a new value (1, then 2).
  - `fw_rv_target` is unchanged: `ready = 0`, `put`, `ready = 1` at one
    edge is an undo.
  - Not taken: dropping `ready` only if `put` doesn't return within the
    time step. This needs an end-of-time-step wait that SV lacks; revisit
    in X4 if put/get crossings need a notion of a blocking call.
- Spec: `semantics/processes.md` C5. `conformance/xing_drive_twice` keeps
  a and b as errors and adds u: 1, then 0 (an undo), then 5, which is the
  edge's only write (5 at edges 4 and 5).
- `src/`: `fw_sync_field` keeps the thread (`process::self()`) and time
  of the last task write. Each typed setter keeps the value from before
  the edge's first task write (`xbase`; `valid_xb`, `ready_xb`, `data_xb`)
  and passes `v == xbase` to `fw_sig_holder::m_task_wr`, which undoes on a
  match. `tests/xing/xing_tb.sv` cases: a (one thread, two values) and b
  are errors; e (two threads at edge 3) is an error; u is the undo.
  Expects 3 errors.
- rt-sv: `__fw_rt_net` keeps `tproc`/`ttime`; `__fw_rt_cell_t` keeps
  `xbase` (`mark_base()` at the first task write); `fw_signal::write`
  passes the cell and `v === xbase` to `__fw_rt_procs::wrote()`. An
  ignored write is never recorded. A thread forked inside `run()` still
  isn't attributed to its component (`running()` returns null), so its
  writes go unchecked, as before.
- Results: `src/` `test_xing_sim` PASS; rt-sv pytest 25 passed
  (conformance included); root suite 866 passed, 3 skipped, 1 xfailed;
  35 SV sim tasks rc=0 (`rundir/log/x3-*`, `x3c-*`).

### 8.7 X4 results: the put and get endpoints (2026-11-21)

Nothing committed.

**What was built:**
- **Spec std** (`fw-hdl-spec/std/fw_rv_xtor.svh`):
  - The put endpoint is `fw_rv_initiator`, as fixed in §8.6. No second
    class.
  - New `fw_rv_get_ep #(T)`. `get()` raises `ready` in the cycle it is
    called and returns the beat at its handshake edge. `ready` is low
    while no `get` is pending, so nothing is taken early or buffered.
    `step()` drops `ready` after a handshake; that is the default, and a
    back-to-back `get` at that edge overrides it. As with the initiator,
    `get` hands off to the endpoint's own `run()`, so the pins are written
    by its component.
  - It registers as a component, not a converter: `fw_rv_proto`'s API is
    `put`, so a pull-style target would be `FW-E-PROTO-XTOR`.
  - `fw_rv_target` (push to a `put` callee) is unchanged.
- **`src/`** (`src/std/sync/`, in `fw_std_pkg`): `fw_rv_put_ep #(T)` and
  `fw_rv_get_ep #(T)`, the same behaviour on `fw_rv_sp_out`/`fw_rv_sp_in`,
  with an export `t`.
  - Calls write the port from the caller's thread. Two callers for one
    edge are `FW-E-XING-DRIVE-TWICE`, as two beats in one cycle would be.

**C1:** the endpoints don't wait for an edge. A call between edges drives
for the next edge, as any write between edges does (spec C1). Only the
original plan's C1 had them wait; the spec's C1 doesn't require it.

**The checks:** `fw-hdl-rt-sv/tests/sv/rv_ep.sv` (`test_protocols.py::test_rv_ep`)
and `tests/xing/rv_ep_tb.sv` (`test_xing_sim.py::test_rv_ep`). Each puts
1..40 through the put endpoint into the get endpoint, with a 0–3 edge
pseudo-random gap before each call on both sides. A step-only checker
logs `valid`, `ready` and `data` at each edge, and each call is checked
against the log:
- **C3:** the call's drive is read from the edge after the call, with its
  data.
- **C7:** the call returns at its handshake edge, and no handshake comes
  earlier.
- **C5:** after the handshake, the signal is down at the next edge unless
  the next call was made at the handshake edge (back to back, with no
  idle cycle).
- **C2:** `get` returns the data sampled at its handshake edge; the data
  is checked in order. The handshake count is exactly 40.

Each run has 7 back-to-back puts. A mutant per endpoint (`+mut_put`,
`+mut_get`: `step()` with no default) must fail. Both fail on the C5
check: rt-sv "put 1: still driven at edge 5" and "get 4: still driven at
edge 16".

**Not built:**
- **`try_put`/`try_get`:**
  - No consumer needs them.
  - On ready/valid, a non-blocking get can't take a beat in zero time
    without `ready` having been raised before the call.
  - On `fw_put_if`/`fw_get_if` they would cost kit collateral for every
    implementer (§8.6).
- **The cycle view (§5.2):** after §6.6, task code reads and writes
  signals with `read()`/`write()`/`tick`, under C1–C8. That is the cycle
  view.
- **SBY proofs:** the endpoints are task code, which doesn't lower. Their
  sync half is one line, the default. A formal model of the task side
  would prove the model, not the class. The random-gap checks with mutants
  take their place.

**Results:** both `test_rv_ep`s pass, mutants included; root suite 867 passed, 3 skipped, 1 xfailed (866 + `src/` `test_rv_ep`); 35 SV sim tasks rc=0; rt-sv pytest 26 passed (25 + `test_rv_ep`). Script `rundir/x4-regress.sh`, logs `rundir/log/x4-*` and `packages/fw-hdl-rt-sv/rundir/log/x4-pytest.log`.

### 8.8 X5: is `comb_pins` still needed? (2026-11-21)

*Decided (user): A, remove.* Done; nothing committed. Removed
`fw_rv_pin::comb_pins` and `fw_rv_pin::comb()`, and the `COMB` parameter of
`fw_rv_pin_in/out`; `.COMB(1)` dropped from `rr_merge_tb` and `pipe_cls_tb`;
`examples/rr_merge/README.md` item 9 and open issue 3 updated.
`fw_rv_pin::m_ph` stays: a pin-driven field is still comb when the tree's
own end declares it (as `fw_rv_pass` does with `set_comb("*")`), and the
pin's write must then run in the comb phase. Results after removal:
`rr_merge` PASS 1528 beats; `rr_merge_pipe` latency 1, PASS 1159 beats;
sync SVUnit and `test_xing_sim` pass (`rundir/log/x5-*`); full regression
in the X5 status row.

The analysis that led to it:

**Why it existed.** Before X2 a sync field was written to `nxt` and
committed at the next edge. A pin driven by an RTL flop therefore reached
the tree one edge late, and the pins and a comb tree disagreed about when a
beat moved. `comb_pins = 1` (`COMB` on `fw_rv_pin_in/out`) made the pins'
fields comb, so a pin value landed at once.

**What it changes now.** Since X2, `fw_rv_pin::put_fwd/put_bwd` write a
sync field's `cur` directly and settle, as for a comb field. The flag now
only sets the field's comb bit on the net. Every place that bit is read:

| Where | Comb field | Sync field (pin-driven) | Observable difference |
|---|---|---|---|
| The pin's write | phase COMB | phase NONE | none: only the pin drives the field |
| `m_commit` | not copied `nxt` → `cur` | copied, but the pin set both | none |
| Settle after a pin change | via `comb_changes` | via `now` | none: both call `settle_now` |
| C2 `pre` for task reads | saved at commit | saved at commit | none: saved for every field |
| Settle schedule (`fw_settle_sched`) | edges between `comb()` nodes | — | none: pins aren't nodes |
| `fw_rv_pin::comb(fname)` | — | — | no callers |

**Evidence.** `comb_pins` was forced to 0 in `fw_rv_pin::new` (temporary,
reverted) and both examples that set `COMB(1)` were run. The results were
identical:

| | `COMB(1)` (as written) | forced to 0 |
|---|---|---|
| `rr_merge` sim | PASS, 1528 beats | PASS, 1528 beats |
| `rr_merge_pipe` class sim (`+sink=1`, random ready) | latency 1, PASS, 1159 beats | latency 1, PASS, 1159 beats |

Logs: `rundir/log/x5-probe-*`, `x5-base-*`.

**Users.** Only `examples/rr_merge/tb/rr_merge_tb.sv` and
`examples/rr_merge_pipe/tb/pipe_cls_tb.sv` (5 bridges each). The tests
use the default. No sibling repo under `/packets/featherweight-hdl` uses
pin bridges. rt-sv's pin bridge has no such flag: a pin value always lands
at once and settles.

**Options:**
- **A, remove** (recommended): drop `comb_pins`, `fw_rv_pin::comb()` and
  the `COMB` parameter, and edit the two benches. Nothing changes in
  behaviour, the user loses a setting that has no effect, and `src/`
  matches the spec and rt-sv.
- **B, keep it accepted and ignored:** the same, plus compatibility for
  unknown outside users. The parameter then documents nothing true.
- **C, keep it:** costs a setting the examples tell users to make, with no
  effect, and a divergence from rt-sv.

**What removing gives up.** No behaviour. The one thing a pin flag could
mean in future is the opposite: pins *registered* on entry, so the tree
sees a pin value only from the next edge. That would be a new option if it
were ever needed, not this one.

### 8.9 X6 results: enforcement and migration (2026-11-21)

§6.6 narrowed X6. The run-time phase check of §6.4 became a static scope
check, the shared-field lint was dropped, and a step block and task code of
one component may share a signal. What was left: produce task blocks from
the code, run the IR pass that X1 wrote over them, keep the back end from
lowering them, and check existing code against the rule.

**Built (IR first, per AGENTS.md):**
- **zuspec-fe-sv `proc_mapper.py`:** a class implementing `fw_run_if` gets
  a `ProcKind.TASK` block, `run`, with no body. Its `reads` and `writes`
  are the paths that `run()` and the component functions and tasks it
  calls touch with `read()`/`write()`. `FW-E-WRITE-MULTI` there now covers
  step and comb blocks only; a block plus task code is `check_xing`'s
  (comb plus task: the error; step plus task: the default, C5). A public
  `task_writes(cls)` gives the paths `run()` writes. Test:
  `test_task_block`.
- **fw-hdl-fe-sv:**
  - `domains.passes` runs zuspec-synth's `check_xing` after
    `check_crossings`. Its `FW-E-RUN-SYNC-ACCESS` and `FW-E-WRITE-MULTI`
    are elaboration diagnostics.
  - `ir_map._procs` skips task blocks in `FW-E-WRITE-IN`: task code may
    drive a child's input.
  - `resolve`: a child input that the scope's `run()` writes is driven,
    not `FW-E-IN-OPEN`. The spec says so too (`connections.md`,
    "Unconnected endpoints").
  - The conformance runner claims `processes`. 16 of its 22 scenarios
    match, including `xing_access` and `xing_write_multi`. The other 6 are
    `PENDING`:
    - two have run-time diagnostics only (`edge_period_bad`,
      `xing_drive_twice`);
    - four are ProcMapper checks that fe-sv reports only when it emits,
      not when it elaborates (`proc_comb_loop`, `proc_step_domains`,
      `proc_write_in`, `proc_write_multi`).
- **zuspec-be-sv `proc_emit.py`:** a task block is a `ValueError`
  ("simulation only, not lowered to RTL"). Test:
  `test_task_block_rejected`. `FW-E-EMIT-RUN` already stops emission
  first.

**Migration: nothing to change.** A survey covered every `run()` in `src/`,
`examples/` and `tests/` (72), the tasks they reach, and the sibling
checkouts:
- `fw-proto-axi-new`, `fw-hdl-sv-weave`, `fw-hdl-weave` and
  `fw-dv-setup`;
- the spec std (`fw_rv_xtor.svh`) and rt-sv's tests.

Its findings:
- **No violations.** No task code touches a non-child's signal. No task
  code writes a signal that a comb block also writes.
- **Own-port task code:** `fw_rv_put_ep`, `fw_rv_get_ep`, `k_mix`, `x_drv`
  and the spec std transactors. All but `k_mix` also give a step default.
- **`k_mix` and `clocked_root_run_and_step` (§7):** X3 already rewrote
  them to the C2/C3 rules. `k_mix` touches its own ports, which is
  allowed.
- **Harness code** (module `initial`s, svunit tests; about 9 files) is not
  task code of a component and stays as it is.

**Not done:**
- `src/` has no static front end of its own. Its `run()`s are checked by
  this survey, not by a tool.
- A task write to a child input that is also on a net isn't counted as a
  second driver (`FW-E-NET-MULTI`). No code does it; the spec doesn't say.

## 9. Open questions

| # | Question | Leaning |
|---|---|---|
| Q1 | Are an endpoint's defaults (drop `valid` after the handshake) the right exception to C5, or must every change be an explicit drive? | *Decided 2026-11-21:* defaults, one per output per edge, overridden by at most one explicit drive (C5) |
| Q2 | May task code read a sync value between edges (for debug or a monitor)? | only through an endpoint, and it re-aligns (C1). A non-aligning `peek()` for debug only, marked as such |
| Q3 | `run()` and `step()` in one component (`core-layer2.md` §5.3): may they share a signal? | *Revised by Q8 (§6.6):* yes, as a default and a drive (C5). *Was, 2026-11-21:* no; refused (`FW-E-RUN-SYNC-ACCESS`). They communicate only through endpoints. The cited case, `design-sync-rtl.md` §3.5 (a target transactor whose `step()` pushes into a FIFO that `run()` pops), shares component state, not signals, and that state has the same ordering race; its FIFO becomes a get endpoint with depth. Plain members written by `run()` and read by `step()` are flagged by a lint unless written only before the run phase |
| Q4 | Comb-only endpoints (a task drives a value that comb logic uses in the same cycle, with no register)? | *Decided 2026-11-21:* no. C3 is register timing; a zero-delay path from a task into comb logic is a modelling error |
| Q5 | An untimed task domain (the fast model, `process-synthesis.md` §11): how does it reach an endpoint? | through C1 with a quantum keeper; out of scope here |
| Q6 | Name: endpoint, crossing, `xing`, transactor? | *As built in X4 (§8.7), open to rename:* `src/` `fw_rv_put_ep`/`fw_rv_get_ep`; the spec std keeps `fw_rv_initiator` as the put endpoint and adds `fw_rv_get_ep`. No `fw_xing_ep` base (§6.6: endpoints are derived) |
| Q7 | Define the domains and the crossing in the Zuspec IR, so that other languages (Python) can build a modelling layer on them? (user, 2026-11-21) | *Decided 2026-11-21:* yes. Sync is already `ProcBlock` `STEP`/`COMB` with a clock/reset `DomainRef`; tasks are `proc_processes`; `domain.py` has kinds, associations and crossing severities. Add an endpoint node (`XingEndpoint`: seated domains, a sync-side port with a default kind per output, a task-side method set), state C1–C8 by edge index rather than by SV time, make `FW-E-RUN-SYNC-ACCESS` and C5 IR passes over read/write sets, and keep a shared conformance suite (IR plus per-edge traces). SV classes become one binding. Would move X1 to define C1–C8 against the IR, and X3 to "the SV binding" |
| Q8 | Is the crossing endpoint an explicit object (a transactor's `pins`, or `fw_xing_ep`), or derived from what task code touches? | *Decided 2026-11-21:* derived (§6.6). Revises Q3 and §6.2–§6.4 |

## 10. Risks

- **Edge identification by time (X0.2)** must be reliable for every clock
  source, including derived domains and clocks from module code. *X0:*
  derived and period domains had no fixed edges. §6.5 replaces edge
  identity by time with release by count.
- **Two drives at one time step with zero-width effects.** A default drop
  followed by an explicit drive, both after the edge, settles comb logic
  twice in one time step. Pure comb logic makes that harmless, but class
  traces may show a zero-width glitch. Traces should record the value at the
  end of the time step.
- **Migration.** Fewer users than feared (one test), but fw-proto
  transactors in other repos may hold `run()` code that touches sync fields.
  A survey of those repos is part of X6.
