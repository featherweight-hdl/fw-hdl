# Islands and boundaries

A design is a set of **islands** joined by channels. An island is one lowered unit:
- an XLS block;
- a native block;
- an extern block;
- hand RTL.

Inside an island, components may talk combinationally. Between islands, the rule is
that **every boundary is registered in both directions**, unless the design lists it
as an exception. Then:
- timing closes per island;
- no combinational loop can cross islands;
- system analysis works on a plain cycle-level graph.

## Channel kinds

There are three kinds of channel between components, each with its own API and pins:

| Kind | Producer's API | Consumer's API | Channel class | Pins |
|---|---|---|---|---|
| stream | `fw_put_if` (`put` waits) | `fw_get_if` / `fw_get_nb_if` | `fw_channel #(T, DEPTH)` | data, valid, ready |
| valid-only | `fw_valid_put_if` (`put` is a function: never waits) | `fw_get_if` | `fw_valid_channel #(T, DEPTH)` | data, valid |
| level | `fw_level_set_if` (`set`) | `fw_level_if` (`get` returns the value) | `fw_level_channel #(T)` | data |

When to use each:
- Use a **stream** by default. A network of streams is a Kahn process network: the
  values on every channel are the same whatever the timing and depths.
- Use **valid-only** when the producer must never stall: a link carried by credits,
  for example. The producer must not send without room, so a credit scheme has to
  guarantee it. In the model, `fw_valid_channel` reports a put while full as a credit
  violation. In RTL the producer's ready is tied high, a valid-only top output has
  no ready pin, and `fw_valid_check` asserts the FIFO is never offered a value
  while full. XLS has no valid-only mode, since `flow_control=none` still emits a
  ready, so integration ties that ready.
- Use a **level** for configuration and status, such as a mode or a threshold. A level has
  no order against streams. XLS registers a `single_value` channel on both sides, so a
  reader sees a new value two cycles after the writer sets it, and may read the
  old value meanwhile. Nothing that must match a stream exactly should depend on a level
  that changes while the stream runs.

Integration rejects a port bound to an end of another kind, at the child and the end
that disagree. Within a class model, SV typing already catches it.

## Register blocks as children

A register block is not a component, so on its own it has no ports. To put one in a
structural tree, give it to an `fw_reg_component #(BLK, W, AW)`:
- `wr` takes software writes as a stream of `{addr, data}`, `AW + W` bits. There
  is no read path through the tree.
- Each register that hardware reads gets one level port of the register's type. In
  `connect()`, the subclass ties each port to its register with `drive`.

```systemverilog
class rk_rc extends fw_reg_component #(rk_regs);
    fw_port #(fw_level_set_if #(bit [31:0])) k;
    fw_port #(fw_level_set_if #(pair_t))     p;
    virtual function void build();
        super.build();
        k = new("k", this);  p = new("p", this);
    endfunction
    function void connect();
        drive(fw_reg_level #(bit [31:0])::make(blk.k, k));
        drive(fw_reg_level #(pair_t)::make(blk.p, p));
    endfunction
endclass
```

In the class model, a level port carries its register's reset value from the start
of `run()`, then the value after each write. Partition makes such a child `native`,
needing no knob. It reads the register map, and which register each port carries,
from the objects that `build()` and `connect()` construct. The RTL is the
generated regblock core under a wrapper:
- `wr_rdy` is tied to 1;
- each level output is the register's `hwif_out` fields, with a reserved field
  held at its reset value.

The Partition task writes the module and its signature, and Integrate takes them as
it takes an extern block.

Partition rejects, at the SV line:
- a level port that no `drive` ties to a register;
- a register with a field hardware writes. A register-block child has no hardware
  inputs yet.

The core decodes only its own address span, so an address beyond it aliases. Writes
are configuration: give them time to land before data that depends on them, since
a level has no order against streams (see §Channel kinds). In tests,
`rtl_testbench(..., after={"in": "cfg"})` does that.
(`tests/xls/compose/regs_pkg.sv`, `tests/xls/test_native.py`.)

## Multi-proc islands

By default each XLS child is its own block. The knob file can instead make several
children one block, as one multi-proc XLS package:

```yaml
island:
  groups:
    rt_core: [rt_tag, rt_resp]      # classes; a specialization as add_k#(1)
```

Partition makes the group's members one child named after the group. It then:
- makes each member class a proc;
- moves each channel with both ends on members inside, as an in-package channel;
- makes every other member port a port of the group, named `<instance>_<port>`.

Codegen runs with `--multi_proc --fifo_module=fw_xls_fifo_wrapper`.
`src/rtl/fw_xls_fifo_wrapper.sv` is `fw_rv_fifo` under XLS's FIFO interface, so a
channel inside a group behaves like one between blocks. The latency report walks into
the group: each member's own schedule, plus 1 cycle per in-package FIFO.

A group has one schedule, because XLS takes one per package. The knob check rejects a
group whose members' `pipeline_stages`, `clock_period_ps` or `worst_case_throughput`
differ. All the members must sit in one structural component, and only streams may
run between them.

## Credited links

A credit sender with a valid-only output and a receiver that returns one credit per
value taken make a link that never stalls its sender. Size the channel to the credits.

There is one exception, from how XLS completes a stage. A stage's sends complete one
at a time, and its receive completes last. So if the receiver returns the credit in
the same activation as a send that can be backpressured, the credit can go out before
the value has left the channel. That channel must hold **credits + 1** values. A
receiver whose outputs never backpressure needs only the credits.
(`tests/xls/test_xls_facts.py`; `tests/xls/compose/exit_pkg.sv`.)

## What counts as registered

A channel between two blocks is registered both ways when either of these holds:

- it is a FIFO: an `fw_channel` of depth ≥ 1, which integrates as `fw_rv_fifo`
  (registered valid and ready, no bypass); or
- it is a wire (depth 0), and the producer's valid and data and the consumer's ready
  are all driven from flops. For XLS procs this means `skid` registers on both ends
  (`xls.chan_flop` in the knob file).

## The checks

`fw.hdl.spl.Integrate` reads each block's real combinational dependencies, output
pin to input pins, from its Verilog with yosys. On those it checks:

| Rule | Severity parameter | Default |
|---|---|---|
| no combinational loop through depth-0 channels | `boundary` | error |
| no depth-0 channel from a block back to itself (XLS accepts this silently) | `boundary` | error |
| no output valid that depends combinationally on a ready | `boundary` | error |
| every block-to-block channel registered both ways | `registered_boundaries` | warn |

The XLS-generated blocks, extern blocks and hand RTL all go through the same check,
because it reads the netlist rather than trusting a declaration.

## Exceptions

Some boundaries must stay unregistered:
- a same-cycle handshake that a register would change;
- a fixed-timing macro port;
- a quasi-static configuration level.

List each one in the knob file with its reason:

```yaml
island:
  exceptions:
    - {channel: c0, kind: same_cycle, reason: grant must follow valid in the same cycle}
```

`kind` is one of `same_cycle`, `fixed_timing`, `single_value`, `cdc` or `merged`
(the two sides are really one island).
