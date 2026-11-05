// Wrapped IP: existing Verilog modules behind classes (fw_extern.svh).
//
//   ext_q      a queue: out gives in's values in order. Its class body is the
//              model; ext_q_rtl wraps src/rtl/fw_rv_fifo.sv, its depth computed
//              from the parameter object.
//   arb3_rtl   fw_arbiter #(bit [7:0], 3) realized by a supplied module with
//              other pin names and an active-low reset (ref_arb3.sv).
//
//   ext_top #(N): in -> q[0] -> c[0] -> ... -> q[N-1] -> c[N-1] -> x (add_k #(3), XLS) -> out
//   arb_top:      a/b/c -> q[i] -> ch[i] -> arb -> out
`include "fw_hdl_macros.svh"

package ext_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;
    import hier_pkg::*;

    class ext_q_param_t;
        int unsigned depth;
        function new(int unsigned depth = 1);
            this.depth = depth;
        endfunction
    endclass

    class ext_q extends fw_component_param #(ext_q_param_t) implements fw_runnable;
        typedef ext_q_param_t param_t;
        fw_port #(fw_get_if #(bit [7:0])) in;
        fw_port #(fw_put_if #(bit [7:0])) out;
        function new(string name, fw_component parent, param_t params = null);
            super.new(name, parent, params);
            add_runnable(this);
        endfunction
        function void build();
            in = new("in", this);
            out = new("out", this);
        endfunction
        virtual task run();
            forever begin
                bit [7:0] x;
                in.t.get(x);
                out.t.put(x);
            end
        endtask
    endclass

    class ext_q_rtl extends ext_q implements fw_extern_impl;
        `fw_extern_utils("fw_rv_fifo", "../../../src/rtl/fw_rv_fifo.sv")
        function new(string name, fw_component parent, param_t params = null);
            super.new(name, parent, params);
        endfunction
        virtual function void extern_map(fw_extern_map x);
            x.param("WIDTH", $bits(bit [7:0]));
            x.param("DEPTH", m_params.depth > 2 ? 4 : m_params.depth);   // computed
            x.clock("clk");
            x.reset("rst");
            x.rv(in, "in", .data("in_data"), .valid("in_vld"), .ready("in_rdy"));
            x.rv(out, "out", "xls", .data("out_data"));
        endfunction
    endclass

    class arb3_rtl extends fw_arbiter #(bit [7:0], 3) implements fw_extern_impl;
        `fw_extern_utils("ref_arb3", "../../stdlib/cosim/ref_arb3.sv")
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        virtual function void extern_map(fw_extern_map x);
            x.param("LOCK", 1);
            x.clock("clk_i");
            x.reset("rst_ni", 1);
            foreach (in[i])
                x.rv(in[i], $sformatf("req%0d", i), .data($sformatf("req%0d_data", i)));
            x.rv(out, "gnt", .data("gnt_data"));
        endfunction
    endclass

    class ext_top #(int N = 3) extends fw_component;
        fw_port #(fw_get_if #(bit [7:0])) in;
        fw_port #(fw_put_if #(bit [7:0])) out;
        ext_q_rtl                  q[N];
        fw_channel #(bit [7:0], 1) c[N];
        add_k #(3)                 x;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            in = new("in", this);
            out = new("out", this);
            foreach (q[i]) begin
                ext_q_param_t p = new(i + 1);
                q[i] = new($sformatf("q[%0d]", i), this, p);
            end
            foreach (c[i]) c[i] = new($sformatf("c[%0d]", i), this);
            x = new("x", this);
        endfunction
        function void connect();
            q[0].in.connect(in);
            for (int i = 0; i < N; i++) begin
                q[i].out.connect(c[i].put_ex);
                if (i + 1 < N) q[i + 1].in.connect(c[i].get_ex);
            end
            x.in.connect(c[N - 1].get_ex);
            x.out.connect(out);
        endfunction
    endclass
    typedef ext_top #(1) ext_top1_t;
    typedef ext_top #(3) ext_top3_t;

    class arb_top extends fw_component;
        fw_port #(fw_get_if #(bit [7:0])) a, b, c;
        fw_port #(fw_put_step_if #(bit [9:0])) out;
        ext_q_rtl                  q[3];
        fw_channel #(bit [7:0], 1) ch[3];
        arb3_rtl                   arb;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            a = new("a", this);
            b = new("b", this);
            c = new("c", this);
            out = new("out", this);
            foreach (q[i]) begin
                ext_q_param_t p = new(2);
                q[i] = new($sformatf("q[%0d]", i), this, p);
            end
            foreach (ch[i]) ch[i] = new($sformatf("ch[%0d]", i), this);
            arb = new("arb", this);
        endfunction
        function void connect();
            q[0].in.connect(a);
            q[1].in.connect(b);
            q[2].in.connect(c);
            foreach (q[i]) begin
                q[i].out.connect(ch[i].put_ex);
                arb.in[i].connect(ch[i].get_nb_ex);
            end
            arb.out.connect(out);
        endfunction
    endclass
endpackage
