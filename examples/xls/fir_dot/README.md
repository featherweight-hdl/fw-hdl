# fir_dot: fixed-point FIR filter and dot product

From XLS's `xls/examples/fir_filter.x` and `dot_product.x` (`orig/`, unmodified). The
fixed-point halves only: the float32 halves need an SV port of DSLX's `apfloat`.

## The tests

`fir_filter_fixed_test` and `dot_product_fixed_test`, transcribed in
[`fir_dot_unit_test.sv`](fir_dot_unit_test.sv).

## The port

| DSLX | SV ([`fir_dot_pkg.sv`](fir_dot_pkg.sv)) |
|---|---|
| `fir_filter_fixed<NUM_TAPS, NUM_SAMPLES, NUM_OUTPUTS = {...}>` | `class fir_c #(NUM_TAPS, NUM_SAMPLES, NUM_OUTPUTS = ...)` |
| `dot_product_fixed<BITCOUNT, VECTOR_LENGTH>` | `class dot_c #(BITCOUNT, VECTOR_LENGTH)` |
| `s32[N]` | `bit signed [31:0] ... [N]` |

Deviations: the concrete functions at the sizes upstream's tests use
(`fir_filter_fixed_4_6`, `dot_product_fixed_32_4`, `dot_product_fixed_8_2`), and the
DSLX wrappers for them in [`dslx_top/fir_dot_tops.x`](dslx_top/fir_dot_tops.x) (the
functions are `pub`, so the wrappers import them).

All three are proven equivalent, each in well under a second.

**`gates-ecp5`** simulates an ECP5 netlist synthesized without DSPs (`synth-ecp5-sim`).
Yosys's ECP5 simulation models have no `MULT18X18D`, so a netlist that uses the DSPs
cannot be simulated with them; `synth.yosys.Synth` warns when that happens. The area in
the QoR table is the netlist with DSPs.
