# rr_merge lowering: results

The class model (`src/*.svh`) lowered to parameterized Verilog by the fw-hdl sync
flow, compared with the hand-written reference `rtl/rr_merge_ref.sv`. Plan and
status: [LOWERING.md](LOWERING.md) (L9 is the parameterized flow; the earlier,
fully unrolled flow of L2–L7 is summarized at the end).

## How to reproduce

From `examples/rr_merge`:

```
direnv exec . env PYTHONPATH=$PWD/../../python python scripts/gen_rtl.py   # -> rtl/gen/rr_merge.sv
direnv exec . dfm run gen-sim     # generated RTL, lockstep with the reference
direnv exec . dfm run ref-sim     # reference alone
direnv exec . dfm run sim         # the class model (sv-weave flow)
direnv exec . sh scripts/compare.sh   # yosys synth of both, equivalence (rundir/compare/)
```

## Pipeline

```
src/*.svh ── elaborate_tree ──────► instance tree, sync wiring (arb.in[i] ↔ in[i])
          ── sync_component_param ► Zuspec IR per class: template_params (T, N / DEPTH),
                                     symbolic widths and sizes, bodies as written
                                     (loops, array/member selects, functions)
          ── composite_param ─────► rr_merge: instances #(.T(T), .N(N)), whole-array nets
          ── zuspec-be-sv ────────► rtl/gen/rr_merge.sv: package rr_merge_types
                                     + rr_arbiter, rr_fifo, rr_merge
```

What the generated RTL looks like:

- **One module per class, parameterized as the class is:** `rr_arbiter #(type T,
  int N = 4)`, `rr_fifo #(type T, int DEPTH = 2)`, `rr_merge #(type T, int N, int
  DEPTH)`. The default `T` is `rr_merge_types::rr_beat_t`, in a generated package.
- **Ports:** a port array is a packed array per field (`input logic [N-1:0]
  in_valid`, `input T [N-1:0] in_data`).
- **Widths:** state keeps its declared widths, symbolically (`logic
  [$clog2(DEPTH)-1:0] wr`, `T mem [DEPTH]`).
- **`comb()`:** an `always_comb`.
- **`step()`:** next-state logic in the class's blocking order. An `always_comb`
  computes `x_n` from `x_n = x`, then one `always_ff` registers it.
- **`mem`:** written from one place in `step()`, so it becomes an enabled write
  (`mem_we/mem_wa/mem_wd`). The read after it takes a bypass, `(mem_we && mem_wa ==
  rd_n) ? mem_wd : mem[rd_n]`.
- **`grant()`:** an SV function, computed once per cycle (`always_comb grant_v =
  grant()`). Its return inside the loop is written as a result plus a done flag.
- **Reset-forced output:** `out.valid` is `assign out_valid = reset ? '0 :
  out_valid_q`.

## The reference

The reference was first written against the fully unrolled flow's interface: N fixed
at 4, flattened ports (`in_0_valid`), a width `W` in place of `T`, and its own
encodings (a reverse priority scan, an `inc()` wrap, a separate data `always_ff`).
It now describes what the classes describe, in hand-written RTL style:

- the same parameters (`type T`, `N`, `DEPTH`) and interface as the generated RTL;
- the same state, by name and width: `ptr`, `locked`, `owner`; `mem`, `wr`, `rd`,
  `count`, `out_valid_q`, `out_data`;
- the same update rules. `comb()` is continuous logic and `step()` one `always_ff`.
  The values `step()` reads after writing them (`rd`, `count`, the head after a push)
  are next-state wires.

The same names and encodings are what let the equivalence proof below close
without hand-written invariants.

## Simulation

| Run | Result |
|---|---|
| class model (`sim`) | PASS, 1528 beats |
| reference (`ref-sim`) | PASS, 1528 beats |
| generated (`gen-sim`) | PASS, 1528 beats; **lockstep with the reference: 2329 cycles, 0 differences** on every output |

The lockstep compare can fail. Changing `ptr_n = (g + 1) % N` to `+ 2` in the
generated file gives lockstep errors from 130 ns.

## Equivalence

`scripts/compare.sh` reads both designs through sv2v, because yosys's reader has no
`parameter type`. It runs two checks:

