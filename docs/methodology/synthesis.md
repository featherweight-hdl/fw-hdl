# Synthesis: the static subset

The synthesis flow reads the SV source with slang, maps the static subset to zuspec
IR, and lowers that IR to XLS IR. From there XLS optimizes, schedules and generates
Verilog, and Yosys maps that Verilog to gates. You write no DSLX.

```
<name>_pkg.sv ─► fw.hdl.xls.IR ─► synth.xls.Codegen ─► synth.yosys.Synth
                 (SV → zuspec IR    (opt_main, then        (generic, ice40,
                  → XLS IR)          codegen_main: Verilog  ecp5, ...)
                                     and its signature)
```

## Functions

A pure `function automatic`, in a package or as a `static` function of a class,
becomes an XLS function. It reads only its arguments and has no side effects.
Codegen turns it into a combinational module or a pipeline.

```{literalinclude} ../../examples/xls/crc32/crc32_pkg.sv
:language: systemverilog
:start-at: function automatic
```

A **parametric** function becomes a static function of a parameterized class,
`lfsr_c#(8)::lfsr(...)`. A typedef names each specialization to compile.

## Procs

A component whose `run()` is a prologue followed by a `forever` loop becomes an XLS
proc:

| SV | Proc |
|---|---|
| one iteration of the `forever` body | one activation |
| class properties, and `run()` locals declared before `forever` | state, initialized from their initializers |
| locals declared inside the `forever` body | values that do not persist |
| `in.t.get(x)` | a blocking receive |
| `out.t.put(v)` | a blocking send |
| a `get`/`put` under `if` | a predicated receive or send |
| `in.t.try_get(x)` on an `fw_get_nb_if` port | a non-blocking receive |
| statement order | the token chain: effects happen in program order |

The run-length encoder of the {doc}`../examples/xls/rle` example, in full:

```{literalinclude} ../../examples/xls/rle/rle_pkg.sv
:language: systemverilog
:start-at: class RunLengthEncoder
:end-before: // rle_dec.x
```

The flow rejects, with a located diagnostic, what it cannot lower. That includes a
`get` or `put` inside a loop, two operations on the same channel in one activation,
`#delay`, `@` and calls to other tasks.

## Composition

A **structural component** only builds and connects: no `run()`. Its children are
blocks, and its channels are their connections. `fw.hdl.spl.Partition` reads it and
emits each block for XLS, plus a description of the shell. After each block has
been compiled, `fw.hdl.spl.Integrate` builds an RTL top from the blocks' signatures:
one instance per block, a ready/valid wire or FIFO per channel, and pins for the
ports at the edge. Integration reads only the signatures, never XLS's Verilog, so a
block can come from somewhere else as long as it has the same signature.

```{literalinclude} ../../examples/xls/rle/rle_pkg.sv
:language: systemverilog
:start-at: class rle_loopback
:end-before: endpackage
```

## Types and operators

| SV | Meaning in the static subset |
|---|---|
| `bit [N-1:0]`, `bit signed [N-1:0]` | 2-state, N bits; `logic` wider than 1 bit is rejected |
| `typedef struct packed` | a bit vector; the first field is the most significant |
| `T a[N]` | a fixed array; out-of-range reads give 0, out-of-range writes do nothing |
| `bit [M-1:0][N-1:0]` | a packed array; element `i` is bits `[i*N +: N]` |
| `+ - *` | wrap at SV's context-determined width |
| `/ %` | only by a non-zero constant, or under a `d != 0` guard |
| `>>`, `>>>` | logical; arithmetic on a signed left operand |
| `for`, `repeat` with constant bounds | unrolled |
| `case` | first match wins; `casez`/`casex` are rejected |
| immediate `assert` | an XLS assertion, with the message |
