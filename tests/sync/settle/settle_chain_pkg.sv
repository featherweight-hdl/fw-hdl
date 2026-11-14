// Classes for the settle scheduler tests (plan S4.3b): woven by the settle
// weaver in test_settle_sched.py, so their comb()s have settle tables.
package settle_chain_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;

    typedef logic [7:0] cbyte_t;

    // comb(): o.valid = r; step() toggles r.
    class c_src extends fw_component implements fw_combinational, fw_steppable;
        fw_rv_sp_out #(cbyte_t) o;
        bit r = 1;
        function new(string name, fw_component parent);
            super.new(name, parent);
            o = new(null, "o", this);
            add_comb(this);
            add_steppable(this);
        endfunction
        virtual function void comb(); o.set_valid(r); endfunction
        virtual function void step(); r = !r;         endfunction
    endclass

    // comb(): o.valid = i.valid.
    class c_wire extends fw_component implements fw_combinational;
        fw_rv_sp_in  #(cbyte_t) i;
        fw_rv_sp_out #(cbyte_t) o;
        function new(string name, fw_component parent);
            super.new(name, parent);
            i = new(null, "i", this);
            o = new(null, "o", this);
            add_comb(this);
        endfunction
        virtual function void comb(); o.set_valid(i.get_valid()); endfunction
    endclass

    // Two independent paths through one comb(): o0.valid = i0.valid,
    // o1.valid = i1.valid (test (b): a false cycle through a c_wire).
    class c_two extends fw_component implements fw_combinational;
        fw_rv_sp_in  #(cbyte_t) i0, i1;
        fw_rv_sp_out #(cbyte_t) o0, o1;
        function new(string name, fw_component parent);
            super.new(name, parent);
            i0 = new(null, "i0", this);
            i1 = new(null, "i1", this);
            o0 = new(null, "o0", this);
            o1 = new(null, "o1", this);
            add_comb(this);
        endfunction
        virtual function void comb();
            o0.set_valid(i0.get_valid());
            o1.set_valid(i1.get_valid());
        endfunction
    endclass

    class c_sink extends fw_component;
        fw_rv_sp_in #(cbyte_t) i;
        function new(string name, fw_component parent);
            super.new(name, parent);
            i = new(null, "i", this);
        endfunction
    endclass
endpackage
