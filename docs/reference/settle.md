# The settle schedule

`src/sync` (in `fw_hdl_pkg`) and `python/fw/hdl/weave/settle.py`. At each edge the
sync kernel commits the sync fields, settles the comb fields by calling `comb()`s, and
then calls the `step()`s (see {doc}`../methodology/sync-logic`). This page covers the
settle: how the kernel orders the `comb()`s, how it reports the order, and how it
treats comb loops.

## Settle tables

The settle weaver writes one table (`fw_settle_table`) per component class that
implements `fw_combinational` or `fw_steppable` and owns struct ports. A table lists
the port fields that the class's `comb()` and `step()` read and write, as
`<port>.<field>`: the port is the member name and the field is the holder's
`add_field()` name (`o.valid`, `i.data`). A parameterized class gets one table, keyed
by its generic name, that is the union over its specializations.

The weaver reads the method bodies through sv-weave's read/write analysis. It stops at
the struct-port boundary: a call to a method of an `fw_sync_port` or `fw_sig_holder`
class is not followed; its effect is the field that the method's `fw_reads` or
`fw_writes` attribute names, under the receiver's path:

```systemverilog
(* fw_reads = "valid" *)  function bit  get_valid();
(* fw_writes = "ready" *) function void set_ready(bit v);
```

A boundary method with neither attribute is opaque. Reads and writes of anything other
than port fields (state) are left out of the table.

For `comb()`, the table also records each written field's dependences: the fields read
by the same top-level statement (`o.valid <- i.valid`). Where one statement could carry
a value to another (a local, or a member that one statement writes and another reads),
every write depends on every read.

| Weaver diagnostic | Level |
|---|---|
| an opaque call in `comb()` (its effects are unknown, so the schedule could be wrong) | error |
| a `comb()` that writes no port field (it can never feed another process) | warning |

Which fields are comb is known only at run time (`set_comb()`), so the table lists all
port fields and the scheduler keeps the comb ones.

### Weaving

Run the weaver with sv-weave, with fw-hdl's binding:

```yaml
sv-weave:
  binding: fw.hdl.weave.binding:FwHdlBinding
  plugin-path: [<fw-hdl>/python]
  sources:
    top: [my_tb]
  weavers:
  - name: fw.hdl.weave.settle:SettleWeaver
```

In a dv-flow, use an `svweave.Weave` task with this config and the design's filesets as
inputs, and compile its output with the design. The woven package registers each table
at start-up. A specialized class finds its table through matchers the weaver writes,
one per specialization it saw, so weave over the sources that specialize the class (the
tb as well as the library).

## The schedule

After connect, the kernel builds one schedule (`fw_settle_sched`) per clock domain:

1. a node per `comb()` object, with the comb fields its table says it reads and writes;
2. an edge A → B when A's `comb()` writes a comb field that B's `comb()` reads;
3. the strongly connected components of that graph, in topological order.

Per settle, a node outside any loop runs once. A **group** (several nodes in a cycle, or
one node that reads what it writes) runs whole passes until a pass changes no comb
value, at most `max_passes` (64). A group that does not converge stops with
`comb() did not settle in 64 passes (a comb loop?); still changing: <field>`.

### Fallback

A node without a usable table is a **fallback**: it may read and write any comb field.
The reasons:

- `no settle table`: the class was not woven;
- `comb() object is not a component`;
- `path <p> does not resolve`: a table path names no port field of the instance.

A fallback is joined to every node that reads or writes a comb field, so the fallbacks
and every node that both reads and writes share one group, which settles by passes as
the naive kernel does. A design with no woven tables at all settles correctly, just
without the saving.

### `+fw_settle_naive`

Runs whole passes over all of a domain's `comb()`s instead of the schedule. Use it to
compare: the results must be the same.

## Comb loops

The kernel classifies each looping group at connect, from the field-level graph (an
edge r → w when a node's `comb()` writes comb field w from comb field r, by the
table's dependences):

| Kind | Meaning | Effect |
|---|---|---|
| `once` | not a loop | each node runs once |
| `false cycle` | the components form a cycle but no field depends on itself (one `comb()` serving independent paths) | settles by passes; not an error |
| `true loop` | a field depends on itself through comb paths | an error, unless waived; settles by passes |
| `fallback` | a group that holds a fallback node | settles by passes |

An unwaived true loop stops the run at connect:

```
fw-hdl: <root>: comb loop through a.o.valid -> b.o.valid -> a.o.valid (comb() of a, b)
```

### Waivers

A component in the loop can declare the loop intended, in `build()` or
`connect()`:

```systemverilog
waive_comb_loop("ready and valid meet in the arbiter; settles in two passes");
```

The reason must not be empty. A waived loop still settles by passes and is listed with
its reason under `+fw_settle_show`.

## `+fw_settle_show`

Prints each domain's schedule at connect (`fw_settle_sched::report()`):

```
fw_settle: <root> domain 0: 3 comb() nodes, 2 groups, 0 fallback
  group 0: once: top.src
  group 1: true loop: top.a, top.b
    fields: a.o.valid -> b.o.valid -> a.o.valid
    waived: ready and valid meet in the arbiter; settles in two passes
```

Each group gives its kind and its nodes in run order. A true loop gives its cycle of
fields; a false cycle gives the fields its nodes share. A fallback node is listed with
its reason (`fallback top.x: no settle table`).
