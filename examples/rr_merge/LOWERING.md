# Lowering rr_merge: class model → Zuspec IR → Verilog → Yosys

The plan and status for lowering `examples/rr_merge` to RTL, and for comparing the
result with a hand-written reference. Pick up from **Status** below.

The pipeline is the one in the sync-RTL design (`fw-proto-axi-new/docs/design-sync-rtl.md`
§5; plan `plan-sync-rtl.md`, stages S5–S6.2s done). Zuspec IR is the hub. Nothing here
is XLS-specific, and nothing emits Verilog except zuspec-be-sv.

```
 SV classes ──(1) static elaboration──► instance tree + sync wiring
            fe/elab/hier.elaborate_tree     (compile-time interpreter; no simulation)
            ──(2) map to Zuspec IR──────► DataTypeComponent per leaf specialization
            fe/elab/sync.sync_component     step() → sync process, comb() → comb process,
                                            ports → FieldInOut, state → Field
            ──(3) sync-subset form + check► SSA (blocking step() → NBA), one driver per
            fe/elab/sync._ssa/_check        field, no latches, Field.drive = SYNC | COMB
            ──(4) composite + emit─────────► rr_merge.sv (+ one module per leaf)
            fe/elab/sync_tree + emit/be_sv  zuspec-be-sv _generate_fw_sync_component
            ──(5) Yosys───────────────────► synth both; cell counts; SBY miter
            ──(6) compare──────────────────► vs hand-written rtl/rr_merge_ref.sv
```

Driver: `fw.hdl.emit.sync.emit_sync(files, top, ...)`; dfm task `fw.hdl.sync.Emit`.

## What the existing path lacks for rr_merge

Taken from reading `python/fw/hdl/fe/elab/sync.py`, `sync_tree.py`, `hier.py` and
zuspec-be-sv:

| # | Gap | Where |
|---|---|---|
| G1 | a class with both `step()` and `comb()` is rejected | `sync.py:495` |
| G2 | arrays of ports `in[N]`: shape, wiring paths `arb.in[0]` | `sync_component`, `_sync_ports`, `sync_tree.port_of` |
| G3 | unpacked state array `T mem[DEPTH]` | `sync.py:548` (integral only); be-sv `_get_sv_type` |
| G4 | locals (`int g`, `T b`, `bit push, pop`) | `_Body` |
| G5 | `for`/`foreach` (unroll: bounds are parameters) | `_Body` |
| G6 | `return` (early return in `step()`; return in a loop in `grant()`) | `_Body` |
| G7 | user function calls (`grant()`): inline | `_Body` |
| G8 | dynamic element select: `in[g].get_valid()`, `mem[rd]`, `mem[wr] = ...` | `_Body` expressions |
| G9 | packed struct member `b.last`; typed `T` ports and state | `_Body`, be-sv sync `_get_sv_type` |
| G10 | `%`, casts, sized constants | `_Body` (`_BIN`), emit |
| G11 | factory creation (`type_id::create`, `new()` + `m_init`) in the interpreter | `hier.elaborate_tree` (unverified) |
| G12 | no reference RTL, no yosys/compare flow for rr_merge | new |

## Decisions (defaults; change before the step that needs them)

- **D1 Module interface.** Clock `clock`, reset `reset` (active high, synchronous), as
  the existing emitter does. Port arrays are flattened per element and field:
  `in_0_valid`, `in_0_ready`, `in_0_data` ... `out_valid`. `T` is a packed struct, so
  `*_data` is `[$bits(T)-1:0]` (9 bits for `rr_beat_t`). The hand-written reference
  uses the same interface, so the miter is a direct port match.
- **D2 Dynamic port index** (`in[g]`, with g computed): lower to a mux over the N
  elements after unrolling. Writes in a `foreach` unroll to one write per element.
- **D3 `mem[DEPTH]`**: small (DEPTH = 2), so registers rather than the IR `Memory` of
  plan S7. Done as one IR field per element (`mem_0`, `mem_1`); a computed index reads a
  `?:` chain and writes one guarded assignment per element. No array type in be-sv needed.
