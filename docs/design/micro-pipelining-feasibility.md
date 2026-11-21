# Micro-pipelining sync logic: phase 1, feasibility (D0)

The implementation, test and doc plan for the first phase of pipelining
ready/valid `comb()` logic (`process-synthesis.md` §5, plan step D0). This
phase is an assessment. It answers whether the D1–D5 approach is sound and
what it costs, using a variant of `examples/rr_merge`. It builds the least
production code that can answer that. Pick up from **§0 Status**.

The phase ends with a results document and a go/no-go per question (§2). The
D1–D5 plan in `process-synthesis.md` §15 is revised from those answers before
D1 starts.

## User benefit

Phase 1 doesn't ship a feature. It gives users and maintainers:

1. **Evidence before commitment.** Measured numbers on an example designers
   already know: cells, flops, logic levels and throughput, for 0, 1 and 2
   stages and for each controller. They show whether the tool can produce
   what a designer would write by hand, and at what cost.
2. **A reference answer.** Hand-written pipelined versions of the
   `rr_merge_pipe` blocks. They are what D3's engine must reproduce, and
   designers can study them as examples today.
3. **A reusable latency-insensitive bench.** A scoreboard that checks streams
   per source, ignoring timing, under randomized backpressure. The repo has
   none (§1.4). Every D-step and S-step needs one, and users can use it for
   their own ready/valid blocks.
4. **A first catalog page in draft**: the map stage (pattern 1), with its
   example running.

## 0. Status

| Step | Status | Notes |
|---|---|---|
| Plan (this doc) | approved and carried out, 2026-11-20 | |
| F0 Baseline | **done** 2026-11-20 | `rr_merge`: sim, ref-sim, gen-sim pass; generated RTL byte-identical; 25/25 `equiv` proven, 3/3 BMC; 181/207 cells, 37 flops as in LOWERING-RESULTS.md; unit tests 328 pass, 2 skip |
| F1 Vehicle: `examples/rr_merge_pipe` | **done (RTL); class sim blocked by G4** | v0 lowers and passes the bench. The classes weave and elaborate but fail on G4 (§0.1) |
| F2 Latency-insensitive bench | **done** | `tb/pipe_bench.sv`, `pipe_mutant.sv`; 4/4 mutants caught; per-source streams independent of DUT timing |
| F3 Answer key: hand-pipelined R1 variants | **done** | 8 variants lower unchanged; 36 configurations / 864 runs pass (`rundir/rtl/matrix.txt`). **A1: go** |
| F4 Measurements | **done** | `scripts/measure.sh`; operator cuts barely help, retiming does. **A2: go, by registers plus retiming. A8: answered** |
| F5 IR spikes: roles, recognizer, delay | **done** | roles as pragmas (A3 go); `spikes/dataflow.py` (A4 go); delay routes i and ii (A5: estimate yes, cut choice no) |
| F6 Thin automated slice (map, stall) | **done** | `spikes/pipeline.py`, `scripts/gen_auto.py`; auto1 ≡ stall1, unbounded, W = 8/16/32. **A6: go** |
| F7 Checks: datapath and controller | **done** | `scripts/formal.sh`: 12/12 as expected (K = 1..3, with mutants). **A7: go** |
| F8 Assessment and plan revision | **done, awaiting review** | `examples/rr_merge_pipe/RESULTS.md`; `process-synthesis.md` §0, §5.3, §5.5, §5.6, §6.1, §14, §15, §17 revised. **Next: G4 first** (`sync-task-domains.md`, decided 2026-11-21), then D1 |

### 0.1 Gaps found (details in `examples/rr_merge_pipe/RESULTS.md`)

- **G1 Nested composites** weren't lowered parameterized. Fixed:
  `composite_param` (`python/fw/hdl/fe/elab/sync_param.py`) lowers a child
  composite as a module of its own and takes the wiring calls that are its
  own; wiring that crosses levels is an error.
- **G2 Packed wires.** zuspec-be-sv declared a composite's internal array
  wires unpacked, while the child ports are packed. Fixed in
  `packages/zuspec-be-sv/src/zuspec/be/sv/sync_param.py` `composite()`.
- **G3 No arrays of child components** in the parameterized lowering, so the
  N input maps are one N-lane class (`pipe_map_in`). Not fixed.
