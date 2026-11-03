// fw_arbiter (src/std/arb/fw_arbiter.svh): directed cases on the class
// model, with its contract checked.
//
// Three inputs of 8-bit values, round robin (rr) and fixed priority (pr).
// The out sink takes a value at once while `ready` is set, and waits clock
// by clock while it is clear.
//
// Contract (fw_arbiter.yaml): values leave in order per input and none is
// lost or duplicated (fw_order_check, per key).
`include "svunit_defines.svh"
`include "fw_hdl_macros.svh"

package fw_arbiter_ut_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;
    import fw_order_pkg::*;

    typedef bit [9:0] out_t;                     // {input, value}

    class src implements fw_get_if #(bit [7:0]);
        bit [7:0]      q[$];
        fw_order_check chk;
        int            key;
        virtual task get(output bit [7:0] t);
            wait (q.size() > 0);
            t = q.pop_front();
            chk.enter({key, t}, key, 0, t);
        endtask
    endclass

    class snk implements fw_put_if #(out_t);
        bit            ready = 1;
        out_t          got[$];
        fw_order_check chk;
        fw_component   clk;                      // for its clock
        virtual task put(input out_t t);
            while (!ready) clk.tick();
            got.push_back(t);
            chk.leave(t, t[7:0]);
        endtask
    endclass

    class ut_top #(fw_arb_policy_e POLICY = FW_ARB_RR) extends fw_component;
        fw_arbiter #(bit [7:0], 3, POLICY) arb;
        src            s[3];
        snk            o = new;
        fw_order_check order;
        fw_export #(fw_get_if #(bit [7:0])) e[3];
        fw_export #(fw_put_if #(out_t))     eo;

        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            order = new("order", fw_order_rule::in_order_per_key());
            order.quiet = 1;
            o.chk = order;
            o.clk = this;
            arb = new("arb", this);
            foreach (s[k]) begin
                s[k] = new;
                s[k].chk = order;
                s[k].key = k;
                e[k] = new($sformatf("e%0d", k), this, s[k]);
            end
            eo = new("eo", this, o);
        endfunction
        function void connect();
            foreach (e[k]) arb.in[k].connect(e[k]);
            arb.out.connect(eo);
        endfunction
    endclass
    typedef ut_top #(FW_ARB_RR)   rr_top;
    typedef ut_top #(FW_ARB_PRIO) pr_top;
endpackage

