# rr_merge_pipe: micro-pipelining feasibility results (D0)

The results of phase 1 (D0) of micro-pipelining sync logic. The plan, the
questions and the steps are in
[`docs/design/micro-pipelining-feasibility.md`](../../docs/design/micro-pipelining-feasibility.md).
Numbers are from 2026-11-20, yosys 0.70 and Verilator 5.055. The scripts that
reproduce them are named in each section.

## Summary

| # | Question | Answer | Go? |
|---|---|---|---|
| A1 | Can the pipelined forms be written as plain sync classes and lowered unchanged? | **Yes.** All 8 variants (stall, elastic and credit at K = 1, 2, a skid connection, a post-merge stage) lower with no change to the flow and pass the bench. Two small flow gaps were fixed on the way (G1, G2), and one remains (G3, arrays of child components) | **go** |
| A2 | Is the gain worth it? | **Not as hand-cut at operators; yes with retiming.** Cutting `f` between its operators barely shortens the path (W = 32: 119 → 113 → 108 levels for K = 0, 1, 2), because the multiply is almost all of `f`. Insert K registers and retime with ABC, and the path drops to 47 (K = 1) and 37 (K = 2) levels, at about 2–4× the flops | **go**, with a changed approach (registers plus retiming, not operator cuts) |
| A3 | Can the protocol roles be carried in sync IR without new nodes? | **Yes.** Each port field gets `channel`, `channel_role` and `channel_side` pragmas, read from the holder's shape, not from a table of port classes | **go** |
| A4 | Can a map be recognized and `f` extracted, with a reason for each rejection? | **Yes.** Both maps match (one with N lanes, one scalar). The arbiter, the FIFO, the composite, a stall stage and 5 near-misses are rejected with a reason | **go** |
| A5 | Can the existing delay machinery estimate `f` and choose cuts? | **Partly.** Both routes run. Route (i) (sync IR → `Term` → `analyze`) ranks W correctly but overestimates `f` by 2×. Route (ii) (`DelayEngine.place`) cuts only between operators, so `f` gets at most 2 stages. Neither cuts inside the multiply. The only built-in model is `unit` | **go for estimation; no-go for choosing cuts** |
| A6 | Can an engine output be built as sync IR and emitted with no new back-end work? | **Yes.** The F6 transform turns the recognized map into a K-stage stall map, IR to IR. zuspec-be-sv emits it unchanged, and it is proven equivalent to the hand-written `stall1` (unbounded, 1353 signal pairs, W = 8, 16, 32) | **go** |
| A7 | Can a pipelined region be checked without cycle-exact comparison? | **Yes.** The latency-insensitive bench passes 864 runs and catches 4/4 mutants. SBY proves datapath ≡ `f` delayed by K and the stall controller's properties for K = 1, 2, 3, and catches both kinds of mutant | **go** |
| A8 | What does pipelining before a stateful merge change at the pins? | **The interleaving, and not only before the merge.** With the sink always ready, a stage after the merge leaves the packet order unchanged. A stage before it changes the order within 5–19 packets. Under backpressure, even a stage after the merge changes it, because it changes when backpressure reaches the arbiter. Per-source order and content held in every run | understood; feeds §6 |

