# Round-robin stream merger: a sync-logic style example

A worked example of synchronous logic in fw-hdl classes (`comb()`, `step()`, value
ports). Its purpose is to agree on a style, and on what sv-weave contributes along the
way. It is small, but it uses every part of the sync model.

```
 in[0] ─┐
 in[1] ─┼─► rr_arbiter ──────► rr_fifo ──► out
 in[2] ─┤   comb: grant, mux,   comb: in.ready
 in[3] ─┘     in[g].ready       step: storage, out register
            step: rr pointer,
              packet lock
```

N ready/valid inputs are merged into one output, a whole packet at a time. The input
that wins the grant keeps it until its `last` beat, and the round-robin pointer then
moves past it. A DEPTH-entry FIFO with a registered output follows the arbiter.

| File | What |
|---|---|
| `src/rr_merge_pkg.sv` | package: the beat type `rr_beat_t`, the classes, the `rr_merge4_t` specialization |
| `src/rr_arbiter.svh` | `rr_arbiter #(T, N)`: `comb()` grant and mux, `step()` pointer and lock |
| `src/rr_fifo.svh` | `rr_fifo #(T, DEPTH)`: `comb()` in.ready, `step()` storage and out register |
| `src/rr_merge.svh` | `rr_merge #(T, N, DEPTH)`: the two, wired; ports are pass-throughs |
| `tb/rr_merge_tb.sv` | pin-level testbench under `fw_root` (four producers, one consumer) |
| `sv-weave.yaml` | fw-hdl's weavers: `fw_sp_comb`, `fw_settle` |
| `flow.yaml` | `dfm run sim`: weave, build with Verilator, run with `+fw_settle_show` |

## What it exercises

| Sync-model feature | Where |
|---|---|
| `comb()` | arbiter grant, mux, `in[i].ready`; FIFO `in.ready` |
| `step()` with state | arbiter `ptr`/`locked`/`owner`; FIFO `mem`/`wr`/`rd`/`count` |
| sync and comb fields on one channel | `fifo.in`: `ready` comb (from the FIFO), `valid`/`data` comb (from the arbiter); `fifo.out` all sync |
| comb paths across components | `out.ready` → `fifo.in.ready` → `arb.in[g].ready`, in one time step |
| reset-force | `valid`/`ready` read 0 at the peer in reset; `step()`s reset state on `in_reset()` |
| parameters | `T`, `N`, `DEPTH`; one specialization named for the weave (`rr_merge4_t`) |
| the porting hazard | FIFO `step()` relies on blocking order (push, then the new head is read) |
| pass-through ports | `rr_merge.in[i]`/`out` via `connect_up` |

## Style, as written

These are the choices the code makes now. Each one is up for discussion.

1. **One class per `.svh`**, included into one package, as in the library.
2. **No constructors.** All construction is in `build()`: ports, then children;
   wiring is in `connect()`. The factory constructs with the implicit `new()` and then
   attaches the component (`m_init(name, parent)`). A component that implements
   `fw_combinational`/`fw_steppable` is registered for its own `comb()`/`step()`, so
   there is no `add_comb(this)`/`add_steppable(this)` either.
3. **Every component registers with the factory, and every instance is created
   through it**: `T::type_id::create(name, this)`, never `new`. A parameterized class
   uses the UVM pattern: `typedef rr_fifo #(T, DEPTH) this_t;` and
   `` `fw_component_param_utils(this_t) `` (the bare class name will not do: Verilator
   reads it inside the class as the default specialization). Each specialization
   registers as `this_t#1`, `this_t#2`, ... in registration order, so overrides refer
   to it by `type_id::get()`, not by name. The
   root (`rr_merge_root`) is the exception: `fw_root` constructs it.
4. **Comb fields are declared on the port member** with `(* fw_sp_comb = "..." *)`
   (sv-weave `fw_sp_comb`), not with `set_comb()` in `build()`. A class declares only
   the fields it **drives**; the fields it reads are the driver's choice.
