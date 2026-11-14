# Synchronous logic in classes

A component can describe clocked logic the way RTL does, and still be a class. It has
three kinds of process:

| Process | Registered by | Runs | Writes |
|---|---|---|---|
| `step()` | `add_step()` (`fw_steppable`) | once per edge of its domain | state, and **sync** port fields |
| `run()` | the component | a task; wakes on the edge | state, and **sync** port fields |
| `comb()` | `add_comb()` (`fw_combinational`) | whenever the domain settles | **comb** port fields only |

One component can have all three. Ports carry values (see {doc}`../reference/struct-ports`):
each field of a port is either **sync** (registered: written now, seen by the peer after the
next edge) or **comb** (a wire: seen at once). Fields are sync unless `set_comb()` says
otherwise.

## The edge: commit, settle, step

The sync kernel (`fw_sync_kernel`) runs each clock domain's edge in three phases:

1. **Commit.** Every sync field written during the previous edge becomes visible.
   A field that was not written holds its value.
2. **Settle.** Every `comb()` of the domain runs, in whole passes, until no comb field
   changes. The bound is 64 passes; past it the kernel stops with
   `comb() did not settle in 64 passes (a comb loop?); still changing: <field>`.
3. **Step.** Every `step()` runs, in any order. Then each `run()` waiting on the edge
   resumes. All of them see the settled values from phase 2; their sync writes are
   committed at phase 1 of the next edge.

Step order does not matter: state is private, and everything another component can see
was fixed before phase 3.

`run()` processes resume *after* the kernel at an edge: while the kernel is live, the
root clock's `tick()` yields `#0` in every other process. A `run()` therefore reads what
that edge's `step()`s read, like a `step()` does. A sync write made at an edge by a process
that ran before the kernel (module code right after the clock rises, say) is held and
lands after that edge's commit, like an NBA.

The naive settle is a fallback. The settle weaver (mode A) replaces it with a static
schedule that iterates only inside comb loops; classes without a schedule keep the
fallback. See {doc}`../reference/settle`.

## Write rules

The kernel checks who writes what, and stops with a named error on a breach:

- a sync field written from `comb()`: `sync field "data" of "o" written from comb()`;
- a comb field written from `step()` or `run()`: `comb field "valid" of "o" written from step()`;
- a field with two drivers, or an input that nobody drives and that is not
  `set_optional()`, after connect (see {doc}`../reference/struct-ports`).

The rule checks compile out with `+define+FW_SYNC_NO_CHECKS`.

## Reset-force

A port holder can be put in a reset domain. While that domain is in reset, the *peer*
reads each field's reset-force value instead of the held one (for ready/valid: `valid` and
`ready` read 0; `data` is not forced). The writer's own reads are never forced. The force
ends on the first edge out of reset.

## When the kernel is active

The roots (`fw_component_root`, `fw_component_root_param`) freeze the field semantics
after `build()`, check connections and sort holders, `comb()`s and `step()`s into domains
after `connect()`, and launch one edge loop per clocked domain after `run()`. A tree with
no value ports and no `comb()` has an inactive kernel and behaves as before: `step()`s run
from `do_run()` as they always have.

## The porting hazard

`step()` updates state in place, with blocking semantics. A state field read after it was
written in the same `step()` gives the new value, where Verilog's NBA would give the old
one. Port outputs keep NBA meaning (sync fields are written now and seen next edge), so the
hazard is limited to a component's own state. Take care when porting `always_ff` code
that reads a register it has already assigned.

## Mixing with RTL

At the `fw_root` boundary, a pin bridge (`fw_rv_pin_in`/`fw_rv_pin_out`) joins a value
port to module pins. When an input pin of a comb field changes, the bridge writes the
field and settles the domain at once, so comb paths run through the class tree within the
same time step. Sync fields go to the pins nonblocking, so RTL at edge *k* sees what the
tree sees after commit *k*.

## Lowering

The same description lowers to synthesizable Verilog: `step()` becomes `always_ff`,
`comb()` becomes `always_comb`, sync fields become registers and comb fields wires. The
lowering path is documented as it is built.
