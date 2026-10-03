# idct_chen: the JPEG inverse DCT, and the `>>>` trap

From XLS's `xls/examples/jpeg/idct_chen.x` (`orig/`, unmodified): the 8x8 inverse DCT
(Chen), as rows then columns.

## The tests

`idct_row_test` and `idct0_test`..`idct3_test`, transcribed in
[`idct_chen_unit_test.sv`](idct_chen_unit_test.sv) (the 64-element vectors copied from
the DSLX mechanically).

## The port

| DSLX | SV ([`idct_chen_pkg.sv`](idct_chen_pkg.sv)) |
|---|---|
| `(x7 + x1) >> u32:8` on `s32` | `(x7 + x1) >>> 8` |
| `let x4 = x8 + w1mw7 * x4;` (rebinding) | `x4 = x8 + w1mw7 * x4;`, every local declared at the top |
| `row0 ++ row1 ++ ... ++ row7` | a loop filling the 64 entries |
| `match i & u8:7 { ..., _ => fail!(...) }` | `case (iu & 8'd7) ... default: assert (0) else $fatal(...)` |

**The trap.** DSLX's `>>` on a signed value is an *arithmetic* shift: DSLX picks the
shift from the type. SV's `>>` is always logical. Every right shift of an `s32` here is
`>>>`; a port that kept `>>` would be wrong for negative coefficients, and idct2/idct3
(negative outputs) would catch it.

No other deviations. Both functions are proven equivalent; `idct` is 1,883 nodes on
both paths.
