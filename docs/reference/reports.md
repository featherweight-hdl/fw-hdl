# Reports and latency contracts

## Latency table (`fw.hdl.report.Latency`)

For every path from a top input to a top output, the report gives the **first-value
latency** in cycles, with every input valid and every output ready:

- **Through a proc block:** the stage of its send minus the stage of its receive
  (read from the block's schedule and optimized IR). Add 1 for each registered
  channel (`flop` or `skid` in its codegen signature).
- **Through a channel:** 1 for a FIFO (depth ≥ 1, no bypass); 0 for a wire.

Output is `latency.md` and `latency.json`. The XLS signature's `pipeline.latency`
is not used: for a proc it counts stages, not the receive-to-send distance.

```
| `req -> rsp` | 3 | tagger[in->out]=0 + q[depth=1]=1 + responder[in->out]=2 |
```

`tests/xls/test_latency_report.py` and `tests/xls/test_resp_tracker.py` check that
the prediction equals the latency measured in simulation, for every knob set.

## Latency contracts

Contracts go in the knob file:

```yaml
contracts:
  latency:
    "req -> rsp": {max: 8}                          # a top path, by top ports
    "rt_resp.in -> rt_resp.out": {fixed: 2}         # one block, class.channel
```

Each contract is checked three times:

1. **Before codegen** (`fw.hdl.check.Contracts`; make `synth.xls.Codegen` need it).
   Each block is bounded by its knobs: at least its channel registers, at most those
   plus `pipeline_stages - 1`. Channels are exact. A contract that no allowed
   schedule meets fails the flow, naming the contract, the path and the range the
   knobs allow. No XLS tool runs.
2. **In codegen.** A block contract becomes an XLS `--io_constraints` entry on the
   receive-to-send distance (the contract minus the block's registers), so the
   scheduler places the operations to meet it.
3. **After codegen** (`fw.hdl.report.Latency` with an `fwKnobs` input). Every
   top-path contract is checked against the exact table. A violation names the path
   and its hops.

## Schedule PPA (`fw.hdl.report.Ppa`)

`xls_ppa.csv` has one row per block, with the columns `block, stages, ii, crit_ps,
crit_src, crit_src_ps, path`.

`crit_src` is the source line whose nodes contribute the most delay to the
critical path the schedule shows; `path` lists the lines along that path. Use a
characterized delay model (for example `asap7`) for this. Under `unit`, every node
costs the same, so bookkeeping nodes can outweigh real logic.

## Delay-model calibration

`delay.scale` in the knob file multiplies the clock period given to the scheduler.
A delay model that is k times pessimistic for the target library takes
`scale: k`. The scheduler then fills each stage as the real library would.
Fitting a model from QoR results is outside fw-hdl.

## Toolchain record

Every `synth.xls.Codegen` run writes `toolchain.json`. It names the `opt_main` and
`codegen_main` that ran: their path, SHA-256 and the xlsynth release.
