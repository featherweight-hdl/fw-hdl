// A register-block child (RQ-F2 native, Q7 (a)):
//
//   rtop: cfg -> rc (rk_rc: a register block, writes in) =k,p=> ka -> out
//                                 in -> ka (kadd: out = (in + k) ^ p.lo) -> out
//
// rc's registers reach ka over two level channels: k, a plain word, and p, a
// struct of two fields. Software writes come in on the stream `cfg` as
// {addr, data}.
package regs_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;

    typedef struct packed {
        bit [15:0] hi;
        bit [15:0] lo;
    } pair_t;

    class rk_regs extends fw_reg_block #(32);
        fw_reg #(bit [31:0]) k;     // 0x0
        fw_reg #(pair_t)     p;     // 0x4
        function new(string name);
            super.new(name);
            k = new("k", this, .reset(32'd3));
            p = new("p", this, .reset('{hi: 16'h0, lo: 16'h11}));
        endfunction
    endclass

    class rk_rc extends fw_reg_component #(rk_regs);
        fw_port #(fw_level_set_if #(bit [31:0])) k;
        fw_port #(fw_level_set_if #(pair_t))     p;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        virtual function void build();
            super.build();
            k = new("k", this);
            p = new("p", this);
        endfunction
        function void connect();
            drive(fw_reg_level #(bit [31:0])::make(blk.k, k));
            drive(fw_reg_level #(pair_t)::make(blk.p, p));
        endfunction
    endclass

    class kadd extends fw_component implements fw_runnable;
        fw_port #(fw_get_if #(bit [7:0]))   in;
        fw_port #(fw_put_if #(bit [7:0]))   out;
        fw_port #(fw_level_if #(bit [31:0])) k;
        fw_port #(fw_level_if #(pair_t))     p;
        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);
        endfunction
        function void build();
            in = new("in", this);
            out = new("out", this);
            k = new("k", this);
            p = new("p", this);
        endfunction
        virtual task run();
            forever begin
                bit [7:0] x;
                bit [31:0] kv;
                pair_t pv;
                in.t.get(x);
                kv = k.t.get();
                pv = p.t.get();
                out.t.put((x + kv[7:0]) ^ pv.lo[7:0]);
            end
        endtask
    endclass

    class rtop extends fw_component;
        fw_port #(fw_get_if #(bit [47:0])) cfg;
        fw_port #(fw_get_if #(bit [7:0]))  in;
        fw_port #(fw_put_if #(bit [7:0]))  out;
        rk_rc                              rc;
        kadd                               ka;
        fw_level_channel #(bit [31:0])     kl;
        fw_level_channel #(pair_t)         pl;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            cfg = new("cfg", this);
            in = new("in", this);
            out = new("out", this);
            rc = new("rc", this);
            ka = new("ka", this);
            kl = new("kl", this);
            pl = new("pl", this);
        endfunction
        function void connect();
            rc.wr.connect(cfg);
            rc.k.connect(kl.put_ex);
            rc.p.connect(pl.put_ex);
            ka.k.connect(kl.get_ex);
            ka.p.connect(pl.get_ex);
            ka.in.connect(in);
            ka.out.connect(out);
        endfunction
    endclass
endpackage
