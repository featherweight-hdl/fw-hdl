# XLS examples: SystemVerilog ports of XLS designs, from source to gates

Each example takes a design from the XLS repository and ports it to fw-hdl's static
SystemVerilog subset. The original DSLX sits beside the port, unmodified (`orig/`,
pinned to xlsynth v0.59.0 in `orig/UPSTREAM`).

**The point is the integration, not the translation.** Each example's upstream tests
become one ordinary SVUnit file that calls the design through a generated API. That one
file, unedited, runs at every level:

| level | the API is answered by |
|---|---|
| `model` | the SV port itself (functions called; procs on the fw-hdl runtime) |
| `rtl` | XLS's Verilog of the port, through generated transactors |
| `gates` | Yosys's generic netlist of that Verilog |
| `gates-ice40`, `gates-ecp5` | the iCE40 / ECP5 netlists, with Yosys's cell models |

Start with [`crc32`](crc32/README.md): every task is spelled out, and it shows the same
test run by hand-written glue on the plain-XLS path, for contrast.

## The examples

| | example | from XLS | shows |
|---|---|---|---|
| E1 | [crc32](crc32) | `examples/crc32/crc32.x` | the template; the plain-XLS contrast (`dslx_glue/`) |
| E2 | [adler32](adler32) | `examples/adler32/adler32.x` | `%` by a constant; a one-trip loop |
| E3 | [lfsr](lfsr) | `examples/lfsr.x`, `lfsr_proc.x` | a parametric function at two widths; a proc that polls (`lfsr_proc`) |
| E4 | [gcd](gcd) | `examples/gcd.x` | two algorithms; the quickcheck as a proof |
| E5 | [prefix_sum](prefix_sum) | `examples/prefix_sum.x` | arrays in and out |
| E6 | [fir_dot](fir_dot) | `examples/fir_filter.x`, `dot_product.x` | signed multiply-accumulate |
| E7 | [idct_chen](idct_chen) | `examples/jpeg/idct_chen.x` | a signed datapath; DSLX `>>` is SV `>>>` |
| E8 | [sha256](sha256) | `examples/sha256.x` | a large unrolled function; a tuple as a struct |
| E9 | [rle](rle) | `modules/rle/*.x` | two procs; their composition (`rle_loop`) |
| E10 | [aes](aes), [aes_ctr](aes_ctr) | `modules/aes/*.x` | AES functions over 2-D arrays; a proc on top |

[`RESULTS.md`](RESULTS.md) has the numbers: every test file at every level, and the SV
path's area and equivalence against the DSLX path's.

## Each example's pipeline

```
orig/*.x ─► DslxTest (upstream's tests) ─► DslxToIR ─► Codegen ─► Yosys ×3 ───────┐
                                                         └────────────────► Equiv ◄┤ (functions)
<name>_pkg.sv ─► fw.hdl.xls.IR ─► Codegen ─► Yosys ×3 (generic, ice40, ecp5) ──────┘
<name>_pkg.sv ─► fw.hdl.api ─► a binding per level ─► SVUnit on Verilator, per level
```

Each example's `flow.yaml` holds its graph; [`flow.yaml`](flow.yaml) holds what they
share (SVUnit, the image and run families over example and level, the `tests` root).

## Running

The flows need, on `PATH` or as noted:

* the XLS tools (`opt_main`, `codegen_main`, `ir_converter_main`,
  `dslx_interpreter_main`, `check_ir_equivalence_main`) on `PATH` or in `$XLS_BIN`,
  and the DSLX standard library in `$XLS_DSLX_STDLIB_PATH`;
* `yosys` (and `sv2v` beside it), from the yosys-bin package;
* `verilator` (5.049 or later).

```
dfm run tests                                    # every example's tests, every level
dfm run tests --tests crc32,rle --views rtl      # some of them; other images aren't built
dfm run crc32.all                                # one example end to end
dfm run quick                                    # the quick subset (crc32, adler32, lfsr, lfsr_proc, rle)
python3 common/report.py                         # RESULTS.md from what the runs left
```

The AES examples need about 14 GB of memory per Yosys run; use `-j 4` for them.

## Layout

```
<example>/
  README.md          the test first, then the DSLX -> SV mapping with every deviation
  orig/              the upstream files, byte for byte, at their upstream paths
  <name>_pkg.sv      the port
  <name>_unit_test.sv  the upstream tests, as SVUnit tests calling the API
  flow.yaml          the example's tasks
  dslx_top/          where the DSLX needs a concrete wrapper (a parametric top)
common/              xls_std_pkg.sv (ports of the DSLX std:: functions used), report.py
```
