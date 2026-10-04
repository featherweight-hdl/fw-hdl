# crc32: one test, from API call to gates

A table-less CRC-32 of one byte, from XLS's `xls/examples/crc32/crc32.x`
(`orig/`, unmodified; `orig/UPSTREAM` pins it to xlsynth v0.59.0).

## The test

Upstream's test, in DSLX:

```
#[test]
fn crc32_one_char() { assert_eq(u32:0x83DCEFB7, main('1')) }
```

The same test in [`crc32_unit_test.sv`](crc32_unit_test.sv), an ordinary SVUnit test
that calls the design through its API:

```systemverilog
`SVTEST(crc32_one_char)
    bit [31:0] crc;
    api.main("1", crc);
    `FAIL_UNLESS_EQUAL(crc, 32'h83DCEFB7)
`SVTEST_END
```

That one file, unedited, runs at every level:

| level | `api` is answered by | sim time of the pass |
|---|---|---|
| `model` | the SV function `crc32_pkg::main` | 0 |
| `rtl` | XLS's Verilog of it, through a generated transactor | 95 |
| `gates` | Yosys's generic netlist of that Verilog (109 cells) | 95 |
| `gates-ice40` | the iCE40 netlist (44 LUT4, 59 FF), with Yosys's iCE40 cell models | 95 |
| `gates-ecp5` | the ECP5 netlist (41 LUT4, 59 FF), with Yosys's ECP5 cell models | 95 |

```
dfm run tests                       # every level
dfm run tests --views gates-ice40   # one level; the other images are not built
dfm run crc32.all                   # everything below, from the DSLX tests to gates
```

The user wrote the port and the test. Everything that connects the test to a level
is generated from the port's function signature (`fw.hdl.api`) and from XLS's module
signature: the API, the model binding, the transactor, the bench.

## The same tests, proven

The file has three more tests, with free inputs (`formal-svunit.md`):

- `crc32_affine`: `crc(a) ^ crc(b) ^ crc(c) == crc(a ^ b ^ c)`. This is the
  `#[quickcheck]` property that XLS proves with `prove_quickcheck_main`.
- `crc32_printable_nonzero`: `std::randomize(m) with { m inside {...}; }`.
- `crc32_alpha_distinct`: a class with `rand` fields, a constraint block, a
  subclass that narrows it, and an inline `with`.

Each one runs in two ways, with no change to the file:

- **Dynamically**, at every level above, on `` `FW_SAMPLES `` random samples.
  The flow sets the count per level: 4096 on `model`, 512 on `rtl`, 128 on
  `gates` and 32 on the vendor-cell netlists. Verilator solves the constraints.
- **Formally**, for every input the constraints allow. This proves the test on
  the SV model. In the flow this is one more view, `formal`, in the same
  report as the levels (`fw.hdl.formal.Prove`):

```
dfm run tests --tests crc32                 # 12 of 12: the seven levels, formal and the chain
dfm run tests --tests crc32 --views formal  # only the proof
```

Or from the command line:

```
python -m fw.hdl.formal examples/xls/crc32/crc32_pkg.sv \
    --api crc32_pkg::main --tests examples/xls/crc32/crc32_unit_test.sv
```

```
proven  crc32_one_char            0.00 s  no input reaches a failure (1 checks, 0 free values)
proven  crc32_affine              3.98 s  no input reaches a failure (2 checks, 3 free values)
proven  crc32_printable_nonzero   0.00 s  no input reaches a failure (2 checks, 1 free values)
proven  crc32_alpha_distinct      0.00 s  no input reaches a failure (3 checks, 1 free values)
4/4 proven
```

The command reads the test body with the same front end as the design:

1. `std::randomize` and `randomize()` give free inputs, and their constraints
   become assumptions.
2. Every `FAIL_*` check becomes a proof obligation.
3. `api.main` resolves straight to `crc32_pkg::main`.

The solver is dv-solve; z3 and boolector give the same answers
(`--solver z3`). A false check gives a counterexample, with its line and the
value of every randomized input. The counterexample is also written as a replay
file, `<test>.cex.json`. `fw.hdl.formal.Replay` (or `--replay DIR`) turns it
into a copy of the test file in which each `randomize()` returns the
counterexample's values. Given to the `TestRunner` in place of the test file,
it runs the failing test, directed, at any level. It fails at the same line.

`tests/xls/test_formal_svunit.py` holds the tests of this command, including a
mutant design. With a wrong polynomial, `crc32_one_char` fails, but
`crc32_affine` still proves: a CRC is affine for any polynomial, so a property
proves only what it says.

### Proven at every level: the chain

The proof is on the SV model. Every other level is covered by checking that
each step down from the model preserves the function, for every input
(`formal-svunit.md` §6, §11):

| link | check | task | time |
|---|---|---|---|
| model → XLS IR | the IR the proofs encoded = the IR XLS optimized | `equiv-ir` (`synth.xls.Equiv`) | 0.03 s |
| XLS IR → RTL | the optimized IR = the pipelined Verilog, over its 3 cycles | `equiv-codegen` (`fw.hdl.formal.CodegenEquiv`) | 0.03 s |
| RTL → netlist | the RTL = the generic, iCE40 and ECP5 netlists | `equiv-netlist.*` (`synth.yosys.Equiv`) | 0.1 / 11.6 / 0.4 s |

`fw.hdl.formal.Chain` puts the proof and the links up to each level into one
result, views `formal-rtl`, `formal-gates`, `formal-gates-ice40` and
`formal-gates-ecp5`. It also checks that each link starts where the previous
one ended:

```
dfm run tests --tests crc32 --views formal-gates-ice40
```

```
formal chain to level gates-ice40: pass

    model    proven          4 of 4 tests proven (formal:dv-solve)
  = XLS IR   equivalent      the proven model's IR = the IR XLS optimized
  = RTL      equivalent      the optimized IR = the Verilog XLS generated
  = netlist  equivalent      the RTL = the netlist (ice40)
