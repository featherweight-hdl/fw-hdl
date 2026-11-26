# Transactor shells: connecting a lowered core to a class environment

Follows `xing-lowering-plan.md` (M6). Lowering a transactor class emits
only its **core**: `comb()`/`step()` as RTL, each task-sync crossing as a
ready/valid port pair. Nothing connects that core back to class-based
task code; `examples/wb_xtor/tb/wb_xtor_mixed.sv` does it by hand with
std's class endpoints through `fw_pin_bridge`. This plan generates the
connection.

## User benefit

A user writes one transactor, as an SV class or in Python (API on one
side, bundle on the other) and gets, with no further code:

- the core module (today);
- a **shell module** with only the bus pins, clock and reset on its
  ports, that contains the core and an SV interface whose tasks are the
  process side of the transactor's crossings (`reqs_put`, `rsps_get`);
- a **bridge class** generated from the same IR, which is all the
  consumer sees: for an initiator it implements the API and exports it
  (the consumer gets a reference); for a target it calls, through its
  port, the API implementation the consumer provides.

A fw-hdl class environment that used the class transactor switches to
the RTL one with the bridge in its place, and the shell module goes
where the transactor's pins were; the integrator hands the bridge its
vif (one line, generated once integration is, §6). A UVM
environment uses a plain bridge with no fw-hdl dependency: it gets the
bridge (an API handle) from the config db, calls `run()` when ready, and
gives a target its API implementation with a `set` call. A cocotb bench
puts the core alone in its HDL top and builds a generated Python bridge
with the core's handle: the same API boundary, the same timing. Nothing
else in the environment changes. This is the classic split (HDL BFM + HVL proxy)
that fw-proto-wb writes by hand, derived from the class.

## 0. Status

| Step | State |
|---|---|
| Plan (this doc) | 2026-11-25: D1–D7 reviewed. D1, D6, D7 agreed; D2 one interface, endpoints inline; D3 logic between `_req` and `_rsp` belongs in the core; D4 no registration on the HDL side (emulation) |
| T0 Hand-written reference (initiator) | done 2026-11-25, revised to per-crossing tasks (`reqs_put`/`rsps_get`, X6 put-returns-at-take): `examples/wb_xtor/shell_ref/`; class-bench results (149 / 185 edges, `+mut_tgt` fails on access 2); shell lint clean `-Wall`; `test_wb_xtor.py::test_shell_ref` (suite 4 pass). Findings §4a |
| T1 Record crossings at lowering | done 2026-11-25: `ir.SyncXingRecord` on `DataTypeComponent.sync_xings` (path, direction, item type, depth, port name per role), own and lifted, filled by `lower_sync_xings`; task code kept through lowering on `DataTypeComponent.task_blocks`, crossings and ports named by path; `test_sync_xing_emit.py::test_xing_records`, `::test_task_blocks_kept`, `test_wb_xtor.py::test_task_code_lowered`. Findings §4c |
| T2 Task code in IR | SV front end done 2026-11-25: TASK blocks carry `body` and `args` (zuspec-fe-sv `proc_mapper`; `test_task_code_*`, `test_wb_xtor.py::test_task_code_ir`). Python front end (zuspec-dataclasses) not started. Findings §4c |
| T3 Shell + interface emission | done 2026-11-25: zuspec-be-sv `xtor_shell.XtorShellEmitter` (interface + shell from `sync_xings`), fw-hdl-fe-sv `emit.emit_xtor` (core `<name>_core`, `<name>_types_pkg`, `<name>_if`, `<name>`); step blocks lose dead locals; `examples/wb_xtor/scripts/emit_xtor.py`, `run_shell.sh` `GEN=1`: generated shells give the hand-written results (149 / 185 edges, mutants fail) and lint clean `-Wall` with the core; `test_wb_xtor.py::test_shell_gen[init,tgt]`, `test_sync_xing_emit.py::test_xtor_shell*`. Findings §4d |
| T4 Bridge (D8): generated from IR | bridge done 2026-11-25: zuspec-be-sv `xtor_bridge.XtorBridgeEmitter` (from `api_endpoints`, `task_blocks`, `sync_xings`), `emit_xtor` writes `<xtor>_bridge_pkg.sv` + `<xtor>_bridge.svh` (`EmitResult.bridge`); IR: `ApiEndpoint.api_params`/`api_scope`; `run_shell.sh` `GEN=1` now uses the generated bridge too: 149 / 185 edges, mutants fail, bridge lint clean `-Wall`; `test_wb_xtor.py::test_shell_gen`, `test_sync_xing_emit.py::test_xtor_bridge`, be-sv `test_xtor_bridge.py`. D4 hand-off: by the integrator (hand-written in the reference benches; generated with integration, §6). Findings §4e |
| T4b Generated connection, fw-hdl bench (D4, D10) | deferred 2026-11-25 to integration generation (§6): tried and backed out; the HDL top, link and class top depend on the design around the transactor, not on the transactor. Notes §4f |
| T4c Plain bridge flavor (D10) | done 2026-11-25: `XtorBridgeEmitter(..., flavor="plain")`, `emit_xtor(flavor=)`; `wb_if` in `wb_api_pkg` (exported by `wb_pkg`); `examples/wb_xtor/plain/`: both shells back to back, plain bridges, plain driver and memory, no fw-hdl on the command line: 79 / 164 edges, `+mut_mem` fails, `+no_set` stops with `$fatal`; bridges lint clean `-Wall`; `test_wb_xtor.py::test_plain`, be-sv `test_plain_*`. Findings §4g. UVM bench proper still to come |
| T5 Target: lower a `run()` that only hands off | done 2026-11-25: D7 in zuspec-fe-sv `proc_mapper` (+ `test_emit_run_handoff`); hand-written target reference in `examples/wb_xtor/shell_ref/` (`wb_target_xtor_if`, `wb_target_xtor`, `wb_target_bridge`, bench `wb_xtor_shell_tgt`); class-bench results (149 / 185 edges, `+mut_init` fails at edge 6); interface and shell lint clean; `test_wb_xtor.py::test_shell_ref_tgt` (suite 5 pass). Findings §4b |
| T6 `wb_xtor` benches | not started |
| T7 cocotb: Python task side on the core (D9) | done 2026-11-25: zuspec-be-sv `xtor_cocotb.XtorCocotbEmitter` (bridge module `<xtor>_bridge.py` and API module `<api scope>.py` from the same IR; endpoint checks shared with the SV bridge in `xtor_bridge.XtorIr`), `emit_xtor(flavor="cocotb")` (no interface or shell); `examples/wb_xtor/cocotb/`: the class bench's driver, memory and checks in cocotb on the two generated cores: **149 / 185 edges, 7 back to back** (the class bench's), `+mut_mem` fails, `+no_set` raises; same results with the start order reversed; event-driven waits by default (2026-11-26: idle 37k -> 287k edges/s), per-edge sampling as `cocotb_wait="edge"`; `test_wb_xtor.py::test_cocotb`, be-sv `test_xtor_cocotb.py`. cocotb 2.1.0 added to `ivpm.yaml`. Findings §4h |

