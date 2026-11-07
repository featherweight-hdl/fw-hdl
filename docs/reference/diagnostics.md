# Diagnostics

Every rule the native flow (`fw.hdl.lower`, {doc}`../methodology/flows`) checks in a
design, with the error that reports it. The rules themselves are defined in
{doc}`../methodology/timing` and {doc}`../methodology/synthesis`; this page says how a
broken one is reported.

## How errors are reported

The `Lower` task stops at the first error and reports it as one error marker,
`<Class>: <message>`. The class says which stage found it:

| Class | Stage | Location in the message |
|---|---|---|
| `AttrError` | reading `fw_*` attributes | always `file:line` |
| `TranslateError` | the front end, class code to process IR | `file:line` for the timing, fork, resource and call rules; otherwise the process or path |
| `StructureError` | the module structure around the class side | the hierarchical path |
| `ElabError` | elaboration (`initial`, constructors, `build`, `connect`) | the path, sometimes a source range |
| `LowerError` | lowering: fork, lock and writer checks, the state machines | `file:line` for the fork and lock checks; otherwise the process and var |
| `EmitError` | writing the schedule as source (`emit_sched`) | the process |

Notes and warnings go to `lower_report.txt`. Lines that start with `warning` there
also become warning markers.

## Attributes

An `fw_*` attribute that isn't in the directive table ({doc}`../methodology/timing`,
Directive summary) is an error, and so is a directive in the wrong place or with the wrong
kind of value. Other attributes are ignored.

| Rule | Message |
|---|---|
| a known directive | `unknown fw-hdl directive {name}` |
| on a target it applies to | `{name} does not apply to a {target}; it goes on a {targets}` |
| a flag takes no value | `{name} is a flag; write (* {name} *)` |
| a value where one is needed | `{name} needs a value` / `{name} takes a string` / `{name} takes a positive integer` / `{name}={text}: not a constant` |
| one of the allowed values | `{name}="{s}": one of {choices}` |
| `fw_arbitrate` policies | `{var}: fw_arbitrate="{p}" is not supported yet (only "priority")` |

## Untimed code

| Rule | Message |
|---|---|
| no clock edges, delays or `wait()` | `{a clock edge or delay \| wait()} in untimed code ({cls.task}). Call a latency-insensitive API to wait, or mark the task or its class (* fw_timed *)` |
| no `fork` | `fork in untimed code ({task}); an engine finds the concurrency in untimed code. fork/join belongs to (* fw_timed *) code` |
| calls into timed code only through a latency-insensitive API | `untimed code ({caller}) calls timed {callee}, which is not declared latency-insensitive. ...` |

## Timed code and fork

| Rule | Message |
|---|---|
| no `join_none` in a process | `fork/join_none inside a process ({task}); processes are started by the component (add_runnable), not forked` |
| `join` only, for now | `fork/join_any is not supported yet (only join)` |
| a process first waits outside a fork | `{proc}: the process first waits inside a fork; put a wait (a port call or tick) before the fork` |
| no `return` in a branch | `return inside a fork branch` |
| branches write disjoint state | `{proc}: fork branches {i} and {j} both write {names}` |
| a branch doesn't read what another writes | `{proc}: fork branch {j} reads {names}, which branch {i} writes; values cross between branches only over an edge, ...` |
| every loop in a branch waits | `{branch}: a path round a loop in a fork branch never waits` |
| edges are `@(posedge clock)` | `a time delay in a process cannot be synthesized` / `waiting on a named event is not supported yet` / `only @(posedge clock) is supported` / `unsupported timing control {kind}` |

## Resources

Lock messages read `{proc}: ...`, after the source location when there is one.

| Rule | Message |
|---|---|
| only the lock operations | `{res}.{method}() is not supported in a process; use reserve, block, acquire and free` |
| a constant access kind | `{res}.{m}: the access kind (FW_READ / FW_WRITE) must be a constant` |
| `fw_guard` names a resource field of the same object | `{field} is (* fw_guard="{g}" *), but {g} is not an fw_resource field of the same object` / `fw_guard on {field}: its object is not static` |
| reserve once per iteration | `reserves {res} twice in one iteration (first at {loc})` |
| reserve, then block, then free | `blocks on {res} without reserving it` / `blocks on {res} twice` / `releases {res} without reserving it` / `releases {res} before blocking on it` |
| write locks freed in program order | `releases the write lock {res} before {older}, reserved earlier; write releases go in program order` |
| guarded calls inside an acquire | `accesses {res} outside an acquire (reserve and block, then release after)` |
| released on every path | `the process ends holding {res} on a path through this code ({conds}); release it on every path` |
| a loop body leaves the locks as it found them | `an iteration of the loop ends holding {res}` / `a loop body releases {res}, reserved before the loop; ...` |
| one fork branch reserves | `fork branches {i} and {j} both reserve; reservations in parallel branches have no program order` |
| a bounded check | `more than 4096 paths to check for locks` |

## Shared state

