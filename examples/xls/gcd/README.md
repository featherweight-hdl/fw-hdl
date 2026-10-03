# gcd: two algorithms, and the quickcheck as a proof

From XLS's `xls/examples/gcd.x` (`orig/`, unmodified).

## The tests

`gcd_euclidean_test` and `gcd_binary_test`, transcribed in
[`gcd_unit_test.sv`](gcd_unit_test.sv) at u8, the width upstream's tests use.

Upstream's `#[quickcheck] prop_gcd_equal` (Euclid == binary on 50,000 random inputs) is
not a test here. It is a proof: `equiv` checks `gcd_euclidean8` against `gcd_binary8`
for *every* 8-bit input pair. The solver does not finish it, so `synth.xls.Equiv`
compares all 65,536 inputs (its exhaustive fallback).

## The port

| DSLX | SV ([`gcd_pkg.sv`](gcd_pkg.sv)) |
|---|---|
| `fn gcd_euclidean<N: u32, DN: u32 = {N * u32:2}>` | `class gcd_c #(N, DN = N * 2)`, static functions |
| `std::iterative_div_mod(a, b).1` | `div_mod_t::iterative_div_mod(a, b).r` ([`../common/xls_std_pkg.sv`](../common/xls_std_pkg.sv)) |
| `match (a[0:1], b[0:1]) { (u1:0, u1:1) => ... }` | `case ({a[0], b[0]}) 2'b01: ...` |
| a returned tuple `(uN[N], uN[N], uN[N])` | `typedef struct packed {...} abd_t`, fields in tuple order |

Deviation: `gcd_euclidean8` and `gcd_binary8` are added. A DSLX test calls a parametric
function directly; SV needs a concrete function to call (and XLS a concrete top).

**The DSLX side needs a wrapper too.** gcd.x's functions are parametric *and* not `pub`,
so no IR top exists for them and no other module can import them.
[`dslx_top/gcd_tops.x`](dslx_top/gcd_tops.x) is gcd.x, unmodified down to a marker line,
with the two concrete wrappers appended.

## Equivalence

| pair | verdict |
|---|---|
| SV `gcd_euclidean8` vs DSLX | proven by the solver (995 nodes on both paths) |
| SV `gcd_binary8` vs DSLX | proven on all 65,536 inputs (the solver does not finish) |
| `gcd_euclidean8` vs `gcd_binary8` (the quickcheck) | proven on all 65,536 inputs |

The binary algorithm's two optimized graphs differ (597 nodes vs 672), and so does the
area: see [`../RESULTS.md`](../RESULTS.md).