Logs go under `build/shell-*.log`.

## 1. What exists

- **Lowering** (`zuspec-synth .../passes/sync_xing_lower.py`): crossing
  field -> `<x>_valid/_ready/_data` (+ `_wait`); task blocks dropped. The
  crossing -> ports link lives only in the pass's local state; nothing
  records it, and `depth` is unused.
- **Task blocks** (`zuspec-fe-sv proc_mapper.py`): `ProcKind.TASK` blocks
  for `run()` and each task using a crossing, with `xing_uses` in order,
  but **no body or signature**.
- **API signatures** reach the IR as `DataTypeProtocol` (`ir_map._api_type`),
  with each component's `converter` role and `api_endpoints` (`t`/`p`).
  GenKit's proxy/imp generators clone methods from it (`gen/kit.py`).
- **`wb_target`** can't be lowered: it implements `run()`
  (`FW-E-EMIT-RUN`).
- **Reference split** (fw-proto-wb, hand written): wrapper
  `wb_initiator_xtor` = `wb_initiator_xtor_core` + `wb_initiator_xtor_if`
  (task `xfer`); `wb_initiator_bridge` holds
  `virtual wb_initiator_xtor_if vif` given to its constructor. Target:
  tasks `recv_req`/`send_rsp`; `wb_target_bridge::run()` loops
  recv -> `access` -> send.
- **Class endpoints**: std `fw_to_sync_ep`/`fw_from_sync_ep` are the
  class form of a lowered crossing's outside.

## 2. Shape

(Revised 2026-11-25: per-crossing tasks; the class side is the
transactor's own task code. Superseded: per-method `access_req`/
`access_rsp` tasks and a D3 split rule.)

```
 class env                         │  shell module  <xtor>_xtor  (pins, clock, reset)
                                   │ ┌──────────────────────────────────────────────┐
 wb_initiator (task code only) ─ vif ─►  <xtor>_xtor_if                             │
   access(rsp, req):               │ │    task reqs_put(input req)   (fw_to_sync)  │
     reqs.put(req);  ─► vif.reqs_put │    task rsps_get(output rsp)  (fw_from_sync)│
     rsps.get(rsp);  ─► vif.rsps_get │    one slot per crossing   ── ready/valid ─┐│
                                   │ │  <xtor>_core  (lowered comb/step) ◄────────┘─── pins
                                   │ └──────────────────────────────────────────────┘
```

The transactor class already specifies the mapping from task calls to
crossings; the shell implements it:

- **Core:** `comb()`/`step()` lowered (M6); each crossing becomes
  ready/valid ports.
