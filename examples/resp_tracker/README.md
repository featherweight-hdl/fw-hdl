# Response tracker: one source, many schedules

A reference design for knob-driven builds. The SV source (`src/rt_pkg.sv`) never
changes. Each knob file in `knobs/` picks queue depth, pipeline stages, channel
registers and latency contracts:

| Knob set | What changes | `req -> rsp` latency |
|---|---|---|
| `k0` | one stage per block, queue depth 2 | 1 |
| `k1` | responder over 3 stages, queue depth 1 | 3 |
| `k2` | skid registers on both sides of the queue, which becomes a wire (depth 0) | 2 |
| `k3` | `k1` with a contract (`max: 0`) no schedule can meet | rejected before codegen |

Build one:

```sh
dfm run all -D kset=k1
```

The flow is fw-hdl tasks only:
1. `fw.hdl.knobs.Resolve`
2. `fw.hdl.spl.Partition`
3. `fw.hdl.check.Contracts`
4. `synth.xls.Codegen` (each block with its own options)
5. `zuspec.xls.Signature`
6. `fw.hdl.spl.Integrate` (boundary checks at error severity)
7. `fw.hdl.report.Latency` and `fw.hdl.report.Ppa`

The latency table is in `rundir/resp_tracker.latency/latency.md`.

`tests/xls/test_resp_tracker.py` builds every knob set. For each one it checks
three things:
- The RTL and the class model give the same response stream under the in-order
  contract (`fw.hdl.verif.canon`).
- That stream matches a reference model.
- The table's latency equals what simulation measures.

**Stage 1** of the design is two blocks and a queue. Later stages add the
keyed table, a slot pool, out-of-order returns and a credited release loop
(schedulable-library-plan.md §6.8).
