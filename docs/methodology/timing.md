# Timing and scheduling semantics

```{admonition} Status: partly implemented
This page defines what fw-hdl code means in time, and what a synthesis engine may do with
it. The front end enforces the untimed and timed rules, fork/join, the writer rule and
the resource checks. Three engines exist: as-written; random, which tests the rules
by adding edges at random legal points; and delay, which adds edges where the logic
would break a clock period. A schedule is lowered and can be emitted as
source. The directive summary at the end gives the status of each
directive, and the sections say what isn't done yet. The decisions are provisional and
are revised as the work teaches us; the record of decisions, with what would make us
revisit each one, is kept in the fw-picorv32 retiming work packet
(`timing-semantics.md`). Constructs whose implementation is deferred are marked
*(later)*.
```

These rules hold for any design. A processor, a DMA engine and an AES accelerator are
written in the same style and follow the same rules; the examples below draw on all three.
The rules are defined on the IR. SV attributes are one surface syntax for them; the Python
(zdc) front end expresses the same things in its own terms.

## Two kinds of code

| | Untimed (the default) | Timed |
|---|---|---|
| Applies to | class code: tasks and functions of components and classes | a class or task marked `(* fw_timed *)`; all SV `interface` and `module` code |
| Program order | binds only through dependencies (below) | is cycle order |
| Clock edges (`@`, `wait`) | an error | written by the author; exact |
| Concurrency | found by the engine | written by the author with `fork`/`join` |
| Who picks the cycles | the engine, from the clock period and goals | the author |

Untimed code is read the way HLS reads C or XLS reads DSLX: as a sequential program whose
cycle structure is the engine's to choose. Timed code is read the way the lowering has
always read fw-hdl code: code between two edges runs in one cycle.

Signal-level code (transactors, `*_core` modules) is always timed and needs no mark,
and so is a bridge: a class that holds a virtual interface. A class that writes edges in
class code, such as a channel or an event set in the fw-hdl library, carries the mark.
Functions take no time and run in their caller's context.

```systemverilog
(* fw_timed *)
class uart_tx_model extends fw_component;   // bit timing is the point of this class
  ...
endclass
```

The mark goes on a class (all its tasks) or on one task.

## Untimed code

### What orders it

An engine may place any statement in any cycle, and overlap any two statements, as long
as these relations hold:

1. **Data.** A use comes after its definition. Fields are state carried from one loop
   iteration to the next.
2. **Control.** Code under a condition, or after an early `return`, comes after the
   condition is known. *(Speculation, below, relaxes this under rules.)*
3. **Effects on one port stay in program order.** Each port carries an implicit order, as
   XLS orders operations on one channel. Two writes, or a write and a later read, on the
   same memory port can't pass each other even when no data links them.
4. **Effects on different ports are not ordered** except through data, a resource, or a
   register (below). To order two ports, use a resource.
5. **Every iteration of a loop takes at least one cycle**, and every path around a
   `forever` waits.

Deleting all fw-hdl directives from an untimed program leaves the sequential program that
defines its behaviour. Every schedule an engine produces must be equivalent to it, port by
port.

### How time enters

Untimed code writes no edges. Time enters through:

- **Calls to timed tasks**, which are blocking port calls such as `wb.t.access(...)`,
  `in.t.get(x)` or `out.t.put(v)`. Each call is one event of unknown latency. The engine
  never splits it or moves code into it, but may run independent work in the same cycles.
  The port must be declared latency-insensitive (below), or the call is an error.
- **`tick(n)`**, which is a constraint, not an event: at least *n* cycles separate the code
  before it from the code after it, in program order. (`fw_component.tick` is itself a
  timed, latency-insensitive task, so it reaches the IR as one timed call.)

Calls on function-only ports, such as a monitor or status interface, take no time. Each is
an effect on its port (rule 3) and happens once its arguments are ready.

### Port declarations

A declaration goes on the port's API interface class when every binding of the API
has the property, or on the bridge that binds it when only some do. For example,
`wb_proto_if` is latency-insensitive in every binding, but `fw_put_if` is so only
over ready/valid (`fw_put_to_rv_bridge`), not over `fw_put_xtor_if`, which has no
handshake. The front end checks the binding actually bound.

`(* fw_latency_insensitive *)` also goes on a timed class or task whose calls tolerate any
delay, such as `fw_event_set` (its `wait_any()` is how untimed code waits for an event)
or a user's own timed task offered to untimed callers.

