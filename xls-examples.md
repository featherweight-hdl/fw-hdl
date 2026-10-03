# XLS examples: SystemVerilog ports of XLS designs, from source to gates

Status: **plan for review**, 2026-10-03. Builds on `xls-phase0.md` (the SV static subset
and be-xls) and `xls-phase2.md` (the SPL → RTL pipeline). The back end (place and route
to an FPGA) is scoped in §9 but deferred.

## 1. Goal

A set of worked examples, each taken from the XLS repository. Each shows:

1. **The original DSLX**, saved verbatim next to
2. **its SystemVerilog port** in the fw-hdl static subset, and
3. **the processing pipeline**, as a dv-flow flow anyone can run and read: SV → zuspec IR → XLS
   IR → optimized IR → scheduled Verilog → **Yosys** netlist and area.

The original DSLX also runs through the same back half (DSLX → XLS IR → … → Yosys).
That puts the two paths side by side: the two IRs are proven equivalent where XLS can
prove it, and the area comes out the same.

**The point the examples make is integration, not translation.** Parity with DSLX is
the entry ticket; it shows we lose nothing. The win is everything around the kernel.
The upstream `#[test]` becomes an ordinary **SVUnit** test that calls the design's API.
That **same test file, unedited**, then runs at every level down to sign-off:

> the SV model → the XLS RTL behind transactors → the Yosys gate-level netlist

On the plain-XLS path, the user builds and owns the harness for each of those levels
by hand. §2.2 is how the examples make this impossible to miss.

The examples also drive the Yosys work. That work is a common set of `synth.yosys` tasks
in **dv-flow-libsynth**, replacing the `libyosys` tasks that the yosys-bin release ships
today (§6).

What the examples are for:
- **Users:** "I know SV; here is how an XLS design looks in it, and what I get out."
- **The AI benchmark** (`ai-benchmark-strategy.md` §4.2): the examples cover families
  F1 (FIR), F2 (AES), F4 (SHA-256), F5 (IDCT), F6 (dot product) and F7 (CRC), and give
  arm B's reference DSLX and arm C's reference SV for each.
- **Us:** a regression on real designs that are bigger than the corpus, and a measure
  of QoR parity with DSLX.

## 2. What each example contains

```
examples/xls/<name>/
  README.md          what the design does; the DSLX → SV mapping, with every deviation; how to run
  orig/              the upstream files, byte-for-byte (license headers intact)
    <file>.x
    UPSTREAM         repo, tag, commit, path and sha256 of each copied file
  <name>_pkg.sv      the SV port (header: "Derived from XLS <path>, Copyright The XLS Authors, Apache-2.0")
  <name>_unit_test.sv  SVUnit tests: each upstream #[test] / #[test_proc] as an `SVTEST, calling the API
  flow.yaml          the pipeline for this example (a fragment of examples/xls/flow.yaml)
  dslx_glue/         E1 only: the SV a user writes by hand to run the same tests on the DSLX path (§2.3)
```

Both fw-hdl and XLS are Apache-2.0. Keeping the headers, plus a line in a top-level
`examples/xls/NOTICE`, covers the copies and the derived ports.

**Shared pieces** live in `examples/xls/common/`:
- `xls_std_pkg.sv`: SV ports of the few DSLX `std::` helpers the examples call
  (`rotr`, `iterative_div_mod`, `flog2`, `find_index`, …), written once;
- the report generator (§8).

The API bindings and transactors that let a test run at each level are **generated or
come from the fw-hdl library**, never written per example (§2.2, G-9).

### 2.1 The per-example pipeline

```
 orig/<f>.x ─► synth.xls.DslxToIR ─► xlsIR ─┐
                                            ├─► synth.xls.Codegen ─► Verilog ─► synth.yosys.Synth ×{generic, ice40, ecp5} ─► netlist + stat
 <name>_pkg.sv ─► fw.hdl.xls.IR ──► xlsIR ──┤        │
                (function or class top)     │        └─► schedule, opt IR, signature
                                            └─► synth.xls.Equiv (opt IR vs opt IR)

 <name>_unit_test.sv ─► SVUnit on Verilator, level = model │ rtl │ gates   (same file; §2.2)
 orig/<f>.x #[test]  ─► DSLX interpreter                                  (upstream's own tests, untouched)
