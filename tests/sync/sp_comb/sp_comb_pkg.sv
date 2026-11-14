// Classes for the fw_sp_comb weaver test (plan S6.1b): comb fields declared
// on port members, woven into set_comb calls by test_sp_comb.py.
package sp_comb_pkg;
    import fw_hdl_pkg::*;

    typedef logic [7:0] cbyte_t;

    // A port of two channels with its own set_comb (stands in for fw_proto's
    // fw_sp_base): records the spec it was given.
    class two_ch_port;
        fw_rv_sig #(cbyte_t) a, b;
        string got;
        function new();
            a = new("a");
            b = new("b");
        endfunction
        function void set_comb(string spec);
            got = spec;
        endfunction
    endclass

    // o: valid and data comb (ready stays sync); i: none declared.
    class c_comb extends fw_component;
        (* fw_sp_comb = "valid, o.data" *) fw_rv_sp_out #(cbyte_t) o;
        fw_rv_sp_in #(cbyte_t) i;
        (* fw_sp_comb = "a.*,b.valid" *) two_ch_port p;
        function new(string name, fw_component parent);
            super.new(name, parent);
            o = new(null, "o", this);
            i = new(null, "i", this);
            p = new();
        endfunction
    endclass

    // Inherits c_comb's declarations; adds one of its own.
    class c_sub extends c_comb;
        (* fw_sp_comb = "*" *) fw_rv_sp_in #(cbyte_t) j;
        function new(string name, fw_component parent);
            super.new(name, parent);
            j = new(null, "j", this);
        endfunction
    endclass

    // A generic class: one applier per specialization.
    class c_gen #(type T = bit) extends fw_component;
        (* fw_sp_comb = "ready" *) fw_rv_sp_in #(T) g;
        function new(string name, fw_component parent);
            super.new(name, parent);
            g = new(null, "g", this);
        endfunction
    endclass

    // The specialization the weaver sees (one in the tb module alone is not in
    // the woven sources, so it would get no applier).
    typedef c_gen #(logic [3:0]) c_gen4_t;
endpackage