| Declaration | Meaning | Needed for |
|---|---|---|
| latency-insensitive | the protocol tolerates any delay before and between its calls (ready/valid, Wishbone with `ack`) | any call from untimed code |
| speculation-safe *(later)* | a call has no side effects and may be dropped; declared on the binding, since a read from memory is safe and a read from a FIFO is not | calls made under speculation |
| outstanding *N*, in order or tagged *(later)* | up to *N* calls can be in flight | overlapping calls on one port |

A port's API stays one blocking call in the source. A latency-insensitive protocol kit
exposes its request and response halves to the engine (the Wishbone initiator's `access`
is `request()` then `response()`), so that an engine can overlap calls without a change to
the source.

## Timed code

Program order is cycle order. Concurrency is written with `fork`:

- the branches start in the cycle the `fork` is reached;
- `join` continues in the cycle the last branch finishes, with no extra edge;
- `join_any` continues in the cycle the first branch finishes;
- `join_none` is not allowed inside a process. Processes are started by the component, as
  `run()` is.

**Determinism rule.** In any one cycle, two branches must not write the same field, and a
branch must not read a field another branch writes in that cycle. Values cross between
branches only over an edge. The front end checks this. With it, the class model in a
simulator and the synthesized netlist agree cycle for cycle; without it, blocking
assignments in the branches would race.

## Shared state

A field used by more than one process must be one of the following. Any other sharing is
an error.

### Registers

Memory-mapped registers, from the register model, are free-running visible state:

- any number of processes read a register field;
- **one hardware process writes a given field.** A second writer is an error unless the
  field carries an arbitration directive, such as `(* fw_arbitrate="priority" *)` with a
  declared order, or round-robin. The same rule holds for any field of the model, not
  only registers: the lowering rejects two of a model's processes writing the same bits
  in the same cycle. Today `"priority"` takes the processes in their lowering order; a
  declared order and round-robin come later. Signal-level code (bridges, interfaces)
  keeps its fixed priority over the model. Software writes over the register bus are governed by the
  field's `sw_write` access, as today;
- reads are ordered per register (rule 3). The value read is whatever the register holds
  in the cycle the schedule puts the read. The model does not define the timing between a
  software write and a hardware read, and neither does the hardware.

Copy configuration once, at a synchronizing call, and work from the copy. Then the engine
can move the rest of the code freely:

```systemverilog
cfg.t.wait_start(d);                 // d: src, dst, len, copied when the transfer starts
for (int i = 0; i < d.len; i++) ...
```

### Resources (hazard locks)

A resource orders accesses to state that several iterations, or several processes, use.
The mechanism follows the hazard locks of PDL (Zagieboylo et al., PLDI 2022), taken
without its one-instruction-per-thread framing:

| Operation | Meaning |
|---|---|
| `reserve(key, R\|W)` | records the access; reservations are made in program order |
| `block(key)` | waits until the access is safe |
| `acquire(key, R\|W)` | `reserve` then `block` |
| `release(key)` | commits; writes commit in program order. The library method is `free(key)`, because `release` is an SV keyword |

A key is an index or address; a resource without keys is one lock. An iteration sees the
state **as of its reservation**. For example, an AES block in flight keeps the round keys it
reserved while a key load writes new ones for later blocks.

There are three kinds of resource:

- **Fields.** In untimed code every field is a resource. The engine inserts the lock
  operations itself, and only when it overlaps iterations; without overlap there are none.
  In timed code the author writes them.
- **State behind a port**, such as memory behind a bus. The engine can't see it, so the
  author declares an `fw_resource` object and acquires it around the port calls. This is how
  two ports are ordered. For example, a copy with overlapping source and destination waits
  only when a read hits an address with a pending write.
- **Ports.** Each port is an implicit whole-port resource. That is rule 3.

The checks are path-sensitive:
- every path runs reserve → block → access → release;
- reservations on one resource are atomic per iteration;
- write releases run in program order;
- an explicit resource used without `acquire` is an error.

The engine treats the same rules as constraints on its schedule.

**Status.** State behind a port works today, with the library class `fw_resource`
({doc}`../reference/lib`):

```systemverilog
(* fw_guard="mem" *) fw_port #(fw_get_if #(bit [31:0])) src;   // a call through src
(* fw_guard="mem" *) fw_port #(fw_put_if #(bit [31:0])) dst;   // is an access to mem
fw_resource #(bit [7:0]) mem;
...
mem.acquire(a, FW_READ);        src.t.get(x);       mem.free(a);
mem.acquire(a + 16, FW_WRITE);  dst.t.put(x + 1);   mem.free(a + 16);
```

