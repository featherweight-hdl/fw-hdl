# Knob files

A knob file decides what the source does not:
- where registers go;
- how deep buffers are;
- each block's schedule;
- how storage is bound;
- which latencies are contracts.

It is YAML, checked against `python/fw/hdl/schema/knobs.schema.json`. An unknown
key or a bad value is an error that names the file and line.

`fw.hdl.knobs.Resolve` (or `fw-hdl knobs resolve <file> -o <dir>`) writes three
files:
- `<top>.knobs.json`: the merged knobs.
- `<top>_knobs_pkg.sv`: one `localparam` per `rtl:` entry.
- `<top>.codegen.json`: per-module options for `synth.xls.Codegen`.

## Merging

`base:` names knob files to merge first, in order, relative to this file. When
files merge:
- dicts merge key by key;
- lists and scalars replace;
- the later file wins.

Every merged value keeps the file and line it came from.

## Keys

| Key | Value | Meaning |
|---|---|---|
| `base` | file or list | knob files merged first |
| `design.top` | class | the structural top |
| `design.xls` | list of classes | the children lowered through XLS |
| `design.files`, `design.incdirs`, `design.model_top` | | sources, include dirs, class-model testbench top |
| `design.extern.<class>` | `{signature, module, files}` | a child supplied as RTL with a hand-written block signature; a class that implements `fw_extern_impl` derives its own instead (see [Wrapped IP](extern.md)) |
| `design.filesets.<name>` | list of files | sources a wrapper's `extern_fileset()` may name (see [Wrapped IP](extern.md)); paths relative to the knob file |
| `design.facts` | list of files | sidecar files of characterization facts (`fw-hdl.facts`, see [Characterization facts](facts.md)); paths relative to the knob file |
| `rtl.<NAME>` | int, bool or string | a localparam of `<top>_knobs_pkg` (for example, a channel depth the source reads) |
| `xls.default` | block options | applied to every XLS block |
| `xls.blocks.<class>` | block options | one block; wins over `default` |
| `xls.chan_flop.<class>.<channel>` | `none`, `flop`, `skid`, `zerolatency` | the register on one channel of a proc block |
| `storage.default`, `storage.<instance path>` | `{bind, module, macro, read_latency, files}` | what holds a channel's values: `flops`, `xls_fifo`, `wrapper` or `sram` (see [Storage binding](../methodology/storage.md)); the path is below the top, such as `q` or `sub.q` |
| `island.groups.<name>` | list of classes | blocks lowered as one multi-proc package (they must share one schedule) |
| `island.exceptions` | list of `{channel, kind, reason}` | boundaries that are not registered both ways; `kind` is `same_cycle`, `fixed_timing`, `single_value`, `cdc` or `merged` |
| `delay.scale` | number > 0 | delay-model pessimism: the scheduler is given `clock_period_ps * scale` |
| `delay.model` | name or file | the scheduler's delay model when a block names none |
| `contracts.latency."<a> -> <b>"` | `{min, max, fixed}` | a latency contract in cycles (see [Reports](reports.md)) |

**Block options:**

| Option | Meaning |
|---|---|
| `pipeline_stages`, `clock_period_ps`, `delay_model`, `worst_case_throughput` | the XLS schedule |
| `flop_inputs`, `flop_outputs`, `flop_inputs_kind`, `flop_outputs_kind` | register every input (output) channel. For a proc this is written on the IR's channel interfaces, because codegen's own flags do not register a proc's channels |
| `reset`, `reset_active_low` | the reset pin |
| `io_constraints` | extra XLS `--io_constraints` entries |
| `extra_args` | passed to `codegen_main` unchanged |

## Register costs

A `flop` or `skid` register on a proc channel costs one cycle; `zerolatency` and
`none` cost nothing. A `skid` register cuts both the valid/data path and the ready
path. That makes a depth-0 channel between two skid-registered ports a registered
island boundary ([Islands](../methodology/islands.md)).

## Example

```yaml
# k2.yaml
base: common.yaml
rtl: {RT_Q_DEPTH: 0}
xls:
  chan_flop:
    rt_tag.out: skid
    rt_resp.in: skid
```

This is from `examples/resp_tracker/knobs/`.
