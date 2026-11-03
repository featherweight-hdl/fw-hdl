// fw_arbiter for tests/xls/lib/test_arbiter.py: as a child, with three
// inputs (round robin or fixed priority) and five (a count that is not a
// power of two); and the class itself.
`include "fw_std_macros.svh"

package lib_arb_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;

    class arb3 #(fw_arb_policy_e POLICY = FW_ARB_RR) extends fw_component;
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
    typedef arb3 #(FW_ARB_RR)   arb3_rr;
    typedef arb3 #(FW_ARB_PRIO) arb3_prio;

    class arb5_rr extends fw_component;
        fw_port #(fw_get_nb_if #(bit [5:0])) a, b, c, d, e;
        fw_port #(fw_put_step_if #(bit [8:0])) out;
        fw_arbiter #(bit [5:0], 5, FW_ARB_RR) arb;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            a = new("a", this);
            b = new("b", this);
            c = new("c", this);
            d = new("d", this);
            e = new("e", this);
            out = new("out", this);
            arb = new("arb", this);
        endfunction
        function void connect();
            arb.in[0].connect(a);
            arb.in[1].connect(b);
            arb.in[2].connect(c);
            arb.in[3].connect(d);
            arb.in[4].connect(e);
            arb.out.connect(out);
        endfunction
    endclass

    // The class itself, for the cycle-exact tests.
    typedef fw_arbiter #(bit [7:0], 3, FW_ARB_RR)   arb_3r;
    typedef fw_arbiter #(bit [7:0], 3, FW_ARB_PRIO) arb_3p;
    typedef fw_arbiter #(bit [5:0], 5, FW_ARB_RR)   arb_5r;
    typedef fw_arbiter #(bit [7:0], 1, FW_ARB_RR)   arb_1;
endpackage