- The class model runs `fw_resource`'s sequential checks (`$error` on misuse). They take
  no time.
- The lowering checks every path of each process: reserve → block → access → free;
  write frees in the order reserved; a call through a port marked
  `(* fw_guard="<resource>" *)` only while a key of that resource is blocked; nothing
  still held at the end of a loop iteration. Keys are compared as written, so the check
  is conservative. A condition matches a later one only while nothing it reads can have
  changed.
- The as-written schedule never overlaps iterations, so the lowering then erases the
  operations. The netlist is the one without the resource.
- **Not yet:** declaring a field a resource and placing its locks by hand in timed code;
  lock realizations (`stall`, `bypass`), which matter only once an engine overlaps
  iterations.

A lock's **realization** is a choice, made separately from the source: `stall` (stall only)
or `bypass` (forwarding), and renaming *(later)*.

- `(* fw_resource="bypass" *)` on the field fixes it.
- Otherwise the engine uses `stall`, and reports the stall cycles each resource costs and
  what `bypass` would save.

A register file written plainly (`regs[rd] = v`) with a `bypass` realization replaces a
hand-written delayed write-back.

## Storage

Every array field is held in a storage realization. The target description lists them,
from flops to distributed RAM, block RAM and ASIC macros. For each one it gives:
- ports;
- read latency (0, or 1 for a registered read);
- width and depth limits;
- write modes;
- delay and area.

- **Choosing a realization:** `(* fw_storage="bram" *)` in the source is a requirement. A
  build knob overrides it per build. Otherwise, the engine uses flops up to a size
  threshold, then the target's default memory.
- **Port capacity:** each storage port allows a limited number of accesses per cycle. The
  engine spreads extra accesses over cycles, for example a multi-cycle fetch from a
  single-port RAM. It uses more ports (a dual-port RAM, or a replicated array for read
  bandwidth) only to meet a goal.
- **Registered reads** are operators with a latency of one cycle.

Port capacity is a different thing from a hazard lock. Locks order accesses; ports limit
how many there are per cycle. A bypass lock wraps whatever storage is chosen.

## Loops and goals

Loops reach the engine as loops. The engine unrolls one only when a goal requires it, or
when the code is not legal otherwise (a constant index into a packed vector, for example).

Goals are attributes on a loop or a process. They state performance, not structure:

| Directive | Meaning |
|---|---|
| `(* fw_ii=N *)` | start an iteration every *N* cycles |
| latency bound *(later)* | at most *N* cycles from the first effect to the last in an iteration |

With no goal, iterations don't overlap and each one runs as soon as it can. The engine
derives unrolling, folding and pipelining from the goals, the clock period and the delay
model. For example, from one AES source with no goal it uses one round datapath for 10
cycles per block; with `fw_ii=1` it unrolls the rounds and starts a block every cycle.

A loop-carried dependency cycle sets a floor on the interval: a chained cipher mode, an
accumulator. When a goal asks for less, the engine reports the recurrence path and uses
the best interval it can reach. It never misses a goal silently.

Sharing one piece of hardware across cycles comes, at first, only from folding a loop.
*(General binding comes later.)*

**Status.** The front end can keep a `for` loop whose bounds and steps are static, and
whose body doesn't wait, as a loop in the IR with its trip count (the `keep_loops`
option). The as-written engine unrolls it again, so the netlist is what it was. When
the body needs the index as a constant, or an inner loop's bound depends on the index,
the front end unrolls the loop itself. `while` loops and loops with a run-time bound
are not kept yet. Folding and pipelining (acting on `fw_ii`) come with the scheduler.

## Speculation *(later)*

Speculation uses a value or condition before it has been computed. There are three cases:

| Case | Example | Directive |
|---|---|---|
| a loop-carried value | a state machine's next state, a pointer chase, a processor's next pc | `(* fw_predict="<expr>" *)` on the field, or a predictor component |
| the loop's continue condition | `while (!done)`, a parser running to an end marker | `(* fw_speculate *)` on the loop |
| a condition inside an iteration | an arm with port calls, started early | the engine's choice |

The engine starts the dependent work on the guess and checks it when the real value
arrives. On a mismatch it discards that work and everything started after it.

