// Characterization facts (fw_facts.svh) on wrapped IP, for the latency report.
//
//   q_fix   ext_q_rtl declaring in -> out in exactly 1 cycle (fw_rv_fifo's)
//   q_rng   ext_q_rtl declaring 1..3 cycles (true, but loose)
//   q_side  ext_q_rtl with no facts() (a sidecar file gives them)
//   pair    structural: in -> q (q_fix) -> c -> x (add_k #(3), XLS) -> out
//
//   fix_top: in -> s (pair) -> c -> q (q_fix) -> out     every hop fixed
//   rng_top: in -> s (pair) -> c -> q (q_rng) -> out     a range
`include "fw_hdl_macros.svh"

package fact_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;
    import hier_pkg::*;
    import ext_pkg::*;

    class q_fix extends ext_q_rtl;
        function new(string name, fw_component parent, param_t params = null);
            super.new(name, parent, params);
        endfunction
        virtual function void facts(fw_facts f);
            f.latency(in, out, .fixed(1));
            f.ii(in, 1);
            f.capacity(in, out, 1);
        endfunction
    endclass

    class q_rng extends ext_q_rtl;
        function new(string name, fw_component parent, param_t params = null);
            super.new(name, parent, params);
        endfunction
        virtual function void facts(fw_facts f);
            f.latency(in, out, .min(1), .max(3));
            f.area(120, "cells", "estimate");
        endfunction
    endclass

    class q_side extends ext_q_rtl;
        function new(string name, fw_component parent, param_t params = null);
            super.new(name, parent, params);
        endfunction
    endclass

    // Negative cases: facts() errors point at the call.
    class q_null extends ext_q_rtl;
        function new(string name, fw_component parent, param_t params = null);
            super.new(name, parent, params);
        endfunction
        virtual function void facts(fw_facts f);
            f.latency(in, null, .fixed(1));
        endfunction
    endclass

    class q_order extends ext_q_rtl;
        function new(string name, fw_component parent, param_t params = null);
            super.new(name, parent, params);
        endfunction
        virtual function void facts(fw_facts f);
            f.latency(in, out, .min(3), .max(1));
        endfunction
    endclass

    class pair extends fw_component;
        fw_port #(fw_get_if #(bit [7:0])) in;
        fw_port #(fw_put_if #(bit [7:0])) out;
        q_fix                      q;
        fw_channel #(bit [7:0], 1) c;
        add_k #(3)                 x;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            ext_q_param_t p = new(1);
            in = new("in", this);
            out = new("out", this);
            q = new("q", this, p);
            c = new("c", this);
            x = new("x", this);
        endfunction
        function void connect();
            q.in.connect(in);
            q.out.connect(c.put_ex);
            x.in.connect(c.get_ex);
            x.out.connect(out);
        endfunction
    endclass

    class fact_top #(type Q = q_fix) extends fw_component;
        fw_port #(fw_get_if #(bit [7:0])) in;
        fw_port #(fw_put_if #(bit [7:0])) out;
        pair                       s;
        fw_channel #(bit [7:0], 1) c;
        Q                          q;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            ext_q_param_t p = new(1);
            in = new("in", this);
            out = new("out", this);
            s = new("s", this);
            c = new("c", this);
            q = new("q", this, p);
        endfunction
        function void connect();
            s.in.connect(in);
            s.out.connect(c.put_ex);
            q.in.connect(c.get_ex);
            q.out.connect(out);
        endfunction
    endclass
    typedef fact_top #(q_fix)   fix_top;
    typedef fact_top #(q_rng)   rng_top;
    typedef fact_top #(q_side)  side_top;
    typedef fact_top #(q_null)  null_top;
    typedef fact_top #(q_order) order_top;
endpackage