5. **`comb()` writes comb port fields only; `step()` writes state and sync fields.**
   A value that both need (the arbiter's grant) is a pure function of state and port
   reads (`grant()`), called from both, not a member that `comb()` writes.
6. **Reset**: `step()` tests `in_reset()` and clears its state there. Data registers
   are not reset. Outputs to the peer rely on reset-force (valid/ready read 0).
7. **State comments** say what the register means, not how it is updated.
8. **An array of ports names its elements `in[0]`, `in[1]`, ...**, after the member.
   A settle-table path that names the member (`in.ready`) covers every element.
9. **The pin bridges need no declaration.** The pins are register outputs in module
   code; a pin value lands in the tree at once and the domain settles, so the tree and
   the pins agree about when a beat moved. (A `COMB` parameter once made the
   pin-driven fields comb for this; it was removed with the two-phase kernel,
   `docs/design/sync-task-domains.md` §8.8.)
10. **State, indices and the functions that return them are declared at hardware
    width** (`bit [$clog2(N)-1:0] ptr`, `idx_t g = grant()`, `function idx_t
    grant()`; not `int`). Lowering keeps the declared width, since the module it emits
    is parameterized and must hold for every parameter value, so it cannot narrow an
    `int` it has not proven in range. With `int` state the first generated design was
    661 cells / 128 flops; with `int` index locals the parameterized arbiter was 136
    cells against 93 (a 32-bit index into `in_data[g]` is a 32-bit shift network).
    Loop counters (`for (int k ...)`) may stay `int`.

## Lowering to RTL

`scripts/gen_rtl.py` lowers the classes to `rtl/gen/rr_merge.sv` (fw-hdl sync flow:
static elaboration, Zuspec IR, zuspec-be-sv): one module per class, parameterized as
the class is (`rr_arbiter #(type T, int N)`, `rr_fifo #(type T, int DEPTH)`,
`rr_merge #(type T, int N, int DEPTH)`), port arrays as array ports, so the RTL can
be handed off and used at any parameter value. The hand-written reference
`rtl/rr_merge_ref.sv` describes the same thing (same parameters, interface and state)
in hand-written style. `dfm run gen-sim` runs the two in lockstep; `scripts/compare.sh`
synthesizes both with yosys and proves them equivalent by induction (unbounded) over a
grid of N and DEPTH, plus a BMC from reset. Plan: [LOWERING.md](LOWERING.md); numbers
and findings: [LOWERING-RESULTS.md](LOWERING-RESULTS.md).

## What sv-weave contributes

| Weaver | Gives | Status here |
|---|---|---|
| `fw_sp_comb` | `(* fw_sp_comb *)` on a port member → its `set_comb()` call at freeze | works, including on `in[N]` (a `foreach`) |
| `fw_settle` | a settle table per `comb()`/`step()` class: fields read and written, comb deps → a static settle order, false-cycle and loop reports | works: `fifo`, then `arb`, each once per settle, no fallback |
| sv-weave verify | elaborates the woven code with the design before writing it; errors point at the weaver | caught the two weaver bugs (fixed) before simulation |
| weave report / manifest | `rundir/rr_merge.woven/woven/weave-report.md` | works |

The generated settle table for `rr_arbiter`:

```
comb_reads : in.data, in.valid, out.ready
comb_writes: in.ready, out.data, out.valid
step_reads : in.valid, out.data, out.ready, out.valid
comb deps  : every comb write depends on every comb read
```

Not yet used: the core sv-weave weavers (copy/compare/print/xcheck, debug profiles).
They apply to classes, and the beat here is a packed struct.

## Status (2026-11-14)

`direnv exec . dfm run sim` passes: weave, build, and 1528 beats checked. The beats
are never interleaved within a packet, arrive in order per source with every source
served, run at 100 per 100 cycles at full rate, and ready/valid read 0 in reset.
With `+fw_settle_show`:

```
fw_settle: ... domain 0: 2 comb() nodes, 2 groups, 0 fallback
  group 0: once: ...dut.fifo
  group 1: once: ...dut.arb
```

Fixes made in fw-hdl to get here (covered by `tests/sync/sp_comb`):
- `fw_settle`/`fw_sp_comb` type naming (`SettleWeaver._type`): a type argument that
  is another class's type parameter (`rr_arbiter #(T, N)` inside `rr_merge`) is
  spelled as what it stands for (`rr_merge_pkg::rr_beat_t`), not as `T`.
- `fw_sp_comb` on a fixed array of ports emits a `foreach` over the elements; a
  dynamic array or queue is an error.
- `fw_sp_comb::apply_tree` applies once per component. `fw_component_root` freezes
  after build and again in `fw_sync_kernel::elaborate`; the second `set_comb` was
  fatal on the frozen holder, for every design that used `fw_sp_comb` under a root.
- The factory (`fw_factory.svh`, `fw_view_ctx.svh`) was in the tree but never
  compiled: neither file was in `fw_hdl_pkg`, `fw_component` lacked `view_ctx()`,
  `m_create_type` and `m_create_origin`, the registration macros were not defined,
  and `fw_view_ctx::global()` used a reserved word (now `get_global()`). All of this
  is wired in now, and the macros are in `fw_hdl_macros.svh`:
  `` `fw_component_utils ``, `` `fw_component_param_utils(this_t) `` (SV-parameterized,
  per specialization), `` `fw_component_obj_param_utils `` (a parameter object; this was
  `fw_component_param_utils` in the factory's comments), `` `fw_component_abstract_utils ``.
  The factory still has no tests of its own.
- Components need no constructor (`fw_component.svh`): `fw_component::new` has
  defaults and attaches only when given a name; `m_init(name, parent)` does the
  attaching, and the factory calls it after `new()`. A component that implements
  `fw_combinational`/`fw_steppable` is registered for itself in `do_build()`;
  `add_comb`/`add_steppable` ignore a second registration of the same object.
- `fw_settle_sched` resolves a table path whose port is an array member (`in.ready`)
  to that field of every element (`in[0].ready`, ...), with dependences across all of
  them (conservative).

## Open issues

1. **Weavers see only specializations named in the woven sources.** A generic class
   specialized only in the testbench gets nothing woven, and nothing says so. The
   package names `rr_merge4_t` for the weave. Should this be the style, or should the
   weave also read the testbench (see 4), or warn about unwoven generics?
2. **Settle dependencies are per `comb()`, not per field.** Every comb write depends
   on every comb read, so the table records `out.valid` ← `out.ready`, which the code
   does not do. Array elements are not told apart either (`in.ready` ← `in.valid` for
   every pair). That is conservative. On a larger design it could report false cycles
   that per-field analysis would not.
3. *Closed:* pin-driven fields need no comb declaration; a pin value lands at once
   (`docs/design/sync-task-domains.md` §8.8).
4. **`fw_root.sv` cannot be woven.** sv-weave elaborates every top, and `fw_root`
   on its own has `Tbind = int`. The flow therefore splits fw-hdl into `fw-pkg`
   (woven) and `fw-mods` (not woven). The testbench is not woven either.
5. **Testbench**: `$finish` reports `23ns` for a 23275-tick run (no timescale), and
   Verilator's STATICVAR warning is easy to miss under `-Wno-fatal`. It was the cause
   of a checker bug found while writing this testbench.
6. **No regression runs this example.** It is not in the root `tests` flow. The
   array-path resolution in `fw_settle_sched` has no unit test of its own; this
   example is its only coverage.