- **G4 Class model: comb pin fields computed from sync fields are one edge
  late.** The kernel evaluates edge T with the values from before T
  (`fw_sync_kernel.svh:252-272`). `fw_rv_pin` corrects for that only when a
  pin reads a sync field directly (`fw_rv_pin.svh:119-133`). `mout`'s comb
  output is computed from `rr_fifo`'s registered `out`, so at the pins it is
  one edge late (latency 2, beats taken twice). It shows up whenever comb
  logic follows a register at an output pin. That's common in pipelined
  designs, so this blocks class-model runs of every variant. Suggested fix:
  a look-ahead settle for pin-bridge comb values. Not fixed: needs a
  decision (kernel change).
- **G5 sv-weave identifies specializations by spelling.** It names them by
  their printed spelling (`rr_arbiter#(rr_merge::T,4)`), so specializations
  from different packages collapse into one (`sv_weave/frontend/specialize.py:37-39`,
  `model.py:444-450`), and `fw_settle` can't summarize their port calls.
  Workaround: `rr_merge`'s `.svh` are included into the vehicle's package,
  not imported. Not fixed.
- **G6 `fw_settle` granularity is the top-level statement** of `comb()`, and
  it falls back to "all writes depend on all reads" when statements share a
  local. The arbiter falls back that way, so a map written as one `foreach`
  closed a false comb loop. Maps are written one statement per field, with
  `f` as a function. That is also the form the recognizer (F5b) wants.
- **Bench sampling.** The bench reads DUT outputs through a clocking block
  (`#1step`), so the class model and the RTL are sampled alike.

Nothing is committed by these steps. The user commits.

## 1. Starting point

From a survey of the repo (2026-11-20):

### 1.1 `rr_merge` has almost nothing to pipeline as written

| Block | Shape (§5.2) | Why |
|---|---|---|
| `rr_arbiter` | none: a stateful merge | `ptr`/`locked`/`owner`. Grant and mux are a function of state, so the arbiter is a region boundary |
| `rr_fifo` | none: a realization | storage; `fifo(DEPTH)` in §4.1 terms |
| `arb.out → fifo.in` | a connection, realized `comb` | carries the comb `ready` chain `out.ready → fifo.in.ready → arb.in[g].ready` |

The payload is `{data[7:0], last}` and nothing is computed on it. The vehicle
therefore adds dataflow shapes around the merge (F1) and keeps `rr_merge`
unchanged inside it. The `ready` chain is still useful as the first case of a
connection realization being swapped (`comb` → `skid`) with no change to the
classes.

### 1.2 Sync IR

- `sync_component_param` (`python/fw/hdl/fe/elab/sync_param.py:740`) gives
  one `DataTypeComponent` per class. `comb()` becomes a `Function` with
  `ProcessKind.COMB` in `comb_processes`, and `step()` becomes `SYNC` in
  `sync_processes` (`zuspec-ir-core` `data_type.py:19, :153-154, :416`).
- Ports are flattened to one `FieldInOut` per field (`in_valid`, `in_ready`,
  `in_data`), with `Field.drive` (SYNC/COMB) and `reset_force`.
- **The bundle protocol is not in the sync IR.** Only field names and
  directions survive. `Field.role` (`fields.py:105`) exists but `sync_param`
  doesn't set it, and it describes the bundle's side (initiator, mirror,
  monitor), not each field's role (valid, ready, data).
- `emit_sync(..., parameterized=True)` (`python/fw/hdl/emit/sync.py:72`) →
  zuspec-be-sv `sync_param.py`.

### 1.3 Pipelining and timing machinery: none of it reads sync IR

- **`@zdc.pipeline`** (zuspec-dataclasses `pipeline_ns.py`; zuspec-synth
  `passes/*`, `ir/pipeline_ir.py`). It parses Python AST, makes per-stage
  valid registers with a hazard-driven stall/flush and forwarding, and cuts
  stages from integer op latencies (`passes/sdc_schedule.py`). There is no
  ready/valid backpressure at its boundaries and no delay model. It is a
  processor-pipeline tool, not a dataflow-region tool. F8 records whether
  any of it is worth reusing; the expectation is that the controller ideas
  are, and the code isn't.
- **`proc/delay.py` `DelayModel` and `proc/timing.py` `analyze`** work on
  hash-consed `Term`s in a `lower.Netlist` built from proc IR. Delay-driven
  cutting exists for proc IR: `proc/sched/delay.py` `DelayEngine`,
  `place(design, model, budget)` (:234), `_split` (:321). Nothing bridges
  sync IR (zuspec-ir-core `Expr`/`Stmt`) to `Term` or to proc IR.

