# One source, many schedules

The source says *what* a design does. A **knob file** says how it is built:
- the stages each block is scheduled into;
- which channels are registered;
- how deep the queues are;
- where storage lives;
- which latencies are contracts.

Changing a knob file never changes the source. Every build is checked against the
same function and the same contracts.

## Goals and knobs

Some things can be said in two places. They differ in who says them:

| | Says | Where | Example |
|---|---|---|---|
| a **goal** or requirement | what the design must achieve, for every build | an attribute in the source ({doc}`timing`, Directive summary) | `(* fw_ii=1 *)` on a loop, `(* fw_storage="bram" *)` on an array |
| a **knob** | how one build is made | the knob file | the stages a block is scheduled into, a channel's binding |

An attribute is part of the design: every build must meet it, and an engine that can't
reports why (a recurrence path, say) rather than missing it silently. A knob is a
per-build choice. It may override an attribute that names a realization (a knob can
put an `fw_storage="bram"` array in flops for a build that has no block RAM), but it
doesn't relax a goal. Today the knob file drives the XLS engine's schedule (stages,
registered channels) and the storage bindings; the source goals are read by the front
end and not yet acted on by an engine.

## The flow

```
knob file ─► fw.hdl.knobs.Resolve ─┬─► <top>_knobs_pkg.sv ──────► (sources)
                                   ├─► fwKnobs ──► Partition, Contracts, Integrate, Latency
                                   └─► xlsCodegenOptions ──► synth.xls.Codegen
```

1. **Resolve** merges the knob file through its `base:` chain and checks it.
2. **Partition** lowers each block. It writes the knob-chosen channel registers onto
   the IR.
3. **Contracts** rejects a knob set that cannot meet its latency contracts. This
   happens before any XLS tool runs.
4. **Codegen** builds every block with its own schedule.
5. **Integrate** wires the blocks and checks the island boundaries
   ([Islands](islands.md)).
6. **Latency** writes the per-path table and checks the contracts exactly.

## What stays the same

"The same function" means the response streams are equal up to the reorderings
the contract allows ([Contracts](../reference/contracts.md)). The cycle a value
appears in is not part of it. In a test, check this two ways:
- run the class model and each knob set's RTL on the same stimulus, and compare
  their traces with `fw.hdl.verif.canon.compare`;
- compare the latency table against measured latency.

`examples/resp_tracker` does both for four knob sets.

## Where values come from

When a value is wrong, the error names the knob file and line. When a value is
surprising, `<top>.knobs.json` lists every file merged, and `Knobs.origin()` gives
the line each value came from.
