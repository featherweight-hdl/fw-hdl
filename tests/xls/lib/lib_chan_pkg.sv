// fw_channel between two steps, for tests/xls/lib/test_fw_channel.py: a
// producer that passes each value on as it arrives, the channel, and a
// consumer that passes each value on as it is offered. Both are
// all-or-nothing steps, so the channel's depth and the output's
// back-pressure decide every cycle.
`include "fw_std_macros.svh"

package lib_chan_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;

    typedef struct packed { bit unused; } chan_pass_t;

    // Takes a value when out has space; a stall leaves it offered.
    class chan_pass extends fw_atomic_step #(chan_pass_t);
        fw_port #(fw_get_nb_if #(bit [7:0]))   in;
        fw_port #(fw_put_step_if #(bit [7:0])) out;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            in = new("in", this);
            out = new("out", this);
        endfunction
        virtual function void step();
            bit [7:0] x;
            if (in.t.try_get(x))
                out.t.put_or_stall(x);
        endfunction
    endclass

    class chan_top #(int D = 1) extends fw_component;
        fw_port #(fw_get_nb_if #(bit [7:0]))   a;
        fw_port #(fw_put_step_if #(bit [7:0])) out;
        chan_pass src, snk;
        fw_channel #(bit [7:0], D) ch;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            a = new("a", this);
            out = new("out", this);
            src = new("src", this);
            snk = new("snk", this);
            ch = new("ch", this);
        endfunction
        function void connect();
            src.in.connect(a);
            src.out.connect(ch.put_step_ex);
            snk.in.connect(ch.get_nb_ex);
            snk.out.connect(out);
        endfunction
    endclass
    typedef chan_top #(0) chan_d0;
    typedef chan_top #(1) chan_d1;
    typedef chan_top #(2) chan_d2;
    typedef chan_top #(3) chan_d3;
endpackage