Rules:
- work under speculation calls only speculation-safe ports and releases no write locks;
- guesses are checked in the order they were made;
- resources touched under speculation need checkpoint and rollback in their realization.

A predictor affects performance only, never results.

## What an engine produces

An engine turns untimed code into timed code. Its output is a schedule in the IR: the
original statements, plus the edges it chose and the parallel blocks where it overlapped
work. The schedule has two uses:

1. **Lowering to RTL.** Untimed code is never lowered directly. Even "no optimization" is
   an engine. It reproduces the as-written schedule: edges only where timed calls put
   them.
2. **Emitting executable source.** A timed task with:
   - `tick(1)` for each edge;
   - `fork`/`join` for each parallel block;
   - each timed call kept as a call;
   - each cycle annotated with its delay (not yet).

The emitted source must satisfy these invariants:

- it runs on the same benches as the untimed source;
- read back through the front end, it lowers to the same netlist;
- it and the netlist agree cycle for cycle on the pins. The untimed source and the
  netlist agree port by port, in order.

**Status.** The engine interface is `zuspec.synth.proc.sched`. An engine takes the
front end's process IR and returns the schedule: timed IR with no untimed region, lock
or kept loop left. Two things stay in it, for the emitter:

- the parallel blocks;
- the calls to other objects, each still marked as a call.

An engine places a call as a unit; if it splits one, the call is inlined. The lowering
then expands the parallel blocks and inlines the calls. The `Lower` task's `schedule`
parameter picks the engine, by name, with options after a colon. Three engines exist so far.
`as-written`'s passes run in this order:

1. check the locks, then erase them;
2. unroll the kept loops;
3. drop the region markers other than calls, so a timed call's body is in place.

Its netlist is the one the flow produced before engines existed.

`random:<seed>` is a soundness harness ({doc}`testing`, Random schedules). It runs the
same passes, then adds about `n` edges (default 8) at random points of untimed code,
inside the process's `forever` loop. It never puts one:

- in timed code, or in untimed code that timed code called;
- inside a call, which it places as a unit;
- between the loop's top and the process's first wait, where the process starts;
- after a nonblocking write (`v <= x`) that untimed code later reads in the same cycle.

Each schedule keeps program order and only moves code into later cycles. That is legal
under the rules above, so the design must behave the same, port by port.

`delay` (`delay:period=<ns>`) places edges by a delay model, so each cycle meets a clock
period. It runs the same passes, then walks each untimed process in program order. On
each path it keeps what every var holds in the current cycle, as a term over the
cycle's start, and costs it as the timing analysis does (LUT packing, select trees,
carry chains). Where a value or a condition would arrive too late for the period, it
adds an edge at the latest legal point before it in that cycle; the legal points are
the random engine's. So:

- an edge inside one arm of an `if` costs cycles only on that arm's paths; an `if`
  whose arms both fit stays one cycle;
- one assignment that is too slow on its own is split into one operator per
  assignment, so an edge can go inside it;
- a slow path the engine may not cut (in timed code, or inside a call) gets no edge.
  The `Lower` report lists it ("over budget, not cut"). So does a path that its edges
  still leave over the period: those edges are dropped, since they would cost
  cycles and still miss the period.

The walk only estimates. The lowering joins paths at shared code and selects values by
state and handshake, so the netlist has paths that no walk of the source shows. With
`rounds=<n>`, the engine closes the loop on the netlist:

1. It lowers its schedule, recording which statement computes each term on the way.
2. It runs the timing analysis.
3. For each path still over the period, it walks back to the latest statement on that
   path where an edge leaves the rest of the path within the period, and schedules
   again with an edge before that statement.