- **D4 Struct fields** (`b.last`): a part-select of the packed value, with the
  struct's layout taken from pyslang.
- **D5 Equivalence**: BMC on a yosys miter (generated vs reference) for depth K; then
  induction if the state encodings line up (they may not: the FIFO's `count`/`wr`/`rd`
  in the class vs whatever the reference uses). Lockstep simulation of class model,
  generated RTL and reference with the existing testbench stimulus as a second check.
- **D6 Synthesis target**: yosys `synth` (generic gates) for cell counts; optionally
  `synth_ice40` for an FPGA-flavored count.

## Steps

- [x] **L0 Baseline.** Run the existing sync emit tests (`tests/python/unit/test_emit_sync*.py`,
      `test_elab_sync_*.py`) on this branch: the factory/`m_init` changes touch the
      interpreter's view of `fw_component`. Fix what breaks.
- [x] **L1 Reference RTL.** Hand-write `rtl/rr_merge_ref.sv` (`rr_arbiter_ref`,
      `rr_fifo_ref`, `rr_merge_ref`) with interface D1. A module testbench reusing the
      class testbench's stimulus and checks, so the reference is checked on its own first.
- [x] **L2 Elaboration.** `elaborate_tree` on `rr_merge4_t`: factory children (G11),
      port arrays in the recorded sync wiring (G2, wiring part).
- [x] **L3 Front end, statements.** G1, G4, G5, G6, G7 in `sync.py` (`_Body`, SSA over
      locals, unroll, inlining). Unit tests on small classes, one per construct.
- [x] **L4 Front end, data.** G2 (shape), G3, G8, G9, G10.
- [x] **L5 Emit.** be-sv sync path: array/struct-width types, sized constants; composite
      with port arrays. Golden + Verilator lint + yosys read for rr_arbiter, rr_fifo,
      rr_merge.
- [x] **L6 Simulate generated RTL** under the module testbench from L1 (lockstep with
      the class model where practical).
- [x] **L7 Yosys.** A flow task: synth generated and reference; cell-count table;
      miter BMC (and induction if it closes). Report in `LOWERING-RESULTS.md`.
- [ ] **L8 Close out.** dfm tasks in `examples/rr_merge/flow.yaml` (`rtl`, `synth`,
      `equiv`); update README; note what moved into fw-hdl.

## Parameterized RTL (L9)

Goal (user, 2026-11-14): the generated RTL is one module per class, parameterized
as the class is (`rr_fifo #(type T, int DEPTH)`), so it can be handed off and reused
at any parameter value. No per-specialization variants. This replaces D1-D3 for the
emitted RTL; the fully elaborated path (`sync.py`) stays for its other users.

Decisions:
- **P1 Interface.** One port per holder field; a port array is a packed array per
  field: `input logic [N-1:0] in_valid`, `input T [N-1:0] in_data`. Data fields have
  the class's type parameter (`T`); clock/reset as D1.
- **P2 Parameters.** Value parameters are module parameters (`parameter int DEPTH = 2`),
  type parameters `parameter type T = <pkg>::rr_beat_t`. The default types (packed
  structs) are emitted into a generated package `<top>_types`. Widths written from
  parameters stay symbolic (`logic [$clog2(DEPTH)-1:0] wr`), taken from the
  declaration syntax; a type parameter is found by following pyslang's alias chain
  (holder `T` → view `T` → class `T`).
- **P3 Structure is kept.** No unrolling, no per-element flattening: `for`/`foreach`
  stay loops, `mem[rd]` stays an array select, `b.last` a member select. Expressions are
  emitted as SV with the class's own width rules (the source is SV).