```

## The port

[`crc32_pkg.sv`](crc32_pkg.sv) follows `crc32.x` line for line.

| DSLX | SV |
|---|---|
| `const U32_MAX = std::unsigned_max_value<u32:32>()` | `localparam bit [31:0] U32_MAX = 32'hFFFF_FFFF` |
| `byte as u32` | `32'(byte_)` |
| `for (_, crc): (u32, u32) in u32:0..u32:8 { ... }(crc)` | `for (int i = 0; i < 8; i++)`, with `crc` as the accumulator |
| `let mask = -(crc & u32:1)` | `bit [31:0] mask = -(crc & 32'd1)` |

Deviations: one. DSLX's parameter `byte` is an SV keyword, so it is `byte_`.

## The pipeline

```
orig/crc32.x ─► DslxTest (upstream's test) ─► DslxToIR ─► Codegen ─────────────┐
                                                          └► Yosys ×3            ├─► Equiv: proven equivalent
crc32_pkg.sv ─► fw.hdl.xls.IR ─► Codegen (2 stages, valid signals) ────────────┘
                                   └► Yosys ×3 (generic, ice40, ecp5) ─► gate-level netlists
crc32_pkg.sv ─► fw.hdl.api.Functions ─► ModelBinding                 ─► level model
                                     └► XlsBinding (+ XLS signature) ─► levels rtl, gates*
crc32_unit_test.sv ─► hdltest.svunit.TestRunner ─► hdlsim.vlt.SimImage/SimRun per level ─► Check
crc32_unit_test.sv ─► fw.hdl.formal.Prove (+ Functions' API, the SV model) ─────────► view formal
Prove's design IR = opt IR = RTL = netlists (Equiv, CodegenEquiv, yosys Equiv) ─► Chain ─► views formal-<level>
```

Every task is spelled out in [`flow.yaml`](flow.yaml).

| | SV path | DSLX path |
|---|---|---|
| optimized IR | 127 nodes | 126 nodes, **proven equivalent** |
| generic cells | 109 | 108 |
| iCE40 cells | 103 | 103 |
| ECP5 cells | 100 | 100 |

## The same test on the plain-XLS path

The DSLX path has upstream's test in the DSLX interpreter, and stops there. To run
`crc32_unit_test.sv` on its RTL and netlist, a user writes
[`dslx_glue/`](dslx_glue): 62 lines in two files.

- The API package, with the types restated from `crc32.x` by hand.
- A transactor for the module's ports, copied from the generated Verilog.
- The bench: clock, reset, the module, the binding.

The flow runs it as levels `dslx-rtl` and `dslx-gates`, and it passes. There is no
`model` level: DSLX gives no SV model to run the test against.

Writing it was not free. The first version presented its call during reset at time 0,
before the reset value had reached the interface, and hung. The generated binding
presents calls from a clocked process when not in reset, so it cannot do that.

## Change a knob, touch no test

Each step changes only `flow.yaml`; the test file is never edited.

| change (both paths' `Codegen`) | fw-hdl levels | `dslx_glue/` |
|---|---|---|
| `pipeline_stages: 2` → `4` (latency 3 → 5) | all pass | passes (it waits on the output valid) |
| `reset: rst_n`, `reset_active_low: true` | all pass: the generated bench connects `.rst_n(!rst)` | **does not compile**: `Pin not found: 'rst'`. The user edits the glue. |
