// Recognized library classes as children:
//
//   ctop: in -> tx (fw_credit_tx #(bit [7:0], 2), valid-only out) -> v
//            (fw_valid_channel, 3) -> rx (crx: ^ 8'h3c, returns a credit) -> out;
//         rx -> cr (fw_channel, 2) -> tx
//   atop: a, b, c -> arb (fw_arbiter #(bit [7:0], 3), round robin) -> out
//         ({index, value}, 10 bits)
//   ptop: as atop, fixed priority (FW_ARB_PRIO): no xls lowering
//
// v holds credits + 1: rx returns its credit in the activation that sends on
// a backpressured out (docs/methodology/islands.md, Credited links).
package lib_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;

    class crx extends fw_component implements fw_runnable;
        fw_port #(fw_get_if #(bit [7:0])) in;
        fw_port #(fw_put_if #(bit [7:0])) out;
        fw_port #(fw_put_if #(bit))       cr;
        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);
        endfunction
        function void build();
            in = new("in", this);
            out = new("out", this);
            cr = new("cr", this);
        endfunction
        virtual task run();
            forever begin
                bit [7:0] x;
                in.t.get(x);
                cr.t.put(1'b1);
                out.t.put(x ^ 8'h3c);
            end
        endtask
    endclass

    class ctop extends fw_component;
        fw_port #(fw_get_if #(bit [7:0])) in;
        fw_port #(fw_put_if #(bit [7:0])) out;
        fw_credit_tx #(bit [7:0], 2)      tx;
        crx                               rx;
        fw_valid_channel #(bit [7:0], 3)  v;
        fw_channel #(bit, 2)              cr;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            in = new("in", this);
            out = new("out", this);
            tx = new("tx", this);
            rx = new("rx", this);
            v = new("v", this);
            cr = new("cr", this);
        endfunction
        function void connect();
            tx.in.connect(in);
            tx.out.connect(v.put_ex);
            rx.in.connect(v.get_ex);
            rx.out.connect(out);
            rx.cr.connect(cr.put_ex);
            tx.cr.connect(cr.get_ex);
        endfunction
    endclass

    class arb_top #(fw_arb_policy_e POLICY = FW_ARB_RR) extends fw_component;
        fw_port #(fw_get_if #(bit [7:0])) a;
        fw_port #(fw_get_if #(bit [7:0])) b;
        fw_port #(fw_get_if #(bit [7:0])) c;
        fw_port #(fw_put_if #(bit [9:0])) out;
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
    typedef arb_top #(FW_ARB_RR)   atop;
    typedef arb_top #(FW_ARB_PRIO) ptop;
endpackage
