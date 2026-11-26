# Task-sync crossings in fe-sv (M6): plan

This is the plan for step M6 of [task-sync-crossings.md](task-sync-crossings.md):
fe-sv checks which side of a crossing (`fw_to_sync`, `fw_from_sync`) each
piece of code uses, and lowers the sync side of a component that owns
crossings to ready/valid ports on its module. M1–M5 are done (that doc's
§0). The design's §6 sketch is taken as given; this file adds what
implementing it needs and the decisions it raises (§3).

---

## User benefit

- **A transactor's sync half becomes RTL.** `wb_initiator` (and std's
  `fw_rv_initiator`, `fw_rv_get_ep`) emit as plain SV modules. The pins
  come from `step()`/`comb()`, and each crossing becomes a ready/valid
  port. The same class that runs in the bench is what's synthesized or
  proven formally, with no hand-written core.
- **The outside of a lowered crossing is std's ready/valid endpoints.**
  The task side stays in simulation: a `fw_rv_initiator` drives
  `reqs_valid`/`reqs_data`, a `fw_rv_get_ep` takes the response. No new
  harness, and the timing is the class model's (a call at edge *k* is on
  the pins for edge *k* + 1).
- **Misuse is caught at elaboration, not at run time.** Using the
  process side from `step()`, `take`/`give` in `comb()`, or another
  component's crossing are static errors (`FW-E-XING-SIDE`,
  `FW-E-XING-COMB`) with a source location, instead of a run-time report
  on the path that happens to run.

## 0. Status

| Step | State |
|---|---|
| Plan (this doc) | 2026-11-24: written; D1 settled (S0); D2–D5 confirmed as proposed (2026-11-24) |
| Overall | 2026-11-24: S0–S7 done. Final regression: fw-hdl-fe-sv 454 pass; wb system tests 5 pass. Follow-ups: §4d (std outside endpoint: done, §4f), §4c (module names vs class names: a Verilator bug, §4g), optional yosys equivalence |
| S0 IR representation | done: new `DataTypeSyncXing` (D1 note) |
| S1 fe-sv: crossings as objects and IR fields | done: `FwXing`; IR field; netlist `kind: xing` |
| S2 ProcMapper: crossing calls | done: calls mapped; `ProcBlock.xing_uses`; block locals typed |
| S3 Static side checks + conformance | done: `check_sync_xing`; 3 scenarios pass on fe-sv and rt-sv. Regressions 2026-11-24: fw-hdl-fe-sv 447 pass; zuspec-fe-sv 161; zuspec-ir-core 244; rt-sv conformance 106 pass / 0 fail; wb system tests 4. zuspec-synth's full suite has 55 fail + 96 errors, all from setup (missing example modules, `pyslang.Compilation`, `docs/rationale`, cast width in `test_proc_to_core`); its domain tests pass |
| S4 IR lowering pass | done: `sync_xing_lower`; be-sv locals/casts; `wb_initiator` emits lint-clean (`rsps_ready`: §4h) |
| S5 Spec: lowering rules | done: processes.md "Lowering" › "Task-sync crossings"; `FW-E-XING-LOWER` in diagnostics.md |
| S6 std rv xtors emit + run | done: `test_sync_xing_mixed.py`; lowered `fw_rv_initiator` = class bench (`got 20 span 26 stall 6`); lowered `fw_rv_get_ep` = class-only reference line for line |
| S7 `wb_xtor` initiator emits + bench | done: `run_mixed.sh`, `test_wb_xtor.py::test_mixed`: 149 / 185 edges, `+mut_tgt` fails as in the class bench. Not done: yosys equivalence (optional) |

Logs go under `build/m6-*.log`.

## 1. Where things are today

- **fe-sv** records each `create` in `FeRt.xings`
  (`packages/fw-hdl-fe-sv/python/fw/hdl/fe/sv/rt.py:91`, `create_xing`
  :340) and nothing else: no `FwObject`, so a crossing isn't a child of
  its component and the IR mapper (`ir_map.py`) never sees it.
