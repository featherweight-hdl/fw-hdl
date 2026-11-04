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
    // f6_rr with a stream output: an all-or-nothing step. Its state is one
    // packed struct, zero at reset (`nxt` is the slot after the last grant).
    // Out not ready: the whole cycle has no effect.
    typedef struct packed {
        bit [3:0]      full;
        bit [3:0][7:0] hold;
        bit [1:0]      nxt;
    } f6_rr_state_t;

    class f6_rr_stall extends fw_atomic_step #(f6_rr_state_t);
        fw_port #(fw_get_nb_if #(bit [7:0]))   in0;
        fw_port #(fw_get_nb_if #(bit [7:0]))   in1;
        fw_port #(fw_get_nb_if #(bit [7:0]))   in2;
        fw_port #(fw_get_nb_if #(bit [7:0]))   in3;
        fw_port #(fw_put_step_if #(bit [9:0])) out;   // {input, data}

        function new(string name, fw_component parent);
            super.new(name, parent);
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
            for (int k = 0; k < 4; k++) begin
                if (!found && s.full[2'(s.nxt + 2'(k))]) begin
                    found = 1'b1;
                    g = 2'(s.nxt + 2'(k));
                end
            end
            if (found) begin
                out.t.put_or_stall({g, s.hold[g]});
                s.full[g] = 1'b0;
                s.nxt = g + 2'd1;
            end
            if (!s.full[0] && in0.t.try_get(x)) begin s.hold[0] = x; s.full[0] = 1'b1; end
            if (!s.full[1] && in1.t.try_get(x)) begin s.hold[1] = x; s.full[1] = 1'b1; end
            if (!s.full[2] && in2.t.try_get(x)) begin s.hold[2] = x; s.full[2] = 1'b1; end
            if (!s.full[3] && in3.t.try_get(x)) begin s.hold[3] = x; s.full[3] = 1'b1; end
        endfunction
    endclass

    // Rejected: put_or_stall in an ordinary step, which cannot stall.
    class f6_bad_stall extends fw_component implements fw_steppable;
        fw_port #(fw_get_nb_if #(bit [7:0]))   in;
        fw_port #(fw_put_step_if #(bit [7:0])) out;

        function new(string name, fw_component parent);
            super.new(name, parent);
            add_steppable(this);
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

    // Two stalling outputs: each value to both, tagged with how many values
    // went before. A value goes to each output as soon as that output is
    // ready, once; the take and the count commit when both have it.
    typedef struct packed { bit [7:0] n; } f6_tee_state_t;
    class f6_tee2 extends fw_atomic_step #(f6_tee_state_t);
        fw_port #(fw_get_nb_if #(bit [7:0]))    in;
        fw_port #(fw_put_step_if #(bit [15:0])) a;
        fw_port #(fw_put_step_if #(bit [15:0])) b;

        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            in = new("in", this);
            a = new("a", this);
            b = new("b", this);
        endfunction

        virtual function void step();
            bit [7:0] x;
            if (in.t.try_get(x)) begin
                a.t.put_or_stall({s.n, x});
                b.t.put_or_stall({s.n, x});
                s.n = s.n + 8'd1;
            end
        endfunction
    endclass
endpackage
