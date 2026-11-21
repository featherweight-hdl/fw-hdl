# Pattern 1: the map stage (draft)

A draft page for the pattern catalog (`docs/design/process-synthesis.md`
§16), from phase 1 (D0). Its example runs in `examples/rr_merge_pipe`.

## Shape

One ready/valid input, one output, and a pure function `f` between them.
There's no state, and the handshake passes straight through:

```systemverilog
function TM f(TI x); ... endfunction       // reads only x

virtual function void comb();
    out.set_valid(in.get_valid());
    out.set_data(f(in.get_data()));
    in.set_ready(out.get_ready());
endfunction
```

- **Write one statement per field.** `fw_settle` orders `comb()` by
  top-level statement. A statement that writes `out.data` and also reads
  `out.ready` puts `ready → data` on the comb graph, and that becomes a false
  loop through any peer whose dependencies are coarse.
- **Lanes.** N lanes are one class with port arrays and one `foreach` per
  field, each lane reading only its own elements. The parameterized lowering
  doesn't take arrays of child components.
- **Recognized by** `fw.hdl.spikes.dataflow.match_map` (spike). It returns
  `f` as the IR expression for `out.data`, or the reason the class isn't a
  map: it has state, it is a filter, its ready depends on the input, and so on.

## Realizations

K is the number of stages. W = 32 figures, `f = a * b + c`, 4 lanes; from
`RESULTS.md`.

| Controller | `in.ready` | Cost per lane | Latency | Throughput | When |
|---|---|---|---|---|---|
| comb (as written) | `out.ready` | 0 | 0 | 1 | `f` fits in the cycle |
| `stall` | `!s<K>_v \|\| out.ready` (comb) | K × (payload + 1) flops | K | 1 | the forward path is long; the `ready` path is short |
| `elastic` | `!s<k>_sv` (a register) | 2K × (payload + 1) flops | K | 1 | the `ready` path is long too |
| `credit` | `count < K + 2` (a register) | K stages + a (K + 2)-entry FIFO and a count | K + 1 | 1 | `ready` comes from far away |

## What to expect

- **Register insertion alone helps only as much as `f` can be cut.** Put
  `f` before stage 1 and let retiming move the registers into it. At W = 32,
  ABC retiming takes stall-1 from 113 to 47 levels, and stall-2 to 37.
- **Cutting `f` by hand between operators** helps only if no one operator
  dominates. Here the multiply is ~95% of `f`, so `mul | add` buys 5 levels.
- **Each stage adds a cycle of latency.** Throughput stays one beat per
  cycle for every controller above.
- **In front of a merge, a stage changes the merge's interleaving.**
  Per-source order and content are kept. See `RESULTS.md` A8.

## Checking it

- **On the bench:** `tb/pipe_bench.sv` compares streams per source, ignoring
  timing, under three sink modes.
- **Datapath ≡ `f`:** with the sink ready, the output equals `f` of the input
  K cycles earlier (`formal/fv_props_datapath.v`).
- **Controller, proven once per template and K:** the j-th beat out is `f`
  of the j-th beat in, occupancy is ≤ K, `out.ready → in.ready`, and a
  stalled output stays (`formal/fv_props_ctrl.v`).
- **Against a hand-written form:** unbounded equivalence by register name,
  when the registers are named alike (`s<k>_v`, `s<k>_d`;
  `yosys/equiv_pair.ys`).