```

The first example, `crc32`, spells every task out in its `flow.yaml`, the way
`tests/xls/compose` does. The others use one compound task,
`xls_examples.fn-pipeline` or `xls_examples.proc-pipeline`, parameterized by the SV top
and the DSLX top. The flows stay short, and `dfm show task` on the compound prints the
same graph.

### 2.2 One test, from API call to gates

**The translation.** Each upstream test becomes an SVUnit test that calls the design
through its API. From `crc32.x`:

```
#[test]
fn crc32_one_char() { assert_eq(u32:0x83DCEFB7, main('1')) }
```

```systemverilog
`SVTEST(crc32_one_char)
    bit [31:0] crc;
    api.main("1", crc);
    `FAIL_UNLESS_EQUAL(crc, 32'h83DCEFB7)
`SVTEST_END
```

`api` is a handle to `crc32_api`, an interface class with one task per function the
example exports. It is **generated from the SV function signatures** (G-9). It is a
task, not a function, so that a call can take time when it runs on RTL.

For a proc (E9, E10), the API is the component's own ports. A `#[test_proc]` becomes
a test that does `enc_in.put(...)` and `dec_out.get(...)`.

**The levels.** The test file and the testbench top never change. One flow parameter,
`level`, picks the fileset that supplies the DUT and binds `api` to it:

| `level` | `api` is bound to | DUT | What a pass shows |
|---|---|---|---|
| `model` | `crc32_api_model`: calls `crc32_pkg::main` directly | the SV source | the port matches upstream's tests; this is the normative semantics, at model speed |
| `rtl` | API → bridge → ready/valid transactor → pins | the XLS Verilog from the SV | XLS compiled our SV correctly, latency and pipelining included |
| `gates` | the same transactor | the Yosys netlist (`write_verilog`) + Yosys cell models, generic or per family | synthesis kept the behaviour: the sign-off simulation |

This is the proto-kit stack that `tests/rv_proto` already demonstrates (API interface
class → bridge → transactor interface → core → pins). It is applied to an XLS block,
and gates are added as a third view next to the `spl` and `rtl` views of
`xls-phase2.md` VIEW-1/2.

**How the examples hammer it home.** Every item below is something a reader *sees*,
not something we claim:

1. **The same bytes at every level.** The report (§8) has one row per example and
   level. Each row shows the test file's sha256, the pass count and the wall time.
   The hash is identical down the column, every row passes, and the time goes from
   milliseconds to seconds to minutes. One table makes the whole argument.
2. **Zero glue, measured.** A report column counts the lines a user wrote beyond the
   port and the tests. It is 0 on our path for every example. On the DSLX path it is
   the size of `dslx_glue/` (§2.3).
3. **Change a knob, touch no test.** Each README has a short script:
   - change `pipeline_stages` from 1 to 4;
   - then set a `clock_period_ps`;
   - then change `target` from `ice40` to `ecp5`;
   - rerun all three levels after each change.

   `git diff` shows only `flow.yaml`. The same script against `dslx_glue/` shows what
   the hand-written glue must track, such as latency.
4. **It's their framework.** The tests use stock SVUnit: its release, its macros, its
   runner. There is no fw-hdl test language. An SV verification engineer recognizes
   the test file on sight. The API is a class handle, so the same calls drop into a
   UVM sequence later.
5. **Debug where it's cheap.** A failure is the same test, the same API call and the
   same message at every level. A mismatch found in the gate-level run is reproduced
   at `model` level in milliseconds. A README exercise walks through this with a
   planted bug.
6. **Lead with the test.** Each README opens with the upstream test beside the SVUnit
   test, then the three-level table, and only then the pipeline.

### 2.3 The contrast: the same tests on the plain-XLS path

On the plain-XLS path, the upstream tests run in the DSLX interpreter and stop there.
The DSLX path keeps running them, untouched (§7). Taking those tests to RTL and gates
is a separate project, in another language.

For E1 only, `dslx_glue/` holds that project. It is the SV a competent engineer writes
to run the *same* `crc32_unit_test.sv` on the DSLX path's RTL and netlist:
- a typed SV API, with DSLX types restated by hand;
- a driver for XLS's port names and handshake;
- valid and latency handling, and reset;
- file lists for each level.

It is reviewed so it is neither padded nor minimized. The report counts it, and the
knob script runs against it.

To be honest about where the gap comes from: Rule 1 of `xls-phase2.md` means a
*pin-level* transactor could be generated from XLS's signature for a DSLX block too.
What DSLX cannot provide is the **SV-level typed API and the `model` level**. There is
no SV model to run the test against before the RTL exists, and no SV type to hold the
results. So the gap is structural, not tooling we chose not to write.

## 3. The example set

Sources are pinned to **xlsynth `v0.59.0`** (`3f668e9b`). That is the tag our XLS tools
come from, so the original DSLX parses with the tools in the flow. The paths below are
from google/xls `main` (2026-10-02); EX-0 confirms them at the pin.

### 3.1 First cut: ten examples

| # | Example | Upstream source | Kind | Shows | Fam. |
|---|---|---|---|---|---|
| E1 | `crc32` | `xls/examples/crc32/crc32.x` | fn | the template example: bit loop, reductions, a fixed loop unrolled | F7 |
| E2 | `adler32` | `xls/examples/adler32/adler32.x` | fn | `%` by a constant (the D-1 divisor rule); a one-trip `for` | — |
| E3 | `lfsr` | `xls/examples/lfsr.x` (+ `lfsr_proc.x`) | fn (+ proc) | a parametric function (`<BIT_WIDTH>`) at two widths; `++` → `{}`; the later FPGA demo (§9) | — |
| E4 | `gcd` | `xls/examples/gcd.x` | fn | two algorithms (Euclid, binary); tuple `match` → `case` on a concatenation; a ported `std::iterative_div_mod`; DSLX's quickcheck becomes an XLS equivalence check of the two | — |
| E5 | `prefix_sum` | `xls/examples/prefix_sum.x` | fn | nested constant loops over an array, `update` → `a[i] = v` | — |
| E6 | `fir_dot` | `xls/examples/fir_filter.x`, `dot_product.x` (fixed-point halves) | fn | signed multiply-accumulate; parametric array sizes | F1, F6 |
| E7 | `idct_chen` | `xls/examples/jpeg/idct_chen.x` | fn | signed datapath; **DSLX `>>` on a signed value is arithmetic, so the port needs `>>>`** (the porting trap to document); `s32[8]` arrays | F5 |
| E8 | `sha256` | `xls/examples/sha256.x` | fn | a large unrolled function (64 rounds); tuple → packed struct; a clock-period sweep that shows XLS pipelining | F4 |
| E9 | `rle` | `xls/modules/rle/{rle_common,rle_enc,rle_dec}.x` | proc ×2 | `recv_if`/`send_if` → `get`/`put` under `if` (P7); struct payloads; **composition**: encoder → decoder through `fw.hdl.spl.Integrate`, with identity checked end to end | — |
| E10 | `aes` | `xls/modules/aes/{aes_common,constants,aes,aes_ctr}.x` | fn + proc | AES-128 encrypt as a large function, then `aes_ctr` as a proc. The upstream proc does several sends and receives on one channel per activation, so the faithful port is **rejected with a located diagnostic** (P10) and the README shows the restructured port, the "next rung" of `killer-app.md` §1.4 | F2 |

Why these ten:
- **They cover the subset.** Functions and procs; scalars, arrays, structs; signed and
  unsigned; loops, `case`, predicated channel ops; parametric code; a composition of
  two blocks.
- **The sizes range widely,** from tens of LUTs (E2, E3) to tens of thousands (E8,
  E10), so the Yosys numbers are interesting and the scheduler has real work.
- **They overlap the corpus where it matters.** The corpus has C1 (CRC), C2 (RLE) and
  C3 (AES), but those are our own designs, not faithful ports. The examples are faithful
  ports; the corpus stays as it is (decision D-8).

### 3.2 Deferred, with the reason

| Upstream | Why not yet |
|---|---|
| `matmul_4x4` (systolic array) | float32 throughout; spawns 16 procs in `unroll_for!` over channel arrays. Worth doing as an **integer variant** once Integrate takes arrays of child components. |
| `fp32_fmac`, `apfloat_fmac`, the float halves of E6 | needs an SV port of DSLX `apfloat` (a large library) |
| `riscv_simple` | 860 lines; a good later example of a CPU as one function |
| `delay`, `ram`, `memory_proc` | memories; XLS's RAM channel rewriting is outside our subset |
| `bitonic_sort`, `cubic_bezier`, `capitalize`, `proc_network` | they add little that E1–E10 don't already show; good for an agent to port as an exercise |

## 4. The DSLX → SV mapping (what every README documents)

Each README has a short table of the idioms it uses. The common ones:

| DSLX | SV port |
|---|---|
| `fn f<N: u32>(…)` (parametric) | a static function in a parameterized class, `f_c#(N)::f(…)` (needs G-3), or one non-parametric function per width the example uses |
| `uN[N]` / `sN[N]` | `bit [N-1:0]` / `bit signed [N-1:0]` |
| tuple `(a, b)` | `typedef struct packed`, fields in tuple order |
| `for (i, acc) in a..b { … }(init)` | `for (int i = a; i < b; i++)` with `acc` as a local |
| `update(arr, i, v)` | `arr[i] = v` |
| `x ++ y` | `{x, y}` |
| `x[lo +: uK]` | `x[lo +: K]` |
| `>>` on `sN` | `>>>` (DSLX picks the shift from the type; SV `>>` is always logical) |
| `as` casts | sized or signed casts; DSLX extends by the source's signedness, as our E14 rule does |
| `match` on a tuple | `case ({a, b})` |
| `proc`: `config`/`init`/`next` | an `fw_component` class: ports built in `build()`, initial state from property initializers, `next` as the `forever` body of `run()` |
| `recv_if(tok, ch, c, dflt)` | `if (c) in.t.get(x); else x = dflt;` |
| `send_if(tok, ch, c, v)` | `if (c) out.t.put(v);` |
| `std::rotr`, `std::flog2`, … | `xls_std_pkg::rotr`, … |
| `#[test] fn t() { assert_eq(want, f(x)) }` | `` `SVTEST(t) `` … `api.f(x, got); `FAIL_UNLESS_EQUAL(got, want)` `` `SVTEST_END `` (§2.2) |
| `#[test_proc]` (send stimulus, recv and check, `terminator`) | an `` `SVTEST `` that `put`s on the input ports and `get`s from the outputs; the test's end replaces `terminator` |

## 5. Layout and running

```
examples/xls/
  README.md        index, the pipeline picture, how to run, link to the results
  NOTICE
  flow.yaml        package xls_examples: shared filesets, the two compound tasks, the `all` and `report` roots
  common/          xls_std_pkg.sv, report.py
  crc32/ adler32/ lfsr/ gcd/ prefix_sum/ fir_dot/ idct_chen/ sha256/ rle/ aes/
```

- `dfm run crc32.all` runs one example: both paths, the tests at all three levels,
  equivalence, synthesis.
- `dfm run crc32.test -D level=gates` runs the tests at one level.
- `dfm run all` runs every example; `dfm run report` writes the results table.
- A **quick subset** (E1, E2, E3, E9: small and fast) joins the fw-hdl `tests` root, so
  the examples cannot rot. The full set is a separate root, because E8 and E10
  equivalence and synthesis take minutes (decision D-9).

## 6. Yosys tasks in dv-flow-libsynth (`synth.yosys`)

### 6.1 Why move them

yosys-bin currently ships `dv_flow/libyosys` (package `yosys`), with the tasks `Synth`,
`SynthIce40`, `SynthXilinx`, `SynthLattice`, `SynthGowin`, `FormalPrepare` and `Script`,
plus an agent skill. Tying the tasks to a binary release means:
- a task fix needs a binary rebuild;
- a Yosys from anywhere else (a distro, OSS CAD Suite, a source build) has no tasks;
- it doesn't follow libsynth's rule, "tasks wrap tools; tools come from PATH".

From reading the current code:
- `args` lines are written *after* `write_*`, so they cannot change the netlist;
- there are no defines;
- `stat` goes only to the log, so there are no numbers to collect;
- Yosys warnings and errors don't become markers.

### 6.2 What `synth.yosys` provides

Types:
- `yosysNetlist`, with a `format=` attribute (json, verilog, blif, edif, rtlil) and
  `family=`;
- `yosysStat`, which is `stat -json` output;
- `libertyLib`.

| Task | Does |
|---|---|
| `synth.yosys.Synth` | Reads `verilogSource`/`systemVerilogSource` (incdirs, defines). Runs `synth` (generic) or `synth_<family>` from **one `target` parameter**: `generic`, `ice40`, `ecp5`, `nexus`, `gowin`, `gatemate`, `xilinx`, … Typed common parameters: `top`, `flatten`, `retime`, `dsp`, `bram`, `abc9`, `device`; family-only options go in `args`. With a `libertyLib` input it maps to cells (`dfflibmap`, `abc -liberty`). **Always writes `stat -json`** (`yosysStat`). Writes the netlist in the requested formats; JSON is what nextpnr reads. |
| `synth.yosys.Script` | Runs the user's `.ys`/`.tcl` script, with the read commands generated from the inputs. This is the escape hatch. |
| `synth.yosys.AgentSkill` | The yosys-synthesis skill, moved over unchanged |

**One task with `target`, not one task per family** (decision D-4):
- a flow changes FPGA family by changing one parameter;
- the netlist records `family=`, which the back end (§9) reads to pick
  `nextpnr-<family>`;
- the docs describe the task once.

The cost is that family-only options are less typed. `args` covers them, and we can
promote one to a typed parameter when it gets used.

**Diagnostics** follow `synth.xls.Codegen`. Each Yosys `ERROR:` and `Warning:` line
that cites `file:line` becomes a marker. When the file is XLS-generated Verilog,
`dv_flow.libsynth.xls.diag.verilog_source()` maps it on to the SV or DSLX line. That
closes the BLK-4 item left open in `xls-phase2.md`, for Yosys; Verilator lint is next.

**Not moved:** `FormalPrepare` belongs with the other formal tasks in
dv-flow-libformal (decision D-5).

### 6.3 Migration

1. `synth.yosys` reaches parity with `yosys.*` (except `FormalPrepare`), documented and
   gated like `synth.xls`.
2. Search the known consumers (fw-hdl, the dv-flow org, edapack docs) for `yosys.*`
   uses. None turned up in this workspace.
3. edapack's yosys-bin recipe stops staging `dv_flow/libyosys` and the `dv_flow.mgr`
   entry point. Its consumer `ivpm.yaml` stays as it is (PATH plus click).
4. One release in between, where `libyosys` tasks log a deprecation pointing at
   `synth.yosys`.

## 7. Verification

Three things check each example. None of them takes expected values from our port.

1. **The SV path: the SVUnit tests at `model`, `rtl` and `gates`** (§2.2), on
   Verilator.
   - `model` is normative (`sv-normative-semantics`).
   - `gates` runs the generic netlist in the quick subset. The full run adds the
     `ice40` and `ecp5` netlists, using the cell models Yosys ships (`simcells.v`,
     `simlib.v`, `<family>/cells_sim.v`).
   - The expected values are the upstream tests', transcribed.
2. **The DSLX path: upstream's own tests,** run by `interpreter_main` on `orig/`,
   unmodified. For E1 they also run through `dslx_glue/` (§2.3).
3. **The two paths against each other: equivalence** of the optimized IRs, below.

**The RTL binding of a function.**
- XLS generates a function module as a fixed-latency pipeline. Codegen is asked for
  `input_valid`/`output_valid` signals, so a transactor can stream calls in and match
  results in order.
- There is no backpressure, so the response side always accepts.
- The latency comes from the signature, so the transactor never hard-codes it. That
  is why the knob script (§2.2) leaves the tests alone.

For **equivalence**, a new task, `synth.xls.Equiv`, runs `check_ir_equivalence_main`
on the two optimized IRs of each function example. Two cases need care:
- **The signatures must match.** Where the DSLX returns a tuple and the SV a packed
  struct (E4, E8), a small adapter in the example's `common/` flattens the DSLX side
  to bits. It is never a change to `orig/`.
- **Some checks may not finish.** Multiplier-heavy designs (E6, E7) and big ones (E8,
  E10) may hit the solver timeout. The task then reports *inconclusive*, not a pass,
  and the tests still gate.

E4 also checks Euclid ≡ binary, which is the upstream quickcheck proved instead of
sampled.

## 8. Results

`dfm run report` collects, for each example and each path (SV, DSLX):
- the XLS IR node count after `opt_main`;
- pipeline stages and critical-path delay (`unit`, and `asap7` where the delay model
  is available);
- Yosys numbers:
  - generic: cell count;
  - ice40: LUT4, carry, DFF, BRAM;
  - ecp5: LUT4, DFF, MULT18;
- the equivalence verdict.

It also writes **the integration table** (§2.2): one row per example and level
(`model`, `rtl`, and `gates` for each target). Each row has:
- the test file's sha256;
- tests passed out of tests run;
- wall time;
- the glue lines the user wrote: 0 on our path, and `dslx_glue/` for E1's DSLX row.

It writes `examples/xls/RESULTS.md` (and JSON). The **expectation is parity**: the
same IR after optimization, up to node names, and area within a few percent. Any
difference is a finding, either in our lowering or in the port.

I propose that the generated `RESULTS.md` is committed as a snapshot and refreshed on
purpose, so the README can link to real numbers (decision D-6).

## 9. Later: place and route to an FPGA

Not part of this plan's work, but these choices shape it:

- **The back end lives in dv-flow-libfpga** (`github.com/dv-flow/dv-flow-libfpga`, now
  in fw-hdl's `ivpm.yaml`; the repo has only its initial commit so far). It covers:
  - nextpnr, for all families;
  - the packers (`icepack`, `ecppack`, `gowin_pack`);
  - timing reports;
  - programming (`openFPGALoader`);
  - the board-constraint types (`.pcf`, `.lpf`, `.cst`).

  That is one audience and one chain, from netlist to a programmed board. libsynth
  stays with synthesis. libproject holds the *recipe* `rtl → bitstream`, composed
  from the two.
- **The post-route netlist is a fourth test level.** nextpnr can write a routed
  netlist with timing, so `level=routed` is the same SVUnit tests again, against the
  design that goes onto the board. The integration table (§8) gains a row and nothing
  else changes. That is the strongest form of the §2.2 argument.
- **What the edapack packages lack.** nextpnr-bin's `bin/` has only `nextpnr-*`. Its
  inputs list icestorm and prjtrellis, but `icepack` and `ecppack` aren't in `bin/`.
  Either they ship there, or there's an icestorm/trellis package.
- **The demo design.** E3 (`lfsr`) on LEDs is the "blinky" of this set. It needs a
  small board shell: a slow clock enable, the output channel always ready, and the
  pins from a constraint file. Candidate boards: iCEBreaker (iCE40UP5K) and ULX3S
  (ECP5). Then E9 (RLE loopback over a UART) is the first real design.
- **Fit.** E8 and E10 fully unrolled won't fit an UP5K. For them the FPGA story is
  "synthesis numbers plus a fit on ECP5-85F", or an iterative (II > 1) variant.

Because §6 records `family=` on every netlist, the back-end tasks need nothing else from
synthesis.

## 10. Gaps the examples expose

| # | Gap | Needed by | Proposal |
|---|---|---|---|
| G-1 | **No dv-flow task makes XLS IR from an SV function.** `fw.hdl.spl.Partition` takes component classes; functions go through the Python API only. | E1–E8, E10 | `fw.hdl.xls.IR`: `top` names a package function, a static class function, or a component class; outputs `xlsIR` (+ the predicted signature for a class). Partition keeps its job (whole designs). |
| G-2 | **No non-blocking receive** (`recv_non_blocking`) | E3 proc half | an SV `try_get(x)` → `bit` in `fw_get_if`, lowered to XLS `receive(..., blocking=false)` (a new P row). Or drop E3's proc half for now (D-7). |
| G-3 | **Parametric functions.** SV has none; the idiom is a static function of a parameterized class. Is a static class function as a function top supported? | E3, E4, E6 | verify in EX-0; if not, add it to the FE (T7 already elaborates specializations for components) |
| G-4 | `std::` helpers | E4, E5, E8 | `examples/xls/common/xls_std_pkg.sv`, to be promoted to `fw_std` if users want it |
| G-5 | No equivalence task | §7 | `synth.xls.Equiv` (libsynth) |
| G-6 | **Yosys reading our Verilog.** XLS's SV output puts asserts in `always` blocks with `$fatal`, and Integrate's top is SV. Yosys's built-in reader may refuse either. | §6 | test in YS-2. Fixes in order: codegen with asserts behind `` `ifndef SYNTHESIS `` (the Synth task defines it); `read_verilog -sv`; `sv2v` (shipped in yosys-bin); ask edapack to bundle yosys-slang. |
| G-7 | **Test levels need views.** The `spl`/`rtl` views and the ready/valid transactors as a library protocol are still open in `xls-phase2.md` (VIEW-1, VIEW-2). | §2.2 | do VIEW-1/2 as part of this work, then add `gates` as a third view |
| G-8 | ~~**No SVUnit in the flow.**~~ **Done (TB-1).** | §2.2 | `hdltest.svunit` in dv-flow-libhdltest (`Lib`, `TestRunner`, `Check`). The generated runner replaces SVUnit's Perl `runSVUnit`; build and run go through `hdlsim.<sim>.SimImage`/`SimRun`, so every hdlsim simulator works. The verdict is an `hdlsim.TestResult`, and failing checks become markers at the test line. SVUnit is found from the `install` parameter, then `$SVUNIT_INSTALL`, then the IVPM copy (`$IVPM_PACKAGES/svunit`, pinned at v3.38.1 by libhdltest's `ivpm.yaml`), then `packages/svunit` above the flow. |
| G-9 | **No call API for a function.** The proto kit gives components an API (interface class + bridge + transactor), but nothing gives one to a package function. | E1–E8, E10 | generate it from the SV signatures: `<pkg>_api` (one task per exported function), `<pkg>_api_model` (calls the function) and `<pkg>_api_xtor` (bridge onto a valid-pipelined transactor whose latency comes from the XLS signature). Output alongside the `xlsIR` by the G-1 task (D-12). |
| G-10 | **No gate-level simulation flow.** | §2.2 `gates` | `synth.yosys.Synth` also writes a simulation netlist (`write_verilog -noattr`) and names the Yosys cell models for the target, as a fileset `SimImage` can take |
| G-11 | XLS function modules have no handshake by default | G-9 | `synth.xls.Codegen` parameters for `--input_valid_signal`/`--output_valid_signal` (and the signature records them) |

## 11. Work items

### 11.1 Examples (EX)
- ☐ **EX-0** Clone xlsynth `v0.59.0`, confirm each §3.1 path, and copy `orig/` with
  `UPSTREAM`. Run each original through `DslxToIR` + `Codegen` (the DSLX path alone),
  so we know the reference half works before porting. Check G-3.
- ☐ **EX-1** `crc32`, end to end, with every task explicit. This is the template:
  the README layout (test first), the SVUnit test at all three levels, both paths,
  Yosys ×3, `dslx_glue/` and the knob script.
- ☐ **EX-2** The compound tasks `fn-pipeline` and `proc-pipeline`; port E2, E3 (fn),
  E5.
- ☐ **EX-3** E4, E6, E7: parametric code, signed arithmetic, the `>>>` trap.
- ☐ **EX-4** E8 (`sha256`), with a clock-period sweep (`clock_period_ps` at three
  points), reported as stages vs area.
- ☐ **EX-5** E9 (`rle`): two procs, composed by Integrate; identity loopback.
- ☐ **EX-6** E10 (`aes`): the function, the rejected faithful `aes_ctr`
  (the diagnostic is captured in the README), and the restructured port.
- ☐ **EX-7** `examples/xls/README.md`, `NOTICE`, the quick subset in `tests`.

### 11.2 Yosys in libsynth (YS)
- ☐ **YS-1** `synth.yosys` package:
  - the `Synth` task (`target`, typed common params, defines and incdirs, liberty);
  - `stat -json` output, netlist formats, `args` placed before the writes;
  - docs, held to the libproject docs gate.
- ☐ **YS-2** Front-end checks (G-6): XLS Verilog from both SV modes, the Integrate
  top, and the fallbacks.
- ☐ **YS-3** Diagnostics: Yosys messages become markers, mapped through
  `verilog_source()`.
- ☐ **YS-4** `Script`; move `AgentSkill` over.
- ☐ **YS-5** Migration (§6.3): deprecation in libyosys, then edapack stops shipping it.

### 11.3 Gaps (GAP)
- ☐ **GAP-1** `fw.hdl.xls.IR` (G-1).
- ☐ **GAP-2** `synth.xls.Equiv` (G-5).
- ☐ **GAP-3** `try_get` (G-2), if D-7 keeps E3's proc half.
- ☐ **GAP-4** Codegen valid signals (G-11).

### 11.4 Tests and the integration story (TB)
- ☑ **TB-1** SVUnit in the flow (G-8): dv-flow-libhdltest, with 16 tests passing,
  including SVUnit runs on Verilator for pass, fail-as-data, `gate`, and two suites.
  It is in fw-hdl's `ivpm.yaml`.
- ☐ **TB-2** The function call API (G-9): the interface class, the model binding and
  the transactor binding, generated from the SV.
- ☐ **TB-3** Levels as views (G-7). Finish VIEW-1/2 of `xls-phase2.md`, then add
  `level={model,rtl,gates}` as one flow parameter. The test file and the TB top stay
  fixed.
- ☐ **TB-4** The gate-level view (G-10), generic first, then `ice40` and `ecp5` cell
  models.
- ☐ **TB-5** E1's `dslx_glue/` and the knob script, plus a review of the glue for
  fairness.
- ☐ **TB-6** `report.py` and `RESULTS.md`: the QoR table and the integration table
  (§8).

## 12. Decisions for review

| # | Question | Proposal |
|---|---|---|
| D-1 | Where the examples live | `fw-hdl/examples/xls/` (next to `examples/counter.sv`), not a separate repo |
| D-2 | Which upstream to copy from | xlsynth `v0.59.0`, matching the tools; re-pin when the tools move |
| D-3 | How faithful the port is | Same names, the same function and proc structure, the same algorithm. Use the SV idiom where DSLX has no direct SV form (§4). Every deviation is listed in the README. No "improvements". |
| D-4 | Yosys task shape | one `Synth` with `target`, not one task per family (§6.2) |
| D-5 | `FormalPrepare` | to dv-flow-libformal, not libsynth |
| D-6 | Results | generated; `RESULTS.md` committed as a snapshot |
| D-7 | E3's proc half (needs non-blocking receive) | keep it, and add `try_get` (GAP-3); it is small and FPGA demos need it |
| D-8 | Overlap with `tests/xls/corpus` (C1–C3) | keep both; the corpus tests our subset, the examples are faithful ports |
| D-9 | Regression | a quick subset (E1, E2, E3, E9) in `tests`; the full set as its own root |
| D-10 | Back-end library (§9) | **Decided:** `dv-flow-libfpga` (repo created; added to `ivpm.yaml`) |
| D-11 | Where SVUnit support lives | **Decided:** dv-flow-libhdltest (renamed from libtest), package `hdltest.svunit` |
| D-12 | Function call API: generated or written | **Decided:** it depends on the path. **fw-hdl flow: generated** from the SV signatures (G-9); that the user writes none of it is the point of §2.2. **Plain-XLS path: hand-written**, as part of `dslx_glue/`. Writing it is the user effort §2.3 measures, so we don't generate it for them. |
| D-13 | Does the DSLX path get the SVUnit tests? | **Decided:** only E1, through hand-written `dslx_glue/`, as the measured contrast. The other examples check the DSLX path with its own tests plus equivalence. |

## 13. Risks

1. **Equivalence doesn't finish** on multiplier-heavy or large designs. It is
   reported as inconclusive; the tests still gate. If it is common, add an "assume
   equal up to bounded inputs" mode or move to Yosys/SBY (`eqy`).
2. **Yosys's built-in SV reader** (G-6). There are three fallbacks; the worst case is
   sv2v in the Synth task.
3. **Hidden subset limits.** Ports may hit constructs the FE rejects in ways the
   corpus didn't, such as parametric functions (G-3) or large constant arrays (AES
   tables, SHA K). EX-0 and EX-1 are meant to find these early. Each new limit gets an
   item, or a documented deviation.
