// A composition test design:
//
//   exit_top #(NVC): in -> lk[0] -> c[0] -> ... -> lk[NVC-1] -> c[NVC-1] -> e -> x
//                       -> ka -> out;  cfg -> rc =k,p=> ka
//   credit_link:     in -> tx (vinc: +1, valid-only out, 2 credits)
//                       -> v (fw_valid_channel, 3) -> rx (srx: ^ 8'h5a, returns a credit)
//                       -> out;  rx -> cr (fw_channel, 2) -> tx
//
// v holds credits + 1 values. In XLS RTL a stage's sends complete one by one
// and its receive completes last (tests/xls/test_xls_facts.py), so while rx's
// out is backpressured its credit can leave one value before that value
// leaves v. A receiver whose output never backpressures needs only credits.
//
// lk[] is built in a loop, each link is a nested structural component, the
// links' inner channels are valid-only, e is extern RTL (ext_neg_rtl), and rc
// is a register block (regs_pkg::rk_rc, native) whose registers reach ka
// (kadd: (x + k) ^ p.lo) over level channels.
package exit_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;
    import kinds_pkg::*;
    import mixed_pkg::*;
    import regs_pkg::*;

    // The credit receiver: a stream out, one credit back per value taken.
    class srx extends fw_component implements fw_runnable;
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
                out.t.put(x ^ 8'h5a);
            end
        endtask
    endclass

    class credit_link extends fw_component;
        fw_port #(fw_get_if #(bit [7:0])) in;
        fw_port #(fw_put_if #(bit [7:0])) out;
        vinc                             tx;
        srx                              rx;
        fw_valid_channel #(bit [7:0], 3) v;
        fw_channel #(bit, 2)             cr;
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

    class exit_top #(int NVC = 2) extends fw_component;
        fw_port #(fw_get_if #(bit [47:0])) cfg;
        fw_port #(fw_get_if #(bit [7:0]))  in;
        fw_port #(fw_put_if #(bit [7:0]))  out;
        credit_link                    lk[NVC];
        fw_channel #(bit [7:0], 1)     c[NVC];
        ext_neg                        e;
        fw_channel #(bit [7:0], 1)     x;
        rk_rc                          rc;
        kadd                           ka;
        fw_level_channel #(bit [31:0]) kl;
        fw_level_channel #(pair_t)     pl;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            cfg = new("cfg", this);
            in = new("in", this);
            out = new("out", this);
            for (int i = 0; i < NVC; i++) begin
                lk[i] = new($sformatf("lk[%0d]", i), this);
                c[i] = new($sformatf("c[%0d]", i), this);
            end
            e = new("e", this);
            x = new("x", this);
            rc = new("rc", this);
            ka = new("ka", this);
            kl = new("kl", this);
            pl = new("pl", this);
        endfunction
        function void connect();
            lk[0].in.connect(in);
            for (int i = 0; i < NVC; i++) begin
                lk[i].out.connect(c[i].put_ex);
                if (i + 1 < NVC) lk[i + 1].in.connect(c[i].get_ex);
            end
            e.in.connect(c[NVC - 1].get_ex);
            e.out.connect(x.put_ex);
            ka.in.connect(x.get_ex);
            ka.out.connect(out);
            rc.wr.connect(cfg);
            rc.k.connect(kl.put_ex);
            rc.p.connect(pl.put_ex);
            ka.k.connect(kl.get_ex);
            ka.p.connect(pl.get_ex);
        endfunction
    endclass
    typedef exit_top #(2) exit2_t;
    typedef exit_top #(3) exit3_t;
endpackage
