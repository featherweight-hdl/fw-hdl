# wb_xtor: Wishbone transactors on the canonical API

A Wishbone protocol package (classic cycles, one access in flight) written
only against the canonical packages: `fw-hdl-spec` (API and std),
`fw-hdl-rt-sv` (the SV runtime) and `fw-hdl-fe-sv` (the static front end).

Each transactor is one class, with the API on one side and the bundle on the
other, as std's `fw_rv_initiator` does:

```
 task code                 wb_initiator                       wb_target                  model
 access(rsp, req) ─► t (fw_export #(wb_if)) │ pins (fw_bundle #(wb_bundle)) ─► pins (fw_mirror) │ p (fw_port #(wb_if)) ─► access()
```

Everything takes the bus's parameters, `AW` (address width) and `DW`
(data width, whole bytes): `wb_if #(AW, DW)`, `wb_proto #(AW, DW)`,
`wb_bundle #(AW, DW)`, `wb_initiator #(AW, DW)`, `wb_target #(AW, DW)`.
The payloads are declared once, as macros of the parameters
(`src/wb_macros.svh`), and the API declares its types with them:

```systemverilog
interface class wb_if #(int AW = 32, int DW = 32);
    typedef `wb_req_t(AW, DW) req_t;
    typedef `wb_rsp_t(DW)     rsp_t;
    pure virtual task access(output rsp_t rsp, input req_t req);
endclass
```

So a user names the payloads through the API, `wb_if #(32, 32)::req_t`,
and RTL without classes declares the same layout with the same macro
(packed structs of one layout assign to each other). A class that
implements `wb_if` doesn't inherit its typedefs (SV rule), so the
transactors and the bench's memory re-declare `req_t`/`rsp_t` from it.

## Files

| File | What |
|---|---|
| `src/wb_macros.svh` | the payload macros: `` `wb_req_t(AW, DW) `` (adr, dat, sel, we) and `` `wb_rsp_t(DW) `` (dat, err) |
| `src/wb_api_pkg.sv`, `src/wb_if.svh` | the API alone, with no fw-hdl dependency: `wb_if #(AW, DW)` (`req_t`, `rsp_t`, `access(rsp, req)`) |
| `src/wb_pkg.sv` | the package, all `#(AW, DW)`: imports and exports `wb_api_pkg`; `wb_proto`, `wb_bundle` (adr, dat_w, sel, we, cyc, stb out; dat_r, ack, err in), `wb_initiator`, `wb_target` |
| `tb/wb_xtor_tb.sv` | the bench's package: a driver, the two transactors back to back, a memory model and a step-only checker |
| `tb/wb_xtor_tb_top.sv` | the bench's top module (simulation only; it calls rt-sv's internal entry points) |
| `scripts/run_sim.sh` | builds the bench under Verilator and runs it plain, `+rand`, `+mut_init` and `+mut_tgt` |
| `tb/wb_emit.sv` | what is lowered to RTL: `wb_initiator #(32, 32)`, its pins connected up to the top's bundle |
| `tb/wb_xtor_mixed.sv` | the bench with the initiator lowered: the module `wb_dut`, the class target, memory and checker through `fw_pin_bridge`; the module's crossing ports driven by std's `fw_to_sync_ep` and `fw_from_sync_ep` |
| `scripts/emit_rtl.py` | lowers `tb/wb_emit.sv` with fe-sv: `wb_dut` over `wb_initiator_rtl` (renamed: the class is compiled with it) |
| `scripts/run_mixed.sh` | emits the RTL, builds the mixed bench and runs it plain, `+rand` and `+mut_tgt` |
| `scripts/emit_xtor.py` | emits `wb_initiator` or `wb_target` as a transactor shell, generated from the IR (`emit_xtor`): core, types package, interface `<xtor>_xtor_if`, shell `<xtor>_xtor` and bridge class `<xtor>_bridge` (`<xtor>_bridge_pkg.sv`); a third argument `plain` gives the plain bridge, with no fw-hdl dependency; `cocotb` gives no interface or shell but a Python bridge `<xtor>_bridge.py` and the API module `wb_api_pkg.py` (docs/design/xtor-shell-plan.md T3, T4, T4c, T7) |
| `plain/` | the plain bench (T4c): both generated shells back to back, driven through plain bridges by a plain driver (`drv_c.svh`) and memory (`mem_c.svh`); no fw-hdl. `run_plain.sh` emits, builds and runs it |
| `cocotb/` | the cocotb bench (T7): the two generated cores back to back in `wb_cocotb_tb.sv`, driven from cocotb through their generated Python bridges; `test_wb_cocotb.py` is the class bench's driver, memory and checks, ported. `run_cocotb.py` emits, builds (cocotb's Verilator runner) and runs it; `WAIT=edge` uses the bridges that sample at every edge instead of waiting on ready/valid |
| `shell_ref/` | the hand-written shell, interface and bridge references (T0, T5); `run_shell.sh <init\|tgt>` runs them in place of a class transactor, `GEN=1` with the generated interface, shell and bridge instead |
| `scripts/elab_check.py` | elaborates the bench with fe-sv, no IR mapping: diagnostics, protocol table, bindings |
| `flow.yaml` | `dfm run scan`: fe-sv's protocol table; it scans the bench too, since a scan sees a generic class only through a specialization |