### 1.4 Checks

- `tb/rr_merge_ref_tb.sv` runs the generated RTL against the reference in
  **cycle-exact lockstep**. `yosys/equiv.ys` pairs **same-named registers**,
  and `yosys/bmc.ys` asserts equality every cycle. A change of latency fails
  all three. They stay valid for the as-written path and the F3 answer key,
  and are useless for pipelined-vs-original.
- The tb's per-source order checks (:104-125) are timing-independent, but
  they live inside that tb.
- There is no reusable transaction-level scoreboard. `cosynth/equiv.py` is an
  SBY harness that compares outputs **shifted by a fixed latency**, data only
  when valid. It applies with `ready` held high, and doesn't apply under
  backpressure.
- Yosys and SBY are in `packages/yosys/bin`. `zuspec-synth` `proc/miter.py`
  has k-induction with invariant certificates.

## 2. The questions

Each F-step answers some of these, and F8 records the answers.

| # | Question | Answered by | Go if |
|---|---|---|---|
| A1 | Can every pipelined form (k stages; `stall`, `elastic`, `credit`; `skid` on a connection) be written as plain sync classes and lowered by today's flow unchanged? | F3 | all lower and lint; gaps listed and small |
| A2 | Is the gain worth it on this kind of logic? | F4 | for a deep `f`, *k* stages cut logic levels roughly *k*-fold at 1 beat/cycle, for flops ≈ *k* × payload width (stall) |
| A3 | Can the bundle protocol (valid/ready/data roles) be carried into sync IR without new nodes? | F5a | yes, as field metadata set from the port class |
| A4 | Can a map shape be recognized in a `comb` `Function`, and `f` extracted, while state and other boundaries are rejected with a reason? | F5b | matches the F1 maps; rejects `rr_arbiter`, `rr_fifo` |
| A5 | Can the existing delay machinery estimate `f` and choose cuts? Route (i): sync `Expr` → `Term` → `analyze`. Route (ii): `f` → a proc-IR `Proc` → `DelayEngine.place`, which reuses the process-level transform (the premise of §5.1) | F5c | estimates rank the variants in the same order as yosys/abc levels; route (ii) gives usable cut points |
| A6 | Can an engine output (stages and controller) be built as sync IR and emitted with no new back-end work? | F6 | generated RTL is equivalent to the F3 answer key (`equiv_induct`, same register names) |
| A7 | Can a pipelined region be checked without cycle-exact comparison? | F2, F7 | bench passes on many seeds; datapath ≡ `f` proven; controller properties proven for small parameters |
| A8 | What does pipelining in front of a stateful merge change at the pins? | F2, F4 | the change is understood and stated in E1 terms (§3.3) |

## 3. The vehicle: `examples/rr_merge_pipe`

### 3.1 Structure

```
 in[0] ─► map f_in ─┐
 in[1] ─► map f_in ─┼─► rr_merge (unchanged) ─► map f_out ─► out
 ...                │
 in[N-1] ► map f_in ┘
```

- **Payload**: `pipe_beat_t #(W)` = `{a[W-1:0], b[W-1:0], c[W-1:0], last}`
  in and `{y[2W-1:0], last}` out. `W` scales the depth of `f`.
- **`f_in`**: `y = a * b + c`, a deep function whose depth is set by `W`.
  `last` passes through.
- **`f_out`**: a cheaper second function (for example a byte-swap with a
  checksum fold), so that a chain of two maps exists for collapsing later
  (D3). Phase 1 pipelines `f_in` and `f_out` separately.
- **The maps** are written in today's sync style: hand-written `comb()` with
  `out.valid = in.valid`, `in.ready = out.ready`, `out.data = f(in.data)`.
  This is the "before" form, and the form D5 must recognize. A declared
  `fw_rv_map` is D1's job and is not built here.
- `rr_merge` is reused as is, by inclusion from `../rr_merge/src`, so the
  example keeps no copy.

### 3.2 Parameters

`N` (2, 4), `DEPTH` (2), `W` (8, 16, 32), and per map a stage count `K` and
a controller (§3.4) in the F3 variants.

### 3.3 Where the pins change (A8)

Pipelining a map **after** the merge delays the output stream and changes
nothing else. Pipelining the per-input maps **before** the merge changes
when each input's beats reach the arbiter, so with competing inputs the
packet interleaving at `out` can change. Within each source, order is kept
and packets stay whole.

