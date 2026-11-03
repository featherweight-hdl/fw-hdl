// Components that wrap a library class with plain ports, so that fw-hdl's own
// lowering of the class is a module the cosim specs in this directory can map.
`include "fw_std_macros.svh"

package cosim_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;

    // fw_arbiter, three 8-bit inputs, round robin or fixed priority.
    class arb3_top #(fw_arb_policy_e POLICY = FW_ARB_RR) extends fw_component;
        fw_port #(fw_get_nb_if #(bit [7:0])) a, b, c;
        fw_port #(fw_put_step_if #(bit [9:0])) out;
        fw_arbiter #(bit [7:0], 3, POLICY) arb;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            a = new("a", this);
            b = new("b", this);
            c = new("c", this);
            out = new("out", this);
            arb = new("arb", this);
        endfunction
        function void connect();
            arb.in[0].connect(a);
            arb.in[1].connect(b);
            arb.in[2].connect(c);
            arb.out.connect(out);
        endfunction
    endclass
    typedef arb3_top #(FW_ARB_RR)   arb3_rr_top;
    typedef arb3_top #(FW_ARB_PRIO) arb3_prio_top;

    // fw_credit_tx, three VCs: 6 credits, one reserved per VC, pool first.
    class ctx3_top extends fw_component;
        fw_port #(fw_get_nb_if #(bit [7:0]))     a, b, c;
        fw_port #(fw_get_nb_if #(bit [1:0]))     cr;
        fw_port #(fw_valid_put_if #(bit [9:0]))  out;
        fw_credit_tx #(bit [7:0], 6, 3, 1, FW_CREDIT_POOL_FIRST, 1) tx;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            a = new("a", this);
            b = new("b", this);
            c = new("c", this);
            cr = new("cr", this);
            out = new("out", this);
            tx = new("tx", this);
        endfunction
        function void connect();
            tx.in[0].connect(a);
            tx.in[1].connect(b);
            tx.in[2].connect(c);
            tx.cr.connect(cr);
            tx.out.connect(out);
        endfunction
    endclass

    // fw_credit_tx, one VC: 8 credits, four per value.
    class ctx1_top extends fw_component;
        fw_port #(fw_get_nb_if #(bit [7:0]))     a;
        fw_port #(fw_get_nb_if #(bit [0:0]))     cr;
        fw_port #(fw_valid_put_if #(bit [8:0]))  out;
        fw_credit_tx #(bit [7:0], 8, 1, 0, FW_CREDIT_POOL_FIRST, 4) tx;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            a = new("a", this);
            cr = new("cr", this);
            out = new("out", this);
            tx = new("tx", this);
        endfunction
        function void connect();
            tx.in[0].connect(a);
            tx.cr.connect(cr);
            tx.out.connect(out);
        endfunction
    endclass
endpackage
