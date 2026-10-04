# fw-hdl

fw-hdl (Featherweight HDL) is a way of writing hardware in ordinary SystemVerilog
classes. A design is a tree of **components** that talk through typed **ports** and
**exports**. The same source is:

* a fast transaction-level **model**, run on any SystemVerilog simulator;
* the input to **synthesis**: its static subset compiles, through XLS, to RTL;
* the thing your **tests** call, through an API generated from it, at every level from
  the model down to a gate-level netlist.

```systemverilog
class blinky extends fw_component implements fw_runnable;
    fw_port #(fw_put_if #(led_t)) out;

    function new(string name, fw_component parent);
        super.new(name, parent);
        add_runnable(this);
    endfunction

    function void build();
        out = new("out", this);
    endfunction

    virtual task run();
        led_t v = 1'b0;
        forever begin
            out.t.put(v);
            tick(BLINK_TICKS);
            v = ~v;
        end
    endtask
endclass
```

Start with {doc}`methodology/index`. The {doc}`examples/xls/index` take real designs
from the XLS repository through every step, from SV source to gates. The
{doc}`reference/index` is generated from the SystemVerilog source and from the
dv-flow task definitions.

```{toctree}
:maxdepth: 2
:caption: Contents

methodology/index
examples/xls/index
reference/index
```
