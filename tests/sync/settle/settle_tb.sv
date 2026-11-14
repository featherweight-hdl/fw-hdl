// Settle scheduler bench (plan S4.3b): a comb chain src -> w1 .. w4 -> sink,
// built in reverse order. Test (a): all woven, 5 evaluations per edge.
// Test (d): w2 is an un-woven class (no table): it falls back, and the
// values match the naive kernel. Test (b): src -> a.i0, a.o0 -> b, b -> a.i1,
// a.o1 -> sink, a false cycle. Test (c): a ring of two c_wires, a true loop:
// waived it settles; with +settle_case_c (unwaived) elaborate is fatal.
// Prints "RESULT <key> <value>" lines.
import fw_hdl_pkg::*;
import fw_std_pkg::*;
import settle_chain_pkg::*;

// Not woven: the same comb() as c_wire, but no table matches it.
class c_wire_nw extends fw_component implements fw_combinational;
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

module settle_tb;
    // Builds the chain, runs `edges` edges; returns the sink's values (one
    // bit per edge) and the comb() calls of the last edge.
    function automatic void chain(string tag, bit nw, bit naive, int edges,
                                  output int unsigned vals,
                                  output int unsigned evals,
                                  output int unsigned n_fb);
        fw_component top  = new(tag, null);
        c_sink       sink = new("sink", top);
        c_wire       w4   = new("w4", top);
        c_wire       w3   = new("w3", top);
        fw_component w2;
        c_wire       w1   = new("w1", top);
        c_src        src  = new("src", top);
        fw_sync_kernel k  = new(tag);
        string err;
        vals = 0;
        if (nw) begin
            c_wire_nw x = new("w2", top);
            x.o.sig.set_comb("valid");
            w1.o.connect(x.i);
            x.o.connect(w3.i);
            w2 = x;
        end else begin
            c_wire x = new("w2", top);
            x.o.sig.set_comb("valid");
            w1.o.connect(x.i);
            x.o.connect(w3.i);
            w2 = x;
        end
        src.o.sig.set_comb("valid");
        w1.o.sig.set_comb("valid");
        w3.o.sig.set_comb("valid");
        w4.o.sig.set_comb("valid");
        src.o.connect(w1.i);
        w3.o.connect(w4.i);
        w4.o.connect(sink.i);
        k.naive = naive;
        k.elaborate(top);
        for (int e = 0; e < edges; e++) begin
            if (k.do_edge(k.doms[0], err)) $fatal(1, "%s: %s", tag, err);
            vals |= sink.i.get_valid() << e;
        end
        evals = k.doms[0].edge_evals;
        n_fb  = k.doms[0].sched.n_fallback;
    endfunction

    // The kinds of the looping groups, "_" for spaces, "," between.
    function automatic string kinds(fw_settle_sched s);
        string r = "";
        foreach (s.grp_kind[g]) begin
            string k = s.grp_kind[g];
            if (k == "once") continue;
            foreach (k[i]) if (k[i] == " ") k[i] = "_";
            r = (r == "") ? k : {r, ",", k};
        end
        return (r == "") ? "none" : r;
    endfunction

    // Test (b).
    function automatic void two(string tag, bit naive, int edges,
                                output int unsigned vals, output string kind);
        fw_component top  = new(tag, null);
        c_src        src  = new("src", top);
        c_two        a    = new("a", top);
        c_wire       b    = new("b", top);
        c_sink       sink = new("sink", top);
        fw_sync_kernel k  = new(tag);
        string err;
        vals = 0;
        src.o.sig.set_comb("valid");
        a.o0.sig.set_comb("valid");
        a.o1.sig.set_comb("valid");
        b.o.sig.set_comb("valid");
        src.o.connect(a.i0);
        a.o0.connect(b.i);
        b.o.connect(a.i1);
        a.o1.connect(sink.i);
        k.naive = naive;
        k.elaborate(top);
        for (int e = 0; e < edges; e++) begin
            if (k.do_edge(k.doms[0], err)) $fatal(1, "%s: %s", tag, err);
            vals |= sink.i.get_valid() << e;
        end
        kind = kinds(k.doms[0].sched);
    endfunction

    // Test (c).
    function automatic void ring(string tag, bit waive, output string kind,
                                 output string waiver);
        fw_component top = new(tag, null);
        c_wire       w1  = new("w1", top);
        c_wire       w2  = new("w2", top);
        fw_sync_kernel k = new(tag);
        string err;
        w1.o.sig.set_comb("valid");
        w2.o.sig.set_comb("valid");
        w1.o.connect(w2.i);
        w2.o.connect(w1.i);
        if (waive) w2.waive_comb_loop("test ring");
        k.elaborate(top);
        if (k.do_edge(k.doms[0], err)) $fatal(1, "%s: %s", tag, err);
        kind = kinds(k.doms[0].sched);
        waiver = "none";
        foreach (k.doms[0].sched.grp_waiver[g])
            if (k.doms[0].sched.grp_waiver[g] != "") waiver = "yes";
    endfunction

    initial begin
        int unsigned v, e, f;
        string       s, w;
        if ($test$plusargs("settle_case_c")) begin
            settle_chain_pkg_woven::__register();
            ring("c_unwaived", 0, s, w);
            $display("RESULT c_unwaived.kind %s", s);
            $finish;
        end
        settle_chain_pkg_woven::__register();
        chain("a",     0, 0, 6, v, e, f);
        $display("RESULT a.vals %0h", v);
        $display("RESULT a.evals %0d", e);
        $display("RESULT a.fallback %0d", f);
        chain("an",    0, 1, 6, v, e, f);
        $display("RESULT a_naive.vals %0h", v);
        $display("RESULT a_naive.evals %0d", e);
        chain("d",     1, 0, 6, v, e, f);
        $display("RESULT d.vals %0h", v);
        $display("RESULT d.fallback %0d", f);
        $display("RESULT d.evals %0d", e);
        chain("dn",    1, 1, 6, v, e, f);
        $display("RESULT d_naive.vals %0h", v);
        two("b", 0, 6, v, s);
        $display("RESULT b.vals %0h", v);
        $display("RESULT b.kind %s", s);
        two("bn", 1, 6, v, s);
        $display("RESULT b_naive.vals %0h", v);
        ring("c", 1, s, w);
        $display("RESULT c.kind %s", s);
        $display("RESULT c.waiver %s", w);
        $finish;
    end
endmodule