| Rule | Message |
|---|---|
| one of a model's processes writes a field in a cycle | `{var} ({origin}) bits {ranges} are written by {procs} in the same cycle. One process writes a field; to let several, declare the arbitration, e.g. (* fw_arbitrate="priority" *)` |
| signal-level code over a model: priority | a warning, `{var} bits ... written by ...; priority goes to ...` |
| processes don't write static variables or properties | `write to static variable {name} in a process` / `write to static property {name} in a process` |
| no `<=` to a local | `nonblocking write to local {name}` |
| fields written at run time are bit vectors | `run-time write to non-integral field {name}` |
| one combinational driver | `{v}: written by two combinational processes` / `{v}: written by a combinational process and {a clocked process \| is an input}` |

## Processes and loops

| Rule | Message |
|---|---|
| a thread loops forever | `{thread}: a thread that does not loop forever is not supported yet` / `process {name} can finish; a process must run forever` |
| every path round a loop waits | `process {proc}: a loop that never waits for the clock (...)` |
| a loop the front end unrolls ends | `loop did not terminate during unrolling` |
| constant `repeat` and `foreach` | `repeat with a run-time count is not supported yet` / `foreach over a run-time array is not supported` |
| loop-carried locals are bit vectors of one width | `loop-carried non-integral local {name}` / `loop-carried handle {name} is not supported` / `local {name} changes width` |
| `break`/`continue` in a loop | `break/continue outside a loop` |
| combinational code doesn't wait, latch or loop | `combinational process {proc} waits` / `... nonblocking write to {vars}` / `... {v} is not written on every path (it would be a latch)` / `... keeps its value on some path (a latch) or is read before it is written (a combinational loop)` |

## Objects and calls

Anti-pattern A1 is run-time object or queue manipulation: build objects at elaboration,
and keep run-time state in fields.

| Rule | Message |
|---|---|
| no `new` in a process (A1) | `object construction inside a process (anti-pattern A1)` |
| no queue mutation in a process (A1) | `{push_back \| ...}() on a queue inside a process (anti-pattern A1)` |
| handles are built at elaboration | `null object calling {method}` / `null object access .{field}` / `null object write .{field}` / `virtual interface .{m} is not static` |
| a called method has a body | `call to {name} has no body` |
| no recursion | `call depth exceeded at {name} (recursion?)` |

## Types and expressions

| Rule | Message |
|---|---|
| constant part selects, replication counts, `$clog2` | `run-time part select` / `replication by a run-time count` / `$clog2 of a run-time value` |
| divide, modulo and power on constants | `run-time {Divide \| Mod \| Power} is not supported` |
| a shift amount no wider than the value | `wide shift amount` |
| static unpacked arrays, no writes to their elements | `run-time array in a process` / `write to an array element inside a process` |
| packed patterns, no strings | `unpacked assignment pattern in a process` / `string concatenation in a process` / `cannot merge values of {key} across a run-time condition` / `value {v} used as a bit vector` / `value {v} used as a condition` |
| supported system calls and built-ins | `unsupported system call {name} in a process` / `unsupported built-in {name} in a process` |
| anything else outside the subset | `unsupported {statement \| expression \| unary \| binary \| member access \| element select \| assignment target} ...` |

## The design top and RTL modules

| Rule | Message |
|---|---|
| one `fw_root` under the top | `top module {top} not found` / `expected one fw_root instance under {top}, found {n}` |
| structural wrappers on the path to the class side | `{path}: procedural code in a module on the path to the class side (it must be structural)` |
| every interface used by the class side | `{path}: an interface the class side does not use` |
| the class side writes no input | `{port}: an input written by the class side` |
| no `inout`, constant selects in connections | `inout is not supported` / `run-time select in a connection` |
| one driver per net | `{v}: driven by both a process and the structure` / `{v}: an input is driven` |
| RTL blocks on the design's clock and reset | `{path}.{port}: the {clock \| reset} of an RTL block must be the design's ...` |
| one rising clock edge, a reset branch for an async reset, no latches | `an always block must be clocked by one rising edge` / `an asynchronous event without a reset branch` / `reset edge and level disagree` / `level-sensitive latches are not supported` |
| comb or clocked writers, not both | `{iface}.{var}: written by both combinational and clocked code` |

## Schedules and the emitter

| Rule | Message |
|---|---|
| a known engine | `no scheduler named {name} (have: {list})` |
| engine options | `as-written: no options ({opts})` / `random: unknown options ({opts}); have seed, n, max` |
| an edge only where an engine may put one (`random`, `insert_edges`) | `no edge may go at {proc} {path} @{pos}: it is not untimed code an engine places (timed code, a call, the way in to where the process starts, or a pending nonblocking write that untimed code reads)` |
| one process per class, when emitting | `{proc}: a second process of class {cls}; one emitted class per source class` |
| the emitted class names only its fields and locals | `{proc}: {var} ({origin}) is neither a field of {obj} nor a local: the emitted source can't name it` |
| a kept call's receiver is a field path | `call to {method}: its receiver has no path from the object` |

## Not rule errors

A few messages report a limit of the translation rather than a broken rule:
`state discovery did not converge`, `the blocking point was not found while
translating its loop`, `the blocking point was reached twice`. Report them as bugs, with
the design.
