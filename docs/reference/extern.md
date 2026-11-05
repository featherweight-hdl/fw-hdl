# Wrapped IP

A wrapper is a class that implements `fw_extern_impl` (`src/fw_extern.svh`). It
stands for an existing Verilog module. See [Wrapped IP](../methodology/ip-reuse.md)
for how to use one.

## `fw_extern_impl`

| Method | Returns |
|---|---|
| `extern_module()` | the module's name |
| `extern_fileset()` | its sources: a fileset name (knob `design.filesets`), or file paths separated by spaces, relative to the file that declares the class |
| `extern_map(fw_extern_map x)` | records the module's parameters and how its pins are used |

`` `fw_extern_utils(MODULE, FILESET) `` (in `fw_hdl_macros.svh`) defines the first two.

## `fw_extern_map`

| Call | Meaning |
|---|---|
| `param(name, value)` | an integer module parameter |
| `param_str(name, value)` | a string module parameter |
| `clock(pin)` | the clock pin (required) |
| `reset(pin, active_low = 0)` | the reset pin; Integrate inverts the design's reset for an active-low one |
| `rv(port, name, style = "fw", data = "", valid = "", ready = "")` | a ready/valid port |
| `valid(port, name, style = "fw", data = "", valid = "")` | a valid-only output port |
| `level(port, pin)` | a level port: one pin |
| `tie(pin, value)` | an input pin held at a constant |
| `open(pin)` | an output pin left unconnected on purpose |

`port` is any port of the wrapper (`fw_endpoint`, the base of every port), including
an element of a port array. `name` fills `${ep}` in the pin template of `style`:

| Style | data | valid | ready |
|---|---|---|---|
| `fw` | `${ep}` | `${ep}_valid` | `${ep}_ready` |
| `xls` | `${ep}` | `${ep}_vld` | `${ep}_rdy` |

The `data`, `valid` and `ready` arguments override single pins (use named arguments:
`.data("in_data")`). A ready/valid port's `fw` template is the `fw_rv` kit's.

In a class simulation `extern_map()` only records; the wrapper's body (inherited from
the class it realizes) is the model.

## Checks

Partition reads the module's header with the record's parameter values applied
(`fw.hdl.rtl_header.read_header`) and checks:

| Rule | Error |
|---|---|
| every module pin is used once | `pin(s) [...] of M are not accounted for` / `pin 'p' of M is both A and B` |
| every pin named exists | `M has no pin 'p'` |
| every parameter named exists and is not a localparam | `no parameter P (module parameters are [...])` |
| every wrapper port is mapped once | `extern_map() does not map port(s) [...]` / `port p is mapped twice` |
| the map call fits the port's kind | `port p is a ready/valid port; map it with x.rv(...)` |
| directions: data and valid follow the port, ready opposes it; a tie is an input, an open an output | `pin 'p' of M is an input, expected an output` |
| widths: data is the payload's width, valid/ready/clock/reset are 1 bit, a tie fits its pin | `pin 'p' of M is 9 bits with parameters ..., expected 8` |
| the map depends only on the class and its parameter object | `a map may depend only on the class and its parameter object` |
| a class is not both a wrapper and in knob `design.extern` | `... also assigned by knob design.extern; keep one` |

## In the partition file

A wrapper child in `partition.json` has `engine: extern`, `realization: wrapped`, a
`sig` key (one per specialization), and under `extern`:
- `module`, `files`;
- `record`: the map, format `fw-hdl.extern-record` version 1;
- `signature_json`: the derived block signature;
- `params`, `ties`, `opens`: what Integrate adds to the instance, as Verilog.

The boundary check elaborates the module with the same parameter values.

## Importer: `fw-hdl wrap`

```
fw-hdl wrap <files> --module M [--abstract NAME] [--class NAME] -o out.svh [--report FILE]
            [-I dir] [-D NAME[=VALUE]]
```

Reads `M`'s header with its default parameters and writes:

- **`out.svh`**, to `` `include `` in a package that imports `fw_hdl_pkg` and
  `fw_std_pkg`:
  - `<M>_params`: a parameter object with the module's parameters and their defaults;
  - with `--abstract NAME`: `virtual class NAME`, holding the ports only;
  - the wrapper `<M>_rtl` (or `--class`), extending `NAME` (or holding the ports itself,
    in which case nothing can substitute for it), with `extern_map()` and a commented
    `facts()` stub. The fileset is the module's files relative to `out.svh`.
- **`out.cosim.yaml`**: a [cosim](../methodology/testing.md) spec with one target (the
  module, its files, parameters, clock, reset and pin map). Its `class` is `TODO` or the
  abstract class; set it to a library class with a cosim driver and rename the port keys
  to that class's ports.
- **The inference report**, on stdout (and `--report`): each port with its pins and a
  confidence.

How pins become ports:

| Pins | Port | Confidence |
|---|---|---|
| clock: a 1-bit input named `clk`, `clock`, `aclk`, `*_clk`, ...; else the `posedge` signal in the body | `x.clock` | |
| reset: a 1-bit input with `rst` or `reset` in its name; else the `negedge`/`posedge` signal beside the clock. Active low when the name ends in `n`, `_n`, `_ni`, `_b`, `_l` or starts with `n` | `x.reset` | |
| valid, ready and data of one stem, directions agreeing (data and valid one way, ready the other). Valid by the kits' templates (`${ep}_valid`), XLS's (`${ep}_vld`) or `valid_${ep}`; data as `${ep}`, `${ep}_data`, `${ep}_dat`, `${ep}_d` or `data_${ep}` | ready/valid | high; medium when two data pins fit |
| valid and data outputs, no ready | valid-only (`fw_valid_put_if`) | medium |
| the same shape on stems numbered 0..N-1 (`req0`, `req1`, ...) | a port array, mapped in a `foreach` | as its members |
| a debug-like output (`dbg`, `debug`, `test`, `scan`, `spare`, `unused`) | `x.open` | low, TODO |
| a debug-like input | `x.tie(pin, 0)` | low, TODO |
| any other pin | a level (`fw_level_if` in, `fw_level_set_if` out) | low |

A valid-only input, an `inout` pin, an interface port and a type parameter are reported
and left as TODO comments. Port types use the widths at the default parameters; change
a parameter in the parameter object and the port types must change with it (the
[checks](#checks) say so).

**Never overwrites.** When `out.svh` (or the cosim file) exists and differs from what
would be written, the new text goes to `out.svh.new`, a unified diff is printed and the
command exits 1. An identical file is left as is.