4. **Parity may not be exact.** Our lowering adds explicit casts and guards (E17
   out-of-bounds reads, E2 divisor guards), which DSLX code doesn't have. `opt_main`
   should remove them; where it doesn't, the report shows the cost, which is itself a
   finding.
5. **SVUnit on Verilator.** ~~Open~~ **Hit and worked around in TB-1.** Verilator
   5.050 and 5.052 (also our 5.049-devel; 5.046 is fine) reject SVUnit's
   `svunit_testsuite` class with "Duplicate declaration of VARSCOPE …
   i__Vloopsize". SVUnit 3.38.1 and `main` are both affected. Renaming one `foreach`
   loop variable fixes it, so `hdltest.svunit.Lib` stages a renamed copy
   (`verilator_compat`, on by default). This is a Verilator regression and should be
   reported upstream with a reduced test case; a two-method class does not
   reproduce it.
6. **Gate-level simulation is slow** for E8 and E10 (tens of thousands of cells).
   Run `gates` for those on the generic netlist with few tests in the full run only,
   and say so in the table.
7. **The contrast must be fair.** If `dslx_glue/` looks padded, the point is lost.
   It is written as an expert would and reviewed (TB-5). §2.3 also says exactly
   which part of the gap is structural.
8. **Upstream churn.** DSLX syntax changes between releases (`lfsr_proc.x` at HEAD
   uses the new `impl` proc style). Pinning the tag avoids this; re-pinning is a
   deliberate task.

