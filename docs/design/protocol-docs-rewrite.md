# Protocol docs and skills: rewrite around task-sync crossings

## User benefit

Someone writing a protocol kit or a transactor from the fw-hdl-spec docs or
the `fw-proto-kit` / `fw-hdl` skills writes code that compiles and lowers on
the first try. Today the prose teaches `declare()`, `d.api(...)` and
`` `fw_bundle_protocol ``, none of which exist, and transactors that drive pins
from `run()` through mailboxes, which don't lower. The code shown in the same
pages (literalincludes) is already the new form, so the prose contradicts the
code right above it.

## §0 Status

- 2026-11-27: research done (map below), plan drafted. Owner: "redo the
  protocol docs and skill to align with the new approach of using a fw-hdl
  domain crossing". Phase 1 in progress.
- 2026-11-27: Phase 1 steps 1-4 done (uncommitted). Sphinx build of
  fw-hdl-spec docs: 0 warnings (added `fw_no_api` to `api/protocols.rst`).
  sbus `check.py` passes. Left for later: `conformance/proto_prefix` and
  `proto_api_dup` `meta.json` descriptions and `semantics/netlist.schema.json`
  (413, 616) still say `declare()`/`fw_bundle_protocol`; `processes.md`
  "Lowering" doesn't state the hand-off-only `run()` exception that
  zuspec-fe-sv `proc_mapper.py` implements.
- 2026-11-28: owner decided §3.1-3.4. Phase 2 = steps 9-11 (§2a). Step 11
  in progress; step 9 impact study in progress.
- 2026-11-28: step 11 done (uncommitted). New spec example
  `docs/examples/apb` (APB-style, plain signals, hand-written initiator +
  target on task-sync crossings, reset_state; bench with a mutant;
  `check.py` = rt-sv sim + mutant FAIL + fe-sv elaborate + emit/lint;
  `dfm run check`; pytest fw-hdl-fe-sv `tests/e2e/test_spec_examples.py`
  runs sbus and apb check.py, closing step 7's test half). `behaviour.rst`
  "Hand-written transactors" and `protocols.rst` Transactors rewritten on
  it; terminology pass; `processes.md` Lowering and `diagnostics.md` state
  the hand-off-only `run()` exception; meta.json/schema descriptions fixed;
  skill caveat removed, fw-proto-kit points at apb. Sphinx 0 warnings.
  Found: `reset_state()` with no reset domain crashes zuspec-be-sv emit
  (ValueError, no diagnostic); a target's API port must be bound at a
  lowering top though run() is dropped.

- 2026-11-28: step 11 verified: `fe-sv tests/e2e/test_spec_examples.py` (sbus +
  apb check.py) 2 passed. Uncommitted in fw-hdl-spec (docs, semantics,
  conformance meta, skill, `docs/examples/apb/`), fw-hdl-fe-sv (the test) and
  fw-hdl (`skills/fw-proto-kit`). Found while building apb: be-sv crashes
  (ValueError, not a diagnostic) on `reset_state()` with no reset domain; a
  lowering top must bind a target's port though its `run()` is dropped; a call
  made during reset is silently lost (X8) unless the caller waits.
  Next: owner decisions in §4, then step 9.
- 2026-11-28: owner accepted §5 resolutions (step 9b). §4 decided (§4a):
  recorder; field writes stay; task code neither reads nor writes signals.
  Step 9 in progress, revised sequence in §4a.
- 2026-11-28: step 9.1 done (uncommitted): `fw_rv_monitor` is a `step()`
  (std `fw_rv_xtor.svh`). rt-sv tests + fe-sv `test_proc_emit`,
  `test_gen_bind`, `test_gen_xtor`: 54 passed. Next: 9.2.
- 2026-11-28: step 9.2 done (uncommitted): static `FW-W-TASK-SIGNAL` (on
  the component, one per signal, naming the tasks) from zuspec-synth
  `check_xing` over Zuspec IR task blocks; zuspec-fe-sv ProcMapper now
  lists only signals in task blocks' `reads`/`writes` and makes a task
  block for every user task that touches a signal (export API tasks
  included). Row in spec `diagnostics.md`. Shipping code (std, apb, sbus,
  wb_xtor, GenKit) gives none; 13 conformance scenarios warn, listed in
  fe-sv `test_conformance.py` `TASK_SIGNAL` (empties in 9.3). Next: 9.3.
- 2026-11-28: step 9.3 done (uncommitted): recorder `test_rec #(T)`
  (spec `conformance/_lib/test_rec.svh`: `put(v)` into a depth-4
  `fw_to_sync`, `step()` writes `o`; rows one edge later). 10 scenarios
  rewritten (edge_div, proc_time, proto_timed, sync_xing_ok, xing_edge_time,
  xing_zero_time on the recorder; proc_run_put, xing_rv_default on
  `fw_rv_initiator`; xing_write_multi = two comb blocks, now lowerable;
  sync_xing_side_bad's run() writes a field), xing_drive_twice deleted.
  Left for 9.4 (pure crossing-port tests, delete with C1-C8): xing_access,
  xing_sample_drive = fe-sv `TASK_SIGNAL`. 9.4 must keep C4/C7 (X5 cites
  them; xing_edge_time, xing_zero_time test them). rt-sv conformance pass;
  fe-sv conformance 112 passed 6 skipped, `test_task_signal` 3,
  `test_proc_emit::test_expected_diags` 3. Next: 9.4.
- 2026-11-28: step 9.4 done (uncommitted). Spec `processes.md`: "Crossings"
  (C1-C8) deleted; new "Task code" section states the rule (task code
  neither reads nor writes signals, `FW-E-TASK-SIGNAL` on the component)
  and re-homes the timing as T1 Position (at edge *k* / between edges,
  entering a domain costs a wait), T2 Order (was C4), T3 Zero time stays at
  the edge (was C7); X5 cites T2, T3. Task parts of Request-update,
  Register or wire, Domain of a process, the edge and sync-subtree text
  gone. `diagnostics.md`: `FW-E-TASK-SIGNAL` added (static form still
  `FW-W-`), `FW-E-RUN-SYNC-ACCESS` and `FW-E-XING-DRIVE-TWICE` retired,
  `FW-E-WRITE-MULTI` loses its task clause; `connections.md` IN-OPEN task
  exception gone. Conformance: `xing_access`, `xing_sample_drive` deleted;
  `task_signal_bad` added, PENDING in rt-sv `conformance.py` (9.5) and fe-sv
  `test_conformance.py` (9.6; fe-sv gives the `FW-W-` on the expected
  paths); `TASK_SIGNAL` mechanism removed. Schema ID regex takes
  multi-part WHATs; `edge_period_bad` gained a trace: schema 117/117.
  Sphinx 0 warnings; rt-sv `test_conformance.py` 6 passed; fe-sv
  conformance 110 passed 7 skipped. Left for 9.5/9.6: rt-sv comments
  citing C2-C5/C7 and zuspec-synth/ir-core "crossing port" code.
  Next: 9.5.
- 2026-11-28: step 9.5 done (uncommitted). rt-sv `fw_signal::read()`/
  `write()` report `FW-E-TASK-SIGNAL` (`__fw_rt_procs::task_signal`) when
  no block is in `call()` and `runs_started`: on the accessed signal's
  component (`scope()`, the one whose code names it; the thread can't tell
  for export tasks or forks), once per signal; the write is ignored, a read
  returns the current value. Kernel paths use cells directly, never
  read/write. Deleted: `write_now`, `xbase`/`mark_base`, `task_wr`,
  `tsamp`/`tproc`/`ttime`/`twice`, `drives`, FW-E-XING-DRIVE-TWICE, run()
  writer learning, read()'s pre-edge value for task code; `at_edge` stays
  for `wait_reset` (T1). C comments → T2/X3/X5. sv/ 4663 → 4630 lines.
  `task_signal_bad` un-pended, passes. rt-sv 27 passed; fe-sv e2e 113
  passed, 1 failed (`test_timed_chan`: static component set misses the 9.3
  recorders in `proto_timed`; not 9.5); `dfm run tests` 11 passed. X8 not
  done. Next: 9.6.
- 2026-11-28: step 9.6 done (uncommitted). Static check is the error
  `FW-E-TASK-SIGNAL`: new zuspec-synth pass `passes/task_signal.py`
  (`check_task_signal`, over `Resolution`, no domains needed; `domains/xing.py`
  deleted). fe-sv `domains.passes` runs it on every design (no domain kinds
  too) and in `explore()` runs; an explored arm's diagnostics go to the
  parameterized emission's `ir_diags`. API functions: ProcMapper records
  `ProcBlock.port_calls` and `DataTypeComponent.api_impls` (new ir-core
  `PortCall`, `ApiImpl`); the pass follows port calls from task blocks through
  `api_connections` (connect, connect_up, socket peers, `imp`) to the
  implementation, a function too. Removed: `XingPort`, FW-E-RUN-SYNC-ACCESS,
  WRITE-MULTI task clause, C5 default, fe-sv IN-OPEN task-write exception
  (`_task_written`, ProcMapper `task_writes`). Spec: `FW-W-TASK-SIGNAL` row
  dropped and noted retired; skill updated; `task_signal_bad` un-pended.
  Tests: zuspec-synth same 55 failed/96 errors as baseline, 1287 passed (+5);
  ir-core 263; zuspec-fe-sv 167; be-sv 264 passed, 6 failed (pre-existing,
  same with ir-core stashed); fe-sv full 471 passed 6 skipped; apb and sbus
  check.py pass; `dfm run tests` passes. Next: 9b (§5).
- 2026-11-28: step 9b.2 done (uncommitted). New zuspec-synth pass
  `passes/lower_check.py` (`check_lowering`, over `Resolution`): a lowered
  top whose default reset resolves to null is `FW-E-DOM-NONE` on the top
  when the design has process code (structural/extern-only designs exempt;
  owner may want it stricter); a port reaching no export is
  `FW-E-SOCK-UNBOUND` unless its component has a `run()` task block and no
  step/comb block calls through it (hand-off-ness itself stays
  `FW-E-EMIT-RUN`). fe-sv: `check_api` defers unbound bare ports of
  `fw_run_if` components (`rt.deferred_unbound`); `domains.lower_checks`
  fills `rt.lower_diags`; `ElabResult.to_ir()` puts them first in
  `ir_diags` and raises on errors. Spec: domains.md "Lookup", protocols.md
  "Resolution", diagnostics.md rows, protocols.rst, behaviour.rst, fw-hdl
  skill. wb_xtor: `api_stub` gone (and the scripts' `api_stub.sv`
  filters); `wb_emit.sv`, `wb_emit_tgt.sv` gained an unused root reset (no
  `rst` port appears). fe-sv `tests/e2e/sv/sync_xing/*_emit.sv` likewise.
  New fe-sv `tests/unit/test_lower_check.py` (3). Tests: fe-sv 445 passed,
  6 skipped, 29 failed, all rt-sv lint/compile from 9b.1's in-progress
  rt-sv (`fw_rt.svh:75` VARHIDDEN, `fw_rt_util.svh:69` WIDTHEXPAND,
  `fw_rt_kern.svh:397` `__fw_rt_xq::reset`); zuspec-synth 1287 passed,
  55 failed, 97 errors (baseline; +1 is the `test_synth_command`
  collection error); be-sv 264 passed; wb_xtor 11 passed; apb + sbus
  check.py pass; `dfm run tests` passes; Sphinx 0 warnings. Found:
  ProcMapper misses `n++` as a state write in run() (FW-W-TASK-MAP, no
  FW-E-EMIT-RUN). Next: 9b.3.
- 2026-11-28: step 9b.1 done (uncommitted). Spec `processes.md` Reset:
  R1 run() starts where `wait_reset_done` returns, R2 killed with its forks
  (and calls blocked on them, in callees and crossings) at the asserting
  edge, R3 restarts from the top; fields keep values; no reset domain =
  time 0; task code reads a reset as `in_reset` does. X8 rewritten
  (emptied in the update of each asserted edge; same-domain blocked calls
  die with their thread); new X9 `FW-E-XING-RESET` (row in
  `diagnostics.md`; call returns at once, try_* 0; a call blocked at the
  asserting edge returns then). Domain ops key on `this` of the calling
  code; `FW-E-DOM-OBJ` for domain ops is static only; open: obj in another
  clock than the thread's run(). rt-sv: `__fw_rt_kern::manage` per run()
  forks `run()` under a process handle; `group()` samples resets before
  evaluate (`rst_sample`) and in the update kills (`process::kill`, which
  in Verilator 5.055 takes forked children and grandchildren, verified)
  then empties crossings (`rst_apply`, `__fw_rt_xq::reset`, `rgen`);
  `xing_reset` for X9; waiting gets tracked as process handles (a killed
  getter stops counting); run-time DOM-OBJ check in `dom_op` removed
  (build-phase `set`/`own` checks kept); `in_reset`/`wait_reset` read the
  pre-edge value from any task thread. Conformance: new `proc_run_reset`,
  `xing_reset_bad`, `proc_callee_tick`; `_lib/test_proc.svh` gains
  `test_rst_pulse`; traces moved for run() starting at edge 3 (edge_div,
  proc_time, proto_timed, xing_edge_time; sync_xing_side_bad 4 edges);
  `wait_reset_done` dropped from 5 scenarios. fe-sv `test_conformance.py`
  PENDING `xing_reset_bad` (run time). Tests: rt-sv 27 passed (conformance
  all pass); fe-sv 476 passed 7 skipped; apb + sbus check.py 2 passed;
  conformance schema 120/120; `dfm run conformance-compile` 120/120.
  Next: 9b.3.

- 2026-11-28: 9b.3 done. Dropped redundant `wait_reset_done` from apb_tb,
  sbus_rtl_tb and the protocols.rst example; skill, `fw_run_if.svh` and
  api/processes.rst state run() follows reset. apb + sbus check.py pass;
  wb_xtor 11 passed; Sphinx 0 warnings. Step 9 complete. Open: strict vs
  narrow `FW-E-DOM-NONE` (narrow: only designs with process code).

- 2026-11-28 (owner): clock-domain crossing for domain ops / API calls
  deferred: needs defined CDC operations, explicit and implicit paths.
  Fix now: ProcMapper `n++` in run() not seen as a write (FW-E-EMIT-RUN
  missed); fe-sv `elaborate()` alone no longer reports an unbound port of a
  component with run() (9b.2 deferred it to `to_ir()`).

- 2026-11-28: both "Fix now" items done (uncommitted). (A) zuspec-fe-sv:
  `StmtMapper` maps `t++`/`++t`/`t--`/`--t` statements and compound
  assignments (`+= -= *= /= %= &= |= ^= <<= <<<= >>=`) to `StmtAugAssign`
  (`>>>=` is still unmapped); ProcMapper's `_Scan` counts inc/dec as writes
  (compound already was), so `n++` in run() is `FW-E-EMIT-RUN` with no
  FW-W-TASK-MAP. `sig++` is not expressible (signals are handles; a write
  is `write()`, already in `check_task_signal`). be-sv: `proc_emit` writes
  `StmtAugAssign` as `t <= t op v` (or `=`), `xtor_cocotb` takes `AugOp`.
  (B) explicit lowering intent: `elaborate(..., lower=False)`; only with
  `lower=True` (`rt.lower`, inherited by `explore()`) does `check_api`
  defer a hand-off target's unbound port to `check_lowering`; otherwise it
  is `FW-E-SOCK-UNBOUND` at elaboration, as in rt-sv. dfm `Elaborate` has
  a `lower` param (default false). Lowering callers with such tops pass
  `lower=True`: wb_xtor test + scripts, apb and sbus check.py emit steps.
  Spec protocols.md "Resolution" and the fw-hdl skill say so. Tests:
  zuspec-fe-sv 172 passed 5 skipped (+5); fe-sv 480 passed 7 skipped
  (`test_lower_check.py` 7: plain elaboration reports the port, `n++`,
  `--n`, `n += v` are EMIT-RUN); be-sv 265 passed, same 6 failed
  (+`test_step_aug_assign`); zuspec-synth 1287 passed, 55 failed, 97
  errors (baseline); wb_xtor 11 passed; apb + sbus check.py pass. Open:
  the SV `for` loop is still a placeholder in StmtMapper.

## §1 The model the docs must teach (as the code has it)

- **Protocol**: a static-only class `extends fw_protocol`, APIs named in the
  macro: `` `fw_protocol_utils(C, REQ, RSP) `` / `` `fw_protocol_param_utils ``;
  prefix by `` `fw_protocol_prefix("s") ``. Normative: spec
  `semantics/protocols.md:53-67`.
- **Bundle**: `` `fw_bundle_utils(C, PROTO) ``; role by mixin `fw_bundle`
  (initiator) / `fw_mirror` (target) / `fw_monitor`.
- **Transactor bases**: `fw_xtor_initiator`, `fw_xtor_target`,
  `fw_xtor_sock_initiator`, `fw_xtor_sock_target`, `fw_xtor_monitor`
  (`protocols.md:68-87`). Bases create the export/port/socket.
- **Task-sync crossings** `fw_to_sync #(T)` / `fw_from_sync #(T)`: task side
  `put`/`get` only hands off; the sync side (`comb` reads `valid`/`peek`,
  `step` does `take`/`give`) drives pins. Rules X1-X8 in
  `semantics/processes.md:305-349`; lowering to `x_valid/x_data/x_ready`
  ports, `processes.md:381-418`. A target's `run()` may only make its port
  call (hand-off).
- **Worked examples**: `examples/wb_xtor` (hand-written, one class with
  crossings; shell + bridges via `emit_xtor`), std `fw_rv_initiator` /
  `fw_rv_target`, sbus (GenKit-generated, composed std rv transactors).

## §2 Plan

Phase 1 is mechanical (doc matches code, no design decision). Phase 2 needs
the §3 decisions.

1. **Phase 1 — declarations** (spec `docs/`):
   `protocol-packages/declare.rst` (declare()/d.api/d.prefix prose, macro
   table row, `fw_bundle_protocol`), `protocols.rst` 20-70,
   `protocol-packages/reference.rst` (FW-E-PROTO-API text, macro, checklist,
   FW-E-EMIT-RUN hand-off exception), `conformance/README.md:103`.
2. **Phase 1 — API reference**: `api/protocols.rst` (drop `fw_protocol_decl`;
   add the `_sock_` bases), `api/macros.rst` (drop `fw_bundle_protocol`, add
   `fw_bundle_utils`, `fw_protocol_prefix`), add `fw_to_sync`/`fw_from_sync`
   to `api/processes.rst`.
3. **Phase 1 — generated transactors**: `protocol-packages/generate.rst`
   175-189 excerpt (real bases `fw_xtor_sock_initiator/_target`, no
   redeclared socket); `protocols.rst` 176-184.
4. **Phase 1 — skills**: `fw-proto-kit` (step 1 row, gen_tb/gen_bind claim,
   point at wb_xtor); spec `fw-hdl` skill (drop the "prose predates the
   macros" caveat once 1-3 land).
5. **Phase 2 — transactor behaviour**: rewrite
   `protocol-packages/behaviour.rst` 104-128 and `protocols.rst` 208-221
   (`ux_init`) around crossings: task side hands off, `comb`/`step` drive
   pins. A tested hand-written crossing transactor in the spec docs (§3.4).
6. **Phase 2 — monitors and terminology** per §3.1-3.3.
7. **Cleanup**: delete or ignore `docs/examples/sbus/build/` (stale build
   output checked in); wire sbus `check.py` into a test so the
   literalincluded example stays honest.
8. **Check**: Sphinx build of fw-hdl-spec docs with no `fw_protocol_decl` /
   missing-symbol warnings; sbus `check.py` passes; grep finds no
   `declare(`, `d.api`, `fw_bundle_protocol` outside history.

## §3 Decisions (owner, 2026-11-28)

1. **Task code never writes signals.** Only `step()`/`comb()` write; task code
   (`run()`, API tasks) hands off through task-sync crossings. This is a spec
   change, not just docs: `processes.md` C1-C7 (crossing ports) and conformance
   `xing_rv_default` allow `run()` writes today; `task-sync-crossings.md` Q2
   closes. rt-sv/fe-sv need a diagnostic. Own step (§2 step 9).
2. **Monitors: design a sync→task crossing first.** Monitor docs wait for it;
   until then the docs don't teach monitor internals (`std.rst` keeps its
   one-line note). Design doc is §2 step 10.
3. **Name: "task-sync crossing"** for `fw_to_sync`/`fw_from_sync`; "domain
   crossing" stays for clock/reset. Plain "crossing" only where unambiguous.
4. **Own example in the spec**: a small, tested, hand-written transactor under
   fw-hdl-spec `docs/examples/`, literalincluded by the docs.

Still open: 5 (does `emit_xtor` apply to GenKit output; docs don't promise
it), 6 (`fw_proto_dir_e` public or internal).

## §2a Phase 2 steps (from §3)

9. **No task-code writes** (spec + rt-sv + fe-sv + conformance): impact first,
   then the change.
10. **Monitor sync→task crossing**: design doc, then implementation.
11. **Docs**: new spec example (§3.4); `behaviour.rst` 104-128 and
    `protocols.rst` `ux_init` rewritten on it; terminology pass (§3.3);
    leftovers from Phase 1 (conformance `meta.json`, `netlist.schema.json`
    descriptions, `processes.md` hand-off-only `run()` exception).

Not in scope (ahead of the code): bench integration (xtor-shell T4b/T6),
depth > 1 semantics (Q4), comb scope (Q5), X8 reset conformance.

## §4 Step 9: task code never writes signals (impact study, 2026-11-28)

Shipping code is already clean: std (`fw_rv_*`, endpoints), GenKit output,
`examples/wb_xtor`, sbus, rt-sv and fe-sv tests never write signals from task
code. `fw_rv_monitor::run()` only *reads*. What changes:

- **Spec** (`semantics/processes.md`): C3 (drive), C5, C6 and the task-write
  parts of C2/C8, Request-update and Register-or-wire go; C1/C2/C4/C7 survive
  as a read-only sampled port. New `FW-E-WRITE-TASK` (static + run time, write
  ignored); `FW-E-XING-DRIVE-TWICE` retired; `FW-E-WRITE-MULTI` loses its
  task clause; `connections.md:83-85` IN-OPEN exception goes. "Crossing ports"
  (implicit per-signal task access) and `fw_to_sync`/`fw_from_sync` (declared,
  lowered to ready/valid) are separate mechanisms; zuspec-be-sv and wb_xtor
  already say "crossing ports" for the latter, so rename the former
  "sampled port".
- **Conformance**: 13 scenarios write from task code, mostly just to observe
  values in the per-edge trace. Delete `xing_drive_twice`; rewrite
  `xing_rv_default`/`proc_run_put` on `fw_rv_initiator`; invert
  `xing_write_multi`; the rest record through a recorder; new `write_task_bad`.
- **rt-sv**: in `__fw_rt_procs::wrote()`, report when `cur == null &&
  runs_started` (covers forked threads and export tasks too); delete the
  C3/C5 machinery (`write_now`, `xbase`, `tsamp`/`tproc`/`ttime`, `task_wr`,
  `drives`). Cheaper than today.
- **Static** (zuspec-synth `check_xing`, zuspec-fe-sv ProcMapper, fe-sv
  `ir_map.py:913-920`): cover every user task that writes signals (export
  tasks without a crossing are invisible today), emit WRITE-TASK, drop
  `XingPort.written/default`.

Sequence (green at each step, ~2 days): (1) static `FW-W-WRITE-TASK` warning;
(2) recorder in conformance `_lib` + rewrite scenarios against today's rules;
(3) spec text, `write_task_bad` PENDING; (4) rt-sv check + delete machinery;
(5) warning → error, drop IR fields; (6) design-doc/naming cleanup;
(7) optional "sampled port" rename.

Open (owner): recorder (test-lib `fw_to_sync`, rows shift one edge) vs a trace
"events" list (schema change); component-field writes from task code stay
allowed (assumed yes, not signals); rule covers writes only, or reads too
(reads ⇒ monitor sync→task crossing becomes a prerequisite).

## §5 Issues found building apb (2026-11-28)

Owner accepted the proposals in 1, 2, 4, §5.3 and §5.3a (2026-11-28). They
join step 9 as step 9b (spec + rt-sv + fe-sv/be-sv + conformance):
reset domain required when lowering; unbound hand-off target port allowed
at a lowering top (drop wb_xtor's `api_stub`); domain ops key on the
component whose code runs, not the thread's; `run()` follows its reset;
`FW-E-XING-RESET` for calls from another reset domain; rt-sv implements X8.

1. **No reset domain.** `domains.md:80` lets a component's default resolve
   to `null` at the top; a lowered `reset_state()` then crashes zuspec-be-sv
   `proc_emit.py:100` (ValueError). Owner: every component has a reset
   domain, at least inherited; no reset is infeasible when lowering.
   Proposal: a lowered top whose default reset domain resolves to `null` is
   an error (`FW-E-DOM-NONE`, on the top); simulation keeps `null` legal for
   sync-free benches. wb_xtor's `wb_emit_tgt.sv` top has no reset domain
   and must gain one.
2. **Target port must be bound at a lowering top.** `protocols.md:210-214`
   resolution runs on every elaboration, so `xt.p` unbound is
   `FW-E-SOCK-UNBOUND` though lowering drops `run()`, the only user of `p`.
   wb_xtor binds a do-nothing `api_stub`, which lowers to an empty
   `module api_stub();` instance; apb binds `xt.p` to `xi.t`. Proposal:
   a target's port at a lowering top may stay unbound when the target's
   `run()` is hand-off only (the port's boundary is the crossings' ports).
3. **Calls during reset.** Spec X8 empties the crossings each edge; rt-sv
   does not implement X8 (`fw_rt_xing.svh:15`). Measured in rt-sv with the
   driver's `wait_reset_done` removed: the item sits in `reqs`, the
   initiator's `comb()` drives `psel` during reset (edges 1-2), the
   transfer completes after reset. Owner: a call into a domain in reset
   should be an error. Proposal below (§5.3).
4. **Callee can't wait on its clock.** `processes.md:226`: domain ops take
   `obj` = the calling component; rt-sv `fw_rt_kern.svh:326` checks it
   against the *thread's* component, so `mem_c::access()` (run on
   `xt.run()`'s thread) calling `tick(this)` is `FW-E-DOM-OBJ` (measured).
   apb uses `fw_time::delay`.

### §5.4 Step 9b sub-steps (2026-11-28)

Domain-op keying (item 4): rt-sv cannot see which component's method is
running, so `obj` (pass `this`) selects the domain and rt-sv stops checking
it against the thread's component; the static check (fe-sv/zuspec) keeps
`obj` = `this` of the enclosing class. A domain op whose `obj` is in another
clock domain than the thread's run() is a clock crossing (open, not 9b).

- 9b.1 Spec + conformance + rt-sv (runtime): run() follows reset
  (start/kill/restart, forks killed); X8 in rt-sv; `FW-E-XING-RESET`;
  domain ops keyed on `obj`, not the thread. New scenarios:
  run restart across a reset pulse, xing call into a domain in reset,
  callee `tick(this)` in an API implementation.
- 9b.2 Lowering (fe-sv/zuspec): `FW-E-DOM-NONE` on a lowered top with no
  reset domain; a hand-off target's port may stay unbound at a lowering
  top; wb_xtor drops `api_stub` and gains a reset domain.
- 9b.3 Examples and docs: drop redundant `wait_reset_done` from run()
  bodies (apb, wb_xtor, std, conformance); skills and behaviour docs.

### §5.3 Reset proposal

- A process-side call (`put`, `get`, `try_*`) on a crossing whose owner's
  reset domain is asserted is `FW-E-XING-RESET`, on the crossing; the call
  returns at once (try_* returns 0).
- A call already blocked when the reset asserts is cancelled at that edge
  (in the same domain: the caller's work is reset too).
- Crossings are emptied when the reset asserts (X8, as now), so `comb()`
  sees nothing during reset and drives no transfer.

### §5.3a run() follows the reset (owner, 2026-11-28)

Owner: `run()` is tied to its component's reset domain: it starts after
the reset deasserts and is killed when it asserts. Consequences:

- **Start:** at the first edge with the reset deasserted, after its
  release (where `wait_reset_done` returns today). No reset domain (sim
  only): at time 0, as now (rt-sv `start_runs`, `fw_rt_kern.svh:364`).
- **Kill:** at the edge where the reset asserts, `run()` and every thread
  it forked are killed. Restart from the top at the next deassert.
  Component fields keep their values unless `reset_state()` sets them.
- **Cancel = kill.** A call blocked in a crossing or in a callee (the
  memory's `access()` on the pump's thread) dies with its thread. That
  settles "what does a cancelled call return": it doesn't return.
- **Same domain:** the caller is reset with the callee, so no error.
  **Different reset domain, callee in reset:** `FW-E-XING-RESET` (§5.3).
- `wait_reset_done` at the top of `run()` becomes redundant (8 of 13
  conformance `run()` scenarios have it; 5 have no reset domain). No
  conformance scenario or std code uses `wait_assert`.
- Open: a `run()` that must act during reset (drive a software reset,
  log it) has to live in a component of an outer reset domain.

## §4a Step 9 decisions and revised sequence (owner, 2026-11-28)

- Conformance observes through a **recorder** (test-library crossing; rows
  shift one edge).
- Task code may write **component fields**; the rule is about signals.
- Task code **neither reads nor writes** signals; no monitor exception.
  `fw_rv_monitor::run()` (std `fw_rv_xtor.svh:283`) is the only shipping
  reader: a tick loop that samples pins and calls *function* listeners
  (`fw_rv_mon_listener`), so it becomes a `step()` with no crossing. A
  sync→task crossing (step 10) is needed only for task-level consumers
  (blocking analysis); it is no longer a prerequisite. With reads gone,
  crossing ports (C1-C8) go entirely: no "sampled port" rename.
- Diagnostic: `FW-E-TASK-SIGNAL` (a signal read or written from task
  code), replacing the planned `FW-E-WRITE-TASK`.

Sequence (green at each step):
1. `fw_rv_monitor` → `step()`; its tests (`proto_xtor`, rt-sv
   `pin_bridge_rv.sv`) still pass.
2. Static `FW-W-TASK-SIGNAL` warning (zuspec-synth `check_xing`,
   zuspec-fe-sv ProcMapper, fe-sv `ir_map.py`), every user task.
3. Recorder in conformance `_lib`; rewrite the 13 scenarios.
4. Spec: delete crossing ports (C1-C8 and their diagnostics), state the
   rule, `task_signal_bad` scenario.
5. rt-sv: report in signal read/write when no sync process runs; delete
   the crossing-port machinery.
6. Warning → error; drop `XingPort` fields.
7. Step 9b (§5).

Gaps found in 9.2 (fix in 9.6): the check runs only in elaboration's
domain passes, so a design with no domain kinds (or `explore()`) skips it;
a *function* implementing an API, run on the caller's thread, is not
checked. Pre-existing, not from 9.2: zuspec-synth has 55 failures and 96
errors with or without the change; `test_synth_command.py` doesn't import
(`No module named 'zuspec.cli'`).
