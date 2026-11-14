// Synthetic classes for the settle weaver's golden test (plan S4.2), next to
// the S3 classes fw_rv_slice and fw_rv_pass, which syn_top specializes.
package settle_syn_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;

    // comb() through a helper method, on one-field ports.
    class syn_helper extends fw_component implements fw_combinational;
        fw_sig #(bit [3:0]) a, b;
        fw_sig #(bit)       en;

        function new(string name, fw_component parent);
            super.new(name, parent);
            a = new("a");
            b = new("b");
            en = new("en");
            add_comb(this);
        endfunction

        function bit [3:0] next();
            return en.get() ? a.get() + 4'd1 : a.get();
        endfunction

        virtual function void comb();
            b.set(next());
        endfunction
    endclass

    // comb() and step(), parameterized: the table is the union of the
    // specializations, keyed by the generic name.
    class syn_mixed #(int W = 8) extends fw_component
            implements fw_combinational, fw_steppable;
        fw_rv_sp_in  #(logic [W-1:0]) in;
        fw_rv_sp_out #(logic [W-1:0]) out;
        logic [W-1:0] acc;

        function new(string name, fw_component parent);
            super.new(name, parent);
            in  = new(null, "in", this);
            out = new(null, "out", this);
            add_comb(this);
            add_steppable(this);
        endfunction

        virtual function void comb();
            in.set_ready(out.get_ready());
        endfunction

        virtual function void step();
            if (W > 8 && in.get_valid()) acc = in.get_data();
            out.set_valid(1);
            out.set_data(acc);
        endfunction
    endclass

    // A comb() that writes no port field: a warning.
    class syn_nowrite extends fw_component implements fw_combinational;
        fw_rv_sp_in #(logic [7:0]) in;
        logic [7:0] seen;

        function new(string name, fw_component parent);
            super.new(name, parent);
            in = new(null, "in", this);
            add_comb(this);
        endfunction

        virtual function void comb();
            seen = in.get_data();
        endfunction
    endclass

    class syn_top extends fw_component;
        syn_helper  h;
        syn_mixed #(8)  m8;
        syn_mixed #(16) m16;
        syn_nowrite n;
        fw_rv_slice #(logic [7:0]) s;
        fw_rv_pass  #(logic [7:0]) p;

        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
    endclass
endpackage
