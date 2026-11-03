// Cycle-step micro-tests: components whose step() is one clock cycle.
`include "fw_std_macros.svh"

package micro_f6_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;

    // A step-form counter: adds what arrives on inc, reports the running total
    // in the cycle it changes.
    class f6_count extends fw_component implements fw_steppable;
        fw_port #(fw_get_nb_if #(bit [7:0]))     inc;
        fw_port #(fw_valid_put_if #(bit [15:0])) out;
        bit [15:0] cnt;

        function new(string name, fw_component parent);
            super.new(name, parent);
            add_steppable(this);
        endfunction
        function void build();
            inc = new("inc", this);
            out = new("out", this);
        endfunction

        virtual function void step();
            bit [7:0] x;
            if (inc.t.try_get(x)) begin
                cnt = cnt + 16'(x);
                out.t.put(cnt);
            end
        endfunction
    endclass

    // A round-robin arbiter, accept-then-arbitrate form: one hold slot per
    // input. Each cycle it grants the first full slot after the last grant,
    // over the slots full at the start of the cycle (a grant never depends on
    // same-cycle valid), then refills every empty slot, including the one
    // just granted. Input k is ready while slot k is empty.
    class f6_rr extends fw_component implements fw_steppable;
        fw_port #(fw_get_nb_if #(bit [7:0]))    in0;
        fw_port #(fw_get_nb_if #(bit [7:0]))    in1;
        fw_port #(fw_get_nb_if #(bit [7:0]))    in2;
        fw_port #(fw_get_nb_if #(bit [7:0]))    in3;
        fw_port #(fw_valid_put_if #(bit [9:0])) out;   // {input, data}
        bit [3:0] full;
        bit [7:0] hold[4];
        bit [1:0] last = 2'd3;

        function new(string name, fw_component parent);
            super.new(name, parent);
            add_steppable(this);
        endfunction
        function void build();
            in0 = new("in0", this);
            in1 = new("in1", this);
            in2 = new("in2", this);
            in3 = new("in3", this);
            out = new("out", this);
        endfunction

        virtual function void step();
            bit       found;
            bit [1:0] g;
            bit [7:0] x;
            for (int k = 1; k <= 4; k++) begin
                if (!found && full[2'(last + 2'(k))]) begin
                    found = 1'b1;
                    g = 2'(last + 2'(k));
                end
            end
            if (found) begin
                out.t.put({g, hold[g]});
                full[g] = 1'b0;
                last = g;
            end
            if (!full[0] && in0.t.try_get(x)) begin hold[0] = x; full[0] = 1'b1; end
            if (!full[1] && in1.t.try_get(x)) begin hold[1] = x; full[1] = 1'b1; end
            if (!full[2] && in2.t.try_get(x)) begin hold[2] = x; full[2] = 1'b1; end
            if (!full[3] && in3.t.try_get(x)) begin hold[3] = x; full[3] = 1'b1; end
        endfunction
    endclass

    // Rejected: a run() and a step() in one component.
    class f6_bad_both extends fw_component implements fw_runnable, fw_steppable;
        fw_port #(fw_get_nb_if #(bit [7:0]))    in;
        fw_port #(fw_valid_put_if #(bit [7:0])) out;

        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);
            add_steppable(this);
        endfunction
        function void build();
            in = new("in", this);
            out = new("out", this);
        endfunction

        virtual task run();
            forever begin
                bit [7:0] x;
                if (in.t.try_get(x))
                    out.t.put(x);
            end
        endtask
        virtual function void step();
            bit [7:0] x;
            if (in.t.try_get(x))
                out.t.put(x);
        endfunction
    endclass
endpackage