## Running

From this directory, under direnv. `test_wb_xtor.py` runs them all
(`dfm run tests` at the repo root runs it with every example's tests).

| Command | Result |
|---|---|
| `direnv exec . sh scripts/run_sim.sh` | `R ok 40 accesses in 149 edges` (plain), `... in 185 edges` (`+rand`); each mutant `R fail ...` |
| `direnv exec . sh scripts/run_mixed.sh` | the same `R ok ... 149 edges` / `185 edges`, and `+mut_tgt` the same `R fail ...`, with the initiator as RTL |
| `direnv exec . sh shell_ref/run_shell.sh init` (or `tgt`; `GEN=1` for the generated shell and bridge) | the same `149 edges` / `185 edges`; the other transactor's mutant `R fail ...` |
| `direnv exec . sh plain/run_plain.sh` | `R ok 40 accesses in 79 edges` (plain), `... in 164 edges` (`+rand`); `+mut_mem` `R fail ...`; `+no_set` stops with the target bridge's `$fatal` |
| `direnv exec . python cocotb/run_cocotb.py` | `R ok 40 accesses in 149 edges, 7 back to back` (plain), `... in 185 edges ...` (`+rand`), as the class bench; `+mut_mem` `R fail ...`; `+no_set` `R fail wb_target_bridge: run() with port 'p' unset ...` |
| `direnv exec . python scripts/elab_check.py` | `ok: true`, no diagnostics; `wb_proto#(32,32)` with API `wb_if#(32,32)`, bundle `wb_bundle#(32,32)`, converters `wb_initiator#(32,32)` (initiator) and `wb_target#(32,32)` (target) |

## Timing

Neither transactor's protocol timing is task code. Each one's task side
meets its sync side through two crossings, `fw_to_sync` and
`fw_from_sync` (`semantics/processes.md`, "Task-sync crossings";
`docs/design/task-sync-crossings.md`). A process-side change re-evaluates
the owner's `comb()` at once, so this costs no cycle.

- **`wb_initiator`** has no thread.
  - `access()` is `reqs.put(req); rsps.get(rsp);`.
  - `comb()` drives `cyc`, `stb` and the request from the waiting request
    (`reqs.valid()`, `reqs.peek()`), so it is on the bus from the edge
    after the call. It raises `stb` only while `rsps.ready()` (room for
    the response): a target's termination can't be refused, so the
    `give` in `step()` must not fail. In this bench there is always room
    (the caller is already in `get`), so the guard costs no cycle.
  - At the edge where `ack` or `err` is high, `step()` takes the request
    and gives the response, and `access()` returns at that edge.
  - A back-to-back `access()` at that edge puts the next request, so `stb`
    stays high, with no idle cycle. With a target that acks
    combinationally, that would be one access per edge. The bench's target
    doesn't do that, so it isn't tested.
- **`wb_target`** keeps a `run()`, because it calls out through its port
  `p`.
  - `step()` gives each new request (`cyc && stb`) to `run()`.
  - `run()` calls `access()`, then puts the response.
  - `comb()` drives `dat_r` and `ack` (or `err`) while a response waits.
  - `step()` takes the response at the termination edge.

  So an access takes at least two edges, and while the callee blocks the
  initiator sees wait states.

The bench checks every call against a per-edge log of the bus:
- the request is on the bus from the edge after the call until it returns
  (C3);
- the call returns at the termination edge, not before (C7);
- `stb` drops afterwards unless the next call came at that edge;
- the data matches a shadow of the memory;
- the target saw each access exactly once.

`+rand` adds 0–3 wait states per access. The memory counts them in its own
`step()`: `access()` hands the request over through a crossing, which costs
the first wait state. `+mut_init` and `+mut_tgt` replace a transactor with
one whose `comb()` keeps `stb` (`ack`) up once raised, and each must fail.

The results are the same as for the earlier version, whose `run()` tasks
drove the pins:
- 149 edges plain;
- 185 with `+rand`;
- the same failing access for each mutant.

## What this example found

1. **Task code needed a construct to reach sync code.** The first version
   had each transactor drive the pins from its own `run()`, through SV
   mailboxes. Its bench memory needed a `run()` and mailboxes too, because
   `access()` runs on the caller's thread, where ticking the memory's
   domain is `FW-E-DOM-OBJ`. That led to `fw_to_sync` / `fw_from_sync`,
   now used here and by std's ready/valid transactors.
2. **rt-sv has no public entry point to elaborate and run.** The top module
   calls `__fw_rt::elaborate` and `__fw_rt_kern::run`, as rt-sv's own tests
   do. `fw_elab #(T)` only elaborates.
3. **fe-sv's `Elaborate` task always maps to IR for emission.** For a
   testbench top that fails on every `run()` (`FW-E-EMIT-RUN`), so there
   is no dfm task that just checks a top. `scripts/elab_check.py` calls
   `elaborate()` directly instead.
4. **Lowering the initiator (M6, `docs/design/xing-lowering-plan.md`).**
   fe-sv lowers each crossing to ready/valid ports; `wb_initiator`'s
   `step()` only hands off, so the module is all comb: `comb()` drives the
   pins, and a comb copy of `step()` drives `reqs_ready`/`rsps_valid`/
   `rsps_data`. The first version left `rsps_ready` unread (the class
   discarded `give`'s result, trusting the depth-1 response crossing to
   have room; `UNUSEDSIGNAL`). Now `comb()` gates `stb` on
   `rsps.ready()`, so the module never starts a cycle it can't complete
   and lints clean under `-Wall`. The outside must still be a receiver
   whose `ready` is "room": std's
   `fw_rv_get_ep` is ready only while a `get` waits, which drops the
   response given in the same edge as the take (tried: `R fail 0 accesses
   returned`). std now has `fw_from_sync_ep` (and `fw_to_sync_ep`), the
   outsides of lowered crossings, which the bench uses. `+mut_init` isn't run mixed: its `comb()` keeps state
   (`up |= ...`), which is a latch, not lowerable RTL.
5. **Not covered yet** (fw-proto-wb has these):
   - `rty`, and block cycles (`cyc` held across accesses);
   - a monitor transactor;
   - reset;
   - a pin map for wrapping an RTL Wishbone port (`fw_extern_if`);
   - lowering the target (it has a `run()`: `FW-E-EMIT-RUN`).
6. The old, `src/`-based version of this example, `examples/wb_initiator`,
   is on branch `legacy`.
