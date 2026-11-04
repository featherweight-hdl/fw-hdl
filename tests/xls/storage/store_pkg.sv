// Designs for tests/xls/test_storage_binding.py: the same source built with
// its channels bound to flops, a wrapper, an XLS FIFO or a RAM (knob
// `storage:`). The source never names the binding.
package store_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;

    // out = in + K
    class st_add #(int K = 1) extends fw_component implements fw_runnable;
        fw_port #(fw_get_if #(bit [9:0])) in;
        fw_port #(fw_put_if #(bit [9:0])) out;
        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);
        endfunction
        function void build();
            in = new("in", this);
            out = new("out", this);
        endfunction
        virtual task run();
            forever begin
                bit [9:0] x;
                in.t.get(x);
                out.t.put(x + 10'(K));
            end
        endtask
    endclass

    // in -> a -> q (8 deep, the store) -> b -> r (2 deep) -> c -> out
    class st_top extends fw_component;
        fw_port #(fw_get_if #(bit [9:0])) in;
        fw_port #(fw_put_if #(bit [9:0])) out;
        st_add #(1)                 a;
        st_add #(2)                 b;
        st_add #(4)                 c;
        fw_channel #(bit [9:0], 8)  q;
        fw_channel #(bit [9:0], 2)  r;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            in = new("in", this);
            out = new("out", this);
            a = new("a", this);
            b = new("b", this);
            c = new("c", this);
            q = new("q", this);
            r = new("r", this);
        endfunction
        function void connect();
            a.in.connect(in);
            a.out.connect(q.put_ex);
            b.in.connect(q.get_ex);
            b.out.connect(r.put_ex);
            c.in.connect(r.get_ex);
            c.out.connect(out);
        endfunction
    endclass

    // st_top one level down: its channels are sub.q and sub.r.
    class st_outer extends fw_component;
        fw_port #(fw_get_if #(bit [9:0])) in;
        fw_port #(fw_put_if #(bit [9:0])) out;
        st_top sub;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            in = new("in", this);
            out = new("out", this);
            sub = new("sub", this);
        endfunction
        function void connect();
            sub.in.connect(in);
            sub.out.connect(out);
        endfunction
    endclass

    // A table child: its storage is its own state, flops only.
    typedef fw_keyed_table #(bit [3:0], bit [7:0], 4) st_tbl_t;
    class st_tbl_top extends fw_component;
        fw_port #(fw_get_nb_if #(bit [11:0]))  ins;
        fw_port #(fw_put_step_if #(bit [3:0])) ins_rsp;
        fw_port #(fw_get_nb_if #(bit [3:0]))   lkp;
        fw_port #(fw_put_step_if #(bit [10:0])) lkp_rsp;
        fw_port #(fw_get_nb_if #(bit [9:0]))   wr;
        fw_port #(fw_get_nb_if #(bit [1:0]))   rm;
        st_tbl_t tbl;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            ins = new("ins", this);
            ins_rsp = new("ins_rsp", this);
            lkp = new("lkp", this);
            lkp_rsp = new("lkp_rsp", this);
            wr = new("wr", this);
            rm = new("rm", this);
            tbl = new("tbl", this);
        endfunction
        function void connect();
            tbl.ins.connect(ins);
            tbl.ins_rsp.connect(ins_rsp);
            tbl.lkp.connect(lkp);
            tbl.lkp_rsp.connect(lkp_rsp);
            tbl.wr.connect(wr);
            tbl.rm.connect(rm);
        endfunction
    endclass
endpackage