- **Unbounded (`yosys/equiv.ys`):** `equiv_make` pairs the two designs' signals by
  name, and `equiv_simple` + `equiv_induct` prove the pairs together by induction.
  The result holds from any state where the paired registers agree, not only from
  reset.
- **Bounded from reset (`yosys/bmc.ys` on `yosys/rr_merge_miter.sv`):** ready,
  valid and data must match every cycle for 40 cycles, from all-zero registers, with
  free inputs (reset included).

| Check | N | DEPTH | Result |
|---|---|---|---|
| equiv (unbounded) | 2, 3, 4, 5, 8 | 1, 2, 3, 4, 8 | **proven, all 25 points** |
| BMC, 40 cycles | 4 | 2 | pass |
| BMC, 40 cycles | 4 | 3 | pass |
| BMC, 40 cycles | 3 | 2 | pass |

Both checks can fail. With `(g + 1) % N` changed to `+ 2` in the generated design,
the induction leaves 2 of 135 points unproven. With `count + push - pop` changed to
`count + push`, it leaves 21.

The proofs cover the parameter values listed, not every value. The modules are
parameterized, so any other point is one `chparam` away (`yosys/equiv.ys`).

## Synthesis (yosys 0.70 `synth`, generic gates, N = 4, DEPTH = 2)

| | by module | arbiter | FIFO | flattened | flops |
|---|---|---|---|---|---|
| generated | **181** | 99 | 82 | 207 | 37 |
| reference | **163** | 93 | 70 | 201 | 37 |

Flattening lets ABC work across module boundaries, so the flattened totals don't
add up from the per-module counts.

What the parameterized form cost at first, and the fixes (a subagent measured each
change):

| Generated RTL | arbiter | FIFO |
|---|---|---|
| first parameterized output | 136 | 130 |
| index locals at hardware width in the class (`idx_t g`, `function idx_t grant()`) | 99 | – |
| one-site array write as an enabled write + bypass read (no `mem_n = mem` copy) | – | 82 |

- **Arbiter.** A 32-bit `int` used as an index (`in_data[g]`, `i == g`) becomes a
  32-bit shift/compare network. The generator keeps declared widths, because the
  module must hold for every N. So the class declares indices at hardware width
  (README style rule 10).
- **FIFO.** `sv2v` turns a whole-array next-state copy (`mem_n = mem`) into one packed
  vector with multiply/subtract index arithmetic. An array written from more than
  one place still takes a next-state copy, but the generator copies it element by
  element.

The remaining FIFO gap (82 vs 70) is the next-state mux structure and the 32-bit
write address `mem_wa`.

## Open

- **Lint.** The generated RTL has Verilator width warnings, and they all come from
  the class's own implicit conversions (`(wr + 1) % DEPTH` is 32-bit arithmetic,
  truncated on assignment). Explicit casts at those conversions would make it lint
  clean for hand-off. The reference has them.
- **Function variants.** A function that reads registers and is called in `step()`
  after a register write gets a variant reading the next-state names
  (`grant_n()`). rr_merge doesn't need one.
- **Not lowered parameterized yet:**
  - role ports (fw_proto);
  - nested composites;
  - functions that write fields;
  - a `return` inside a loop of a process;
  - port arrays connected other than element for element.
- **The dfm task** `fw.hdl.sync.Emit` doesn't resolve until the fw-hdl Python package
  is installed in the env. `scripts/gen_rtl.py` stands in for it.

## Earlier: the fully unrolled flow (L2–L7)

Before L9, the flow elaborated one specialization:
- loops were unrolled;
- arrays were flattened per element (`in_0_valid`, `mem_0`);
- module names were hashed (`rr_arbiter__5d7e211b`).

It gave 180 cells against 186 for the reference of that time. Its lockstep sim and
BMC passed, but data had to be compared only while valid. The emitter wrote the
un-reset data registers during reset, and the class holds them. The parameterized
flow's next-state logic holds them, so data is now compared every cycle. That path,
`fe/elab/sync.py`, stays for its other users. `emit_sync(..., parameterized=True)`
selects the new one.

The same work turned up a style point. With the class state as first written (`int
ptr, owner; int unsigned wr, rd, count`), the unrolled design was 661 cells and 128
flops, and synthesis couldn't prove the upper bits stay zero.