## 14. Order of work

1. EX-0, which de-risks the plan: confirm the originals compile through our DSLX path,
   and check G-3.
2. ~~TB-1 (SVUnit on Verilator)~~: done.
3. GAP-1, GAP-4, YS-1, YS-2, TB-2: the minimum to run EX-1 at `model` and `rtl`.
4. TB-3, TB-4: the levels as views, including gates.
5. EX-1 (`crc32`) end to end, with TB-5 (the contrast). This is the demo; review it
   before scaling out.
6. EX-2, EX-3, then GAP-2 and EX-4.
7. EX-5 and EX-6 (procs), with GAP-3.
8. YS-3, YS-4, TB-6, EX-7.
9. YS-5 (migration), once the examples have used `synth.yosys` in anger.

## 15. Log

- 2026-10-03: plan written. Surveyed google/xls `main` (`xls/examples`, `xls/modules`);
  the xlsynth `v0.59.0` tag exists (`3f668e9b`). Read the yosys-bin `libyosys` tasks
  (in `packages/yosys/dv_flow/libyosys`); no `yosys.*` users found in this workspace.
  nextpnr-bin has `nextpnr-{ice40,ecp5,gowin,gatemate,machxo2,mistral,generic}`, with
  no packers in `bin/`.
- 2026-10-03: review round 1.
  - Vectors are replaced by SVUnit tests that call the API.
  - The integration story is now the headline: one test file at `model`, `rtl` and
    `gates`, with the plain-XLS contrast measured on E1 (§2.2, §2.3).
  - The back end is in dv-flow-libfpga (D-10 decided; added to `ivpm.yaml`).
  - New gaps G-7 to G-11, work items TB-1 to TB-6, and decisions D-11 to D-13.
  - No dv-flow library supports SVUnit today (dv-flow-libtest is an empty repo).
- 2026-10-03: review round 2.
  - dv-flow-libtest was renamed **dv-flow-libhdltest**. It is now populated with
    `hdltest.svunit` (TB-1 done) and added to `ivpm.yaml`.
  - D-11 to D-13 are decided. D-12 depends on the path: generated on the fw-hdl flow,
    hand-written on the XLS path.
  - Risk 5 occurred (a Verilator regression) and is worked around.