- **ProcMapper** (`packages/zuspec-fe-sv/src/zuspec/fe/sv/proc_mapper.py`)
  maps `step()`/`comb()` to IR. Its only library-method cases are
  `read()`/`write()`/`in_reset` (`_map_call` :216). `reqs.valid()` falls
  through to `ExprCall(ExprRefLocal("valid"))`, which zuspec-be-sv
  rejects ("unsupported expression ExprCall", `proc_emit.py:175`). The
  crossing handle isn't integral, so it isn't in the field context.
- **Run-time checks** exist in rt-sv (`fw_rt_xing.svh` `sync_ok`,
  `proc_ok`). There are no static checks and no conformance scenarios.
- **Naming clash:** IR `XingPort` / `check_xing`
  (`zuspec-synth/.../passes/domains/xing.py`) and the `xing_*` scenarios
  are the older *signal* crossings (task code touching signals), not
  these. New names below use `sync_xing` / `SyncXing` to keep them apart.

## 2. The lowering

For a crossing `x` owned by component `C`, `C`'s module gets:

| Crossing | Ports | Sync-side call → RTL |
|---|---|---|
| `fw_to_sync #(T) x` | in `x_valid`, in `T x_data`, out `x_ready` | `x.valid()` → `x_valid`; `x.peek()` → see D2; `x.take(t)` in `step()` under path condition *c* → `x_ready = c` (comb), `t = x_data`, returns `x_valid` |
| `fw_from_sync #(T) x` | out `x_valid`, out `T x_data`, in `x_ready` | `x.ready()` → `x_ready`; `x.waiting()` → see D3; `x.give(v)` in `step()` under *c* → `x_valid = c`, `x_data = v` (comb), returns `x_ready` |

The handshake is the edge where `valid && ready`, which is when rt-sv
applies the staged `take`/`give`. `depth` doesn't change the module: the
queue lives on the outside (the endpoint that drives the port), so depth
is the outside's concern.

**`x_ready`/`x_valid` come from `step()`'s control flow.** `step()`
lowers to `always_ff`, but the handshake signal it decides is
combinational. The pass builds a comb block that is a slice of `step()`:
the same locals and conditions, every field/signal write dropped, the
output defaulted to 0 at the top and set to 1 (with the data) at each
`take`/`give` site. Reads in `step()` see pre-edge values, so evaluating
the slice combinationally gives the same condition. Several call sites
OR together; the data is muxed by site (last site wins, as in SV).

## 3. Decisions (confirmed 2026-11-24)

- **D1 IR representation.** A crossing is a component field of a new IR
  type `SyncXingType(dir, item_type)` (dir = `to_sync` | `from_sync`),
  and its methods stay as `ExprCall(ExprAttribute(ExprRefField(x), m))`
  until the lowering pass. S0 first checks whether IR's existing
  `QueueType` (`zuspec-ir-core data_type.py`) fits instead; reuse it if
  so. The lowering is a zuspec-synth pass, not fe-sv code (AGENTS.md:
  prefer IR transforms).
  *S0 outcome:* `QueueType` doesn't fit: it is a FIFO inside one component
  (zdc `Queue`, synthesized as a FIFO), with no direction and no sides.
  `DataTypeChannel` is a TLM channel, also without sides. Added
  `DataTypeSyncXing(direction: SyncXingDir, element_type, depth)` to
  zuspec-ir-core `data_type.py`, and `SyncXingUse(path, method)` /
  `ProcBlock.xing_uses` to `proc_block.py`.
- **D2 `peek()` when empty.** The spec says it returns the type's
  default. Proposed: lower exactly, `x_valid ? x_data : '0`, so the
  lowered module matches the class model edge for edge. Alternative:
  `x_data` raw, and change the spec to "unspecified when `!valid()`"
  (cheaper RTL; wb's `adr`/`dat_w` would then show the driver's data
  while `stb` is low).
