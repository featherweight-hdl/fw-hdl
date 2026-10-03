# lfsr: a parametric function at two widths

From XLS's `xls/examples/lfsr.x` (`orig/`, unmodified). `lfsr_proc.x` is copied too; its
port waits on a non-blocking receive (xls-examples.md GAP-3).

## The tests

`lfsr7_test` and `lfsr8_test`, transcribed in [`lfsr_unit_test.sv`](lfsr_unit_test.sv),
including the full-period checks: 127 (and 255) calls in a row through the API, each
feeding the last result back in. At `rtl` and `gates` that is 382 calls through the
transactor; the file is the same.

## The port

| DSLX | SV ([`lfsr_pkg.sv`](lfsr_pkg.sv)) |
|---|---|
| `pub fn lfsr<BIT_WIDTH: u32>(...)` | `class lfsr_c #(BIT_WIDTH)` with `static function lfsr(...)`; `lfsr_c#(7)::lfsr` is `lfsr<u32:7>` |
| `for (index, xor_bit): (u32, u1) in u32:0..BIT_WIDTH {...}(u1:0)` | `for (int index = 0; index < BIT_WIDTH; index++)` with `new_bit` as the accumulator |
| `if tap_mask[index+:u1] == u1:0 { xor_bit } else { ... }` | `new_bit = (tap_mask[index] == 1'b0) ? new_bit : new_bit ^ current_value[index]` |
| `current_value[u32:0+:uN[BIT_WIDTH - u32:1]] ++ new_bit` | `{current_value[BIT_WIDTH-2:0], new_bit}` |

No deviations. `lfsr7` and `lfsr8` are each proven equivalent to the DSLX.

Two specializations of one class used to collide in fw-hdl's front end (both became IR
function `lfsr`); this example found it (xls-examples.md G-3, fixed).