module fw_arbiter_unit_test;
    import svunit_pkg::svunit_testcase;
    import fw_hdl_pkg::*;
    import fw_arbiter_ut_pkg::*;

    string name = "fw_arbiter_ut";
    svunit_testcase svunit_ut;

    reg clock = 0, reset = 1;
    always #5 clock = ~clock;

    `fw_root_begin(rr_top, u_rr, clock, reset)
    `fw_root_end
    `fw_root_begin(pr_top, u_pr, clock, reset)
    `fw_root_end

    function void build();
        svunit_ut = new(name);
    endfunction

    // Fresh trees for each test.
    task setup();
        svunit_ut.setup();
        reset = 1;
        repeat (2) @(posedge clock);
        reset = 0;
        wait (u_rr.root != null && u_rr.root.elaborated);
        wait (u_pr.root != null && u_pr.root.elaborated);
        @(negedge clock);
    endtask

    task teardown();
        svunit_ut.teardown();
    endtask

    task automatic edges(int n);
        repeat (n) @(posedge clock);
        @(negedge clock);
    endtask

    function automatic out_t ov(int k, bit [7:0] x);
        return {2'(k), x};
    endfunction

    // Every value entered has left, in order per input.
    function automatic bit rr_contract_ok();
        u_rr.root.order.finish();
        return u_rr.root.order.n_errors == 0;
    endfunction
    function automatic bit pr_contract_ok();
        u_pr.root.order.finish();
        return u_pr.root.order.n_errors == 0;
    endfunction

    `SVUNIT_TESTS_BEGIN

    `SVTEST(empty_grants_nothing)
        edges(6);
        `FAIL_UNLESS_EQUAL(u_rr.root.o.got.size(), 0)
        `FAIL_UNLESS_EQUAL(u_pr.root.o.got.size(), 0)
    `SVTEST_END

    // All inputs waiting with out stalled; on release, round robin from
    // input 0 visits every input before any repeats.
    `SVTEST(round_robin_rotates)
        u_rr.root.o.ready = 0;
        u_rr.root.s[0].q = '{8'h10, 8'h11};
        u_rr.root.s[1].q = '{8'h20, 8'h21};
        u_rr.root.s[2].q = '{8'h30, 8'h31};
        edges(4);
        u_rr.root.o.ready = 1;
        edges(12);
        `FAIL_UNLESS_EQUAL(u_rr.root.o.got.size(), 6)
        `FAIL_UNLESS_EQUAL(u_rr.root.o.got[0], ov(0, 8'h10))
        `FAIL_UNLESS_EQUAL(u_rr.root.o.got[1], ov(1, 8'h20))
        `FAIL_UNLESS_EQUAL(u_rr.root.o.got[2], ov(2, 8'h30))
        `FAIL_UNLESS_EQUAL(u_rr.root.o.got[3], ov(0, 8'h11))
        `FAIL_UNLESS(rr_contract_ok())
    `SVTEST_END

    // Fixed priority: input 0, kept busy, wins every grant until it runs dry.
    `SVTEST(priority_lowest_wins)
        u_pr.root.o.ready = 0;
        u_pr.root.s[0].q = '{8'h10, 8'h11, 8'h12};
        u_pr.root.s[1].q = '{8'h20};
        u_pr.root.s[2].q = '{8'h30};
        edges(4);
        u_pr.root.o.ready = 1;
        edges(12);
        `FAIL_UNLESS_EQUAL(u_pr.root.o.got.size(), 5)
        `FAIL_UNLESS_EQUAL(u_pr.root.o.got[0], ov(0, 8'h10))
        `FAIL_UNLESS_EQUAL(u_pr.root.o.got[1], ov(0, 8'h11))
        `FAIL_UNLESS_EQUAL(u_pr.root.o.got[2], ov(0, 8'h12))
        `FAIL_UNLESS_EQUAL(u_pr.root.o.got[3], ov(1, 8'h20))
        `FAIL_UNLESS_EQUAL(u_pr.root.o.got[4], ov(2, 8'h30))
        `FAIL_UNLESS(pr_contract_ok())
    `SVTEST_END

    // A grant made while out stalls is kept: input 0 arriving later does not
    // take it, under either policy.
    `SVTEST(grant_held_under_backpressure)
        u_rr.root.o.ready = 0;
        u_pr.root.o.ready = 0;
        u_rr.root.s[1].q = '{8'h21};
        u_pr.root.s[1].q = '{8'h21};
        edges(3);
        u_rr.root.s[0].q = '{8'h05};
        u_pr.root.s[0].q = '{8'h05};
        edges(3);
        u_rr.root.o.ready = 1;
        u_pr.root.o.ready = 1;
        edges(6);
        `FAIL_UNLESS_EQUAL(u_rr.root.o.got[0], ov(1, 8'h21))
        `FAIL_UNLESS_EQUAL(u_pr.root.o.got[0], ov(1, 8'h21))
        `FAIL_UNLESS_EQUAL(u_rr.root.o.got[1], ov(0, 8'h05))
        `FAIL_UNLESS_EQUAL(u_pr.root.o.got[1], ov(0, 8'h05))
        `FAIL_UNLESS(rr_contract_ok())
        `FAIL_UNLESS(pr_contract_ok())
    `SVTEST_END

    // One input alone streams one value per clock.
    `SVTEST(one_input_full_rate)
        u_rr.root.s[2].q = '{8'h01, 8'h02, 8'h03, 8'h04, 8'h05, 8'h06};
        edges(9);
        `FAIL_UNLESS_EQUAL(u_rr.root.o.got.size(), 6)
        `FAIL_UNLESS(rr_contract_ok())
    `SVTEST_END

    // Reset with values held and out stalled: the new tree is empty.
    `SVTEST(reset_mid_traffic)
        u_rr.root.o.ready = 0;
        u_rr.root.s[0].q = '{8'h01, 8'h02};
        u_rr.root.s[1].q = '{8'h03};
        edges(3);
        setup();
        edges(4);
        `FAIL_UNLESS_EQUAL(u_rr.root.o.got.size(), 0)
        u_rr.root.s[1].q = '{8'h07};
        edges(4);
        `FAIL_UNLESS_EQUAL(u_rr.root.o.got.size(), 1)
        `FAIL_UNLESS_EQUAL(u_rr.root.o.got[0], ov(1, 8'h07))
        `FAIL_UNLESS(rr_contract_ok())
    `SVTEST_END

    `SVUNIT_TESTS_END
endmodule