- **D3 `waiting()`.** std's rv target and get endpoint drive pin `ready`
  from `waiting()` (a `get` is blocked, nothing queued), not `ready()`
  (there's room). Proposed: a separate input `x_wait`, emitted only when
  `waiting()` is used, and `x_ready` only when `ready()`/`give` is used.
  The outside `fw_rv_*` endpoint already has that distinction.
- **D4 Port names.** `<x>_valid`, `<x>_ready`, `<x>_data` (flattened like
  bundles). Alternative: one rv bundle per crossing (same pins, grouped
  in the IR).
- **D5 Components with a `run()`.** `wb_target` and `fw_rv_target` keep
  `FW-E-EMIT-RUN`. Only components whose task code is export tasks
  (`access()`, `put()`) emit; those tasks are dropped from the module.
  Splitting a `run()` target into an emitted core plus a sim-only shell
  is out of scope for M6.

## 4. Steps

- **S0 IR representation.** Read `QueueType`, `IfProtocolType` and how
  `DataTypeComponent` fields carry types; pick D1's form. Output: a short
  note appended to §3 D1.
- **S1 fe-sv objects and IR fields.** `create_xing` makes an `FwObject`
  (kind `xing`, dir, item type, depth) under its component.
  `IrMapper` emits a field of D1's type for each; the netlist lists them.
  Unit test: elaborate std's `fw_rv_initiator` and find the field.
- **S2 ProcMapper.** Put crossing fields in the context; map
  `valid/peek/ready/waiting` as expressions and `take/give` as calls
  with their out argument and return value kept, keyed on
  `_owner(sub) in ("fw_to_sync", "fw_from_sync")` the way `_Scan` keys
  on `fw_*`. Record per block which crossing methods it uses.
- **S3 Static checks + conformance.** Over the IR proc blocks (a
  `check_sync_xing` pass next to `check_xing`): `FW-E-XING-COMB` for
  `take`/`give` in comb; `FW-E-XING-SIDE` for process-side methods in
  step/comb, sync-side methods in task code, and a crossing used by a
  component that isn't its owner. Conformance scenarios in fw-hdl-spec
  (`sync_xing_ok`, `sync_xing_comb_bad`, `sync_xing_side_bad`) with
  `expect.json`; this also closes most of M3.
- **S4 Lowering pass** (zuspec-synth, before `flatten_structure`): add
  the ports (§2, D3, D4), build the comb slice for `x_ready`/`x_valid`/
  `x_data`, rewrite the sync-side calls in `step()`/`comb()` to port
  refs, drop the crossing fields. Unit tests on hand-built IR.
- **S5 Spec.** `semantics/processes.md` "Lowering": the §2 table, D2, D3,
  and that depth lives outside.
- **S6 std emit + run.** e2e tests in `fw-hdl-fe-sv/tests/e2e`
  (model: `test_proc_emit.py`): emit `fw_rv_initiator` and `fw_rv_get_ep`;
  check the ports; run each lowered module under `fw_pin_bridge` with
  std rv endpoints on its crossing ports and compare timing with the
  class model (as `test_rv_mon_mixed` does).
- **S7 `wb_xtor`.** Emit `wb_initiator #(32,32)`; add a mixed bench
  (lowered initiator + rv endpoints on `reqs`/`rsps` + the class
  `wb_target` and memory) and require the class bench's results:
  `R ok 40 accesses in 149 edges` / `185` with `+rand`, mutants fail.
  Add it to `tests/python/system/test_wb_xtor.py`. Optional: yosys
  equivalence against fw-proto-wb's `wb_initiator_xtor_core`
  (`examples/wb_initiator/ref/`) if the interfaces line up.

## 4a. What S0–S3 changed

- **zuspec-ir-core:** `SyncXingDir`, `DataTypeSyncXing` (`data_type.py`);
  `SyncXingUse`, `ProcBlock.xing_uses` (`proc_block.py`).
- **fw-hdl-fe-sv:** `FwXing` (`objects.py`); `create_xing` registers it
  as a child (`rt.py`); `_xing_field` in the concrete and parameterized
  paths, `_ekey` for the type (`ir_map.py`); netlist entry `kind: xing`
  with `dir`, `type`, `depth` (`netlist.py`); `check_sync_xing` runs in
  the domain passes at elaboration (`domains.py`); ProcMapper gets
  `type_fn=self._type` so step/comb locals map.
- **zuspec-fe-sv `proc_mapper.py`:** `_Scan` records `(path, method)` of
  `fw_to_sync`/`fw_from_sync` calls; in bodies the call is
  `ExprCall(ExprAttribute(<field>, m), args)` (an output argument as its
  target); a user task (not in fw_hdl_pkg) that uses a crossing is a
  `TASK` block named for it (be-sv skips `TASK` blocks); `type_fn`
  parameter for locals. Fixes found on `wb_initiator`: `_owner` drops
  parameter lists before splitting on `::` (a class-local payload type
  is `fw_to_sync#(...wb_initiator::req_t)::take`); the scan enters a
  local's initializer (`req_t r = reqs.peek();`); a write to a member of
  a block-local struct (`p.dat = ...`) is not `FW-E-WRITE-PATH`.
- **zuspec-synth:** `passes/domains/sync_xing.py` `check_sync_xing`.
- **fw-hdl-spec conformance:** `sync_xing_ok` (trace, from X3–X5; rt-sv
  agrees), `sync_xing_side_bad`, `sync_xing_comb_bad`; README rows.
- **Tests:** `fw-hdl-fe-sv/tests/unit/test_sync_xing_ir.py` (fields,
  uses, the mapped `take`, netlist entry; class-local payload, depth 2,
  export task; concrete and parameterized).
- **Found for S4:** be-sv's proc emitter (`proc_emit.py` `stmts`) takes
  only assign/if/pass: no `StmtAnnAssign` (block locals) and no
  expression statements (`void'(x.give(p))`), which `wb_initiator`'s
  `comb()`/`step()` and the scenario's `step()` use. S4 (or a be-sv
  change) has to handle them.
