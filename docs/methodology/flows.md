# Flows

Every step is a [dv-flow](https://github.com/dv-flow/dv-flow-mgr) task, so a flow is a
file you can read and run with `dfm`. fw-hdl provides three task packages. The tool
wrappers come from dv-flow-libsynth (`synth.xls`, `synth.yosys`), and the SVUnit
runner from dv-flow-libhdltest (`hdltest.svunit`).

| Package | Tasks | Reference |
|---|---|---|
| `fw.hdl.xls` | `IR`: SV functions or components → XLS IR | {doc}`../reference/tasks` |
| `fw.hdl.api` | `Functions`, `Components`: the generated API; `ModelBinding`, `XlsBinding`: what answers it at each level | {doc}`../reference/tasks` |
| `fw.hdl.spl` | `Partition`, `Integrate`: a structural component → per-block XLS → an RTL top | {doc}`../reference/tasks` |

## A function, from source to tests

This is the graph of the {doc}`../examples/xls/crc32` example, less its DSLX half:

```yaml
- name: ir                       # SV -> XLS IR
  uses: fw.hdl.xls.IR
  needs: [src]
  with:
    top: [crc32_pkg::main]

- name: rtl                      # XLS IR -> Verilog
  uses: synth.xls.Codegen
  needs: [ir]
  with:
    pipeline_stages: 2
    input_valid_signal: input_valid
    output_valid_signal: output_valid

- name: api                      # the API the tests call
  uses: fw.hdl.api.Functions
  needs: [src]
  with:
    functions: [crc32_pkg::main]

- name: dut-model                # level model: the SV answers
  uses: fw.hdl.api.ModelBinding
  needs: [api]

- name: bind-rtl                 # levels rtl and gates: the XLS module answers
  uses: fw.hdl.api.XlsBinding
  needs: [api, rtl]

- name: synth                    # Yosys, per target
  strategy:
    select:
      axes:
        target: [generic, ice40, ecp5]
    body:
    - uses: synth.yosys.Synth
      needs: [rtl]
      with:
        target: "${{ this.target }}"
```

Each level's DUT is a fileset: `dut-model` alone, or `bind-rtl` with the Verilog or
with one of the netlists. The test task takes one test file and runs it against each.

## A composition

For a structural component the XLS step runs per block:

```
fw.hdl.spl.Partition ─► per block: synth.xls.Codegen ─► zuspec.xls.Signature ─► fw.hdl.spl.Integrate ─► RTL top
```

`Integrate` reads the blocks' signatures, not their Verilog, and writes the top
module: an instance per block, a wire or FIFO per channel, pins for the edge. The
{doc}`../examples/xls/rle` example's `rle_loop` runs it (`rle/loop_flow.yaml`).
