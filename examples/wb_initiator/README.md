# wb_initiator: a Wishbone initiator in Pattern 1

The worked example of
[`docs/design/sync-task-domains.md`](../../docs/design/sync-task-domains.md)
§4 and §5.1 (step X7). A transactor split in two:

- **A sync core** (`wb_init_core`): all of the protocol's timing, as
  `step()`/`comb()`. It runs as a class, and it lowers to RTL that is
  proven equivalent to fw-proto-wb's hand-written `wb_initiator_xtor_core`.
- **A task side** made only of library crossings: `fw_rv_put_ep` for the
  request and `fw_rv_get_ep` for the response. `access()` is
  `ereq.put(r); ersp.get(p);`, with no timing of its own.

```
 task code            wb_init                                   bus
 access() ─► ereq (put ep) ─► req ┐                       ┌─► adr/dat_w/sel/we/cyc/stb
                                  ├─ wb_init_core (sync) ─┤
 access() ◄─ ersp (get ep) ◄─ rsp ┘                       └◄─ dat_r/ack/err/rty
```

## Files

| File | What |
|---|---|
| `src/wb_sig.svh` | the bus as a sync struct port: the holder `wb_sig` and its ends `wb_sp_out` (master) and `wb_sp_in` (target) |
| `src/wb_init_core.svh` | the sync core |
| `src/wb_init.svh` | the initiator: the core, the two endpoints and `access()`/`read()`/`write()` |
| `src/wb_init_core_pkg.sv`, `src/wb_init_pkg.sv` | the core's package (lowers; needs only `fw_hdl_pkg`) and the initiator's (`fw_std_pkg` too) |
| `ref/` | fw-proto-wb's `wb_types_pkg` and `wb_initiator_xtor_core`, vendored: the beat types and the equivalence reference |
| `rtl/wb_init_emit_top.sv`, `rtl/gen/wb_init_core.sv` | the emit top and the lowered core (checked in, kept current by the test) |
| `tb/wb_init_tb.sv` | the bench: a memory target, an edge logger and the §4 checks |
| `yosys/equiv.ys` | unbounded equivalence of the two cores |

## Running

From this directory. Logs go under `rundir/`.

| Command | What |
|---|---|
| `direnv exec . sh scripts/run_sim.sh` | the bench under Verilator: plain, `+rand`, and the `+mut_ws` mutant (must fail) |
| `direnv exec . env PYTHONPATH=$PWD/../../python python scripts/gen_rtl.py` | lower the core to `rtl/gen/wb_init_core.sv` |
| `direnv exec . sh scripts/equiv.sh` | the lowered core ≡ `ref/wb_initiator_xtor_core.sv`, unbounded |

The root suite runs all three: `tests/python/system/test_wb_initiator.py`.

## What the bench shows

With a target that acks in the first bus cycle and accesses back to back,
the run is §4's table: access *i* is called at edge 2*i* and returns at
2*i* + 2.

| Edge | Task side | Core |
|---|---|---|
| 2*i* | `put(r)` drives `req.valid` for the next edge (C3) | idle: `req.ready` |
| 2*i* + 1 | request handshake: `put` returns (C7), `get` raises `rsp.ready`; the put endpoint's default drops `req.valid` (C5) | launches the phase: `cyc`, `stb` |
| 2*i* + 2 | ack, so response handshake: `get` returns, `access()` returns, and the next `put` drives `req.valid` at the same edge (C6) | ends the phase: `stb` low |

The only idle cycle is the core's own (`stb` low between phases), as in
fw-proto-wb's SV interface. `+rand` adds 0–3 wait states per phase and 0–3
idle edges between accesses, and checks the data and that each access is
one bus phase. `+mut_ws` gives the target one wait state without `+rand`,
and the table check must fail.

## Notes

- **For fw-proto-wb.** The core here is the class form of
  `wb_initiator_xtor_core` (the working tree on 2026-11-21: the two-state
  core with the phase held until the response is taken). fw-proto-wb could
  generate its core from `wb_init_core` and drop the hand-written task
  interface (`wb_initiator_xtor_if.sv`) for the two endpoints.
- **Comb fields.** The core and the target declare their comb fields with
  `set_comb()` in `new()`, since this bench is built without the
  `fw_sp_comb` weaver. The lowering finds them from `comb()` either way.
- **Clocks.** The bench builds the tree in `new()`, without the connect
  phase that would let children inherit a clock (`do_connect()`), so it
  connects each component's clock, children included, as
  `tests/xing/rv_ep_tb.sv` does.