- **Found for S7:** `wb_initiator #(32,32)` maps with no diagnostics, but
  as a specialization (`FW-I-EMIT-SPEC`: its `pins` bundle type can't be
  written over AW/DW yet), so its module wouldn't be parameterized.

## 4b. What S4 changed

- **zuspec-synth `passes/sync_xing_lower.py`** `lower_sync_xings(ctxt)`,
  run by fe-sv `emit_sv` before `flatten_structure`:
  - each crossing field becomes `<x>_valid`/`_ready`/`_data` ports (plus
    `<x>_wait` when `waiting()` is used), in the field's place; other
    field indices are remapped;
  - calls rewritten as §2; `peek()` and `take`'s output are
    `x_valid ? x_data : T'(0)` (D2; SV copies an output argument's default
    back when `take` returns 0);
  - per step block with `take`/`give`: a comb block `<step>_xing` (the
    step with field/signal writes dropped, `ProcBlock.state` fields as
    local copies, handshake defaults then 1 at each call; under
    `!in_reset` when the step has a reset branch); dead locals and empty
    `if`s removed. A step left with only local writes is dropped (it only
    handed off): `wb_initiator` lowers to two comb blocks;
  - task blocks dropped (D5);
  - a child's crossing ports are lifted to the parent as
    `<child>_<port>`, with binds, up to the top;
  - `SyncXingLowerError` `FW-E-XING-LOWER`: `take` into a non-local,
    `take`/`give` outside `if` (loops, cases), one crossing handed off by
    two step blocks, a crossing used other than by a method call, child
    arrays with crossings.
- **zuspec-be-sv:** `proc_emit.py` declares block locals at the top of
  the `always` block (`StmtAnnAssign`; blocking; `'0` without an
  initializer); `ExprCast` to a `DataType` prints `T'(v)`/`N'(v)`;
  `structural.py` passes its type naming in and collects the types of
  block locals and casts for the types package.
- **Tests:** `fw-hdl-fe-sv/tests/e2e/test_sync_xing_emit.py` (ports,
  slice with an `in_reset` branch, a state variable and `waiting()`;
  lifting; lint; `take` into a field is an error).
- **Behaviour to note:** `x_valid` of a `give` does not depend on
  `x_ready` (ready/valid style); a give without room transfers nothing,
  as in the model. Code that discards give's result leaves `x_ready`
  unread: `wb_initiator`'s `rsps_ready` lints as `UNUSEDSIGNAL`.