- **Interface:** per crossing, a one-item slot (the crossing's depth)
  and one task per process-side method (`<x>_put`/`<x>_try_put` for
  `fw_to_sync`, `<x>_get`/`<x>_try_get` for `fw_from_sync`), with the
  crossing semantics of `semantics/processes.md` X3–X8. Derived from the
  crossings alone (name, direction, type, depth): no task code is
  needed, so nothing about the API or the task code is synthesized.
- **Bridge:** the API boundary (D8), its task code lowered from the IR,
  with its crossings carried by the interface: an initiator's API methods, a
  target's `run()`. Loops, conditionals, several callers, matching
  responses by tag all stay where they were.

| | Initiator (`wb_initiator`) | Target (`wb_target`) |
|---|---|---|
| Crossings | `reqs`: to_sync; `rsps`: from_sync | `reqs`: from_sync; `rsps`: to_sync |
| Interface tasks | `reqs_put(input req)`, `rsps_get(output rsp)` | `reqs_get(output req)`, `rsps_put(input rsp)` |
| Bridge | implements `wb_if` on export `t`; `access`: `reqs.put(req); rsps.get(rsp);` over the vif | port `p`; `run()`: `reqs.get(r); p.access(s, r); rsps.put(s);` over the vif |

## 3. Decisions (reviewed 2026-11-25)

- **D1 Names.** Follow fw-proto-wb: shell module `<xtor>_xtor`, interface
  `<xtor>_xtor_if`, core `<xtor>_xtor_core`, bridge class
  `<xtor>_bridge` (in `<xtor>_bridge_pkg`). Tasks `<m>_req`/`<m>_rsp` for
  API method `<m>`. (fw-proto-wb uses `xfer`, `recv_req`/`send_rsp`; we
  take the names from the API instead, so nothing is chosen by hand.)
- **D2 One interface.** The interface is the bridge between the API and
  the crossings, so it is one generated interface: per crossing, the
  one-item slot (registers; the crossing is depth 1) and its ready/valid side toward the core,
  inline; per API method, the `_req`/`_rsp` tasks over those slots. No
  std per-crossing sub-interfaces. (The slot logic is the same for
  every crossing of a direction, so the generator emits it from one
  template per direction; std's class endpoints `fw_to_sync_ep`/
  `fw_from_sync_ep` define the timing it must match.)
- **D3 One task per crossing method (revised 2026-11-25).** The
  interface's tasks are the process side of each crossing, not a split of
  the API methods: the transactor's task code already maps each call to
  its crossings, and stays class code. Its semantics are the spec's
  (X3–X8): with depth 1, `put` returns at the edge that takes its item;
  `get` returns at the edge that gives one; `waiting()` drives `<x>_wait`.
  (Replaces the `_req`/`_rsp` split and `FW-E-SHELL-SPLIT`.)
- **D4 Vif hand-off on the class side only (revised 2026-11-25).** The
  shell and its interface stay synthesizable for emulation, so nothing on
  the HDL side registers itself. Whoever builds the bridge hands it the
  virtual interface, taken by hierarchical reference; no db keyed by
  path, no factory type override, no spec additions. Who builds it
  depends on the bridge's flavor (D10):
  - **fw-hdl bench** (we own both the HDL top and the class top): the
    generator knows each shell's HDL path and the class path of the
    bridge that stands in for the transactor, so it emits the connection
    (`top.xi.vif = hdl_top.xi.u_if`, today hand-written in T0's top).
  - **UVM bench:** the HVL top constructs each bridge with its vif
    (`new(hdl_top.xi.u_if)`) and registers the *bridge* (an API handle)
    with `uvm_config_db`, not the vif. UVM code deals only in APIs; the
    shell's interface never reaches it.
  (Superseded: a path-keyed `fw_vif_db` filled by the HVL top, the bridge
  looking itself up in `build()`, replaced in by factory type override.)
- **D5 Clock and reset.** The shell has a `clock` port (the endpoints
  are clocked even when the core is all comb, like `wb_initiator`'s) and
  a `reset` port that clears the slots; the tasks wait out
  reset. The domain's clock is the one the class transactor was bound
  to.
- **D6 Where it's generated, and from what (revised 2026-11-25).** Both
  front ends (SV classes through fe-sv, Python through
  zuspec-dataclasses) map a transactor to Zuspec IR; the IR is lowered
  to the **SV transactor form**: core module, interface, shell module and
  the class side. Nothing is generated from SV text, and nothing assumes
  the transactor was written in SV. `emit_sv(..., shell=True)` in fe-sv
  drives it for SV input. Needed in the IR:
  - per component, each crossing's name, direction, item type, depth and
    port names, recorded by the lowering pass (T1);
  - the task code: API method signatures and task bodies, with crossing
    calls as calls on the crossing field (T2).
- **D8 The class side is a bridge, generated from the IR (revised
  2026-11-25).** The consumer thinks only in terms of the API (an SV
  interface class, a Python Protocol):
  - **initiator:** the consumer *gets* a reference to an API
    implementation. The bridge implements the API and exports it through
    the transactor's export (`t`); its methods are the transactor's task
    code with the crossing calls made through the interface.
  - **target:** the consumer *provides* an API implementation. The bridge
    holds the transactor's port (`p`) and calls that implementation; its
    `run()` is the transactor's task code (`reqs.get` -> `p.access` ->
    `rsps.put`) over the interface.
  The vif, the crossings and the shell never reach the consumer. The task
  code is lowered from the IR (a Python transactor has no SV class to
  reuse), each crossing call rewritten to the interface's task
  (`reqs.put(x)` -> `vif.reqs_put(x)`), the rest as written; the
  per-crossing cut (D3) keeps that a rename. Superseded: reusing the
  transactor class with rt-sv forwarding its crossings.
- **D9 cocotb: the same form, with the interface in Python.** The
  boundary every test bench uses is the **core**: its pins plus each
  crossing's ready/valid (and `_wait`) ports, with the crossing
  semantics of processes.md X3–X8. The SV interface is one
  implementation of the task side of that boundary; for cocotb it is
  generated Python that drives and samples the core's crossing ports
  directly (no SV interface, no shell module: the core is in the HDL
  top). The cocotb bridge is given the **hierarchical path to the
  core** (cocotb's counterpart of the SV bridge's vif, D4) and hides
  everything below it; it keeps D8's contract: the consumer *gets* an
  implementation of the API's Protocol (initiator) or *provides* one
  that the bridge calls (target). Because the Python is generated, the
  timing rules of §4a (decide from this edge's handshake; writes land
  after what the edge samples) are the generator's job, checked against
  the class bench's results (149 / 185 edges for `wb_xtor`).
- **D10 Bridge flavors (2026-11-25).** One IR, several bridge classes;
  each flavor differs only in how it is built, how it is started and how
  a target is given its API implementation. The task code (crossing
  calls through `vif`) is the same.
  - **fw-hdl** (T4, done): `extends fw_component`; `fw_export` /
    `fw_port` endpoints, created in `build()`; a target's `run()` is
    `fw_run_if`, started by the fw-hdl runtime; the port is bound by
    fw-hdl connection.
  - **plain** (for UVM, and any non-fw-hdl class code): no fw-hdl
    dependency at all (no `fw_hdl_pkg`, no base class). Constructed with
    its vif (`function new(virtual <shell>_if u_if)`). It implements the
    API of its exports directly. Every bridge has `task run()`, which the
    environment calls once it is ready to execute (e.g. from a driver's
    `run_phase`); a target's `run()` is its task code, an initiator's
    returns at once. No separate gate (reviewed 2026-11-25): a target's
    implementation is called only from its `run()`, so no `run()`, no
    calls; an initiator's API calls go straight to the crossings. A target is given its API implementation by a plain
    set call, one per port: `set_<port>(<API> imp)` (`set_p(...)`);
    `run()` stops with `$fatal` if a port is unset.
  - **cocotb** (D9, T7, done): a Python class built with the core's
    handle and its clock (`wb_target_bridge(dut.xt, dut.clk)`); the
    rest as plain: it implements its exports' APIs (a `Protocol`),
    `set_<port>(imp)`, `async run()`, which raises if a port is unset.
  The plain flavor needs the API (the interface class and its types) in
  a package with no fw-hdl dependency; `wb_pkg` today holds `wb_if`
  beside `wb_proto`/`wb_bundle`/the class transactors and imports
  `fw_hdl_pkg`, so the API moves to its own package (`wb_api_pkg`,
  imported by `wb_pkg`).
- **D7 Target lowering.** A `run()` that only calls crossings and the
  component's own API ports is dropped from the core like other task
  blocks (it becomes the bridge's `run()`), instead of `FW-E-EMIT-RUN`.
  Any other `run()` keeps the error. `busy = reqs.give(r)` (give's result
  as state) is the `x_ready` case noted in M6 §5.

## 4. Steps

- **T0 Hand-written reference (initiator).** Write by hand what the
  generator must produce for `wb_initiator`: `wb_initiator_xtor_if`
  (one slot and one task per crossing: `reqs_put`/`rsps_get`), the shell `wb_initiator_xtor`
  (emitted core renamed `wb_initiator_xtor_core` + interface), the
  bridge `wb_initiator_bridge` and `fw_vif_db`. Bench: the class bench
  with `wb_initiator` overridden by the bridge and the shell on the bus;
  results unchanged (149 / 185 edges, `+mut_tgt` fails). This settles
  the timing (§5) before anything is generated. Files under
  `examples/wb_xtor/shell_ref/`.
- **T1 Record crossings at lowering.** `lower_sync_xings` attaches, per
  component type, a list of `{name, dir, type, depth, ports}` to the
  component (metadata), and lifted names for the top.
- **T2 Task code in IR.** API method signatures and task bodies of
  each transactor in the IR (ProcMapper for SV: today TASK blocks have
  only `xing_uses`; the Python front end for zuspec-dataclasses), with
  crossing calls on the crossing field and port calls on the port.
- **T3 Shell + interface emission.** be-sv: SV `interface` with one
  slot and one task per process-side method per crossing (the §4a
  template), ports for the core's crossing signals; shell module with
  core + interface. Lint clean under Verilator `-Wall`.
- **T4 Bridge (D8).** be-sv emits the bridge from the IR: implements the
  API on export `t` (initiator) or calls through port `p` from `run()`
  (target); task code with crossing calls as `vif.<x>_<method>`; vif
  hand-off per D4. Checked against T0's hand-written bridge.
- **T4b Generated connection, fw-hdl bench (D4). Deferred (§6).**
  This plan's output is the transactor's own pieces (core, types
  package, interface, shell, bridge): a library an integrator
  references, not regenerates. The HDL top, the vif hand-off and the
  class top holding the bridges are integration, generated with the
  collateral around a design (§6). Tried 2026-11-25 and backed out;
  notes in §4f.
- **T4c Plain bridge flavor (D10).** `XtorBridgeEmitter` gets a flavor;
  the plain one emits `new(vif)`, `run()` for every bridge, `set_<port>()`
  for each port, and no fw-hdl imports. Move `wb_if` to `wb_api_pkg`.
  Bench: a UVM-shaped SV top (no UVM library needed to start; a plain
  driver class that calls `run()` and `set_p()`) against both shells;
  same results. A UVM bench proper when UVM is available under Verilator.
- **T7 cocotb (D9).** Generated from the same IR: per transactor, the
  Python task side (one slot per crossing, put/get coroutines on the
  core's ready/valid ports, X3–X8) and the cocotb bridge, constructed
  with the core's hierarchical path; bench: cocotb driver and memory against `wb_initiator_xtor_core`
  (and the target's core), same results as the class bench.
- **T5 Target lowering** per D7; `wb_target` emits.
- **T6 Benches** (`examples/wb_xtor`):
  - `wb_xtor_shell_init`: the class bench with `wb_initiator` overridden
    by `wb_initiator_bridge` and the shell on the bus;
  - `wb_xtor_shell_tgt`: same for the target;
  - `wb_xtor_shell_both`: both shells back to back.
  Each must give the class bench's `R ok 40 accesses in 149 edges` /
  `185` with `+rand`, and `+mut_tgt` fails as before. Add to
  `tests/python/system/test_wb_xtor.py`; replace the hand-built
  `wb_xtor_mixed.sv` once T6 covers it.

## 4a. What T0 found (2026-11-25)

- **Files** (`examples/wb_xtor/shell_ref/`): `wb_initiator_xtor_if.sv`
  (one slot and one task per crossing: `reqs_put`/`rsps_get`), `wb_initiator_xtor.sv` (shell:
  core + `u_if`; ports clock + bus only), `wb_initiator_bridge_pkg.sv`,
  `emit_core.py` (core emitted as `wb_initiator_xtor_core`),
  `wb_xtor_shell_init.sv` (bench), `run_shell.sh`.
- **Timing rule for the generated interface (synthesizable form).**
  Tasks wait only on `@(posedge clock)` (no `wait`, no event controls),
  and every variable has one writer: tasks own `reqs_put`, `reqs_data`,
  `rsps_got`, `rsps_wait`; the clock owns `reqs_took`, `rsps_gave`,
  `rsps_q`; a slot is full when its toggles differ. Tasks are called at
  an edge (class threads run only at edges) or wake at one, and run
  before that edge's `<=` updates land, so they **decide from this
  edge's handshake (`valid && ready`), not from the registers**, which
  lag it by the update. All writes are `<=`, so a task at an edge never
  changes what that edge samples. Two wrong versions found on the way:
  - blocking writes from the tasks: a caller resuming at an edge could
    change what that edge's clocked side sampled (`+mut_tgt`: "called at
    8, returned at 8");
  - polling the registered flags after `@(posedge clock)`: every access
    returns one edge late (C7: "termination at edge 5, returned at 6"),
    and back-to-back puts lose a cycle.
- **Edge cases of the T0 form (revised to per-crossing tasks):**
  - `put` twice from one thread: fixed by X6 itself, since a depth-1
    `put` returns only at the edge that takes its item.
  - `get` entered at an edge that gives an item with no `get` waiting:
    now exercised (the per-crossing `reqs_put` returns at the take edge,
    the same edge that gives the response) and handled: `rsps_get` takes
    it from the ports at entry, unless a get waiting before the edge
    (`rsps_wait`) already took it.
  - Still open: two *threads* calling `put` (or `get`) on one crossing in
    the same edge; both see the slot as it was before the edge. The
    class model serializes them. Needs a task-side arbiter in the
    template (T3).
- **No FIFOs: one slot per crossing (depth 1).** `reqs` holds
  `reqs_data` from `reqs_put` until the edge that takes it; `rsps`
  holds `rsps_q` from a giving edge with no waiter until `rsps_get`
  (`rsps_ready = !rsps_full`). The slot is the class crossing's own depth-1
  storage, not added buffering, so the timing is unchanged (results
  identical). It is needed: `rsps` must hold a response given at an
  edge where no `get` waits yet, and `rsps_ready` (room) must not depend
  on a waiting `get`, or `stb` (gated on `rsps_ready`) could wait on a
  `get` that waits on the `put`. A crossing declared
  deeper would get a deeper slot; none does today.
- **Hand-off gaps (D4):** `fw_object` has no path (only the optional
  `fw_acc::path`) and rt-sv has no type override, so T0's HVL top builds
  the bridge in its own top class and assigns `t.xi.vif = xi.u_if` after
  elaboration (run tasks start at the first clock edge, so this is in
  time). T4 needs: a path-keyed `fw_vif_db` without depending on
  `fw_acc` (or a cfg-based hand-off), and a type override in rt-sv for
  the drop-in replacement.
- **Types package:** the core's types package is named after the emitted
  top (`wb_initiator_xtor_lowered_types_pkg`); the interface imports it.
  T3 should name it after the transactor (`wb_initiator_xtor_types_pkg`).
- The bridge passes `wb_if::req_t` to a task taking the core's `req_t`:
  two packed structs of one layout (the `wb_req_t` macro), so they
  assign; a generated bridge relies on the same layout rule.

## 4b. What T5 found (2026-11-25)

- **Files** (`examples/wb_xtor/shell_ref/`): `wb_target_xtor_if.sv`
  (`reqs_get`/`rsps_put`), `wb_target_xtor.sv` (shell),
  `wb_target_bridge_pkg.sv` (holds port `p`; its `run()` is
  `wb_target::run()` with `reqs.get`/`rsps.put` as `vif.reqs_get`/
  `vif.rsps_put`), `wb_xtor_shell_tgt.sv` (bench: class driver, initiator
  and memory; the shell on the bus through pin bridges). The emit top is
  `tb/wb_emit_tgt.sv`. `emit_core.py` and `run_shell.sh` take
  `init|tgt`.
- **The template is per crossing direction.** The target interface is the
  initiator's with the roles swapped: `fw_from_sync`'s get (initiator
  `rsps_get`, target `reqs_get`) and `fw_to_sync`'s put (initiator
  `reqs_put`, target `rsps_put`) are the same code with the names
  changed. It matched the class bench on the first run, so T3 can emit
  per crossing from `{name, dir, type}` (T1's record).
- **D7 rule as implemented** (`proc_mapper`, emit only): `run()` is
  hand-off if it writes or reads no component state or pin and uses no
  time. Crossing methods and calls through a port's `get_if()` are
  hand-off. Anything else stays `FW-E-EMIT-RUN`.
- **The API port must be bound to emit.** `top.xt.p` unbound is
  `FW-E-SOCK-UNBOUND`, so `wb_emit_tgt.sv` binds it to a stub export
  (`api_stub`), which is emitted as an empty module. T5's rule should
  extend to the elaborator: when `run()` is dropped, the port it calls
  is the bridge's and may be unbound at emit (T3/T4).
- **The core has a clock.** `wb_target`'s `step()` keeps `busy`, so the
  core is `always_ff` and the shell wires `clock` to it; the initiator's
  core is combinational only. The shell template must connect `clk` when
  the core has one.
- **Dead locals in the emitted core.** `step()`'s `r` and `s` are left
  unused after lowering turns `give`/`take` into port reads
  (`-Wall` `UNUSEDSIGNAL` on the core, not on the hand-written files).
  An emitter cleanup for T3's lint-clean goal.
- **Sensitivity.** A one-edge-late `reqs_get` wake gives 189 / 225 edges,
  so the exact-count checks catch it. A one-edge-late `rsps_put` return
  changes nothing, which is correct: the `reqs` slot holds the next
  request until `run()` comes back.
- **No target mutant on the HDL side.** The class `+mut_tgt` mutates the
  class target, which this bench replaces; `+mut_init` is the failing
  case. T6's back-to-back bench needs a mutant from the HDL side.
- **Two shells back to back** (T6) needs the checker on HDL pins (a
  mirror bridged in), since neither class transactor is left.

## 4c. What T1/T2 found (2026-11-25)

- **The record (T1).** `ir.SyncXingRecord` (zuspec-ir-core
  `proc_block.py`): `path` (`[x]` own, `[child, x]` lifted), `direction`,
  `element_type`, `depth`, `ports` (role -> port name: `valid`, `ready`,
  `data`, and `wait` when a block calls `waiting()`). `lower_sync_xings`
  fills `DataTypeComponent.sync_xings` on every component with crossing
  ports. For `wb_xtor`: `wb_initiator_xtor_core` has `reqs` TO_SYNC and
  `rsps` FROM_SYNC, `wb_target_xtor_core` the reverse, depth 1, port names
  `reqs_valid`/`reqs_ready`/`reqs_data` etc.; the `_lowered` tops have
  them as `xi/reqs` -> `xi_reqs_valid`, ... That is all the per-direction
  interface template (§4b) needs.
- **The task code (T2, SV).** A TASK block's `body` and `args` are the
  task's code (zuspec-fe-sv `proc_mapper._task`):
  - crossing calls as in step bodies (`ExprCall(ExprAttribute(<field>,
    m))`), blocking ones (`put`, `get`, task calls through a port) in
    `ExprAwait`, as the Python front end writes an `await`;
  - `i = p.get_if(); i.access(s, r)` becomes `p.access(s, r)` on the
    endpoint, named by its path (`ExprHierarchical([p])`); `i` is
    dropped. SV ports and exports are `api_endpoints`, not fields, so
    the path is how the body names one;
  - `args`: name, IR type, direction (`SignalDirection`);
  - code it cannot map (an API local given anything but `get_if()`,
    an unsupported construct) leaves the body empty with the warning
    `FW-W-TASK-MAP` (not an error: the core still lowers; only the bridge
    is lost).
  For `wb_xtor` the bodies are exactly the hand-written bridges':
  initiator `access(output rsp, input req)`: `await reqs.put(req);
  await rsps.get(rsp)`; target `run()`: locals `r`, `s`, `while 1:
  await reqs.get(r); await p.access(s, r); await rsps.put(s)`.
- **The T4 open points, resolved (2026-11-25).**
  - *Task code survives lowering.* `lower_sync_xings` moves TASK blocks
    from `proc_blocks` to a new `DataTypeComponent.task_blocks` (no RTL
    back end reads it; `proc_emit` still rejects a TASK block in
    `proc_blocks`). In them a crossing, whose field is gone, is named by
    path, `ExprHierarchical([x])`, which is its `sync_xings` record's
    path; other field references take the lowered indices. One IR
    carries core and bridge: for `wb_xtor`, `wb_initiator_xtor_core`
    has `access` = `await reqs.put(req); await rsps.get(rsp)` and
    `wb_target_xtor_core` has `run` = `while 1: await reqs.get(r); await
    p.access(s, r); await rsps.put(s)`, beside its records
    (`test_sync_xing_emit.py::test_task_blocks_kept`,
    `test_wb_xtor.py::test_task_code_lowered`).
  - *One port-call form: the path.* The same rewrite names a port or
    export *field* (`FieldKind.Port`/`Export`/`Callable*`/`Protocol*`,
    the Python front end's form) by path, so after lowering both front
    ends give `ExprHierarchical([p])`. T4 reads one form.
  - *API tasks.* No change needed: the SV function mapper already sets
    `Function.is_async` for a task (`wb_if.access` has it), the flag a
    Python `async def` sets. `is_task` is a lowering flag (SV `task` vs
    `function` for generated code), not the API's. T4 reads `is_async`.

## 4d. What T3 found (2026-11-25)

- **Pieces.** `zuspec.be.sv.xtor_shell.XtorShellEmitter(core, name,
  types)` writes, from a lowered flat core's own `sync_xings`, its
  `FieldInOut` ports and its step blocks' `clock_net`:
  - `<name>_if(input logic clock)`: per crossing the §4a/§4b template
    for its direction (`<x>_put` for to_sync, `<x>_get` for from_sync,
    item argument `item`), the core's port names as the interface's
    signals; a from_sync crossing's `wait` port when the core has one,
    else an interface-local `<x>_wait`. Types are written qualified
    (`<name>_types_pkg::req_t`), no import.
  - `<name>`: ports the core's non-crossing ports, as the core names
    them (`pins_adr`, not `adr`: no prefix stripping, nothing guessed);
    `u_if` and `u_core`. The interface's clock is the core's step clock
    net (`clk`); a core with no step (the initiator) gets a `clk` input
    the shell adds, so both shells have `clk`.
  - Refuses (rather than emits wrongly): depth > 1, a parameterized
    core, step blocks on two clocks, interface name clashes.
  `fw.hdl.fe.sv.emit.emit_xtor(ctxt, top, xtor, out, name=)` runs
  `emit_sv` with the transactor renamed `<name>_core`, the top
  `<name>_lowered` (unused) and the types package `<name>_types_pkg`
  (§4a's naming item; `emit_sv` gained `types_package`), then writes the
  two files and lists them after the packages.
- **Result.** `run_shell.sh` with `GEN=1` (benches instantiate the
  generated shell under `` `ifdef GEN_SHELL ``, its port names) gives the
  hand-written shells' output exactly for both transactors (149 / 185
  edges; `+mut_tgt` / `+mut_init` fail as before). Generated interface,
  shell and core lint clean under `-Wall`.
- **Dead locals (§4b) fixed in the lowering**, not the emitter:
  `sync_xing_lower` runs its `_drop_dead` on a handing-off step's body
  (a take's target or give's value used only by the hand-off is dead
  once the comb block does it). `wb_target`'s step lost `r` and `s`.
- **Still open.**
  - The API port must still be bound for emit (`api_stub` in
    `wb_emit_tgt.sv`, §4b): `emit_xtor` takes an emit top, so this did
    not block T3. T4/T6 can let `emit_xtor` take the class directly.
  - Concurrent callers on one crossing (§4a): the template still has
    no task-side arbiter. One caller per crossing (true for both wb
    bridges) is a documented limit of `xtor_shell`.
  - Pin names: a bench (or T6's generated top) uses the core's names.

## 4e. What T4 found (2026-11-25)

- **Pieces.** `zuspec.be.sv.xtor_bridge.XtorBridgeEmitter(core, name,
  iface, type_m, types)`, from the lowered core's IR alone:
  - each API endpoint becomes `fw_<kind> #(<API>) <name>`, created in
    `build()`; an export the core implements itself (`imp == []`) makes
    the bridge `implements <API>`, with the API's typedefs as its own;
  - each task block becomes a `virtual task`: an implemented API method's
    with the API's signature (`Function.args`, types as the API spells
    them), `run()` with `implements fw_run_if`, any other with its own
    args; the body as written, with a crossing call `<x>.put/get` as
    `vif.<x>_put/_get` and a port call as `<p>_if.<m>` (`<p>_if =
    <p>.get_if()` at the task's start); `forever` for `while 1`;
  - locals take the core's types package types (the interface's), API
    arguments the API's; packed structs of one layout, so they assign
    (§4a).
  - Refuses: sockets, an export implemented by a child, an API function
    (not a task), an API method with no task code, an empty task body
    (`FW-W-TASK-MAP`), a crossing method the interface lacks (`try_put`,
    `waiting`, the other direction's), a call on anything but a crossing
    or a port.
  SV style: package `<xtor>_bridge_pkg.sv` includes the class's
  `<xtor>_bridge.svh`. It is class code, compiled after the API's
  package, so `emit_xtor` returns it as `EmitResult.bridge`, not in the
  filelist.
- **IR addition.** The API's specialization was lost: `ApiEndpoint` had
  `api='wb_if'` only. It gains `api_params` (as `ProtocolRef.params`,
  `{AW: 32, DW: 32}`) and `api_scope` (the declaring package, `wb_pkg`),
  filled by fw-hdl-fe-sv `ir_map` (`class_params`, `package_of`). The
  bridge spells the API `wb_pkg::wb_if #(32, 32)`.
- **Result.** The generated bridges are the hand-written ones (same
  declarations and bodies; `p_if` for `i`). With `GEN=1` the benches use
  the generated interface, shell and bridge: 149 / 185 edges for both,
  `+mut_tgt` / `+mut_init` fail as before. The bridge lints clean under
  `-Wall` (warnings only in rt-sv, the spec bindings and `wb_pkg`).
- **Still open (T4b, D4).** The bridge has a `vif` member that the HVL
  top sets after elaboration (`t.xi.vif = xi.u_if`), as T0's. Revised
  D4 (2026-11-25): no `fw_vif_db` or type override; the generator emits
  that line when integration is generated (§6; T4b notes §4f), and a plain flavor for UVM is built with
  its vif (T4c, D10).

## 4f. T4b notes, for integration generation (2026-11-25)

Tried and backed out (the pieces below are integration, §6). What it
showed:


- **The HDL top is the lowered top.** `emit_xtor` already lowered the
  bench's emit top (`tb/wb_emit.sv`: the transactor, its pins connected
  up to the top's bundle) to `<xtor>_xtor_lowered`, with the core as
  instance `xi` and its crossings lifted to top ports. T4b emits the same
  top with the shell in place of the core (`<xtor>_xtor_hdl`): the lifted
  crossing ports go (the shell keeps them inside its interface), and a
  shell's added clock (`clk`, a core with no state) becomes a top input.
  It is synthesizable and lints clean under `-Wall` (with the target's
  `api_stub`, which stands in for its port, as in the lowered top).
- **The link.** Hierarchical references can't be made from a package,
  and the HDL top must not import class code (emulation). So the
  connection is a separate, simulation-only module,
  `<xtor>_xtor_hdl_link`: the HDL top's ports, the HDL top as `u_hdl`,
  and `connect(<bridge_pkg>::<bridge> xi)`, which does `xi.vif =
  u_hdl.xi.u_if`. All references are downward. The bench instances the
  link where it had the shell and calls `xi.connect(t.xi)` after
  elaboration. Both names come from the IR: the instance path is the
  transactor's field path, the bridge's type is `emit_xtor`'s.
- **It worked.** An emitter over the flattened top (shells for the core
  instances, crossing nets dropped, a crossing net used elsewhere
  refused) and the link gave, with `GEN=1`, 149 / 185 edges and failing
  mutants; both HDL tops linted clean under `-Wall`.
- **Its input was wrong.** It read `tb/wb_emit.sv`, a second top written
  by hand to hold the transactor alone; the bench's class top
  (`shell_top_c`) is a third. The input should be the user's one class
  top (`top_c` in `tb/wb_xtor_tb.sv`, which runs as a pure class
  simulation) and a **cut**: which instances go to HDL. From that: the
  HDL top (below the cut, transactors as shells), the class top (above
  it, transactors as bridges) and the link. The bridge keeps the
  transactor's endpoints (`t`, `p`), so `d.p.connect(xi.t)` carries over;
  the `pins` connections are what crosses the cut.
- **The cut.** Derived where it can be: a transactor whose pins go up to
  the top's boundary bundle (`connect_up`) puts the boundary at the cut.
  Back-to-back transactors (`xi.pins.connect(xt.pins)`) make it a choice
  (T6's three benches), named as instance paths. Other users of the pins
  (the checker's `k.p.connect(xi.pins)`) go to HDL or cross by a pin
  bridge.
- **A structural top.** The IR has the elaborated structure, not the
  build code: `top_c::build()`'s `$test$plusargs` type choice and
  `d.k = k` would be lost. A generated class top needs a structural user
  top (clock domains, creates with parameters, connects), anything else
  refused and moved into a child (a test or config component), as on the
  HDL side. Check first that fe-sv's IR has the port/export connections
  (`bind_map`, `ir_map.py:865`, or only `ApiEndpoint.imp`), the clock
  domains and the create parameters.

## 4g. What T4c found (2026-11-25)

- **API package.** `wb_if` moved to `src/wb_api_pkg.sv` (its class in
  `src/wb_if.svh`), which needs only `wb_macros.svh`; `wb_pkg` imports
  and exports it, so `import wb_pkg::*` still sees `wb_if`. fe-sv
  follows the export: `api_scope` is now `wb_api_pkg`, and both flavors
  spell the API `wb_api_pkg::wb_if #(32, 32)`. Every compile list gains
  `wb_api_pkg.sv` ahead of `wb_pkg.sv`. (`wb_pkg`'s other classes are
  still inline, against the one-class-per-`.svh` style.)
- **The plain bridge.** Same task code as the fw-hdl flavor; only the
  wrapper differs: no base class, `local` vif and port handles,
  `new(u_if)`, `set_<port>(imp)`, a port call made on the handle itself
  (no `get_if()`), and `run()` for every bridge, a target's checking its
  ports first (`$fatal`). Its only dependencies are the API package and
  the core's types package (the crossings' item types), both plain SV.
- **Bench** (`examples/wb_xtor/plain/`, `run_plain.sh`): both generated
  shells back to back on one bus; the HVL side does what a UVM bench
  would (build each bridge with its shell's interface, `set_p(mem)`,
  fork both `run()`s, then use the initiator's API). Driver and memory
  are plain classes on `wb_api_pkg` only. Built with no fw-hdl package
  on the command line. Results: `R ok 40 accesses in 79 edges` (plain),
  `164` (`+rand`: 0–2 idle edges between accesses, 0–2 wait states in
  the memory); `+mut_mem` fails; `+no_set` stops with the bridge's
  `$fatal`. The counts are this bench's own (its driver is not the class
  bench's), so they are pinned as a regression, not compared with 149 /
  185; the task code they run is the fw-hdl flavor's, which is.
- **Not done.** A UVM bench proper (needs UVM under Verilator); the
  plain bench stands in for it.

## 4h. What T7 found (2026-11-25)

- **Shape.** `emit_xtor(..., flavor="cocotb")` writes the core and its
  types package as before, no interface or shell, and two Python
  modules: the bridge (`wb_initiator_bridge.py`) and the API, named
  after its SV package (`wb_api_pkg.py`: `wb_if` as a `typing.Protocol`,
  `req_t`/`rsp_t` as dataclasses). In Python a method's outputs are its
  return value: `rsp = await xi.access(req)`. The bridge has the plain
  flavor's contract (D10) and only cocotb as a dependency.
- **The task side is the SV interface's code, in Python.** Per crossing,
  the same state (`put_t`/`took`, `gave`/`got`/`wait`/`q`), the same
  put/get code and the same always-block updates, generated line for
  line from `sync_xings` like `xtor_shell`. Items are packed/unpacked by
  the core's struct layout (first field most significant); the API's
  dataclass of the same name is used when its fields match, else the
  bridge declares its own.
- **Timing: event-driven by default (2026-11-26).** A transfer is at the
  first rising edge whose sampled ready and valid are both high. The
  bridge waits only for that: a put drives valid and its item, checks
  ready settled in the ReadOnly phase, else sleeps on ready's rising
  edge and checks again, then waits for the clock edge (where it
  returns, X6). A from-sync crossing's watcher sleeps on valid while
  the slot has room, notes the item at ReadOnly and hands it over at the
  edge (to a waiting get, else into the slot, dropping ready); a get at
  that edge takes it directly (X5). Writes are made only from code
  resumed by a clock edge, so they land after what the edge sampled.
  Assumes synchronous ready/valid: they change only in the time steps
  of this clock's edges. The previous form (the SV interface's code with
  deferred writes and a sample at every edge, for signals that may change
  between edges) is kept as `cocotb_wait="edge"` (`emit_xtor.py ...
  cocotb-edge`, `WAIT=edge run_cocotb.py`). Both give the class bench's
  149 / 185 edges at the first run, and the same with the bridges,
  checker, driver and target started in reverse order. Calls are made at
  an edge or before the first.
- **Speed** (this machine, 20000 edges after start-up, one run each):
  cocotb clock alone 327k edges/s; both bridges idle 37k (edge) ->
  287k (event); back-to-back accesses 34k -> 38k. For scale, the plain
  SV bridges under Verilator `-O3`: 1.9M edges/s. Idle edges now cost
  almost nothing; busy ones do not improve because Wishbone's ready and
  valid change on every access, so each transfer still costs several
  wakes (ReadOnly, the signal's edge, the clock edge, per side): about
  8 per edge at ~3 us each. Busy throughput is bound by Python wakes per
  transfer, not by the waiting scheme.
- **Clock.** The bridge takes the clock as well as the core: the
  initiator's core is combinational and has no clock port. When the
  core has one it could be found from the IR (minimal spec); not done.
- **Bench** (`examples/wb_xtor/cocotb/`, `run_cocotb.py` via
  `cocotb_tools.runner`): `wb_cocotb_tb.sv` holds only the two cores,
  their crossing ports left open (the bridges drive them through
  `dut.xi`/`dut.xt`; Verilator accepts writes to them). The driver,
  memory (wait states from the same LFSR), gaps and checks are the class
  bench's, ported, so the counts are comparable, unlike the plain
  bench's. `+mut_mem` fails at access 1; `+no_set` makes the target's
  `run()` raise.
- **Task code to Python** covers what transactors use: crossing and port
  calls, locals, assignment, `if`, `while`, `break`/`continue`/`return`
  and simple expressions. `~x` (and anything else that needs a width) is
  refused; so are depths other than 1, as in the SV interface.
- **Placement.** The emitter is in zuspec-be-sv beside `xtor_shell` and
  `xtor_bridge`: it is the task side of the SV core's boundary. If a
  general IR-to-Python text emitter appears (zuspec-be-py builds live
  classes, not text), the task-code lowering should move onto it.

## 5. Risks and open points

- **Timing equality.** The interface endpoints must give the class
  crossings' timing (put visible to `comb()` in the same edge, get
  returning at the giving edge). In an SV interface this is ordering of
  task wake-ups against the clock edge; T0 settles it before anything is
  generated.
- **Concurrent callers.** `put`/`get` from two threads
  pair responses by order, as the class's `put`/`get` already do; a
  bridge for an out-of-order protocol would need tags. Not needed for
  Wishbone classic.
- **be-sv** interface emission: T3 added it for transactor shells only
  (`xtor_shell.py`), not general SV interfaces.
- **Emulation.** The shell and interface must stay synthesizable (D4):
  no registration, no class references, and interface tasks in the
  clocked, XRTL-style form an emulator compiler accepts (wait on the
  clock, nonblocking writes to the slot state). T0 writes them that way
  even though only Verilator runs them for now.
- **D6 also serves Python.** Transactors described in Python
  (zuspec-dataclasses) lower through the same IR, so T1–T4 must not
  depend on fe-sv's elaboration objects, only on the IR.

## 6. Later: integration and collateral around a design (direction, 2026-11-25)

Not a step of this plan. A transactor's generated pieces are a library;
putting them in a bench is integration, generated from the design's IR
and a cut (§4f). Two cases: a fw-hdl design connected to pins (HDL top,
class top with bridges, vif hand-off by generated hierarchical
reference; §4f) and a generated UVM testbench, below. D4/D10 are shaped
for both.

### 6a. Generated UVM testbenches

The plain bridge (D10) makes a core UVM testbench around a fw-hdl design
with signal-level interfaces derivable:

- **Transactors from protocol types.** Each of the design's
  signal-level interfaces has a protocol type (`wb_proto`) and a role;
  the generator picks the transactor for the opposite role (a design's
  Wishbone target port gets `wb_initiator`'s shell).
- **hdl_top / hvl_top pair.** hdl_top instances the design and one
  shell per interface, wired pin to pin, with clock and reset. hvl_top
  constructs one plain bridge per shell with its vif (hierarchical
  reference) and registers each bridge (an API handle) with
  `uvm_config_db`, then calls `run_test()`.
- **A core UVM env.** Available UVM agents are found by the same key
  (protocol type and role); the env constructs one agent per interface,
  each getting its bridge from the config db, its driver calling
  `run()` in `run_phase` and (for a target) giving the bridge the
  agent's responder with `set_<port>()`.

Needs, beyond T4c: a protocol type and role on each of the design's
signal-level interfaces in the IR; a registry of transactors and of UVM
agents keyed by (protocol type, role), keyed on types, not name strings;
and the agent's side of the contract (what an agent must accept to be
driven by a bridge), to be written down with fw-proto.

### 6b. Pre-built components and modular lowering

Integration must not lower everything every time. A generator needs to
know that a component is **pre-built**: the user gives its shell class
(a class with the transactor's form: its endpoints and bundle, no
implementation to lower) and the generator uses an implementation that
already exists, generated earlier (this plan's output, referenced) or
hand-coded (fw-proto-wb's BFMs), instead of lowering it. This is
modular lowering: each component lowered once, on its own, and
referenced by the components around it.

Needs: a way to mark a class as pre-built and bind it to its
implementation (core, interface, shell, bridge; for cocotb the core's
path contract), keyed on the type, not a name string; the IR carrying
the pre-built component as an external with its port and endpoint
signature (as `DataTypeExtern` does for extern RTL); and lowering that
stops at it. The shell's and bridge's interface (D3: one task per
crossing method; D8/D10: the bridge's endpoints) is then the contract a
hand-coded implementation must meet.

