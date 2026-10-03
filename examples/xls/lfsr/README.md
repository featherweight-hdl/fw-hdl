# lfsr: a parametric function at two widths

From XLS's `xls/examples/lfsr.x` and `lfsr_proc.x` (`orig/`, unmodified).

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

## The proc half: a proc that polls (`lfsr_proc`)

[`lfsr_proc_pkg.sv`](lfsr_proc_pkg.sv) ports `user_module`, which free-runs: each
activation it polls for a new `(seed, tap_mask)` with `recv_non_blocking`, sends the
current value, and steps the LFSR. In SV the seed port is an `fw_get_nb_if`, and
`valid = seed_and_mask_r.t.try_get(new_state)` takes a seed if one is waiting and leaves
`new_state` alone otherwise. fw-hdl lowers it to XLS's `receive(..., blocking=false)`.

`fw_get_nb_if` is opt-in on purpose. Blocking `get`/`put` make a network of components
a Kahn process network, whose values do not depend on timing; that is what lets every
other test in these examples run unchanged at every level. A component that polls gives
that up.

**This example's test shows why.** Upstream's `#[test_proc]` expects the proc to see each
new seed on the activation right after the test sends it, which is how the DSLX
interpreter happens to schedule the two procs. Transcribed literally, the test passes at
`model` and fails at `rtl` and every gate level: the proc runs every clock, the test's
seed takes cycles to reach its input, and in the meantime the proc sends 3, the next
value from the initial `(1, 1)`. The RTL and the three netlists agree with each other
exactly; only the schedule differs. Neither answer is wrong: a polling proc's outputs
depend on timing.

**The one deviation**, in [`lfsr_proc_unit_test.sv`](lfsr_proc_unit_test.sv): after each
seed is sent, `recv_until_seed` accepts outputs that continue the old sequence, checking
each one against `lfsr` under the old tap mask, at most `MAX_LAG` (8) of them, until
the seed itself comes out. From then on every value is upstream's, checked exactly.
Neither seed occurs in the first 8 values of the sequence it replaces, so the first
match is unambiguous. The design is unchanged.

| level | values received | old values skipped per seed |
|---|---|---|
| DSLX interpreter (upstream) | 1, 1, 2, 4, 8, 17, 237, 219 | 0 |
| `model` | 1, 1, 2, 4, 8, 17, 237, 219 | 0 |
| `rtl`, `gates`, `gates-ice40`, `gates-ecp5` | 1, 3, 7, 1, 2, 4, 8, 17, 35, 71, 237, 219 | 2 (3, 7; then 35, 71) |

The test passes at every level. It checks what `recv_non_blocking` promises, that a
seed takes effect on some later activation and the outputs follow it from there, not
when.
