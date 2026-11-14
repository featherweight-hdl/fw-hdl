// S2.4: the sync kernel. Each test builds a small tree of components, runs
// fw_sync_kernel.elaborate() (freeze, connection check, sort into domains)
// and calls do_edge() by hand: the tree is unclocked, so there is one domain
// and no process. The last test runs a clocked root (fw_root) instead. SVUnit can't catch $fatal, so the error paths are tested
// through do_edge()'s return and fatal_on_rule = 0.
`include "svunit_defines.svh"
import fw_hdl_pkg::*;

typedef bit [7:0] kbyte_t;

// Holds comb `o.valid` at r; step() toggles r.
class k_src extends fw_component implements fw_combinational, fw_steppable;
    fw_rv_sp_out #(kbyte_t) o;
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
class k_wire extends fw_component implements fw_combinational;
    fw_rv_sp_in #(kbyte_t)  i;
    fw_rv_sp_out #(kbyte_t) o;
    function new(string name, fw_component parent);
        super.new(name, parent);
        i = new(null, "i", this);
        o = new(null, "o", this);
        add_comb(this);
    endfunction
    virtual function void comb(); o.set_valid(i.get_valid()); endfunction
endclass

// comb(): o.valid = !i.valid; with o connected to i, it never settles.
class k_inv extends k_wire;
    function new(string name, fw_component parent);
        super.new(name, parent);
    endfunction
    virtual function void comb(); o.set_valid(!i.get_valid()); endfunction
endclass

// A register stage: step() copies i to o (sync) and holds i.ready at 1.
class k_reg extends fw_component implements fw_steppable;
    fw_rv_sp_in #(kbyte_t)  i;
    fw_rv_sp_out #(kbyte_t) o;
    function new(string name, fw_component parent);
        super.new(name, parent);
        i = new(null, "i", this);
        o = new(null, "o", this);
        add_steppable(this);
    endfunction
    virtual function void step();
        o.set_valid(i.get_valid());
        o.set_data(i.get_data());
        i.set_ready(1);
    endfunction
endclass

// Breaks both write rules: comb() writes sync `data`, step() comb `valid`.
class k_bad extends fw_component implements fw_combinational, fw_steppable;
    fw_rv_sp_out #(kbyte_t) o;
    function new(string name, fw_component parent);
        super.new(name, parent);
        o = new(null, "o", this);
        add_comb(this);
        add_steppable(this);
    endfunction
    virtual function void comb(); o.set_data(8'h11); endfunction
    virtual function void step(); o.set_valid(1);    endfunction
endclass

class k_out extends fw_component;
    fw_rv_sp_out #(kbyte_t) o;
    function new(string name, fw_component parent);
        super.new(name, parent);
        o = new(null, "o", this);
    endfunction
endclass

class k_sink extends fw_component;
    fw_rv_sp_in #(kbyte_t) i;
    function new(string name, fw_component parent);
        super.new(name, parent);
        i = new(null, "i", this);
    endfunction
endclass

// S2.4b, on a clocked root. step() counts edges into o.data.
class k_cnt extends fw_component implements fw_steppable;
    fw_rv_sp_out #(kbyte_t) o;
    kbyte_t n;
    function new(string name, fw_component parent);
        super.new(name, parent);
        o = new(null, "o", this);
        add_steppable(this);
    endfunction
    virtual function void step(); n++; o.set_data(n); endfunction
endclass

// step() and run() both log i.data at each edge; run() also forwards it
// to o (a sync write from run()).
class k_mix extends fw_component implements fw_steppable, fw_runnable;
    fw_rv_sp_in #(kbyte_t)  i;
    fw_rv_sp_out #(kbyte_t) o;
    kbyte_t stp[$], rn[$];
    function new(string name, fw_component parent);
        super.new(name, parent);
        i = new(null, "i", this);
        o = new(null, "o", this);
        add_steppable(this);
        add_runnable(this);
    endfunction
    virtual function void step(); stp.push_back(i.get_data()); endfunction
    virtual task run();
        forever begin
            clock.get_if().tick(1);
            rn.push_back(i.get_data());
            o.set_data(i.get_data());
        end
    endtask
endclass

// step() logs i.data at each edge.
class k_log extends fw_component implements fw_steppable;
    fw_rv_sp_in #(kbyte_t) i;
    kbyte_t got[$];
    function new(string name, fw_component parent);
        super.new(name, parent);
        i = new(null, "i", this);
        add_steppable(this);
    endfunction
    virtual function void step(); got.push_back(i.get_data()); endfunction
endclass

// cnt -> mix -> lg; drv (written by the test module) -> lg2.
class k_root extends fw_component_root #(fw_component);
    k_cnt cnt;
    k_mix mix;
    k_log lg, lg2;
    k_out drv;
    function new(string name);
        super.new(name);
    endfunction
    virtual function void build();
        cnt = new("cnt", this);
        mix = new("mix", this);
        lg  = new("lg", this);
        drv = new("drv", this);
        lg2 = new("lg2", this);
    endfunction
    virtual function void connect();
        cnt.o.connect(mix.i);
        mix.o.connect(lg.i);
        drv.o.connect(lg2.i);
    endfunction
endclass

module fw_sync_kernel_unit_test;
    import svunit_pkg::svunit_testcase;
    import fw_hdl_pkg::*;

    string name = "fw_sync_kernel_ut";

    // The clocked root of the last test; idle until clk_rst falls.
    logic clk = 0, clk_rst = 0;
    fw_root #(.Tbind(k_root)) u_root (.clock(clk), .reset(clk_rst));
    svunit_testcase svunit_ut;

    function void build();
        svunit_ut = new(name);
    endfunction
    task setup();
        svunit_ut.setup();
        fw_sig_holder::phase = FW_SYNC_PH_NONE;
        fw_sig_holder::fatal_on_rule = 1;
        fw_sig_holder::rule_errs = 0;
    endtask
    task teardown();
        fw_sig_holder::phase = FW_SYNC_PH_NONE;
        fw_sig_holder::fatal_on_rule = 1;
        svunit_ut.teardown();
    endtask

    `SVUNIT_TESTS_BEGIN

    // src -> a -> b -> sink, all comb valid; the comb()s are listed b, a,
    // src (creation order), so settling takes several passes.
    `SVTEST(comb_chain_settles_in_one_edge)
        fw_component top  = new("top", null);
        k_wire       b    = new("b", top);
        k_wire       a    = new("a", top);
        k_src        src  = new("src", top);
        k_sink       sink = new("sink", top);
        fw_sync_kernel k  = new("top");
        string err;
        bit    e;
        src.o.sig.set_comb("valid");
        a.o.sig.set_comb("valid");
        b.o.sig.set_comb("valid");
        src.o.connect(a.i);
        a.o.connect(b.i);
        b.o.connect(sink.i);
        k.elaborate(top);
        `FAIL_UNLESS_EQUAL(k.active, 1)
        `FAIL_UNLESS_EQUAL(k.doms.size(), 1)
        `FAIL_UNLESS_EQUAL(k.doms[0].combs.size(), 3)
        `FAIL_UNLESS_EQUAL(k.doms[0].holders.size(), 3)
        `FAIL_UNLESS_EQUAL(src.o.sig.frozen, 1)
        e = k.do_edge(k.doms[0], err);
        `FAIL_UNLESS_EQUAL(e, 0)
        `FAIL_UNLESS_EQUAL(sink.i.get_valid(), 1)
        `FAIL_UNLESS_EQUAL(src.r, 0)
        e = k.do_edge(k.doms[0], err);
        `FAIL_UNLESS_EQUAL(e, 0)
        `FAIL_UNLESS_EQUAL(sink.i.get_valid(), 0)
    `SVTEST_END

    // src -> s1 -> s2 -> s3 -> sink, all sync. The value reaches s1 at edge
    // 1 and the sink at edge 4: a latency of exactly 3.
    `SVTEST(sync_pipeline_latency_3)
        fw_component top  = new("top", null);
        k_out        src  = new("src", top);
        k_reg        s1   = new("s1", top);
        k_reg        s2   = new("s2", top);
        k_reg        s3   = new("s3", top);
        k_sink       sink = new("sink", top);
        fw_sync_kernel k  = new("top");
        string err;
        bit    e;
        src.o.connect(s1.i);
        s1.o.connect(s2.i);
        s2.o.connect(s3.i);
        s3.o.connect(sink.i);
        k.elaborate(top);
        `FAIL_UNLESS_EQUAL(k.doms[0].steps.size(), 3)
        src.o.set_valid(1);
        src.o.set_data(8'h42);
        for (int n = 1; n <= 4; n++) begin
            e = k.do_edge(k.doms[0], err);
            `FAIL_UNLESS_EQUAL(e, 0)
            if (n == 1) begin
                `FAIL_UNLESS_EQUAL(s1.i.get_valid(), 1)
            end
            `FAIL_UNLESS_EQUAL(sink.i.get_valid(), (n == 4))
        end
        `FAIL_UNLESS_EQUAL(sink.i.get_data(), 8'h42)
        `FAIL_UNLESS_EQUAL(src.o.get_ready(), 1)
    `SVTEST_END

    `SVTEST(forbidden_writes_detected)
        fw_component top  = new("top", null);
        k_bad        bad  = new("bad", top);
        k_sink       sink = new("sink", top);
        fw_sync_kernel k  = new("top");
        string err, exp_comb, exp_step;
        bit    e;
        bad.o.sig.set_comb("valid");
        bad.o.connect(sink.i);
        k.elaborate(top);
        fw_sig_holder::fatal_on_rule = 0;
        exp_comb = "sync field \"data\" of \"o\" written from comb()";
        exp_step = "comb field \"valid\" of \"o\" written from step()";
        e = k.do_edge(k.doms[0], err);
        `FAIL_UNLESS_EQUAL(e, 0)
        `FAIL_UNLESS_EQUAL(fw_sig_holder::rule_errs, 2)
        `FAIL_UNLESS_STR_EQUAL(fw_sig_holder::rule_err, exp_step)
        // comb() alone, through settle: the sync write is the error.
        fw_sig_holder::rule_errs = 0;
        e = k.settle(k.doms[0], err);
        `FAIL_UNLESS_EQUAL(fw_sig_holder::rule_errs, 1)
        `FAIL_UNLESS_STR_EQUAL(fw_sig_holder::rule_err, exp_comb)
        `FAIL_UNLESS_EQUAL(fw_sig_holder::phase, FW_SYNC_PH_NONE)
    `SVTEST_END

    `SVTEST(comb_loop_named_error)
        fw_component top = new("top", null);
        k_inv        a   = new("a", top);
        fw_sync_kernel k = new("top");
        string err, exp;
        bit    e;
        a.o.sig.set_comb("valid");
        a.o.connect(a.i);
        k.elaborate(top);
        e = k.do_edge(k.doms[0], err);
        exp = "comb() did not settle in 64 passes (a comb loop?); still changing: top.a";
        `FAIL_UNLESS_EQUAL(e, 1)
        `FAIL_UNLESS_STR_EQUAL(err, exp)
    `SVTEST_END

    // A run() resumes after the kernel's do_edge() at its edge, so it reads
    // what that edge's step() reads, and its sync write lands at the next
    // edge. A write from a process that ran before the kernel at an edge
    // (here the test, right after the rising clock) lands after that edge.
    `SVTEST(clocked_root_run_and_step)
        k_root r;
        int    n;
        clk_rst = 1;
        #1;
        repeat (2) begin clk = 1; #5; clk = 0; #5; end
        clk_rst = 0;
        repeat (10) begin
            clk = 1;
            r = u_root.root;
            if (r != null && r.elaborated)
                r.drv.o.set_data(kbyte_t'(100 + r.lg2.got.size()));
            #5;
            clk = 0;
            #5;
        end
        `FAIL_UNLESS(r != null)
        `FAIL_UNLESS(r.m_kernel.active)
        n = r.mix.stp.size();
        `FAIL_UNLESS(n >= 8)
        `FAIL_UNLESS_EQUAL(r.mix.rn.size(), n)
        for (int k = 0; k < n; k++) begin
            `FAIL_UNLESS_EQUAL(r.mix.stp[k], k)
            `FAIL_UNLESS_EQUAL(r.mix.rn[k], k)
            `FAIL_UNLESS_EQUAL(r.lg.got[k], (k == 0) ? 0 : k - 1)
            `FAIL_UNLESS_EQUAL(r.lg2.got[k], (k == 0) ? 0 : 99 + k)
        end
        clk_rst = 1;
        #1;
        fw_sync_kernel::m_live = 0;
    `SVTEST_END

    `SVUNIT_TESTS_END
endmodule
