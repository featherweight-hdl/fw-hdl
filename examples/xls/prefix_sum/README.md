# prefix_sum: arrays in, arrays out

From XLS's `xls/examples/prefix_sum.x` (`orig/`, unmodified): a Hillis-Steele parallel
prefix sum over `u16[16]`.

## The test

`prefix_sum_test`, transcribed in [`prefix_sum_unit_test.sv`](prefix_sum_unit_test.sv).
The arrays cross the API as SV unpacked arrays and compare with `==` (SVUnit's
`FAIL_UNLESS_EQUAL` uses `!==`, which unpacked arrays don't have).

## The port

| DSLX | SV ([`prefix_sum_pkg.sv`](prefix_sum_pkg.sv)) |
|---|---|
| `u16[ARRAY_SIZE]` | `typedef bit [15:0] values_t [ARRAY_SIZE]` |
| `for (i, c) in u32:0..std::flog2(ARRAY_SIZE) {...}(values)` | `for (int i = 0; i < $clog2(ARRAY_SIZE); i++)` |
| `update(updated, j, c[j] + c[j - lookback])` | `updated[j] = c[j] + c[j - lookback]` |

Deviation: `std::flog2` is `$clog2`, which is the same for a power of two (16).

Proven equivalent; 82 nodes on both paths.

Found here: XLS flattens an array onto a port with element 0 in the *low* bits. The
first binding used SV's `{>>{...}}` streaming, which puts it in the high bits (and
which Verilator did not compile for this case).