That is legal under E1 (per-connection order and content), but it means the
check for a merge is per source, not one global order. F2 builds the bench
that way, and F4 runs both placements to show it. The finding goes into
`process-synthesis.md` §6 as a property of stateful merges: an arbiter's
choice is not ordered against its inputs' latencies unless a rule says so.

### 3.4 Variants (the F3 answer key)

| Variant | What changes | Pattern |
|---|---|---|
| `v0` | as written: 0 stages, `comb` connections | baseline |
| `skid` | `skid` realization on `arb.out → fifo.in` (in the parent) | realization swap (§4.2); cuts the `ready` chain |
| `stall-K` | `f_in` in K = 1, 2 stages; one `ready` enables every stage | map + `stall` controller |
| `elastic-K` | the same with a skid per stage | map + `elastic` |
| `credit-K` | valid-only stages, an output FIFO of depth K, credits to the input | map + `credit` |
| `out-K` | `f_out` pipelined, `f_in` as written | post-merge placement (§3.3) |

Every variant is a separate sync class tree, written by hand in the same
style as `rr_merge`, with stage registers named by a fixed scheme (`s1_v`,
`s1_d`, …). F6 must generate the same names so that `equiv.ys`-style
pairing works.

## 4. Steps

Run Python as `direnv exec . env PYTHONPATH=$PWD/python …`, and send all
build, sim and formal output to `examples/rr_merge_pipe/rundir/log/*.log`.

### F0 Baseline

- Run `examples/rr_merge`: `scripts/gen_rtl.py`, `dfm run gen-sim`,
  `dfm run ref-sim`, `scripts/compare.sh`; and the sync unit tests
  (`tests/python/unit/test_sync_param.py`, `test_emit_sync*.py`,
  `test_elab_sync_*.py`).
- **Exit:** all green, logged, with the numbers in LOWERING-RESULTS.md
  reproduced (cells, induction grid). Anything that has drifted is fixed or
  recorded before F1.

### F1 Vehicle

- `examples/rr_merge_pipe/`: `src/` (`pipe_pkg.sv`, `pipe_map_in.svh`,
  `pipe_map_out.svh`, `rr_merge_pipe.svh`), `flow.yaml`, `sv-weave.yaml`,
  `scripts/gen_rtl.py`, `README.md`.
- Class model sim (`dfm run sim`) under `fw_root`, as for `rr_merge`.
- Lower `v0` with `emit_sync(parameterized=True)`. This is the first check
  that a payload struct of parameterized width and a multiply go through the
  parameterized flow; gaps are fixed in place if small, or recorded.
- **Exit:** class sim and generated-RTL sim pass on F2's bench (F1 and F2
  are done together); Verilator `-Wall` lint clean or warnings listed.

### F2 Latency-insensitive bench

A reusable stream scoreboard and driver, in SV, used by the class model and
the RTL benches.

- **Drivers**: per input, random gaps, random packet lengths, a seed
  plusarg. Sink: random `ready`, with modes for always-ready, 50% and bursty.
