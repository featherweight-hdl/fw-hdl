# sha256: one big unrolled function

From XLS's `xls/examples/sha256.x` (`orig/`, unmodified): one 512-bit chunk, 64 rounds,
unrolled.

## The tests

`compute_pad_bits_test`, `sha256_empty_payload_test` and `sha256_abc_test`, transcribed
in [`sha256_unit_test.sv`](sha256_unit_test.sv). They pass at every level, including the
gate-level netlists (110k generic cells, 48k iCE40, 50k ECP5).

## The port

| DSLX | SV ([`sha256_pkg.sv`](sha256_pkg.sv)) |
|---|---|
| `pub type Digest = (u32, u32, ...)` | `typedef struct packed { bit [31:0] d0, ..., d7; } Digest` (tuple order) |
| `(chunk ++ bits[1536]:0) as u32[64]` | `w[i] = chunk[511 - 32*i -: 32]` (element 0 most significant) |
| `std::rotr(x, y)` | `xls_std_pkg::rotr_c#(32)::rotr(x, y)` ([`../common/xls_std_pkg.sv`](../common/xls_std_pkg.sv)) |
| `std::round_up_to_nearest`, `std::ceil_div` | ported; `ceil_div`'s divide gets the explicit guard the static subset requires (D-1), which gives DSLX's `x / 0` result |
| `pad_to_512b_chunk(message as u24)` in the abc test | `{"abc", 1'b1, 423'b0, 64'd24}` in the test, with the arithmetic in a comment |

`sha256` returns a tuple in DSLX and a packed struct in SV, so the equivalence check
compares it with [`dslx_top/sha256_tops.x`](dslx_top/sha256_tops.x), which flattens the
DSLX tuple to `bits[256]`.

## Equivalence

`compute_pad_bits` is proven. `sha256` is **inconclusive**: the solver does not finish
within the flow's budget, and a 30-minute run ran out of memory. Both optimized graphs
have 4,961 nodes, which is not a proof. The tests at every level are the evidence.

To do (xls-examples.md EX-4): a clock-period sweep, pipeline stages against area.
