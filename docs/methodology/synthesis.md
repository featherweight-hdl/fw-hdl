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
| statement order | the token chain: effects happen in program order, except that effects on exclusive paths are not ordered against each other |
| several `get`s or `put`s on one port, under guards | one operation per activation; see below |
| a `get`/`put` in a constant-bound `for` or `repeat` | unrolled |
| state used (read and written) only under a guard | a predicated `state_read` and `next_value` |

The run-length encoder of the {doc}`../examples/xls/rle` example, in full:

```{literalinclude} ../../examples/xls/rle/rle_pkg.sv
:language: systemverilog
:start-at: class RunLengthEncoder
:end-before: // rle_dec.x
```

A port carries at most one item per activation, so several operations on one port
need guards:

| Guards | Lowered as |
|---|---|
| exclusive: the arms of an `if`/`else` or `case`, or `v == j` and `v == k` for different constants (as an unrolled loop over `k` gives) | `proven_mutually_exclusive`: XLS merges them into one operation, and rejects the design if it cannot prove the guards exclusive |
| can both hold, with no other effect ordered between the operations | `runtime_mutually_exclusive`: XLS merges them and the RTL asserts in simulation that at most one fires. The class model would do both, so an assertion here is a design error |

```systemverilog
for (int k = 0; k < 4; k++)
    if (v == k) begin                 // exclusive for different k
        in.t.get(x);
        sum[k] = sum[k] + x;
        out.t.put({k[1:0], sum[k]});
    end
```

State written several times in one activation (an unrolled search that sets
`vld[k]`, then a release that clears one entry) is exact: each write applies in
program order and the last one wins, as in the class model.

A cycle-step component ({doc}`components`, an `fw_steppable`) becomes a proc in the
same way, with its `step()` body as the activation:

| SV | Proc |
|---|---|
| one call of `step()` | one activation, at II=1 |
| `if (in.t.try_get(x)) ...`, or `if (a && in.t.try_get(x)) ...` with no `else` | a non-blocking receive into a temporary, predicated on `a` in the second form |
| `out.t.put(v)` on an `fw_valid_put_if` port | a send that the design never back-pressures (Integrate ties its ready and asserts it is not needed) |
| `out.t.put_or_stall(v)` on an `fw_put_step_if` port, in an `fw_atomic_step` | a send predicated on its `if`s, which blocks: when out is not ready, the whole activation stalls, with no state update and no receive. Another send that was ready has transferred, and does not repeat |
| the step's receives, in a pipeline | one stage: codegen gets an `--io_constraints` that keeps every streaming receive in the first one's stage, so an activation takes the requests of one cycle |
| the state `s` of an `fw_atomic_step` | one state element, zero at reset |
| statement order | none across channels: the cycle is atomic, and a receive token-ordered after a send cannot be scheduled at II=1. Operations on one channel keep the rules above |

An array of ports, `fw_port #(..) in[N]`, becomes one channel per element (`in_0`,
`in_1`, ...). An element is named by a constant or by the variable of a loop
`for (int k = A; k < B; k++)` with constant `A` and `B`; such a loop is unrolled
in the front end, so each iteration names one channel:

```systemverilog
for (int k = 0; k < NVC; k++)
    if (!m_hv[k] && in[k].t.try_get(x)) begin
        m_hold[k] = x;
        m_hv[k] = 1'b1;
    end
```

The flow rejects, with a located diagnostic, what it cannot lower. That includes:
- a component with both `run()` and `step()`;
- two operations on one port where one is unguarded;
- two whose guards can both hold, with another effect between them;
- two operations on a level;
- `#delay`, `@` and calls to other tasks.

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

## Recognized classes

Some library classes are not mapped from their bodies. Their body is the model, and
a registry entry gives the hardware. A child of such a class needs no knob, and
Partition takes the entry's lowering:

| Class | Lowering | Parameters it takes |
|---|---|---|
| `fw_reg_component #(BLK, W, AW)` | native: the regblock core ({doc}`islands`, Register blocks as children) | `W` 8/16/32/64 |

A child is recognized by its own class or by the nearest base with an entry. The
following are errors at the child's SV line, not a fallback to mapping the body:
- a parameter value the entry does not take, such as `fw_reg_component` with
  `W = 12`;
- a subclass that defines `run()`.

An extern assignment in the knob file wins over an entry, so RTL supplied for a
library class is used as is. A recognized class cannot join a multi-proc group yet.

A library class written as a cycle step, such as `fw_credit_tx`, or as an
all-or-nothing step, such as `fw_arbiter`, has no entry: its `step()` is in the
static subset, so it is mapped like any component and assigned to XLS by its class
name ({doc}`../reference/lib`).

The registry is the zuspec lowering registry, keyed by SV class name. An entry's
lowering builds Zuspec IR from the class parameters (target `zuspec`), so the block
goes through the same backends and checks as a mapped class; XLS IR text (`xls`)
remains for an existing XLS proc. The channel classes and port APIs that the front
end matches are entries too.
{doc}`../reference/registry` says how to add one.

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
