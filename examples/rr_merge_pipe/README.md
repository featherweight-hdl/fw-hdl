# rr_merge_pipe: a map on each side of rr_merge

The vehicle for phase 1 (D0) of micro-pipelining sync logic
([`docs/design/micro-pipelining-feasibility.md`](../../docs/design/micro-pipelining-feasibility.md)).
`rr_merge` (from [`../rr_merge`](../rr_merge), unchanged) with a function on
each input and one on the output, written by hand in pipelined forms, run on
a latency-insensitive bench, measured, and pipelined automatically by a
spike. The findings are in [`RESULTS.md`](RESULTS.md).

```
 in[0] ─► ┐                  ┌──────────┐
 in[1] ─► ┤ min: f_in,       │ rr_merge │   mout: f_out
 ...      ┤ N lanes      ──► │ arb→fifo │ ──► one lane   ──► out
 in[N-1]► ┘ y = a * b + c    └──────────┘     y ^ (y >> 3)
```

| File | What |
|---|---|
| `src/pipe_types_pkg.sv` | beat types per W (8, 16, 32): `pipe_in`, `pipe_mid`, `pipe_prod` (K = 2 stage 1) |
| `src/rr_merge_pipe_pkg.sv` | the class package: includes `rr_merge`'s classes and the ones below |
| `src/pipe_map_in.svh`, `pipe_map_out.svh` | the maps as written (one statement per field, `f` a function) |
| `src/rr_merge_pipe.svh` | `rr_merge_pipe` (v0) |
| `src/pipe_map_in_key.svh` | the answer key: `pipe_map_in` as stall, elastic and credit, K = 1, 2 |
| `src/pipe_stage_key.svh` | `pipe_skid`, `pipe_map_out_stall1`, `rr_merge_skid` |
| `src/rr_merge_pipe_key.svh` | the variant composites `rr_merge_pipe_<variant>` |
| `tb/pipe_bench.sv` | the latency-insensitive bench (per-source scoreboard, monitors, measures) |
| `tb/pipe_mutant.sv` | breaks the output stream on purpose, to show each check fires |
| `tb/pipe_rtl_tb.sv`, `tb/pipe_cls_tb.sv` | the bench on generated RTL, and on the classes |
| `formal/` | SBY harnesses: datapath ≡ `f`, stall-controller properties |
| `yosys/equiv_pair.ys` | unbounded equivalence of two forms by register name |
| `models/yosys_generic.json` | a delay model characterized from yosys (F5c) |

## Running

From this directory, with Python as
`direnv exec . env PYTHONPATH=$PWD/../../python python`. Logs go under
`rundir/`.

| Command | What |
|---|---|
| `scripts/gen_rtl.py` | lower v0 and the 8 answer-key variants to `rtl/gen/<module>.sv` |
| `scripts/gen_auto.py [K ...]` | pipeline v0's input map automatically (spike F6): `rtl/gen/rr_merge_pipe_auto<K>.sv` |
| `sh scripts/run_rtl.sh <file> <module> [W] [N] [seeds] [sinks]` | one module on the bench |
| `sh scripts/run_matrix.sh` | every variant: W = 8, 16, 32 and N = 2, 4 (`rundir/rtl/matrix.txt`) |
| `sh scripts/run_mutants.sh` | each bench check catches its mutant |
| `sh scripts/measure.sh` | cells, flops and logic levels per variant × W (`rundir/measure/measure.txt`) |
| `sh scripts/equiv_auto.sh [gold gate]` | the generated `auto1` ≡ the hand-written `stall1`, unbounded |
| `sh scripts/formal.sh [K ...]` | SBY proofs and their mutants |
| `dfm run sim` | the classes on the bench: passes since the two-phase edge closed G4 ([`sync-task-domains.md`](../../docs/design/sync-task-domains.md) §8.3; RESULTS.md, "The class model") |

Run each `sh` script as `direnv exec . sh scripts/<name>.sh`.

## The bench

`tb/pipe_bench.sv` drives N inputs and one sink, and checks streams, not
cycles, so every variant runs on it whatever its latency:

- **Drivers.** Packets of 1–4 beats. Each source's beats, packet lengths and
  gaps come from its own generator, so a seed gives every variant the same
  streams. `tag` = {source, seq}.
- **Sink.** `ready` always on (`+sink=0`), 50% random (`+sink=1`), or in
  bursts (`+sink=2`).
- **Checks.** Each beat out is its source's next expected beat (order,
  content, no loss or duplication, against an independent 64-bit model).
  Packets arrive whole, and the queues are empty at the end. A monitor
  checks that a stalled output stays.
- **Measures.** The latency of a lone beat, beats per 100 cycles with every
  source valid and the sink ready, and the source order of the first 200
  packets.

It samples the DUT's outputs through a clocking block (`#1step`), so the
classes and the RTL are sampled alike.
