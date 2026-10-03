# rle: two procs, and their composition

From XLS's `xls/modules/rle/{rle_common,rle_enc,rle_dec}.x` (`orig/`, unmodified).

## The tests

Upstream's six `#[test_proc]`s, in [`rle_unit_test.sv`](rle_unit_test.sv). A test proc
spawns the encoder or decoder, sends stimulus on its input channel, and receives and
checks its outputs. Here each test puts on the component's input port and gets from its
output port, through the generated component API:

```systemverilog
foreach (stimuli[counter]) begin
    stimulus = '{symbol: stimuli[counter], last: counter == 3};
    enc.input_r_put(stimulus);
end
...
enc.output_s_get(enc_output);
`FAIL_UNLESS_EQUAL(enc_output, expected)
```

At `model` the SV components run on the fw-hdl runtime; at `rtl` and `gates` the XLS
procs run, each channel driven or collected on its ready/valid pins.

## The port

| DSLX | SV ([`rle_pkg.sv`](rle_pkg.sv)) |
|---|---|
| `proc RunLengthEncoder<SYMBOL_WIDTH, COUNT_WIDTH>` | `class RunLengthEncoder #(...) extends fw_component` |
| channels `input_r`, `output_s` | `fw_port #(fw_get_if #(EncInData)) input_r`, `fw_port #(fw_put_if #(EncOutData)) output_s` |
| `init { State {...} }` | the class's properties, initialized |
| `next(state)` | the body of `forever` in `run()` |
| `recv_if(tok, input_r, !state.prev_last, zero_input)` | `if (!prev_last) input_r.t.get(input_);` |
| `send_if(tok, output_s, do_send, data)` | `if (do_send) output_s.t.put(...)` |
| `struct PlainData<SYMB_WIDTH>` | a packed struct in `class rle_common #(...)` |
| `fail!("invalid_count_0", ...)` | `assert (0) else $fatal(1, "invalid_count_0")` |

The specializations: `RunLengthEncoder32`/`RunLengthDecoder32` are upstream's codegen
ones (count width 2, which the overflow tests use too); `..._32_32` are the tests'
common one.

**Verilator 5.049** swaps the nested types of two specializations of one class depending
on which is named first (fixed in 5.053). The flow and the test name the count-width-2
specialization first.

The QoR table compares like for like (`rtl-qor`: upstream's two specializations). The
SV path is the smaller one; why is still to look into.

## The composition (not upstream)

[`loop_flow.yaml`](loop_flow.yaml) builds `rle_pkg::rle_loopback`, a structural
component: the encoder feeds the decoder through a channel. The SPL -> RTL pipeline of
xls-phase2.md partitions it, has XLS implement each block, and integrates the top from
the blocks' signatures alone. [`rle_loop_unit_test.sv`](rle_loop_unit_test.sv) checks
that what goes in comes back out, at every level.
