# X0 probes: sync and task domains

Throwaway probes for step X0 of
[`sync-task-domains.md`](../../sync-task-domains.md). They ran on a scratch
mirror of the repo. These patches recreate it; none is applied to `src/`.
The findings are in the plan's §8 (X0 findings).

| File | What |
|---|---|
| `x0-kernel.patch` | the X0 kernel against `src/`: two-phase edge, `<=` pin bridges, pin inputs to `cur`, no early-write guard, and an absolute edge index on clock domains (that last part is superseded by the plan's §6.5) |
| `x0-tests.patch` | the test changes that go with it: re-baselined `fw_sync_kernel_unit_test.sv` (debug `$display`s left in), an `edge_index()` stub in `tests/clock_domain/cd_root2.svh`, a fixed stream seed (`+s0=<hex>`) in `pipe_bench.sv` |
| `x03-rr_merge_tb.patch` | `rr_merge_tb.sv` with three sampling modes (`RR_SAMPLE_CB`, `RR_SAMPLE_LATE`, as is) and a monitor; for today's kernel |
| `edge_phase.sv`, `run_edge_phase.sh` | X0.2: does every process that ticks a domain see the same edges? |
| `put_ep.sv`, `run_put_ep.sh` | X0.4: a minimal put endpoint, run with the task before and after the kernel at each edge |

## Recreating the mirror

```sh
M=<scratch>/x0; R=$PWD
mkdir -p $M/examples $M/tests
for f in flow.yaml python packages .envrc; do ln -s $R/$f $M/$f; done
cp -r src $M/; cp -r examples/rr_merge examples/rr_merge_pipe $M/examples/
cp -r tests/sync tests/clock_domain $M/tests/
cd $M && patch -p1 < $R/docs/design/probes/sync-domains-x0/x0-kernel.patch \
      && patch -p1 < $R/docs/design/probes/sync-domains-x0/x0-tests.patch
direnv allow .
```

Run `dfm run sim` in each example. Run the sync SVUnit suite through a
throwaway package that imports `tests/sync/flow.yaml`, as
`tests/sync/test_sync_svunit.py` does.

## Probes

- **X0.2** works against either kernel (it only ticks clocks):
  `direnv exec . sh docs/design/probes/sync-domains-x0/run_edge_phase.sh`
  uses this repo's `src/` and shows the two processes out of phase. Set
  `S=$M/src` to use the patched clocks, which keep them in phase.
- **X0.4** needs the X0 kernel:
  `S=$M/src direnv exec . sh docs/design/probes/sync-domains-x0/run_put_ep.sh`
  should print `SAME in both orders`. Adding `DEFS=+define+NAIVE` builds the
  negative control, which should print `DIFFER`.

Build output goes to `build/` here (not kept).