- **Limit:** one handshake per crossing per edge (the model's second
  `take`/`give` in an edge moves the next item; one port can't).
- **Regressions 2026-11-24:** fw-hdl-fe-sv 451 pass. zuspec-be-sv: 6
  fail in `generator.py` (`_collect_local_vars` arity) and old smoke
  tests expecting `always @(...)`, not in the files S4 touched.
- **Not done:** hand-built-IR unit tests in zuspec-synth (the e2e tests
  cover the pass through fe-sv); simulation against the class model is
  S6/S7.

## 4c. What S6 changed

- **fe-sv `emit_sv(rename=...)`:** renames component types (module
  names). A module named like a class compiled in the same simulation
  (`fw_rv_initiator`) crashes Verilator 5.055 (internal error in
  V3Ast.h); the mixed tests emit `fw_rv_initiator_rtl`. Open question for
  later: should emission avoid std class names by default?
- **Tests** `fw-hdl-fe-sv/tests/e2e/test_sync_xing_mixed.py`, sources in
  `tests/e2e/sv/sync_xing/`:
  - `rvi_emit.sv` emits a top with std `fw_rv_initiator` (pins connected
    up); the module has `parameter type T`, no `always_ff` (its step only
    handed off). `rvi_mixed.sv`: class `fw_rv_initiator` on the lifted
    `xi_req_*` ports, the stalling RTL target of rt-sv's
    `pin_bridge_rv.sv`: `R got 20 span 26 stall 6 drops 0 bad 0`, as the
    class-only bench.
  - `rvg_emit.sv` / `rvg_mixed.sv`: std `fw_rv_get_ep`; module
    `rvg_class` (class endpoint on the RTL source) and `rvg_mixed` (the
    lowered one between, its `rsp_ready` and `rsp_wait` both from the
    class endpoint's ready) print the same: `R sent 30 got 30 bad 0`,
    `R ready low 93 stall 9`.

## 4d. What S7 changed

- `examples/wb_xtor`: `tb/wb_emit.sv`, `scripts/emit_rtl.py`,
  `tb/wb_xtor_mixed.sv`, `scripts/run_mixed.sh`; `check()` in
  `wb_xtor_tb.sv` now calls `check_parts(d, k, m)`, which the mixed bench
  uses; README files, results and findings.
- `tests/python/system/test_wb_xtor.py::test_mixed`.
- **Found:** the outside of a lowered `fw_from_sync` must be ready on
  *room*, with `waiting()` separate: std's `fw_rv_get_ep` (ready while a
  get waits) drops `wb_initiator`'s response, given in the edge of the
  take, before `access()` reaches its `get`. The bench defines
  `rsp_ep_c` (ready = `q.ready()`). S6's get-endpoint test passed with
  `fw_rv_get_ep` outside because the lowered endpoint gives only while
  waiting. Follow-up: a std endpoint for the outside of a lowered
  `fw_from_sync` (ready = room, plus a `wait` output from `waiting()`).
- `+mut_init` isn't run mixed: its `comb()` keeps state (`up |= ...`), a
  latch.
- Yosys equivalence against `examples/wb_initiator/ref` not attempted
  (optional in the plan).

## 4e. Throughput (2026-11-24)

One `take`/`give` per crossing per edge is one item per clock, a
ready/valid port's full rate; it rules out two items in one edge, not
back-to-back transfers. `test_rv_initiator_one_per_cycle` (always-ready
target, `+always_ready` in `rvi_mixed.sv`): the lowered `fw_rv_initiator`
moves 20 items in 20 cycles, valid high throughout (`span 20 stall 0
drops 0`). The put of item *n*+1 follows the return of put *n* at the
handshake edge and is on the pins in the next cycle (X3).

## 4f. Problem 1: std outsides of lowered crossings (2026-11-24)

- **std:** `fw_to_sync_ep #(T, DEPTH)` (`fw_to_sync_ep.svh`) and
  `fw_from_sync_ep #(T, DEPTH)` (`fw_from_sync_ep.svh`): the process side
  of a lowered crossing on its ready/valid ports, holding the crossing's
  queue of the crossing's depth; `put`/`try_put`, `get`/`try_get` (with
  `fw_put_if`/`fw_get_if` exports). `fw_from_sync_ep`'s `ready` is the
  queue's `ready()` (room) and its `waiting` output is `waiting()`, for
  `<x>_wait`. `fw_rv_get_ep` keeps its "ready only while a get waits"
  (deliberate, checked by rt-sv's `rv_ep`). docs/std.rst, processes.md
  "Lowering".
- **Benches:** `wb_xtor_mixed.sv` uses both (its `rsp_ep_c` is gone);
  `rvg_mixed.sv +lowered` uses `fw_from_sync_ep`, `rsp_wait` from its
  `waiting`. New `test_depth2_mixed` (`dep_pkg.sv`, `dep_emit.sv`,
  `dep_mixed.sv`): depth-2 crossings, class vs lowered: `R put 0 0 1 2 4 5
  7 8`, `R get 3 3 6 6 9 9 12 12 bad 0` in both.
- **Confirmed** that `fw_rv_get_ep` as the outside of `wb_initiator`'s
  `rsps` loses the response: `R fail 0 accesses returned`.
- **Regressions:** fw-hdl-fe-sv 458 pass; fw-hdl-rt-sv 27 pass (with
  conformance); `test_wb_xtor.py` 3 pass.

## 4g. Problem 3: module names that match class names (2026-11-24)

- **Cause:** a Verilator 5.055 bug, not a naming rule. SV keeps modules
  (definitions name space) apart from package classes, and pyslang
  accepts a module and class of one name. Verilator fails (internal error,
  `V3Ast.h:1173 ... has type 'MODULE'`) only when both are parameterized
  *and* specialized with the same value. Different values, an
  unparameterized side, or a module at its defaults compile, with or
  without an import. Minimized in
  `docs/design/probes/xing-lowering/verilator-bugs/` (no matching
  upstream issue found).
- **Where it bites:** a mixed bench that runs a parameterized class beside
  its own lowered, still-parameterized module, e.g. `fw_rv_initiator
  #(item_t)`. `wb_initiator #(32, 32)` emits with its values folded (no
  parameters), so the `wb_xtor` mixed bench gives 149/185/mut-fail with
  no rename. Its rename is harmless and stays.
- **Decision (proposed):** emission keeps class names by default: the
  shipped RTL is named after its class, and the clash only arises in a
  mixed bench under Verilator. Such benches use `emit_sv(rename=...)`,
  whose docstring now states the actual cause.

## 4h. Problem 2: `wb_initiator`'s unread `rsps_ready` (2026-11-24)

- **Cause:** `step()` discarded `rsps.give(p)`'s result, assuming the
  depth-1 response crossing has room at every termination. That holds in
  the bench (the caller is in `get` before the request is taken), but
  nothing in the class enforced it, and a Wishbone termination can't be
  refused, so a full `rsps` would drop the response silently.
- **Fix (in the class, not the lowering):** `comb()` raises `cyc`/`stb`
  only while `reqs.valid() && rsps.ready()`. The emitted module reads
  `rsps_ready` in its comb block; Verilator `-Wall` lint clean.
- **Results unchanged:** class and mixed benches 149 / 185 edges, 7 back
  to back, mutants fail as before; `test_wb_xtor.py` 3 pass.
- **std checked:** `fw_rv_xtor` and `fw_from_sync_ep` also discard
  `give`'s result, but only on a ready/valid handshake whose `ready` is
  the crossing's room, so they're already guarded.
- **Possible follow-up (not done):** a lint in `check_sync_xing` for a
  discarded `give` with no `ready()` read in the same component.

## 5. Risks

- **Slicing `step()`** must keep locals that feed a condition but drop
  writes, including writes to locals that only feed dropped writes (dead
  code, harmless). Loops and function calls in `step()` need the same
  treatment as the step mapper already gives them; if a condition
  depends on a call to the component's own function, the slice calls it
  too.
- **`give`'s return used as state** (`busy = reqs.give(r)` in
  `wb_target`): the return is `x_ready` and the transfer is `c && x_ready`;
  covered by D5 for now, since `wb_target` doesn't emit.
- **Packages touched:** zuspec-ir-core (type), zuspec-fe-sv (ProcMapper),
  zuspec-synth (passes), fw-hdl-fe-sv (rt, ir_map, tests), fw-hdl-spec
  (spec, conformance). Each is its own repo under `packages/`.