Only when no such statement may take an edge does it lower the budget for the whole
walk. It runs at most `n` lowerings and keeps the round that meets the period with the
fewest edges. The check is on the netlist's worst path, state decode included
(`check=state` holds only each state's own paths). The model and period default to
the `Lower` task's `delay_model` and `clock_period`. The report says what each edge
was cut for: the statement, its source line and its arrival.

### Emitted source

The `Lower` task writes the schedule as source when `emit_sched` is set:
`<top>_sched_pkg.sv` (named after the design top, whatever the netlist module is called), a package with one class per process of class code.
`<cls>_sched` extends the source class `<cls>` and overrides the task the process runs
(`run`):

```systemverilog
(* fw_timed *)
class fw_picorv32_sched extends fw_picorv32;
    function new(input string name, input fw_component parent);
        super.new(name, parent);
    endfunction
    virtual task run();
        bit [31:0] step_bus_addr = 32'h0;   // the inlined code's locals
        ...
        pc = 32'h0;                         // the state where the process starts
        ...
        forever begin
            ...
            wb.t.access(step_bus_addr, 32'h0, 4'hf, 1'h0, step_bus_access_dat_r, ...);
            ...
            tick(32'h1);
        end
    endtask
endclass
```

- An edge the engine adds is `tick(1)`; a wait on a condition is
  `while (!(c)) tick(1);`.
- A call to another object (a port, an export, a channel) is the call the source
  made; so is a timed call on the object itself, such as `tick`.
- A parallel block is `fork ... join`.
- Untimed functions of the class itself are inlined. The fields keep their names, and
  the inlined code's locals become locals of the task.

The task starts by setting the fields the process writes to the values they have where
the process starts (where it first waits). It then runs the code before its first edge
again, which must give the same state. It does when that code only sets things from
fields, as the top of a `forever` loop usually does; the round trip checks it.

The `SchedSource` task passes the package on as simulation source, with a define that
the design top tests to bind `<cls>_sched` in place of `<cls>`:

```systemverilog
`ifdef FW_PICORV32_SCHED
    import fw_picorv32_top_sched_pkg::*;
    `define FW_PICORV32_CLS fw_picorv32_sched
`else
    `define FW_PICORV32_CLS fw_picorv32
`endif
    class fw_picorv32_top_bind extends fw_component_root #(`FW_PICORV32_CLS);
```

The three invariants are checked as follows:

- **Round trip.** Read back in place of the source class, the emitted class lowers to
  the same states and registers. Locals have new names, so the netlists are compared
  by simulation rather than as text (`tests/python/unit/test_elab_emit.py`).
- **Executable.** On picorv32 the emitted class passes the `sched-wb-eq-*` and
  `sched-tlm-eq-*` benches, on every program and on rv32ui.
- **Cycle-exact.** The `cyc-eq-*` bench runs the emitted class beside its netlist,
  each with its own memory, and compares every output pin every cycle. It aligns the
  two at their first bus cycle: the class runtime (`fw_root`) starts the threads one
  cycle after reset, the netlist at once.

Not yet:

- the delay of each cycle as a comment;
- a process whose task has arguments;
- more than one process of the same class.

The XLS engine is one engine behind this interface. It orders all effects of an
activation in program order (its token chain), which is stricter than rules 3–4 and
therefore a legal refinement of them. It is reached only through its adapter.

## Directive summary

"Read" means the front end parses and checks the directive and carries it into the
process IR (`Var.attrs`, `Loop.attrs`, `Region`); "acted on" means an engine uses it.

| Directive | On | Meaning | Status |
|---|---|---|---|
| `fw_timed` | class, task | timed code | enforced: edges, `wait` and `fork` in untimed code are errors; regions in the IR |
| `fw_latency_insensitive` | API interface class, or the class/task that binds it | calls from untimed code are allowed | enforced: other calls from untimed code into timed code are errors; each allowed call is a `Region` tagged `call` |
| `fw_resource="stall"\|"bypass"` | field, `fw_resource` | lock realization | read |
| `fw_guard="<field>"` | port field | calls through the port access the state the named `fw_resource` field guards | enforced at lowering: such a call outside a block .. free is an error |
| `fw_storage="<kind>"` | array field | storage realization (a knob may override it) | read |
| `fw_arbitrate="<policy>"` | field | several writers, with this conflict rule | enforced at lowering: two of the model's processes writing the same bits in one cycle is an error without it. `"priority"` only; others are errors for now. Register fields in the MMIO flow: not yet |
| `fw_ii=N` | loop, process | goal: initiation interval | read; carried on the loops the front end keeps. Not yet acted on |
| `fw_predict="<expr>"` *(later)* | field | speculation, a loop-carried value | read |
| `fw_speculate` *(later)* | loop | speculation, the continue condition | read |
| speculation-safe, outstanding | port binding | port declarations (syntax to be settled with the protocol kits) | not yet |

An `fw_*` attribute that isn't listed here is an error, as is a directive on the wrong
kind of declaration or with the wrong kind of value. Other attributes are ignored.

A directive on a field or loop is checked when the front end meets that field or loop
in a process. One on code that is never lowered isn't checked.