**Recommendation:** go to D1, with three changes to the plan, all in
`process-synthesis.md` §15:
1. D3's engine inserts registers and a controller, and leaves the balancing
   to a retiming step (yosys/ABC, or the vendor tool's). It does not choose
   cuts at operators.
2. The class-model timing gap G4 is fixed before any pipelined design is run
   as classes.
3. Every check of a merge compares per source.

## A1: the answer key lowers unchanged (F3)

`src/pipe_map_in_key.svh`, `src/pipe_stage_key.svh`,
`src/rr_merge_pipe_key.svh`, lowered by `scripts/gen_rtl.py` into
`rtl/gen/rr_merge_pipe_<variant>.sv`.

| Variant | What | Lowered unchanged | Lint (`-Wall`, besides those `rr_merge` has) |
|---|---|---|---|
| `v0` | as written | yes | — |
| `stall1`, `stall2` | `f_in`, K = 1, 2, one enable per lane | yes | none |
| `elastic1`, `elastic2` | a skid stage per K | yes | none |
| `credit1`, `credit2` | valid-only stages, a FIFO of K + 2, a credit count | yes | 2–4 width warnings (FIFO index arithmetic) |
| `skid` | `skid` on `arb.out → fifo.in` (`rr_merge_skid`) | yes | none |
| `out1` | `f_out`, K = 1 | yes | none |

Every variant has `rr_merge`'s own lint set: DECLFILENAME 1, UNUSEDSIGNAL 1,
WIDTHEXPAND 7, WIDTHTRUNC 4 (`rundir/lint/summary.txt`).

What it took, and where the flow fell short:

- **One class per K.** The stage types differ with K (TM for K = 1; TP and
  TM for K = 2), and a class has no generate-like way to vary its state.
  The engine (D3) generates IR, so this doesn't matter there. It matters
  for hand-written code and for projecting back to source.
- **G1, nested composites** (`rr_merge` inside `rr_merge_pipe`) weren't
  lowered parameterized. Fixed in `composite_param`.
- **G2, packed wires.** zuspec-be-sv declared a composite's internal array
  wires unpacked. Fixed.
- **G3, no arrays of child components**, so the N input maps are one
  N-lane class. Open.
- **Bench results** (`scripts/run_matrix.sh`, `rundir/rtl/matrix.txt`): all 9
  designs pass at W = 8, N = 4 (20 seeds × 3 sink modes), at W = 16 and 32,
  and at N = 2 (3 seeds × 3 sink modes each): 36 configurations, 864 runs.
  Every one runs at 100 beats in 100 cycles with the sink ready.

## A2: measurements (F4)

`scripts/measure.sh`: yosys `synth -flatten` to generic gates, N = 4,
DEPTH = 2. Levels are `ltp -noff`, the gates on the longest path between
flops and ports. Latency is the bench's lone-beat latency.

| Variant | W = 8 cells / flops / levels | W = 16 | W = 32 | latency | beats / cycle |
|---|---|---|---|---|---|
| v0 | 1902 / 85 / 37 | 6973 / 133 / 68 | 26709 / 229 / 119 | 1 | 1.0 |
| stall1 | 1979 / 189 / 31 | 7081 / 301 / 63 | 26739 / 525 / 113 | 2 | 1.0 |
| stall2 | 2173 / 325 / 30 | 7429 / 533 / 61 | 27463 / 949 / 108 | 3 | 1.0 |
| elastic1 | 2211 / 293 / 33 | 7434 / 469 / 64 | 27358 / 821 / 114 | 2 | 1.0 |
| elastic2 | 2753 / 565 / 31 | 8345 / 933 / 61 | 29060 / 1669 / 113 | 3 | 1.0 |
| credit1 | 4811 / 525 / 31 | 11568 / 829 / 63 | 34557 / 1437 / 110 | 3 | 1.0 |
| credit2 | 3732 / 765 / 30 | 9811 / 1229 / 62 | 31502 / 2157 / 112 | 4 | 1.0 |
| skid | 1986 / 137 / 36 | 7144 / 217 / 67 | 26961 / 377 / 117 | 2 | 1.0 |
| out1 | 1930 / 111 / 37 | 7017 / 175 / 68 | 26785 / 303 / 119 | 2 | 1.0 |

What the table shows:

- **Cutting at operators doesn't pay here.** `f_in` alone is 31 / 61 / 122
  levels at W = 8 / 16 / 32, and `a * b` alone is 30 / 63 / 117. The
  longest path in stall2 runs `in_data → a * b → s1_d`. The answer key cuts
  `f` between the multiply and the add, so stage 1 holds nearly all of it.
- **Retiming does pay.** Insert the registers, then run ABC retiming
  (`synth -flatten; dffunmap; abc -dff -D 1`) at W = 32:

  | | levels | flops | cells |
  |---|---|---|---|
  | stall1, retimed | **47** (from 113) | 1150 | 28580 |
  | stall2, retimed | **37** (from 108) | 2059 | 30687 |

  This is indicative only. `abc -dff` retimes through the enable muxes
  `dffunmap` leaves, and the retimed netlists' equivalence wasn't checked.
- **The costs:**
  - stall1 adds about 300 flops at W = 32 (4 lanes × 73 bits).
  - Elastic doubles that, for a `ready` cut at every stage.
  - Credit has the largest area (a FIFO per lane). credit1 has more cells
    than credit2 (fewer flops) because its D = 3 isn't a power of two
    (`% 3` and `i * 3 + rd` indexing).
  - The skid connection costs 148 flops and cuts 2 levels (the `ready` chain).
  - out1 changes nothing: `f_out` is one XOR level.

## A3, A4: roles and the recognizer (F5a, F5b)

- **Roles** (`python/fw/hdl/fe/elab/sync_param.py`, `_channel_roles`):
  - A sync port whose holder fields are exactly `valid` (1 bit, forward),
    `ready` (1 bit, backward) and `data` (forward) is a ready/valid channel.
  - Each flattened `FieldInOut` gets `pragmas` `{channel, channel_kind: rv,
    channel_role, channel_side}`. No new IR node or field.
- **Recognizer** (`python/fw/hdl/spikes/dataflow.py`, `match_map`):
  - It matches `out.valid := in.valid`, `in.ready := out.ready` and
    `out.data := e(in.data)`, with `e` reading only the input's data and
    calling only pure functions of the component.
  - It handles N lanes: one loop per field, each lane reading only its own
    element.
  - Tests (`tests/python/unit/test_pipe_recognize.py`, 13):
    - matches `pipe_map_in` (lanes) and `pipe_map_out`;
    - rejects `rr_arbiter`, `rr_fifo` and `pipe_map_in_stall1` ("has step():
      state") and `rr_merge` ("a composite");
    - rejects 5 near-misses: valid depends on data (a filter), ready depends
      on the input, data depends on `out.ready`, two inputs (a join), and a
      map written with an `if`.

Limits worth knowing:
- The recognizer works on the statement structure: a map written with an
  `if` is rejected, not normalized.
- G6 shapes how users must write maps. `fw_settle` orders `comb()` by
  top-level statement, so a map that mixes `out.data` and `in.ready` in one
  statement makes a false comb loop with any peer that falls back to coarse
  dependencies (the arbiter does). One statement per field is both what
  `fw_settle` needs and what the recognizer wants.

## A5: delay (F5c)

**Route (i)** (`python/fw/hdl/spikes/delay_term.py`, 5 tests). It symbolically
executes the sync-IR function into a zuspec-synth `Term`, specialized at W,
then runs `timing.analyze`. The translator was a small piece of work (about
200 lines with the model characterization). The only built-in model,
`unit`, gives 2 levels at every W, so the spike characterizes one: each
operator synthesized alone by yosys at widths 4–128
(`models/yosys_generic.json`).

| W | `f_in`, model | `f_in`, yosys | `f_out`, model | yosys |
|---|---|---|---|---|
| 8 | 62 | 31 | 1 | 1 |
| 16 | 124 | 61 | 1 | 1 |
| 32 | 236 | 122 | 1 | 1 |

The ranking is right but the estimate is about 2× too high, for two reasons:
- Synthesis absorbs `+ c` into the multiplier's final adder, while an
  additive model charges a full adder for it.
- The model looks the multiply up at its result width (a 2W × 2W multiply),
  where synthesis builds a W × W one.

The same additive view predicts that a cut between `*` and `+` halves the
depth. F4 shows it doesn't.

**Route (ii)** (`python/fw/hdl/spikes/delay_proc.py`, 10 tests; a subagent's
spike, 164 lines). It builds a one-process proc-IR design `forever { x =
get(); put(f(x)); }` and runs `DelayEngine.place`:

- **Cuts fall only at operator boundaries.** `split_assign`
  (`threeaddr.py:36, :48`) makes one assignment per operator, so `f` gets at
  most 2 stages (`mul | add`) at any budget. With a width-scaled model, the
  multiply alone is reported as over budget.
- **The result is multi-cycle, not a pipeline.** Process-loop iterations
  don't overlap (`ir.py:40`), so throughput is 1/k.
- **Below the cost of one operator, `place` drops all its cuts**
  (`sched/delay.py:275`).
- **`optimize()` is too slow for the wide multiply**: over 200 s at W = 16
  (`lower.py:993`).
- About 1,100 lines of zuspec-synth had to be understood.

**Conclusion:**
- Estimation from sync IR is cheap, and route (i) is the one to keep.
- Choosing cuts at the operator level is the wrong tool for an `f` that one
  operator dominates. D3 should either expand operators (partial products,
  an adder tree) before cutting, or insert registers and leave the balancing
  to a retiming step. F4's retiming numbers favour the second, which also
  needs no delay model to be accurate. The model then only has to say how
  many stages, K ≈ ⌈depth / budget⌉.

## A6: the automated slice (F6)

`python/fw/hdl/spikes/pipeline.py`; `scripts/gen_auto.py` writes
`rtl/gen/rr_merge_pipe_auto<K>.sv`.

- **The transform.** `stall_map(match, K)` builds a new `DataTypeComponent`
  from the recognized map:
  - clock and reset ports;
  - the map's ports, with `s<k>_v`/`s<k>_d` stage registers;
  - a `comb` process for the controller;
  - a `step` process that moves every stage on `!s<K>_v || out.ready`, and
    puts `f` in front of stage 1.

  `replace_child` swaps it into the composite. zuspec-be-sv emits the result
  with no change.
- **Bench:** `auto1` and `auto2` pass at W = 8 and 32 (5 seeds × 3 sink
  modes each), with latency 2 and 3 and full throughput.
- **Equivalence** (`scripts/equiv_auto.sh`, `yosys/equiv_pair.ys`): `auto1`
  ≡ the hand-written `stall1`, unbounded (`equiv_induct`), at W = 8, 16 and
  32. 1353 signal pairs were proven and none were left unproven. The
  negative control (`auto1` against `elastic1`) is not proven (12 pairs
  left), as expected.
- **No K = 2 equivalence:** the answer key's `stall2` cuts `f` at its
  operators, and the transform doesn't (see A5). The two are checked on the
  bench and by F7 instead.
- **Projection probe** (`project_class`, `rundir/rr_merge_pipe_auto2_projection.svh`):
  - The channel pragmas are enough to turn the flattened fields back into
    view calls: `out[i].set_valid(s2_v[i])`, `s1_d[i] = f(in[i].get_data())`.
  - What a real projection must restore: `build()` and factory
    registration, the `fw_sp_comb` attributes, parameter defaults, `bit`
    state (it comes back as `logic`), and class-style function syntax.
  - Functions are lowered only when something calls them (a test found
    this), so a projection can't print a function nothing calls.

## A7: checks (F2, F7)

- **The bench** (`tb/pipe_bench.sv`; `tb/pipe_mutant.sv`;
  `scripts/run_rtl.sh`, `run_matrix.sh`, `run_mutants.sh`). Per-source
  scoreboard against an independent 64-bit model, packets whole, every queue
  empty at the end, output protocol monitor, throughput, lone-beat latency,
  and the order of the first 200 packets. Each source's stream is the same
  for a seed whatever the DUT's timing. DUT outputs are sampled through a
  clocking block (`#1step`). All 4 mutants are caught:

  | Mutant | Caught by |
  |---|---|
  | `f` off by one | content check |
  | dropped beat | content check |
  | reordered beat | content check |
  | data changed while stalled | protocol monitor |

- **Formal** (`scripts/formal.sh`, `formal/`; SBY prove mode):

  | K | datapath ≡ `f` delayed K (W = 8, smtbmc/boolector) | wrong shift | controller (2-bit payload, `abc pdr`) | broken `in.ready` |
  |---|---|---|---|---|
  | 1 | PASS | FAIL (expected) | PASS | FAIL (expected) |
  | 2 | PASS | FAIL (expected) | PASS | FAIL (expected) |
  | 3 | PASS | FAIL (expected) | PASS | FAIL (expected) |

  The controller properties:
  - for any index j, the j-th beat out is `f` of the j-th beat in (order, no
    loss, no duplication, content);
  - occupancy is 0..K;
  - `out.ready → in.ready`;
  - a stalled output stays.

  The input protocol is assumed.
- **The argument:**
  - The datapath proof is at full width, with the sink always ready.
  - The controller proof covers backpressure, at a 2-bit payload.
  - The controller never reads the data (`f` runs before stage 1 and the
    rest only moves it), so its correctness holds at any width, by data
    independence.
  - The gap: that the controller is data-independent is argued from its
    structure, not checked. A check that the controller's next-state logic
    doesn't depend on `s*_d` would close it.
- **What didn't carry over:**
  - `cosynth/equiv.py`'s harness hard-codes the AES case (`key`, `block_`
    ports), so only its pattern was reused.
  - sv2v drops `assert`/`assume`. The first harness was vacuous until the
    properties were moved out of the sv2v path.
  - Default SBY needs yices, which isn't installed: use `smtbmc boolector`
    and `aigsmt boolector`.

## A8: interleaving at a merge (F2, F4)

The same per-source streams (seeds 1, 2) and the same sink modes, comparing
the source order of the first 200 packets out with v0's:

| Seed, sink | stall1 | stall2 | out1 |
|---|---|---|---|
| 1, always ready | differs from packet 17 | from 12 | **same** |
| 1, 50% | from 17 | from 18 | from 18 |
| 1, bursty | from 19 | from 19 | from 85 |
| 2, always ready | from 5 | from 5 | **same** |
| 2, 50% | from 129 | from 152 | from 107 |
| 2, bursty | from 39 | from 39 | from 39 |

A stage before an arbiter changes which inputs are valid when it decides. A
stage after it changes, under backpressure, when the arbiter sees `ready`.
The per-source checks passed every time. In E1 terms, an arbiter's
interleaving isn't ordered against latency anywhere around it, so a check or
a rule about a merge must be per source. A design that needs a fixed
interleaving must say so, as an ordering rule (§6.6).

## The class model (F1): blocked by G4

**Closed (2026-11-21).** The two-phase edge of
[`sync-task-domains.md`](../../docs/design/sync-task-domains.md) (X2, §8.3)
evaluates every `step()` and then commits, and settles comb after the
commit, so `mout`'s comb output is current at the pins. `dfm run sim`
passes: `PASS: rr_merge_pipe (classes) sink=1: 1159 beats`. The finding
below is kept as it was found.

The classes weave and elaborate, but they fail the bench: lone-beat latency
is 2 against the RTL's 1, and beats are taken twice.

- **The cause.** The kernel evaluates edge T with the values from before T
  (`fw_sync_kernel.svh:252-272`). `fw_rv_pin` corrects for that only when a
  pin reads a sync field directly (`fw_rv_pin.svh:119-133`). Here `mout`'s
  comb output is computed from `rr_fifo`'s registered `out`, so at the pins
  it is one edge late.
- **The evidence.** With `mout` removed, the class model passes, with
  latency 1.
- **Why it matters.** Any comb logic after a register at an output pin hits
  this. In pipelined designs that is the norm, so every variant would fail
  as classes.
- **Suggested fix:**
  - a look-ahead settle for the pin bridges' comb values: commit, settle,
    record, restore;
  - or move the kernel's commit after the steps, which conflicts with
    `after_tick` and the early-write guard.

Other class-model gaps found:
- **G5:** sv-weave identifies specializations by their printed spelling, so
  specializations from different packages collapse into one
  (`sv_weave/frontend/specialize.py:37-39`, `model.py:444-450`). The vehicle
  works around it by including `rr_merge`'s `.svh` rather than importing
  `rr_merge_pkg`.
- **G6:** described under A3, A4.

## Where the bench should live

`tb/pipe_bench.sv` is specific to this example's beat (`tag` = {source,
seq}, the `f_out(f_in(x))` model). What generalizes is its structure:
- per-source queues of expected beats, filled by a model;
- attribution by a source field;
- packets checked whole;
- a monitor of output stability;
- timing-independent per-source streams;
- clocking-block sampling.

That belongs in fw-proto (the family strategy: fw-proto owns transactors),
parameterized by a beat type, a source-of function and a model. It should
move when a second user appears, not before.

## `@zdc.pipeline`

Nothing to reuse in code. It has no ready/valid backpressure and cuts by
integer operator latencies. Its idea of a per-stage valid with a global
stall is the `stall` controller here, which took about 30 lines of IR to
build.