- **P4 step() is next-state logic.** `always_comb` computes `x_n` with the class's
  blocking order (`x_n = x` first, then the body on `x_n`), one `always_ff` registers
  `x <= x_n`. Locals are declared at the top of the block and zeroed (the class
  zero-initializes them). `return` in a process body: the rest of the body becomes the
  else branch (as before). A reset-forced output read in step() reads
  `reset ? F : x_n` (the holder's `get_x`), simplified on paths where reset is known.
- **P5 Functions.** A function of the class is emitted as an SV function (read-only:
  writing state or ports from a function is an error for now). A function that reads
  state and is called from step() gets a variant reading the `_n` names.
- **P6 Composite.** One module per class; children instantiated with the parameter
  expressions of their declaration (`rr_arbiter #(.T(T), .N(N))`). A port array
  connected element-for-element (`foreach (in[i]) arb.in[i].connect_up(in[i])`) is
  connected whole; any other element mapping is an error for now.
- **P7 Tools.** Yosys's own reader lacks `parameter type`; the yosys flow reads
  `sv2v` output (sv2v is in the env). Verilator reads the SV directly.
- **P8 IR.** zuspec-ir-core: `DataTypeComponent.template_params` (`TemplateParam*`),
  `DataTypeInt.width_expr`, `DataTypeArray.size_expr`; references to parameters are
  `ExprRefParam(name)`, to type parameters `DataTypeRef(name)`; `$clog2` is
  `ExprCall(ExprRefUnresolved("clog2"))`. Sync processes with blocking (class order)
  semantics carry `metadata["order"] = "blocking"`.

Steps:
- [x] **L9a IR + be-sv.** The IR fields of P8; be-sv emits parameters, symbolic
      widths, packed port arrays, arrays, loops, locals, functions, next-state step().
- [x] **L9b Front end.** `fe/elab/sync_param.py`: class type → parameterized IR
      component (P1-P5). Unit tests.
- [x] **L9c Composite + driver.** `sync_tree` parameterized composite (P6); `emit_sync`
      option; `scripts/gen_rtl.py` writes the parameterized `rtl/gen/rr_merge.sv`.
- [x] **L9e Reference aligned with the classes** (user, 2026-11-14): same parameters,
      interface and state as the classes, hand-written style; tb uses the array ports.
- [x] **L9d Verify.** Verilator lint; lockstep `gen-sim` against the reference (tb
      adapted to array ports); BMC (via sv2v) against the reference at DEPTH = 2, 3, 4;
      cell counts. Results in `LOWERING-RESULTS.md`.

## Status

2026-11-14: plan written; the existing path surveyed (above).
- L0 done: the 37 sync elab/emit unit tests pass on this branch (factory + `m_init`).
- Probe (`rtl/rr_merge_emit_top.sv`, class variables `rr_merge`, `rr_arbiter4`,
  `rr_fifo2`): all three stop at G1 ("both step() and comb()"). `rr_merge` gets through
  `elaborate_tree`, factory children included, before that, so G11 looks fine.
- L1 done: `rtl/rr_merge_ref.sv` (binary ptr/owner + locked; FIFO binary wr/rd/count,
  out_valid/out_data registers), `tb/rr_merge_ref_tb.sv`; `dfm run ref-sim` passes with
  1528 beats, the same count as the class `sim` (same stimulus code and seed, so consistent with
  matching handshakes; not a lockstep compare).
  Verilator `-Wall` lint clean; yosys `synth` 183 cells (37 flops). The reference has no
  reset term on ready (class comb() has none; the class tb's ready = 0 in reset comes
  from the pin bridge).
- L2-L7 done (results: [LOWERING-RESULTS.md](LOWERING-RESULTS.md)):
  - `hier._obj_paths` names port-array elements (`rr_merge.arb.in[0]`; was `?`).
  - `sync.py` `_Body` rewritten as symbolic execution: locals, `for`/`foreach`
    (unrolled), `return`, inlined functions, computed indices (`?:` chains), struct
    members, `%`/`*`, parameters; SSA folded in (the old `_ssa`/`_raw` passes are gone).
    Locals become named comb wires (process `wires`, deduplicated). A class may have
    both step() and comb(); each field's drive is the process that writes it. Port and
    state arrays are flattened per element (`in_0_valid`, `mem_0`).
  - `sync_tree` expands port arrays.
  - zuspec-be-sv (packages/, separate repo): `ExprIfExp` from `zuspec.ir.core.expr`
    accepted (was "unknown expr"; `zuspec.ir.core.ExprIfExp` is a different class from
    `expr_phase2`); comparisons and `&&`/`||` parenthesized as operands (was
    `count + a && b`, `!a == b`).
  - Tests: `tests/python/unit/test_elab_sync_body.py` (new, 9 tests);
    `test_elab_sync_shape.py` bad_fn (a call) is now inlined.
  - Example: state narrowed to hardware widths (661 → 180 cells); reference fixed to
    force out_valid in reset; `scripts/gen_rtl.py` → `rtl/gen/rr_merge.sv`; dfm `gen-sim`
    (lockstep); `scripts/compare.sh`, `yosys/bmc.ys`, `yosys/equiv.ys`,
    `yosys/rr_merge_miter.sv`.
- Next: L8 (dfm tasks for synth/equiv once fw-hdl is installed in the env; README);
  unbounded proof (state-mapping invariants).
Note: the fw-hdl Python package is not installed in the IVPM venv; run Python with
`direnv exec . env PYTHONPATH=$PWD/python ...` (dfm tasks from `fw.hdl.*` do not
resolve until it is installed).
- 2026-11-14: L9 planned (parameterized RTL, above). Probe: a hand-written
  parameterized arbiter of that shape lints in Verilator and synthesizes via sv2v + yosys.
- 2026-11-14: L9a-L9c done.
  - zuspec-ir-core: `DataTypeComponent.template_params`, `DataTypeInt.width_expr`,
    `DataTypeArray.size_expr`; `ModuleInstance.parameters` values may be IR exprs/types.
  - zuspec-be-sv: new `sync_param.py` (dispatched from `generator.py`): parameters,
    symbolic widths, packed array ports, next-state step(), functions (a return inside
    a loop becomes a result + done flag: sv2v's conversion left latches), composite
    with `#(.T(T), .N(N))`, a `<var>_types` package for the default struct.
  - fw-hdl: `fe/elab/sync_param.py` (`sync_component_param`, `composite_param`);
    `emit_sync(..., parameterized=True)`; `scripts/gen_rtl.py` uses it.
  - Tests: `tests/python/unit/test_sync_param.py` (8, Verilator lint included); the
    existing sync tests and be-sv's unit tests pass.
  - L9d so far: Verilator lint clean but for width warnings (the class's own `int`
    arithmetic); lockstep `gen-sim` PASS (2329 cycles, a `+ 2` bug is caught); BMC
    DEPTH=2 passes with data compared every cycle (the reset-time data difference of
    the unrolled flow is gone: next-state logic holds data in reset, as the class).
    Cells 255 vs reference 186 (unrolled flow: 180): being investigated.
- 2026-11-14: L9d, L9e done (results: [LOWERING-RESULTS.md](LOWERING-RESULTS.md)).
  - Reference rewritten to describe what the classes describe (it had N fixed at 4,
    flattened ports, `W` for `T`, its own encodings). Same parameters, interface and
    state names as the generated RTL.
  - `scripts/compare.sh`: both through sv2v; unbounded equivalence by induction
    (`yosys/equiv.ys`, pairs same-named state) over N in {2,3,4,5,8} x DEPTH in
    {1,2,3,4,8}; BMC from reset at (4,2), (4,3), (3,2). Injected bugs make it fail.
  - Cells: first parameterized output 136/130 (arbiter/FIFO). Class index locals at
    hardware width (`idx_t g`, `function idx_t grant()`, README rule 10) and the
    emitter's enabled-write arrays bring it to 99/82 (reference 93/70).
  - Emitter: a no-argument function on current values is computed once
    (`always_comb grant_v = grant()`), no conditional call (latches for its locals);
    functions after the declarations; return types from the prototype syntax.
- Next: explicit casts at the class's implicit width conversions (lint-clean
  hand-off RTL); L8 close-out (dfm tasks once fw-hdl is installed).