- **Model**: a reference function per map, `f_in` and `f_out` in SV (the
  same `f` as the classes, through a shared function in the package so the
  model can't drift).
- **Scoreboard**: per source, an expected queue of `f_out(f_in(x))` beats.
  At `out`, each packet is attributed to a source by matching its first beat
  against the queue heads. To keep that unambiguous, payloads carry the
  source id and a sequence number in `a`/`c` fields chosen by the driver,
  and `f` is chosen to keep them recoverable. Checks: every beat accounted
  for, per-source order, packets whole, no beat lost or duplicated, queues
  empty at the end.
- **Throughput**: beats per cycle at `out` while the sink is always ready,
  and the cycle count from first input to last output.
- **Protocol monitors**: `valid` held until a transfer, data stable while
  `valid && !ready`, at every port.
- Location: `examples/rr_merge_pipe/tb/` for this phase. F8 decides where it
  goes (`src/` library or `fw-proto` per the family strategy).
- **Exit:** `v0` passes 20 seeds × 3 sink modes. A mutant (an `f` off by
  one, a dropped beat, a beat reordered within a source) is caught by each
  check in turn.

### F3 Answer key

- Write the §3.4 variants by hand as sync classes: a `stall` stage class, a
  `skid` class, a `credit` wrapper, and composites per variant, parameterized
  by `T`, `K` where the current flow allows (record where it doesn't, and
  fall back to one class per K).
- Lower each with today's flow, unchanged. Do not extend the flow in F3: any
  failure is an A1 finding. Fix it only if it's a plain bug.
- **Exit:** every variant passes the F2 bench (20 seeds × 3 sink modes) as
  class model and as generated RTL; lint results tabulated. **A1 answered.**

### F4 Measurements

- A script `scripts/measure.sh` like `rr_merge`'s `compare.sh`: per variant ×
  `W` × `N`, run yosys `synth` (cells, flops) then `abc -D` and `ltp -noff`
  (logic levels on the worst path), plus throughput and latency from the F2
  bench.
- Optionally run the ECP5 model from fw-picorv32 for a second delay figure,
  if it can be run from here without copying it.
- Results go in `examples/rr_merge_pipe/RESULTS.md`: one table per `W`, rows
  for variants, columns for cells, flops, levels, beats/cycle and latency.
- Both placements (§3.3) run under contention: report the output
  interleaving difference and confirm per-source checks pass.
- **Exit:** the tables are filled. **A2 and A8 answered.**

### F5 IR spikes

Throwaway-quality code in `python/fw/hdl/fe/elab/` or a `spikes/`
directory. It is judged by what it shows, not kept as is, but it is unit
tested so the numbers in F8 can be trusted.

- **F5a Roles.** Set a per-field role (valid, ready, data, `last` as data)
  on each flattened port `FieldInOut`, from the port class
  (`fw_rv_sp_in/out`), in `sync_param.py`. Spike it as `Field.metadata` or
  `pragmas`, not as a new IR field, until Q9 is decided. *Test:* roles on
  `rr_arbiter`, `rr_fifo`, `pipe_map_in`. **A3.**
- **F5b Recognizer.** Given a component's `comb` `Function` and its roles,
  match the map template (`o.valid := i.valid`, `i.ready := o.ready`,
  `o.data := f(i.data)` with `f` reading only `i.data` and constants) and
  return `f` as an `Expr` tree, or a reason for no match: reads state, writes
  a sync field, `ready` depends on data (that's a filter, out of scope here),
  and so on. *Tests:* matches `pipe_map_in`/`pipe_map_out`; rejects
  `rr_arbiter` (state), `rr_fifo` (state, `step()`); rejects three
  hand-made near-misses. **A4.**
- **F5c Delay.** Specialize `f` at a given `W`, then:
  - route (i): a small `Expr`/`Stmt` → `Term` translator (symbolic
    execution of `StmtIf` into `ite`), a minimal `Netlist`, `timing.analyze`
    with the `unit` model;
  - route (ii): build a one-process proc-IR `Design` for
    `forever { x = get(); put(f(x)); }`, and run `DelayEngine.place` at a
    budget, reading back the edges it chose.

  Compare both with F4's yosys levels across `W`. Record each route's effort
  in lines and days. *Tests:* translator unit tests on `+`, `*`, `?:`, struct
  member select. **A5.**

### F6 Thin automated slice

One pattern, one controller, end to end: a recognized map, cut by the delay
result, with a `stall` controller, built as sync IR and emitted.

- Input: the `v0` IR of `rr_merge_pipe`, a target in levels or ns, and the
  F5 recognizer and cutter.
- Transform (Zuspec IR → Zuspec IR, per AGENTS.md): replace the map's `comb`
  `Function` with K stage registers (a `sync` process) and a `comb` process
  for the controller. The stage logic is the slices of `f` at the cut points.
  Register names follow the F3 scheme.
- Emit with zuspec-be-sv, unchanged.
- Also project to source: print the result as a sync class (even crudely),
  to see what S2/D3 projection needs. This is a probe, not a deliverable.
- **Exit:** for `W` = 16, 32 and two targets, the generated RTL passes the
  F2 bench, and `equiv.ys`-style induction against the F3 `stall-K` answer
  key passes. **A6 answered.**

### F7 Checks: datapath and controller

- **Datapath ≡ `f`.** With `ready` held high and no backpressure, the
  pipelined map is `f` delayed by K. Reuse `cosynth/equiv.py`'s fixed-shift
  harness (pre = `v0` map, post = F6 output, shift K). Run its mutants
  (wrong shift must fail).
- **Controller.** SBY properties per controller template, for small payloads
  (1–2 bits) and K = 1, 2, 3, over free `valid`/`ready`/data: no loss, no
  duplication, order kept (a tagged token at the input appears once at the
  output, in order), the `valid`/`ready` protocol at both ports, and bounded
  liveness when the sink is ready (BMC: a token leaves within K + c cycles).
  Use `formal.sby.BMC` dfm tasks where they fit, prove mode otherwise.
- Together these give the §5.6 argument: datapath ≡ `f`, plus a controller
  proven once, implies the region is E1-equivalent to `v0`. F8 records any
  gap in that argument, for example whether the fixed-shift check plus the
  controller proof covers backpressure without a full stream miter.
- **Exit:** both pass, with mutants caught. **A7 answered.**

### F8 Assessment

- `RESULTS.md` completed: answers A1–A8, each with its evidence and go/no-go.
- Revise `process-synthesis.md`:
  - §0 status: D0 done;
  - §5: what F5 found about roles, recognition and delay;
  - §6: the merge interleaving finding (§3.3);
  - §14: gaps found;
  - §15: D1–D5 rescoped (for example, whether D1's region node is `Field`
    metadata plus a `Function` annotation, and which delay route D3 takes);
  - §17: leanings on Q8, Q9 updated, and new questions added.
- Decide where the F2 bench lives, and whether the `@zdc.pipeline` passes
  have anything to reuse.
- **Exit:** the user reviews the assessment and decides on D1.

## 5. Tests

| Level | What | Where | Runs |
|---|---|---|---|
| Unit (Python) | roles, recognizer, `Expr`→`Term`, proc-IR build, F6 transform | `tests/python/unit/test_pipe_*.py` | pytest, with the root suite |
| Lint | every variant's generated RTL | per-variant `gen_rtl.py`, Verilator `-Wall` | F1, F3, F6 |
| Simulation | class model and generated RTL, F2 bench, 20 seeds × 3 sink modes, N ∈ {2, 4}, W ∈ {8, 16, 32} | `examples/rr_merge_pipe/flow.yaml` | dfm |
| Mutants | bench catches a wrong `f`, a lost beat, a reordered beat; equiv harness catches a wrong shift; SBY catches a broken controller (dropped enable) | same places | each exit |
| Equivalence | F6 output ≡ F3 answer key (induction); datapath ≡ `f` (shifted) | `yosys/`, `cosynth/equiv.py` | F6, F7 |
| Formal | controller templates | `examples/rr_merge_pipe/formal/` | F7 |
| Regression | `examples/rr_merge` flows and the sync unit tests unchanged | F0 set | every step |

## 6. Docs

| Doc | What | Step |
|---|---|---|
| this plan | status updated as each step finishes | every step |
| `examples/rr_merge_pipe/README.md` | the vehicle, the variants, how to run | F1, updated F3 |
| `examples/rr_merge_pipe/RESULTS.md` | measurements, findings, A1–A8 | F4–F8 |
| `examples/rr_merge_pipe/docs/map-stage.md` | **draft** catalog page for pattern 1 (Problem → What you write → What the tool derives → Implementations and costs → Checks → Pitfalls), using F3/F4 numbers. It moves to `docs/methodology/` when D3 makes the "tool derives" part real | F8 |
| `process-synthesis.md` | §0, §5, §6, §14, §15, §17 revisions | F8 |
| bench usage | a short section in the README on using the F2 scoreboard for any ready/valid block | F2 |

## 7. Risks

| Risk | If it happens |
|---|---|
| The parameterized flow can't lower a struct payload of width `W` or a `*` | fix if small (it's on the D path anyway); else fix `W` per class and record |
| A controller can't be written in today's sync subset (for example, the skid needs a pattern the front end rejects) | that is an A1 finding; record the construct and work around it by hand in RTL for F4 only |
| Packet attribution in the scoreboard is ambiguous | the driver encodes source and sequence in the payload; `f` is chosen to keep them recoverable |
| Neither delay route is cheap | F4 shows yosys levels are good enough as the oracle for D3 v1; record and move on |
| `DelayEngine.place` assumes things about proc IR that a lifted `f` lacks | route (i) only; record what route (ii) needs |
| Scope creep into D1 (declared `fw_rv_map`, a real region node) | out of scope here; the spikes use metadata |

## 8. Out of scope

Declared shapes (`fw_rv_map` …, D1), join, filter and fork, chain collapsing
and re-cutting (D3), side inputs, related streams and ordering automata (D4),
inference on extracted Verilog (D5), process networks (S-steps), and any XLS
path.
