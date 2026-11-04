# Components, ports and exports

## A component

A component extends {sv:class}`fw_hdl_pkg::fw_component`. Its constructor takes a
name and a parent; the parent is `null` only for the root.

```{literalinclude} ../../tests/blinky/blinky.svh
:language: systemverilog
:start-at: class blinky
```

Three methods carry the elaboration and run phases:

| Phase | Method | What it does |
|---|---|---|
| build | `build()` | create child components, ports, exports and channels |
| connect | `connect()` | connect ports to exports (`port.connect(export)`) |
| run | `run()` or `step()` | the component's behaviour; only for a runnable or a steppable |

The root walks the tree: every component is built, then everything is connected,
then every registered runnable's `run()` is forked. A component opts in to a
`run()` process with `add_runnable(this)` in its constructor, or to a per-cycle
`step()` with `add_steppable(this)` (see [Cycle-step components](#cycle-step-components)).
A structural component (one that only builds and connects) does neither.

## Ports and exports

A **port** is where a component *calls* an API. During connect, the port resolves its
provider's implementation into its public member `t`. At run time the component calls
`port.t.method(...)` directly, with no per-call lookup.

An **export** is where an API is *provided*. It wraps the implementing object (the
*imp*) or forwards to another export below it in the hierarchy.

The connection rules follow from which way the calls flow, toward the imp:

* a port connects to an export (`port.connect(export)`), or to an outer port
  (`inner.connect(outer)`), to reach up the hierarchy;
* an export connects to another export below it, never to a port.

An unconnected port leaves `t` null. Calling `get_if()` on one reports the whole
bind map before it stops, so the failure says what else is unwired.

## The standard APIs

The APIs are interface classes in {doc}`../reference/std`:

| API | Methods | Used for |
|---|---|---|
| {sv:class}`fw_std_pkg::fw_put_if` | `put(t)` | writing a value out |
| {sv:class}`fw_std_pkg::fw_get_if` | `get(t)` | taking a value in |
| {sv:class}`fw_std_pkg::fw_get_nb_if` | `get(t)`, `try_get(t)` | polling: opt-in, see below |
| {sv:class}`fw_std_pkg::fw_reqrsp_if` | `call(rsp, req)` | blocking request/response |
| {sv:class}`fw_std_pkg::fw_mem_if` | `read`, `write` | protocol-independent memory access |

Outputs come first in an argument list (`call(out, in)`), as for a function's result.

## Channels

Two ports cannot connect to each other. A channel sits between a producer's put port
and a consumer's get port:

```systemverilog
fw_channel #(pkt_t, 2) ch;          // in build(): ch = new("ch", this);
prod.out.connect(ch.put_ex);        // in connect()
cons.in.connect(ch.get_ex);
```

`DEPTH` is how many values the channel holds. `DEPTH == 0` is a rendezvous: `put()`
returns once a `get()` has taken the value. In RTL, depth 0 becomes a ready/valid
wire and a larger depth becomes a ready/valid FIFO of that depth.

### Determinism, and the polling opt-in

`put()` and `get()` block, and there is no peek. So a network of components joined
by channels is a **Kahn process network**. Each channel carries the same stream of
values whatever the timing and whatever the depths, unless the network deadlocks.
That is what lets synthesis choose pipeline depths and FIFO sizes freely. It also lets
one test compare streams at every level.

A component that must poll declares its port as
`fw_port #(fw_get_nb_if #(T))` and connects it to the channel's `get_nb_ex`. Its
`try_get(t)` returns at once, 1 if it took a value. The opt-in is deliberate:
a polling component's outputs can depend on timing. The
{doc}`../examples/xls/lfsr` example shows what that means for its test.

## Cycle-step components

Some components are defined by what they do in one clock cycle, not by the stream
they produce: an arbiter, a merge, a credit counter. Such a component implements
{sv:class}`fw_hdl_pkg::fw_steppable` and registers with `add_steppable(this)`. Its
`step()` is called once per rising edge of the component's clock domain:

```{literalinclude} ../../tests/xls/micro/micro_f6_pkg.sv
:language: systemverilog
:start-at: class f6_count
:end-at: endclass
```

`step()` is a function, so it cannot wait, and the language limits it to what never
waits:

| In a step | Call |
|---|---|
| take a value if one is there | `try_get(x)` on an `fw_get_nb_if` port, usually as `if (p.t.try_get(x))` |
| read a level | `get()` on an `fw_level_if` port |
| send a value | `put(x)` on an `fw_valid_put_if` port |
| set a level | `set(x)` on an `fw_level_set_if` port |

A blocking `get()` or `put()` is a task and does not compile in `step()`. So a plain
step's outputs have no back-pressure. When it must know whether the receiver has
room, that knowledge comes in as an input, such as credits or a level, or the class
is an all-or-nothing step (below).

**What a cycle sees.** Fields have ordinary sequential semantics inside `step()`;
they belong to the component, so nothing else sees them mid-cycle. Between
components, a value one step puts or sets is seen by other steps from the *next*
edge. Values that `run()` processes or a testbench put before the edge are seen at
that edge. Space works the same way: a step's put into an
{sv:class}`fw_std_pkg::fw_valid_channel` counts the values waiting at the start of
its edge. So the order in which steps run at an edge never changes the result, and
the class model agrees with the RTL cycle for cycle.

Two consequences follow:
* a queue that a step fills every cycle needs `DEPTH >= 2`: one entry for the value
  the consumer takes this cycle, one for the value arriving;
* a step cannot use a wire (`DEPTH == 0`). The RTL wire moves a value in the cycle it
  is put, which the model cannot show, so the model stops with an error and
  partition rejects the design.

In XLS a step is one proc activation at II=1. Every receive is non-blocking, and
effects on different channels are not ordered, because the cycle is atomic.
{doc}`synthesis` lists the rules. A component has a `run()` or a `step()`, never
both. `tests/xls/test_step.py` checks a step counter and a round-robin arbiter
against XLS's RTL cycle for cycle. `examples/resp_tracker` builds its two blocks in
either form (`-D form=rt_step_pkg`).

### All-or-nothing steps

A step whose output is a stream, which the receiver may back-pressure, extends
{sv:class}`fw_hdl_pkg::fw_atomic_step` and puts with `put_or_stall(v)` on an
`fw_put_step_if` port. Each cycle:

- if every `put_or_stall` found its output ready at the start of the cycle, the step
  commits, as an ordinary step does;
- otherwise the step has no effect: no state changes, nothing is taken from an input,
  and nothing is put or set. The next edge runs it again from the same state.

`put_or_stall` returns nothing, so the step cannot branch on whether its output is
ready, and it cannot tell a stalled cycle from one that did not happen. This is how
XLS runs a proc activation whose send blocks, so the class model and the RTL agree
cycle for cycle under any back-pressure.

The runtime puts the state back after a stall, so all of it lives in one packed
struct, `s`, the base class's type parameter. `s` is zero at reset, in the model and
in the RTL, so choose encodings whose reset state is zero. Fields outside `s` must
not change in `step()`.

```{literalinclude} ../../tests/xls/micro/micro_f6_pkg.sv
:language: systemverilog
:start-at: typedef struct packed
:end-before: // Rejected: put_or_stall
```

Connect an `fw_put_step_if` port to a channel's `put_step_ex`. The channel is ready
when it had space at the start of the edge: a value another step took during the
edge frees space from the next edge. So a one-deep channel between an
all-or-nothing step and its consumer carries one value every other cycle; use
`DEPTH >= 2` for full rate.

The library channels undo their own effects after a stall. A class that implements
a port API itself, such as a test's source, and changes state in `try_get`, `put`
or `set` must record an {sv:class}`fw_hdl_pkg::fw_step_undo` with
`fw_step_ctx::record()` while `fw_step_ctx::atomic` is set.

`put_or_stall` in an ordinary step is an error, at the call's line in the front end
and when it runs in the model.

## Structural components

A component with children and no `run()` is **structural**: it only builds and
connects. Partition reads its `build()` and `connect()` by running them, so they are
ordinary code. They may contain:
- loops and arrays of children, ports and channels;
- an `if` on a class parameter;
- children configured by a parameter object (`fw_component_param`).

```systemverilog
add_k #(1)                 stage[N];
fw_channel #(bit [7:0], 1) ch[N-1];
function void build();
    in = new("in", this);  out = new("out", this);
    foreach (stage[i]) stage[i] = new($sformatf("stage[%0d]", i), this);
    for (int i = 0; i < N - 1; i++) ch[i] = new($sformatf("ch[%0d]", i), this);
endfunction
function void connect();
    stage[0].in.connect(in);
    for (int i = 0; i < N - 1; i++) begin
        stage[i].out.connect(ch[i].put_ex);
        stage[i + 1].in.connect(ch[i].get_ex);
    end
    stage[N - 1].out.connect(out);
endfunction
```

The rules are about meaning, and each is reported at the SV line that breaks it:
- An instance's name is the name of the field that holds it: `x = new("x", this)`, or
  `x[i] = new("x[i]", this)` for an array. In RTL, `x[2]` becomes `x_2`.
- A child's port connects to a channel end or to one of this component's own ports.
  Two children are joined only through a channel.
- Every port and every channel end is connected exactly once, and a channel has one
  consumer end.
- A field that `build()` leaves null is fine, as with a child under an `if`, unless
  `connect()` reaches through it.
- A component has children or a `run()`, not both.

Each distinct child becomes one generated block. "Distinct" means its class
specialization plus the values of its parameter object. A plain class or a typedef
keeps its own name. Anything else is named `<class>__<hash8>`, and `partition.json`
keeps the SV class beside it as `alias`. A block body reads `m_params.<field>` as a
constant.

## The root and the edge of the tree

The tree's root is wrapped by {sv:mod}`fw_root`, which holds it in reset and starts it.
The design top describes, in one block, how the root's ports and exports reach pins:

```{literalinclude} ../../tests/blinky/blinky_top.sv
:language: systemverilog
:start-at: module blinky_top
```

`` `fw_root_bind_port `` builds a bridge over a live interface (here
{sv:class}`fw_std_pkg::fw_put_xtor_bridge` over `fw_put_xtor_if`) and connects the
port to it. The component does not know its `put()` reaches a pin.

## Clock domains

Every component has a `clock` port, its clock domain
({sv:class}`fw_hdl_pkg::fw_clock_domain_if`). It inherits the port from its parent
unless it is connected explicitly. The root's domain is seated by `fw_root` from its
`clock` and `reset`. `tick(n)` waits `n` cycles of the component's domain. See
{doc}`../reference/clocking`.
