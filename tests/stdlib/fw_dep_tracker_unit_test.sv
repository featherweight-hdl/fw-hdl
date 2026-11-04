// fw_dep_tracker (src/std/dep/fw_dep_tracker.svh), 4 producer tags and 4
// dependent tags: the per-cycle rules in the class header, one edge at a
// time.
//
// ent and ret have sources that offer their queued values in order; ok has
// a sink that keeps the latest value. Contract: fw_dep_check, told of each
// entry and retire as it is taken and of each release as ok shows it, so a
// dependent released before its producer retires is an error.
`include "svunit_defines.svh"
`include "fw_hdl_macros.svh"

package fw_dep_tracker_ut_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;
    import fw_order_pkg::*;

    typedef class dt_top;

    // Each producer entry is a new instance for the checker.
    class dt_src #(type T = int) implements fw_get_nb_if #(T);
        T      q[$];
        bit    is_ret;
        dt_top top;
        virtual task get(output T t);
            wait (q.size() > 0);
            void'(try_get(t));
        endtask
        virtual function bit try_get(inout T t);
            if (q.size() == 0)
                return 1'b0;
            t = q.pop_front();
            if (is_ret)
                top.on_ret(int'(t));
            else
                top.on_ent(int'(t));
            return 1'b1;
        endfunction
    endclass

    class dt_ok implements fw_level_set_if #(bit [3:0]);
        bit [3:0] v;
        dt_top    top;
        virtual function void set(input bit [3:0] t);
            for (int d = 0; d < 4; d++)
                if (t[d] && !v[d])
                    top.on_release(d);
            v = t;
        endfunction
    endclass

    class dt_top extends fw_component;
        fw_dep_tracker #(4, 4) t;
        fw_dep_check chk;
        dt_src #(bit [2:0]) s_ent = new;
        dt_src #(bit [1:0]) s_ret = new;
        dt_ok               o_ok = new;
        bit [3:0] live;
        longint   pinst[4];          // producer tag -> checker instance
        longint   dinst[4];          // dependent tag -> checker instance
        longint   n_inst;
        fw_export #(fw_get_nb_if #(bit [2:0]))    e_ent;
        fw_export #(fw_get_nb_if #(bit [1:0]))    e_ret;
        fw_export #(fw_level_set_if #(bit [3:0])) e_ok;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            t = new("t", this);
            s_ret.is_ret = 1;
            s_ent.top = this;
            s_ret.top = this;
            o_ok.top = this;
            o_ok.v = '1;
            e_ent = new("e_ent", this, s_ent);
            e_ret = new("e_ret", this, s_ret);
            e_ok = new("e_ok", this, o_ok);
        endfunction
        function void connect();
            t.ent.connect(e_ent);
            t.ret.connect(e_ret);
            t.ok.connect(e_ok);
        endfunction
        function void on_ent(int e);
            int id = e & 3;
            if (chk == null)
                return;
            if (e[2]) begin
                dinst[id] = n_inst++;
                chk.dependent(dinst[id]);
            end else if (!live[id]) begin
                live[id] = 1;
                pinst[id] = n_inst++;
                chk.producer(pinst[id]);
            end
        endfunction
        function void on_ret(int p);
            if (chk != null && live[p]) begin
                live[p] = 0;
                chk.retire(pinst[p]);
            end
        endfunction
        function void on_release(int d);
            if (chk != null)
                chk.release_dep(dinst[d]);
        endfunction
    endclass
endpackage

module fw_dep_tracker_unit_test;
    import svunit_pkg::svunit_testcase;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;
    import fw_order_pkg::*;
    import fw_dep_tracker_ut_pkg::*;

    string name = "fw_dep_tracker_ut";
    svunit_testcase svunit_ut;

    reg clock = 0, reset = 1;
    always #5 clock = ~clock;

    `fw_root_begin(dt_top, u_dt, clock, reset)
    `fw_root_end

    function void build();
        svunit_ut = new(name);
    endfunction

    task automatic edges(int n);
        repeat (n) begin
            @(posedge clock);
            @(negedge clock);
        end
    endtask

    function automatic bit [2:0] prod(bit [1:0] p);
        return {1'b0, p};
    endfunction
    function automatic bit [2:0] dep(bit [1:0] d);
        return {1'b1, d};
    endfunction

    // One entry an edge, then n edges more.
    task automatic enter(bit [2:0] e[$], int n = 0);
        foreach (e[i])
            u_dt.root.s_ent.q.push_back(e[i]);
        edges(e.size() + n);
    endtask

    task automatic retire(bit [1:0] p);
        u_dt.root.s_ret.q.push_back(p);
        edges(1);
    endtask

    function automatic bit [3:0] ok();
        return u_dt.root.o_ok.v;
    endfunction

    task setup();
        svunit_ut.setup();
        reset = 1;
        repeat (2) @(posedge clock);
        reset = 0;
        wait (u_dt.root != null && u_dt.root.elaborated);
        @(negedge clock);
        // Retire whatever the earlier test left live, which releases every
        // dependent; then check afresh.
        u_dt.root.chk = null;
        u_dt.root.s_ent.q.delete();
        for (int p = 0; p < 4; p++)
            u_dt.root.s_ret.q.push_back(p);
        edges(6);
        u_dt.root.live = '0;
        u_dt.root.chk = new("chk");
        u_dt.root.chk.quiet = 1;
    endtask

    task teardown();
        svunit_ut.teardown();
    endtask

    `SVUNIT_TESTS_BEGIN

    // With no producer live, a dependent does not wait.
    `SVTEST(no_producer_no_wait)
        enter('{dep(0)}, 1);
        `FAIL_UNLESS_EQUAL(ok(), 4'b1111)
    `SVTEST_END

    // 0 then 1 enter; dependent 0 waits on 1, the youngest. Retiring 1
    // releases it, though 0 is still live (sticky); dependent 1 then waits
    // on 0, until 0 retires.
    `SVTEST(youngest_and_sticky)
        enter('{prod(0), prod(1), dep(0)});
        `FAIL_UNLESS_EQUAL(ok(), 4'b1110)
        retire(1);
        `FAIL_UNLESS_EQUAL(ok(), 4'b1111)
        enter('{dep(1)});
        `FAIL_UNLESS_EQUAL(ok(), 4'b1101)
        retire(0);
        `FAIL_UNLESS_EQUAL(ok(), 4'b1111)
        `FAIL_UNLESS_EQUAL(u_dt.root.chk.n_errors, 0)
    `SVTEST_END

    // Dependent 0 enters at the edge that retires 2, the youngest: it records
    // 2, and the same retire releases it.
    `SVTEST(same_edge_retire_releases)
        enter('{prod(2)});
        u_dt.root.s_ent.q.push_back(dep(0));
        u_dt.root.s_ret.q.push_back(2);
        edges(1);
        `FAIL_UNLESS_EQUAL(ok(), 4'b1111)
        `FAIL_UNLESS_EQUAL(u_dt.root.chk.n_errors, 0)
    `SVTEST_END

    // 0, 1, 2 enter and 1 retires from the middle: dependent 0 waits on 2;
    // when 2 retires, dependent 1 waits on 0, the youngest left.
    `SVTEST(retire_from_the_middle)
        enter('{prod(0), prod(1), prod(2)});
        retire(1);
        enter('{dep(0)});
        `FAIL_UNLESS_EQUAL(ok(), 4'b1110)
        retire(2);
        `FAIL_UNLESS_EQUAL(ok(), 4'b1111)
        enter('{dep(1)});
        `FAIL_UNLESS_EQUAL(ok(), 4'b1101)
        retire(0);
        `FAIL_UNLESS_EQUAL(ok(), 4'b1111)
        `FAIL_UNLESS_EQUAL(u_dt.root.chk.n_errors, 0)
    `SVTEST_END

    // 0 stays live while 1, 2 and 3 enter and retire 20 times; a dependent
    // then waits on 0, the only one live.
    `SVTEST(long_lived_producer)
        enter('{prod(0)});
        repeat (20)
            for (int p = 1; p < 4; p++) begin
                enter('{prod(p)});
                retire(p);
            end
        enter('{dep(3)});
        `FAIL_UNLESS_EQUAL(ok(), 4'b0111)
        retire(0);
        `FAIL_UNLESS_EQUAL(ok(), 4'b1111)
        `FAIL_UNLESS_EQUAL(u_dt.root.chk.n_errors, 0)
    `SVTEST_END

    // Retiring 3, which is not live, does nothing; entering 0 again while it
    // is live does nothing, so one retire of 0 leaves no producer live.
    `SVTEST(misuse_does_nothing)
        enter('{prod(0)});
        retire(3);
        enter('{prod(0), dep(2)});
        `FAIL_UNLESS_EQUAL(ok(), 4'b1011)
        retire(0);
        `FAIL_UNLESS_EQUAL(ok(), 4'b1111)
        enter('{dep(2)});
        `FAIL_UNLESS_EQUAL(ok(), 4'b1111)
        `FAIL_UNLESS_EQUAL(u_dt.root.chk.n_errors, 0)
    `SVTEST_END

    `SVUNIT_TESTS_END
endmodule
