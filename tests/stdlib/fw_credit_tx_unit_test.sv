// fw_credit_tx (src/std/credit/fw_credit_tx.svh): directed corner cases on
// the class model, with its contract checked throughout.
//
// The DUT has 2 VCs and 3 credits: 1 in the pool and 1 reserved per VC, spent
// pool first. Values are offered between clock edges; a test reads the
// output as (cycle, {vc, value}) pairs, cycles counted from its start.
//
// Contract (fw_credit_tx.yaml): values leave in order per VC
// (fw_order_check, per key), and no more than CREDITS credits are ever out
// (fw_lifetime: one id per credit spent, freed by its return).
`include "svunit_defines.svh"
`include "fw_hdl_macros.svh"

package fw_credit_tx_ut_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;
    import fw_order_pkg::*;

    localparam int CREDITS = 3;
    typedef fw_credit_tx #(bit [7:0], CREDITS, 2, 1, FW_CREDIT_POOL_FIRST, 1) dut_t;
    typedef bit [8:0] out_t;                     // {vc, value}

    // A source the test pushes into; try_get takes the head.
    class src #(type T = bit [7:0]) implements fw_get_nb_if #(T);
        T             q[$];
        realtime      taken[$];                  // when each value was taken
        fw_order_check chk;                      // values: enter on take
        fw_lifetime   credits;                   // returns: free on take
        int           key, n_free[2];
        virtual task get(output T t);
            wait (q.size() > 0);
            void'(try_get(t));
        endtask
        virtual function bit try_get(inout T t);
            if (q.size() == 0)
                return 1'b0;
            t = q.pop_front();
            taken.push_back($realtime);
            if (chk != null)
                chk.enter({key, 8'(t)}, key, 0, 8'(t));
            if (credits != null)
                credits.free({32'(t), n_free[int'(t)]++});
            return 1'b1;
        endfunction
    endclass

    class snk implements fw_valid_put_if #(out_t);
        out_t          got[$];
        realtime       at[$];
        fw_order_check chk;
        fw_lifetime    credits;
        int            n_alloc[2];
        virtual function void put(input out_t t);
            got.push_back(t);
            at.push_back($realtime);
            chk.leave(t, t[7:0]);
            credits.alloc({32'(t[8]), n_alloc[t[8]]++});
        endfunction
    endclass

    class ut_top extends fw_component;
        dut_t           dut;
        src #(bit [7:0]) s0 = new, s1 = new;
        src #(bit [0:0]) scr = new;
        snk             o = new;
        fw_order_check  order;
        fw_lifetime     credits;
        fw_export #(fw_get_nb_if #(bit [7:0])) e0, e1;
        fw_export #(fw_get_nb_if #(bit [0:0])) ecr;
        fw_export #(fw_valid_put_if #(out_t))  eo;

        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            order = new("order", fw_order_rule::in_order_per_key());
            credits = new("credits", CREDITS);
            order.quiet = 1;
            credits.quiet = 1;
            s0.chk = order; s0.key = 0;
            s1.chk = order; s1.key = 1;
            scr.credits = credits;
            o.chk = order;
            o.credits = credits;
            dut = new("dut", this);
            e0 = new("e0", this, s0);
            e1 = new("e1", this, s1);
            ecr = new("ecr", this, scr);
            eo = new("eo", this, o);
        endfunction
        function void connect();
            dut.in[0].connect(e0);
            dut.in[1].connect(e1);
            dut.cr.connect(ecr);
            dut.out.connect(eo);
        endfunction
    endclass
endpackage

module fw_credit_tx_unit_test;
    import svunit_pkg::svunit_testcase;
    import fw_hdl_pkg::*;
    import fw_credit_tx_ut_pkg::*;

    string name = "fw_credit_tx_ut";
    svunit_testcase svunit_ut;

    reg clock = 0, reset = 1;
    always #5 clock = ~clock;

    `fw_root_begin(ut_top, u_root, clock, reset)
    `fw_root_end

    realtime t0;

    function void build();
        svunit_ut = new(name);
    endfunction

    // A fresh tree for each test: reset, release, and start between edges.
    task setup();
        svunit_ut.setup();
        reset = 1;
        repeat (2) @(posedge clock);
        reset = 0;
        wait (u_root.root != null && u_root.root.elaborated);
        @(negedge clock);
        t0 = $realtime;
    endtask

    task teardown();
        svunit_ut.teardown();
    endtask

    // Wait n rising edges, then sit between edges.
    task automatic edges(int n);
        repeat (n) @(posedge clock);
        @(negedge clock);
    endtask

    // The cycle (rising edge, counted from the test's start) of output i.
    function automatic int cyc(int i);
        return int'((u_root.root.o.at[i] - t0 - 5) / 10);
    endfunction

    function automatic out_t ov(bit vc, bit [7:0] x);
        return {vc, x};
    endfunction

    // The contract held: nothing reordered, lost or duplicated per VC that
    // has left, and never more than CREDITS credits out.
    function automatic bit contract_ok();
        return u_root.root.order.n_errors == 0 && u_root.root.credits.n_errors == 0;
    endfunction

    `SVUNIT_TESTS_BEGIN

    `SVTEST(empty_sends_nothing)
        edges(6);
        `FAIL_UNLESS_EQUAL(u_root.root.o.got.size(), 0)
    `SVTEST_END

    // VC 0 spends the pool, then its reserve, then waits; VC 1 still sends on
    // its reserve. A return to VC 0 releases the next value.
    `SVTEST(credits_cap_and_reserve)
        u_root.root.s0.q = '{8'h01, 8'h02, 8'h03};
        edges(6);
        `FAIL_UNLESS_EQUAL(u_root.root.o.got.size(), 2)
        `FAIL_UNLESS_EQUAL(u_root.root.o.got[0], ov(0, 8'h01))
        `FAIL_UNLESS_EQUAL(u_root.root.o.got[1], ov(0, 8'h02))
        u_root.root.s1.q.push_back(8'h09);
        edges(3);
        `FAIL_UNLESS_EQUAL(u_root.root.o.got.size(), 3)
        `FAIL_UNLESS_EQUAL(u_root.root.o.got[2], ov(1, 8'h09))
        u_root.root.scr.q.push_back(1'b0);
        edges(3);
        `FAIL_UNLESS_EQUAL(u_root.root.o.got.size(), 4)
        `FAIL_UNLESS_EQUAL(u_root.root.o.got[3], ov(0, 8'h03))
        `FAIL_UNLESS(contract_ok())
    `SVTEST_END

    // A credit returned at an edge is spent from the next edge, not the same.
    `SVTEST(return_spendable_next_cycle)
        u_root.root.s0.q = '{8'h01, 8'h02, 8'h03};
        edges(5);
        `FAIL_UNLESS_EQUAL(u_root.root.o.got.size(), 2)
        u_root.root.scr.q.push_back(1'b0);
        edges(3);
        `FAIL_UNLESS_EQUAL(u_root.root.o.got.size(), 3)
        `FAIL_UNLESS_EQUAL(u_root.root.o.at[2] - u_root.root.scr.taken[0], 10.0)
        `FAIL_UNLESS(contract_ok())
    `SVTEST_END

    // Both VCs waiting: grants alternate, VC 0 first, one per cycle.
    `SVTEST(round_robin_tie)
        u_root.root.s0.q = '{8'h10, 8'h11};
        u_root.root.s1.q = '{8'h20};
        edges(6);
        `FAIL_UNLESS_EQUAL(u_root.root.o.got.size(), 3)
        `FAIL_UNLESS_EQUAL(u_root.root.o.got[0], ov(0, 8'h10))
        `FAIL_UNLESS_EQUAL(u_root.root.o.got[1], ov(1, 8'h20))
        `FAIL_UNLESS_EQUAL(u_root.root.o.got[2], ov(0, 8'h11))
        `FAIL_UNLESS_EQUAL(cyc(1), cyc(0) + 1)
        `FAIL_UNLESS_EQUAL(cyc(2), cyc(1) + 1)
        `FAIL_UNLESS(contract_ok())
    `SVTEST_END

    // A value is sent from the cycle after it arrives (one hold per VC), and
    // back-to-back values on one VC go one per cycle.
    `SVTEST(hold_latency_and_rate)
        u_root.root.s1.q = '{8'h31, 8'h32};
        edges(5);
        `FAIL_UNLESS_EQUAL(u_root.root.o.got.size(), 2)
        `FAIL_UNLESS_EQUAL(u_root.root.o.at[0] - u_root.root.s1.taken[0], 10.0)
        `FAIL_UNLESS_EQUAL(cyc(1), cyc(0) + 1)
        `FAIL_UNLESS(contract_ok())
    `SVTEST_END

    // Reset with credits spent and values waiting: the new tree starts with
    // all CREDITS credits and empty holds.
    `SVTEST(reset_mid_traffic)
        u_root.root.s0.q = '{8'h01, 8'h02, 8'h03, 8'h04};
        edges(4);
        `FAIL_UNLESS_EQUAL(u_root.root.o.got.size(), 2)
        setup();
        `FAIL_UNLESS_EQUAL(u_root.root.o.got.size(), 0)
        u_root.root.s0.q = '{8'h05, 8'h06};
        u_root.root.s1.q = '{8'h07};
        edges(6);
        `FAIL_UNLESS_EQUAL(u_root.root.o.got.size(), 3)
        `FAIL_UNLESS(contract_ok())
    `SVTEST_END

    `SVUNIT_TESTS_END
endmodule
