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

    // fw_keyed_table: 8 slots, 4-bit keys, 8-bit values.
    class tbl8_top extends fw_component;
        fw_port #(fw_get_nb_if #(bit [11:0]))   ins;
        fw_port #(fw_put_step_if #(bit [4:0]))  ins_rsp;
        fw_port #(fw_get_nb_if #(bit [3:0]))    lkp;
        fw_port #(fw_put_step_if #(bit [11:0])) lkp_rsp;
        fw_port #(fw_get_nb_if #(bit [10:0]))   wr;
        fw_port #(fw_get_nb_if #(bit [2:0]))    rm;
        fw_keyed_table #(bit [3:0], bit [7:0], 8) t;
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
            t = new("t", this);
        endfunction
        function void connect();
            t.ins.connect(ins);
            t.ins_rsp.connect(ins_rsp);
            t.lkp.connect(lkp);
            t.lkp_rsp.connect(lkp_rsp);
            t.wr.connect(wr);
            t.rm.connect(rm);
        endfunction
    endclass

    // fw_token_pool: 4 tokens, a 4-bit value carried through.
    class pool4_top extends fw_component;
        fw_port #(fw_get_nb_if #(bit [3:0]))    req;
        fw_port #(fw_valid_put_if #(bit [5:0])) tok;
        fw_port #(fw_get_nb_if #(bit [1:0]))    rel;
        fw_token_pool #(4, bit [3:0]) p;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            req = new("req", this);
            tok = new("tok", this);
            rel = new("rel", this);
            p = new("p", this);
        endfunction
        function void connect();
            p.req.connect(req);
            p.tok.connect(tok);
            p.rel.connect(rel);
        endfunction
    endclass

    // fw_slot_reserve: 6 slots, up to 3 a request, a 4-bit value carried.
    class rsv6_top extends fw_component;
        fw_port #(fw_get_nb_if #(bit [5:0]))    rsv;
        fw_port #(fw_valid_put_if #(bit [5:0])) gnt;
        fw_port #(fw_get_nb_if #(bit [1:0]))    rel;
        fw_slot_reserve #(6, 3, bit [3:0]) r;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            rsv = new("rsv", this);
            gnt = new("gnt", this);
            rel = new("rel", this);
            r = new("r", this);
        endfunction
        function void connect();
            r.rsv.connect(rsv);
            r.gnt.connect(gnt);
            r.rel.connect(rel);
        endfunction
    endclass

    // fw_dep_tracker: 4 producer tags, 4 dependent tags.
    class dep4_top extends fw_component;
        fw_port #(fw_get_nb_if #(bit [2:0]))    ent;
        fw_port #(fw_get_nb_if #(bit [1:0]))    ret;
        fw_port #(fw_level_set_if #(bit [3:0])) ok;
        fw_dep_tracker #(4, 4) t;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            ent = new("ent", this);
            ret = new("ret", this);
            ok = new("ok", this);
            t = new("t", this);
        endfunction
        function void connect();
            t.ent.connect(ent);
            t.ret.connect(ret);
            t.ok.connect(ok);
        endfunction
    endclass
endpackage
