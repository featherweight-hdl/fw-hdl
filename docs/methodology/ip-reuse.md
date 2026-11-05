# Wrapped IP

Much RTL work is choosing, parameterizing, replicating and connecting modules that
already exist. fw-hdl's structural components already make the replicating and
connecting easy: `build()` and `connect()` run as ordinary SystemVerilog, so loops,
arrays and computed parameters work. A **wrapper** brings an existing Verilog module
into that structure: the module stands behind a class, and the class's instances are
built, configured and connected like any other child.

## Starting from a module: `fw-hdl wrap`

Most of a wrapper can be read off the module's header. The importer does that:

```
$ fw-hdl wrap rtl/dma_like.sv --module dma_like --abstract dma_engine -o dma_engine.svh
dma_like: 12 pins
  clock  aclk  (by name)
  reset  aresetn  active-low (by name)
  rv     cmd  cmd_data/cmd_ready/cmd_valid  high: data, valid and ready; directions agree
  valid  done  done/done_vld  medium: no ready pin: a valid-only output
  level  cfg_en  cfg_en  low: no protocol matched: a level
  level  cfg_burst  cfg_burst  low: no protocol matched: a level
  level  status_busy  status_busy  low: no protocol matched: a level
  tie    scan_en = 0  low: debug-like input, tied to 0
  open   dbg_state  low: debug-like output, left open
```

Then finish it by hand:
1. Read the report. Check every `low` line and every `TODO` in the file: a level that is
   really a stream, a tie that should be a port.
2. Fill in `facts()` from the datasheet (see [Facts](#facts-what-the-wrappers-boundary-does)).
3. Set the cosim skeleton's `class` when the module realizes a library class, and run it.
4. Use the wrapper like any child: `dma = new("dma", this, params);`.

The file is yours from then on. Running the importer again never overwrites it; it writes
`dma_engine.svh.new` beside it. See [Importer](../reference/extern.md#importer-fw-hdl-wrap).

## A wrapper is a subclass

Write the class the module realizes first: its ports, its parameter object and, if
there is one, a model body. Then write the wrapper as a subclass that implements
`fw_extern_impl`:

```systemverilog
`include "fw_hdl_macros.svh"

class q extends fw_component_param #(q_param_t) implements fw_runnable;
    fw_port #(fw_get_if #(bit [7:0])) in;
    fw_port #(fw_put_if #(bit [7:0])) out;
    ...                                     // build(); run() is the model
endclass

class q_rtl extends q implements fw_extern_impl;
    `fw_extern_utils("fw_rv_fifo", "../rtl/fw_rv_fifo.sv")
    ...                                     // new()
    virtual function void extern_map(fw_extern_map x);
        x.param("WIDTH", $bits(bit [7:0]));
        x.param("DEPTH", m_params.depth > 2 ? 4 : m_params.depth);  // computed
        x.clock("clk");
        x.reset("rst");
        x.rv(in,  "in",  .data("in_data"), .valid("in_vld"), .ready("in_rdy"));
        x.rv(out, "out", "xls", .data("out_data"));
    endfunction
endclass
```

Because the wrapper is a subclass:
- its ports are the class's ports, so it fits wherever the class does;
- it inherits the class's body, which is its model in a class simulation;
- a library class can be realized by a supplied module the same way: a subclass of
  `fw_arbiter #(bit [7:0], 3)` can wrap your own arbiter RTL.

A structural component then uses the wrapper like any child, in loops and with
computed parameter objects:

```systemverilog
foreach (q[i]) begin
    q_param_t p = new(i + 1);
    q[i] = new($sformatf("q[%0d]", i), this, p);
end
```

## What the elaborator does with it

When Partition elaborates the top, it runs each wrapper's `extern_map()` after
`connect()`. The result is a record per class specialization. Partition then:
1. reads the module's header with the record's parameter values applied, so widths
   written in terms of parameters are known;
2. checks that every module pin is accounted for exactly once: a port's pin, the
   clock or the reset, a tie, or an open output;
3. checks each pin's direction and width against the port it belongs to;
4. derives the block signature from the class's ports and the map.

Nobody writes the signature. Integrate instantiates the module with its parameters,
an inverted reset when the reset is active-low, the ties and the open outputs.

Each error points at the `extern_map()` line that caused it. For example:

```
ext_pkg.sv:61:13: error: q_rtl: port in data: pin 'in_data' of fw_rv_fifo is 9 bits
    with parameters WIDTH=9, DEPTH=1, expected 8
```

A map may depend on the class and its parameter object, but not on the instance (its
name or position). Two instances of one specialization must give the same map; Partition
rejects one that does not.

## Facts: what the wrapper's boundary does

Nothing schedules a wrapped module, so fw-hdl cannot see its latency. The wrapper
says it, in `facts()`:

```systemverilog
virtual function void facts(fw_facts f);
    f.latency(in, out, .fixed(1));
    f.ii(in, 1);
endfunction
```

The latency report then goes through the wrapper, and through any structural
component that holds it. A range (`.min(1), .max(3)`) gives a path a range. Declared
numbers are marked unverified until a measurement agrees. A sidecar file (knob
`design.facts`) gives the same facts for RTL with no wrapper class. See
[Characterization facts](../reference/facts.md).

## Supplied RTL without a wrapper class

The knob `design.extern` still assigns a class to a module with a hand-written block
signature, for RTL that has no SV wrapper. A class may not have both. See
[Knob files](../reference/knobs.md).

The API, the record and every error are in [Wrapped IP](../reference/extern.md).
