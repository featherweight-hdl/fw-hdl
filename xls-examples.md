# XLS examples: SystemVerilog ports of XLS designs, from source to gates

Status: **in progress**, 2026-10-03 (approved; progress in §11 and §15). Builds on `xls-phase0.md` (the SV static subset
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
    xls/.../<file>.x each at its upstream path, so DSLX imports resolve with --dslx_path=orig
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
   the hand-written glue must track. **Measured on E1** (EX-1): a latency change does
   *not* break a well-written glue, because it waits on the output valid. Port-level
   options do break it. With `reset: rst_n, reset_active_low: true`, all five fw-hdl
   levels pass (the generated bench wires `.rst_n(!rst)`), and the glue fails to
   compile (`Pin not found: 'rst'`). The README says exactly this, not more.
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
come from, so the original DSLX parses with the tools in the flow. EX-0 confirmed every
path below at the pin.

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
| E10 | `aes` | `xls/modules/aes/{aes_common,constants,aes,aes_ctr}.x` | fn + proc | AES-128/256 key schedule, encrypt and decrypt as large functions over `u8[4][4]`, then `aes_ctr` as a proc. ~~The upstream proc does several sends and receives on one channel per activation, so the faithful port is rejected (P10).~~ **Corrected in EX-6:** that was google/xls `main`; at the pinned tag `aes_ctr` does one operation per channel, and the faithful port is accepted | F2 |

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
- `dfm run tests --views gates` runs every example's tests at one level;
  `dfm run tests --tests crc32 --views rtl` narrows to one example. The other levels'
  images are not built (`std.TestRunner` prunes the graph).
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
- wall time, and the simulation time of the last pass (risk 6);
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
| G-1 | ~~**No dv-flow task makes XLS IR from an SV function.**~~ **Done (GAP-1).** | E1–E8, E10 | `fw.hdl.xls.IR`: each `top` entry (a function by path, `crc32_pkg::main`, or by unambiguous name; or a component class) becomes one `xlsIR` package, whose module is named `pkg__name`. A class also gets its predicted signature. Partition keeps its job (whole designs). |
| G-2 | ~~**No non-blocking receive**~~ **Done (GAP-3).** | E3 proc half | `fw_get_nb_if` (extends `fw_get_if`) adds `try_get(inout t)`; `v = port.t.try_get(x)` lowers to XLS `receive(..., blocking=false)` with `x = valid ? data : x`. **Opt-in, not on `fw_get_if`:** blocking get/put keep a network a Kahn process network (fw_channel.svh); a polling port gives that up, so only components that declare one lose it. `fw_channel` gains `get_nb_ex`. |
| G-3 | ~~**Parametric functions.**~~ **Done (EX-0).** SV has none; the idiom is a static function of a parameterized class. | E3, E4, E6 | One specialization already worked. Two specializations of one class collided (both became IR `lfsr`), because the FE keyed a function by name and location. It is now keyed by hierarchical path (`lfsr_c#(7)::lfsr`). Micro test E21; the `lfsr7`/`lfsr8` ports are proven equivalent to the DSLX originals. |
| G-12 | **A parametric DSLX function cannot be an IR top**, on the DSLX path either. `gcd.x`, `fir_filter.x` and `dot_product.x` have no concrete wrapper (`lfsr.x` does: `lfsr7`, `lfsr8`). | E4, E6 | each example keeps a short `dslx_top.x` beside `orig/` that imports the original and instantiates it at the widths the SV port uses. `orig/` stays untouched (D-3). |
| G-4 | `std::` helpers | E4, E5, E8 | `examples/xls/common/xls_std_pkg.sv`, to be promoted to `fw_std` if users want it |
| G-5 | ~~No equivalence task~~ **Done (GAP-2).** | §7 | `synth.xls.Equiv` (libsynth) |
| G-6 | **Yosys reading our Verilog.** ~~XLS's SV output puts asserts in `always` blocks with `$fatal`~~ | §6 | **Tested (YS-2).** `read_verilog -sv` takes XLS's SV for crc32, sha256, idct and both RLE procs, SVA asserts included. It rejects **AES** (and `aes_ctr`): XLS assigns whole rows of 2-D unpacked arrays ("Insufficient number of array indices"). Both sv2v and XLS's Verilog-2001 output read fine. `Synth`'s `frontend: auto` tries Yosys's reader, then sv2v, with a note. Integrate's top reads after a fix to `fw_rv_fifo` (YS-2). |
| G-7 | **Test levels need views.** The `spl`/`rtl` views and the ready/valid transactors as a library protocol are still open in `xls-phase2.md` (VIEW-1, VIEW-2). | §2.2 | do VIEW-1/2 as part of this work, then add `gates` as a third view |
| G-8 | ~~**No SVUnit in the flow.**~~ **Done (TB-1).** | §2.2 | `hdltest.svunit` in dv-flow-libhdltest (`Lib`, `TestRunner`, `Check`). The generated runner replaces SVUnit's Perl `runSVUnit`; build and run go through `hdlsim.<sim>.SimImage`/`SimRun`, so every hdlsim simulator works. The verdict is an `hdlsim.TestResult`, and failing checks become markers at the test line. SVUnit is found from the `install` parameter, then `$SVUNIT_INSTALL`, then the IVPM copy (`$IVPM_PACKAGES/svunit`, pinned at v3.38.1 by libhdltest's `ivpm.yaml`), then `packages/svunit` above the flow. |
| G-9 | ~~**No call API for a function.**~~ **Done (TB-2).** | E1–E8, E10 | Package `fw.hdl.api`, generated from the SV signatures (D-12). `Functions` writes `<api>_pkg`: the interface class, the proxy a test gets from `get()`, and `<api>_model`. Each level supplies a module named `<api>_harness` that registers its binding: `ModelBinding` (the SV function answers) or `XlsBinding` (per function, a transactor interface on the XLS module's pins, the bridge class, clock and reset). It is a separate package from `fw.hdl.xls`, because the `model` level needs no XLS. |
| G-10 | ~~**No gate-level simulation flow.**~~ **Done (TB-4).** | §2.2 `gates` | `synth.yosys.Synth` (`sim_netlist`, on by default) outputs, as `verilogSource`, the target's cell models from Yosys's data directory and then `netlist.v`. The netlist's top keeps the XLS module's name and ports, so `XlsBinding`'s harness runs on it unchanged. Verified on generic, iCE40 and ECP5. |
| G-11 | ~~XLS function modules have no handshake by default~~ **Done (GAP-4).** | G-9 | `synth.xls.Codegen` parameters `input_valid_signal`/`output_valid_signal`; the signature records them and the latency |

## 11. Work items

### 11.1 Examples (EX)
- ☑ **EX-0** Clone xlsynth `v0.59.0`, confirm each §3.1 path, and copy `orig/` with
  `UPSTREAM`. Run each original through `DslxToIR` + `Codegen` (the DSLX path alone),
  so we know the reference half works before porting. Check G-3.
  - All 17 files are in `examples/xls/*/orig/`, plus `examples/xls/NOTICE`.
  - Upstream's 38 `#[test]`/`#[test_proc]` pass in `dslx_interpreter_main`, run on the
    `orig/` copies. The release interpreter has no JIT, so `gcd.x`'s quickcheck is
    skipped; E4's equivalence check (§7) proves it instead.
  - Every non-parametric top goes through IR → `opt_main` → `codegen_main` (1 stage):

    | top | opt IR nodes | Verilog lines |
    |---|---|---|
    | `crc32::main` | 128 | 81 |
    | `adler32::main` | 6 | 35 |
    | `lfsr7`, `lfsr8` | 5, 7 | 35 |
    | `prefix_sum` | 82 | 198 |
    | `idct` | 1,883 | 2,754 |
    | `sha256::main` | 4,964 | 3,959 |
    | `RunLengthEncoder32`, `RunLengthDecoder32` (procs) | 36, 59 | 130, 138 |
    | `aes::encrypt` | 4,248 | 3,463 |
    | `aes_ctr` (proc) | 4,319 | 3,514 |

    `adler32` is 6 nodes because one byte never reaches the modulus; `opt_main`
    folds it away.
  - G-3 is fixed. G-12 is new: the parametric files need a DSLX wrapper.
  - Note for E10: `aes::encrypt` takes a `key_width` argument (128 or 256), so
    the port covers both, as upstream does.
- ◐ **EX-1** `crc32`, end to end, with every task explicit. This is the template:
  the README layout (test first), the SVUnit test at all three levels, both paths,
  Yosys ×3, `dslx_glue/` and the knob script.
  - Done: `crc32_pkg.sv` (one deviation: DSLX's parameter `byte` is an SV keyword, so
    `byte_`). Its optimized IR is **proven equivalent** to the DSLX's, and both are
    128 nodes. `crc32_unit_test.sv` passes at `model` (time 0) and at `rtl` (time 95:
    reset, then the 2-stage pipeline). Under `std.TestRunner` a planted wrong
    expectation is reported as `fail crc32-model`, with a marker at the test line.
  - Done since: Yosys ×3 on both paths, `equiv` (proven), and `gates` at all three
    targets. `dfm run crc32.all` from a clean rundir takes 7.6 s, and the one test
    file passes at five levels: `model`, `rtl`, `gates`, `gates-ice40`, `gates-ecp5`.
    First QoR row (cells; 2 stages, unit delay model):

    | target | SV path | DSLX path |
    |---|---|---|
    | generic | 109 | 108 |
    | ice40 | 103 (44 LUT4, 59 FF) | 103 |
    | ecp5 | 100 (41 LUT4, 59 FF) | 100 |

    The generic gap is real but small. The two optimized IRs are proven equivalent
    yet differ by one node (127 vs 126), and ABC maps them to a slightly different
    XOR/XNOR/NOT mix. The FPGA targets come out identical.
  - Since then: `dslx_glue/` (TB-5), the README (test first), and the knob script, run
    and recorded. Left for your review: the glue's fairness, and the README.
- ◐ **EX-2** The compound tasks `fn-pipeline` and `proc-pipeline`; port E2, E3 (fn),
  E5.
  - **No compounds.** dv-flow compounds cannot carry this pipeline. A compound's
    parameters are not visible inside a `select:` body it contains. Its inner tasks
    cannot be named from outside, and tests inside it are invisible to
    `std.TestRunner`. So `../flow.yaml` instead has shared `img`/`run` families over
    *example × level*, and each example offers `bench-<level>` tasks and its own
    test matrix. The per-example fragments are generated from one template and
    checked in, so each is readable on its own.
  - E2 adler32, E3 lfsr7/lfsr8 and E5 prefix_sum are done. Each is proven equivalent
    to its DSLX, with the same optimized node counts, and passes upstream's tests at
    all five levels. E3's proc half waits on GAP-3.
  - Found and fixed on the way:
    - `$clog2` of a constant was not in the subset;
    - parameter values inside function bodies did not count as constants;
    - arrays cross the XLS binding with element 0 in the *low* bits, as XLS flattens
      them (`{>>{}}` had the order reversed);
    - several libsynth tasks gained list forms: DslxToIR `tops`, Equiv `pairs`, and
      Synth running one Yosys per module.
- ☑ **EX-3** E4, E6, E7: parametric code, signed arithmetic, the `>>>` trap.
  - **E4 gcd.** Euclid and binary are static functions of a parameterized class, with
    `std::iterative_div_mod` ported to `common/xls_std_pkg.sv`. Euclid is proven
    equivalent (995 nodes on both paths). Binary defeats the solver, so the new
    exhaustive fallback in `Equiv` proves it on all 65,536 inputs. It proves Euclid ≡
    binary, upstream's quickcheck, the same way. G-12 bites here: gcd.x's functions are
    parametric and not `pub`, so the DSLX side is `dslx_top/gcd_tops.x`, a copy of
    gcd.x with concrete wrappers appended.
  - **E6 fir_dot.** The FIR filter at 4/6 and the dot products at 32/4 and 8/2 are
    proven equivalent, each in under 0.05 s. Yosys has no simulation model of the ECP5
    DSP (`MULT18X18D`), so `gates-ecp5` simulates a netlist made without DSPs.
    `Synth` now warns about cells without a model.
  - **E7 idct_chen.** Every signed `>>` is `>>>`. Both functions are proven
    equivalent, `idct` at 1,883 nodes on both paths, and all five tests pass at every
    level.
- ☑ **EX-4** E8 (`sha256`), with a clock-period sweep (`clock_period_ps` at three
  points), reported as stages vs area.
  - Done: the port, with Digest as a packed struct and `dslx_top/` flattening the
    tuple for comparison. The three tests pass at all five levels, including the
    110k-cell generic netlist (16 min end to end). `compute_pad_bits` is proven;
    `sha256` is *inconclusive* within the solver budget. Both netlists have 4,961
    nodes, but identical counts are not a proof.
  - Since: the sweep (`dfm run sha256.sweep`), asap7 delay model:

    | period | stages | generic cells | tests |
    |---|---|---|---|
    | (2 stages, unit model) | 3 | 109,731 | 3/3 |
    | 4000 ps | 24 | 126,843 | 3/3 |
    | 2000 ps | 46 | 144,406 | 3/3 |
    | 1000 ps | 113 | 196,519 | 3/3 |

    250 ps cannot be met (XLS suggests 358). The same test file passes against every
    pipeline (levels `rtl-p<period>`); its pass time tracks the latency.
- ☑ **EX-5** E9 (`rle`): two procs, composed by Integrate; identity loopback.
  - Done: the encoder and decoder procs, at the specializations the test procs spawn.
    Upstream's six `#[test_proc]`s pass at all five levels through the new component
    API (`fw.hdl.api.Components`). It has one task per port, `<port>_put` or
    `<port>_get`. The model binding runs the SV components on the fw-hdl runtime, and
    the XLS binding drives and collects each ready/valid channel.
  - Verilator 5.049 swaps two specializations' nested types depending on which is
    named first; 5.053 is fixed. The example names the count-width-2 one first.
  - Since: the composition, `rle_loop` (not upstream). `rle_pkg::rle_loopback` joins the
    encoder and decoder by an `fw_channel`; Partition → XLS per block → Signature →
    Integrate builds the top. Identity holds at `model` and `rtl`. The component API
    maps a structural top with the structure mapper and spells its payloads as
    declared, and XlsBinding reads Integrate's `blockSignature`.
  - Like for like (upstream's two specializations, `rtl-qor`), the SV path is
    *smaller*: 89 vs 95 IR nodes, 309 vs 432 generic cells, 105 vs 144 flops. The
    state is the same size, so it is in how the two front ends lower a proc. To look
    into.
- ◐ **EX-6** E10 (`aes`): the function, the rejected faithful `aes_ctr`
  (the diagnostic is captured in the README), and the restructured port.
  - `aes`: key schedule, encrypt, decrypt over `typedef bit [7:0] Block [4][4]`. 2-D
    arrays map to XLS arrays of arrays, and the RTL binding packs N-dimensional
    arrays row-major, element 0 low. The six tests pass at `model` and `rtl`. All
    three equivalences are inconclusive within the budget; the node counts match
    (494/494, 2,234/2,234, 4,247/4,248).
  - **Correction:** at the pinned tag `aes_ctr` does one op per channel per
    activation, so there is no P10 rejection to show. It ports faithfully. The key and
    the channel blocks are packed arrays with descending ranges, so DSLX element `k`
    of `n` is index `n-1-k`. Upstream's test proc passes at `model` and `rtl`.
  - Found: an argument named `block` is an XLS IR keyword. be-xls now suffixes `_`
    to every name in `IR_KEYWORDS` (found by trying each with opt_main).
  - Found: Yosys needs 14.7 GB per AES module through sv2v and 4.9 GB on XLS's
    Verilog-2001 (`Codegen system_verilog: false`). The AES examples synthesize the
    latter, and the README says to use `-j 4`.
  - To do: the gate levels. The rerun after the memory fix was stopped by the
    host (low memory, with another session's jobs running too) before any AES synth
    finished. Rerun `aes.all` and `aes_ctr.all` alone, at `-j 1` or `-j 2`.
- ◐ **EX-7** `examples/xls/README.md`, `NOTICE`, the quick subset in `tests`.
  - Done: the index README, a README per example (the test first, then the mapping
    and every deviation), NOTICE (now covering `dslx_top/` and the std ports), and a
    test that every `orig/` file matches UPSTREAM's sha256.
  - The quick subset exists (`dfm run quick`: crc32, adler32, lfsr, lfsr_proc, rle)
    but is **not** in the fw-hdl `tests` root yet. It would make that root need the XLS
    tools, and they have no package yet (X1-0). Wire it in with X1-0.

### 11.2 Yosys in libsynth (YS)
- ☑ **YS-1** `synth.yosys` package:
  - the `Synth` task (`target`, typed common params, defines and incdirs, liberty);
  - `stat -json` output, netlist formats, `args` placed before the writes;
  - docs, held to the libproject docs gate.
  - Targets: `generic`, `ice40`, `ecp5`, `nexus`, `machxo2`, `machxo3`, `gowin`,
    `gatemate`, `xilinx`. Yosys 0.69 has no `synth_ecp5`/`synth_nexus` any more; they
    are `synth_lattice -family`. It also has no `-retime`/`-abc9`, so those are not
    typed parameters; `synth_args` carries any family-only flag.
  - The default top is the `module=` attribute that `synth.xls.Codegen` now sets.
    Fileset `params` do not survive between dv-flow tasks; attributes do.
  - Yosys's own ECP5 cell model declares some flops twice (Verilator MODDUP warnings).
    That is upstream and harmless.
- ☑ **YS-2** Front-end checks (G-6): XLS Verilog from both SV modes, the Integrate
  top, and the fallbacks. Done for XLS's SV of every example (the DSLX path); AES needs
  sv2v or XLS's Verilog-2001. The Integrate top (`rle_loop`) failed at first:
  `fw_rv_fifo`'s `next()` used a cast and a `return ?:` that Yosys's reader rejects.
  Rewritten as `if`/`else`, it reads with `frontend=yosys`. `Synth` now records the
  frontend it actually used (`frontend=yosys` or `frontend=sv2v`) on the netlist.
- ◐ **YS-3** Diagnostics: Yosys messages become markers, mapped through
  `verilog_source()`. Basic form done with YS-1: `ERROR:` and `Warning:` lines, located
  where Yosys gives a file and line, deduplicated, mapped through `verilog_source()`.
  Still to do: check the mapping on a real XLS-Verilog error.
- ☐ **YS-4** `Script`; move `AgentSkill` over.
- ☐ **YS-5** Migration (§6.3): deprecation in libyosys, then edapack stops shipping it.

### 11.3 Gaps (GAP)
- ☑ **GAP-1** `fw.hdl.xls.IR` (G-1). Functions are found by hierarchical path or an
  unambiguous name (a bare name that two functions share is an error naming both).
- ☑ **GAP-2** `synth.xls.Equiv` (G-5). The verdict is `equivalent`, `not-equivalent`
  (with the counterexample), `inconclusive` (a timeout; a warning unless
  `require_proof`), or `error`. Written as `equiv.json`.
- ☑ **GAP-3** `try_get` (G-2), if D-7 keeps E3's proc half.
  - As G-2 says; the first version had `output t`, which SV resets on every call, so
    the model "polled" its state away. It is `inout`.
  - **E3's proc half (`lfsr_proc`)** ports and lowers. Its upstream test is
    timing-dependent: it assumes the interpreter's schedule. It passes at `model`. At
    `rtl` and all three netlists it fails the same way (1, 3, ...): the pipelined proc
    polls again before the seed arrives. ~~The suite runs `model`; `lfsr_proc.timing`
    runs the rest, failing by design.~~ **Fixed in the test, not the design:** after
    each seed, `recv_until_seed` accepts up to 8 outputs that continue the old sequence
    (each checked) until the seed appears, then checks upstream's values exactly. It
    passes at all five levels (0 values skipped at `model`, 2 per seed at `rtl` and the
    netlists). This is the one deviation in the transcription (lfsr/README.md). It is
    still the clearest demonstration of why the other tests are level-independent:
    they are KPNs, and this test has to say what it means by "eventually".
  - The `model` binding's outputs are now a rendezvous (a component's put waits for
    the test's get), so a polling proc cannot run ahead in zero time.
- ☑ **GAP-4** Codegen valid signals (G-11). Also added to libsynth along the way:
  `synth.xls.DslxTest` (upstream's own tests, failures as markers at the assert), and
  each `dslxSource` fileset's base on the DSLX import path, so `orig/` trees import as
  upstream does.

### 11.4 Tests and the integration story (TB)
- ☑ **TB-1** SVUnit in the flow (G-8): dv-flow-libhdltest, with 16 tests passing,
  including SVUnit runs on Verilator for pass, fail-as-data, `gate`, and two suites.
  It is in fw-hdl's `ivpm.yaml`.
- ☑ **TB-2** The function call API (G-9): the interface class, the model binding and
  the transactor binding, generated from the SV. `hdltest.svunit.TestRunner` gained a
  `harness` parameter (modules instantiated beside the suites), which is how a level's
  `<api>_harness` enters the bench without the test bench changing.
- ☑ **TB-3** Levels as views (G-7). Finish VIEW-1/2 of `xls-phase2.md`, then add
  `level={model,rtl,gates}` as one flow parameter. The test file and the TB top stay
  fixed.
  - dv-flow already has the mechanism. The image and run are `select:` families over
    `level` (`img.model`, `img.rtl`), so a level nobody asks for is never built. The
    checks are a `matrix:` tagged `std.Test` with `view`, under a `std.TestRunner` root.
    So the knob is `dfm run tests --views rtl`, not `-D level=` (§5 is updated).
  - E1 runs `model`, `rtl`, `gates`, `gates-ice40` and `gates-ecp5` this way, plus
    `dslx-rtl` and `dslx-gates` for the contrast. VIEW-1/2 of `xls-phase2.md` (views
    of a *component* design) are not needed for function examples; they come back
    with E9.
- ☑ **TB-4** The gate-level view (G-10), generic first, then `ice40` and `ecp5` cell
  models. Verilator warns UNOPTFLAT on the netlists' bit-blasted output flops; it is a
  performance note, not an error.
- ◐ **TB-5** E1's `dslx_glue/` and the knob script, plus a review of the glue for
  fairness.
  - `dslx_glue/` is 62 lines in two files. It contains the API package with the types
    restated by hand, a one-call-at-a-time transactor, and the bench. It passes at
    `dslx-rtl` and `dslx-gates`. The fw-hdl path generates 99 lines, pipelined and with
    a model binding; the user writes none of them.
  - The first version of the glue hung: it sampled reset at time 0, before the
    harness's value reached the interface, so it presented its call during reset. That
    is recorded in the README as what writing glue costs. The generated binding
    presents calls from a clocked process, so it cannot make that mistake.
  - The knob script ran (§2.2 point 3). The fairness review is yours.
- ☑ **TB-6** `report.py` and `RESULTS.md`: the QoR table and the integration table
  (§8). `common/report.py` reads a run directory. It produces the integration table
  (test sha256 per example, pass counts, the sim time of the last pass, run and
  build wall times, glue lines), the QoR table (IR nodes, latency, cells per target
  with the headline cell classes, the equivalence verdict and how it was reached)
  and the sweep table. Image build times come from file timestamps, since dv-flow
  records no durations.

## 12. Decisions for review

| # | Question | Proposal |
|---|---|---|
| D-1 | Where the examples live | `fw-hdl/examples/xls/` (next to `examples/counter.sv`), not a separate repo |
| D-2 | Which upstream to copy from | xlsynth `v0.59.0`, matching the tools; re-pin when the tools move |
| D-3 | How faithful the port is | Same names, the same function and proc structure, the same algorithm. Use the SV idiom where DSLX has no direct SV form (§4). Every deviation is listed in the README. No "improvements". |
| D-4 | Yosys task shape | one `Synth` with `target`, not one task per family (§6.2) |
| D-5 | `FormalPrepare` | to dv-flow-libformal, not libsynth |
| D-6 | Results | generated; `RESULTS.md` committed as a snapshot |
| D-7 | E3's proc half (needs non-blocking receive) | keep it, and add `try_get` (GAP-3); it is small and FPGA demos need it. **Done, opt-in:** `fw_get_nb_if`, not a method on every `fw_get_if` (G-2). Review this choice. |
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
5. **SVUnit on Verilator.** ~~Open~~ **Hit and worked around in TB-1.** Every Verilator
   since v5.048 (5.050, 5.052, 5.053 devel; v5.046 is fine) rejects SVUnit's
   `svunit_testsuite` class with "Duplicate declaration of VARSCOPE …
   i__Vloopsize". SVUnit 3.38.1 and `main` are both affected. Renaming one `foreach`
   loop variable fixes it, so `hdltest.svunit.Lib` stages a renamed copy
   (`verilator_compat`, on by default). It is a Verilator regression.
   - The trigger, reduced to a 30-line test case: an in-class method and an
     out-of-block method each loop `foreach (q[i])` over the same member, with method
     calls in the body.
   - The likely cause is Verilator be7d26c5b, which added `__Vloopsize`.
   - The report is ready to file in `~/projects/verilator/bug-reports/`, with an
     SVUnit pull-request item (the one-line rename).
6. **A broken bench can still pass.** ~~Open~~ **Hit in EX-1.** Yosys's iCE40 cell
   models give input ports default values, and Verilator 5.049 drives the *connected*
   net with them (against LRM 23.2.2.4). The iCE40 netlist held the bench's reset low,
   and the test still passed; only the pass time (55 instead of 95) showed it.
   `synth.yosys.Synth` now defines `NO_ICE40_DEFAULT_ASSIGNMENTS` for those models.
   The mitigation in general is the integration table's sim time per level: a level
   that answers sooner than its latency allows is a finding.
7. **Gate-level simulation is slow** for E8 and E10 (tens of thousands of cells).
   Run `gates` for those on the generic netlist with few tests in the full run only,
   and say so in the table.
8. **The contrast must be fair.** If `dslx_glue/` looks padded, the point is lost.
   It is written as an expert would and reviewed (TB-5). §2.3 also says exactly
   which part of the gap is structural.
9. **Upstream churn.** DSLX syntax changes between releases (`lfsr_proc.x` at HEAD
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
- 2026-10-03: implementation, round 1 (approved; committed first: libhdltest on its
  `main`, the plan and `ivpm.yaml` on `xls-backend`).
  - **EX-0** done. All 17 originals are in `orig/`, and upstream's 38 tests pass from
    there. The DSLX path compiles every non-parametric top. G-3 is fixed (functions
    are keyed by hierarchical path). G-12 is new (parametric DSLX tops need a
    wrapper).
  - **GAP-1, GAP-2, GAP-4, TB-2, TB-3, TB-4, YS-1** done; YS-2 and YS-3 in part.
    - New fw-hdl dv-flow packages `fw.hdl.xls` (`IR`) and `fw.hdl.api` (`Functions`,
      `ModelBinding`, `XlsBinding`).
    - libsynth gained `synth.xls.DslxTest`, `synth.xls.Equiv`, Codegen's valid
      signals, and `synth.yosys.Synth`. libhdltest's `TestRunner` gained `harness`.
  - **EX-1** runs end to end (`dfm run crc32.all`, 7.6 s from clean). It checks
    upstream's test, proves equivalence, runs Yosys ×3 on both paths, and runs the one
    test file at five fw-hdl levels and two DSLX-path levels.
  - Findings:
    - Yosys's reader rejects XLS's AES output (sv2v fallback).
    - Fileset `params` do not cross dv-flow tasks; use `attributes`.
    - dv-flow's up-to-date check does not see a change to a task's implementation;
      clear the rundir when developing tasks.
    - Verilator drives connected nets with input-port defaults (iCE40 cell models).
    - The first hand-written glue hung on a time-0 reset race.
  - Tests: libsynth 36, libhdltest 17, `tests/xls` + zuspec-be-xls 119 and 29 (the
    function tests rerun after the lookup change), fw-hdl `test_fn_api` 7.
    Docs gates: libsynth and libhdltest 100%; fw.hdl's new packages are fully
    documented (the 2 gaps are older `tests/formal` tasks).
- 2026-10-03: implementation, round 2 ("build out the full suite").
  - E2 to E10 are ported: adler32, lfsr (fn and proc), gcd, prefix_sum, fir_dot,
    idct_chen, sha256, rle (enc, dec, and the `rle_loop` composition through
    Integrate), aes and aes_ctr. EX-3, EX-4, EX-5, GAP-3 and YS-2 are done.
  - Eleven examples pass one SVUnit test file at all five levels. aes and aes_ctr pass
    at `model` and `rtl`; their gate levels are still to run (EX-6). lfsr_proc's
    transcribed test depended on when the proc polls (D-7); it now syncs on each new
    seed and passes everywhere (GAP-3).
  - GAP-3: `fw_get_nb_if` gives a port `try_get`, which be-xls lowers to XLS's
    non-blocking receive. It is opt-in, because polling gives up level-independent
    results.
  - Findings: `block` is an XLS IR keyword (be-xls escapes all of them); Yosys needs
    up to 14.7 GB per AES module through sv2v (4.9 GB on XLS's Verilog-2001);
    `fw_rv_fifo`'s `next()` was not readable by Yosys (rewritten); `aes_ctr` at the
    pinned tag does one op per channel, so the P10 rejection was a `main` artifact.
  - `common/report.py` writes `examples/xls/RESULTS.md` and `results.json`.
