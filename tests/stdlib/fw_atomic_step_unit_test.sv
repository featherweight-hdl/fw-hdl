// fw_atomic_step (src/fw_atomic_step.svh) and the step runtime
// (fw_steppable.svh): an all-or-nothing step whose stream output stalls has
// no effect, and a step that commits behaves as an ordinary step.
//
// The DUT, `relay`, takes a value from `in` (two in pair mode, adding them),
// puts the sum on `out` with put_or_stall, counts commits in its state, sets
// the count on the level `lv` and puts the value on the valid-only `vo`. The
// test feeds `in` and drains the channels between clock edges. A plain step,
// `drain`, can take from `out` in the same edges.
`include "svunit_defines.svh"
`include "fw_hdl_macros.svh"

package fw_atomic_step_ut_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;

    typedef bit [7:0] T;
    typedef struct packed {
        bit [7:0] n;        // steps committed
        bit [7:0] last;     // the last value taken
    } relay_state_t;

    class relay extends fw_atomic_step #(relay_state_t);
        fw_port #(fw_get_nb_if #(T))    in;
        fw_port #(fw_put_step_if #(T))  out;
        fw_port #(fw_level_set_if #(T)) lv;
        fw_port #(fw_valid_put_if #(T)) vo;
        bit pair;

        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction

        function void build();
            in = new("in", this);
            out = new("out", this);
            lv = new("lv", this);
            vo = new("vo", this);
        endfunction

        virtual function void step();
            T x, y = 0;
            if (in.t.try_get(x)) begin
                if (pair)
                    void'(in.t.try_get(y));
                out.t.put_or_stall(x + y);
                s.n++;
                s.last = x;
                lv.t.set(s.n);
                vo.t.put(x);
            end
        endfunction

        function relay_state_t state();
            return s;
        endfunction
    endclass

    // A plain step: takes one value from `out` per edge while `on`.
    class drain extends fw_component implements fw_steppable;
        fw_port #(fw_get_nb_if #(T)) in;
        bit on;
        T   got[$];

        function new(string name, fw_component parent);
            super.new(name, parent);
            add_steppable(this);
        endfunction

        function void build();
            in = new("in", this);
        endfunction

        virtual function void step();
            T x;
            if (on && in.t.try_get(x))
                got.push_back(x);
        endfunction
    endclass

    class atomic_ut_top extends fw_component;
        relay                   dut;
        drain                   dr;
        fw_channel #(T, 8)      in_ch;
        fw_channel #(T, 1)      out_ch;
        fw_level_channel #(T)   lv_ch;
        fw_valid_channel #(T, 16) vo_ch;

        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction

        function void build();
            dut = new("dut", this);
            dr = new("dr", this);
            in_ch = new("in_ch", this);
            out_ch = new("out_ch", this);
            lv_ch = new("lv_ch", this);
            vo_ch = new("vo_ch", this);
        endfunction

        function void connect();
            dut.in.connect(in_ch.get_nb_ex);
            dut.out.connect(out_ch.put_step_ex);
            dut.lv.connect(lv_ch.put_ex);
            dut.vo.connect(vo_ch.put_ex);
            dr.in.connect(out_ch.get_nb_ex);
        endfunction
    endclass
endpackage

module fw_atomic_step_unit_test;
    import svunit_pkg::svunit_testcase;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;
    import fw_atomic_step_ut_pkg::*;

    string name = "fw_atomic_step_ut";
    svunit_testcase svunit_ut;

    reg clock = 0, reset = 1;
    always #5 clock = ~clock;

    `fw_root_begin(atomic_ut_top, u_root, clock, reset)
    `fw_root_end

    function void build();
        svunit_ut = new(name);
    endfunction

    task setup();
        svunit_ut.setup();
        reset = 1;
        repeat (2) @(posedge clock);
        reset = 0;
        wait (u_root.root != null && u_root.root.elaborated);
        @(negedge clock);
    endtask

    task teardown();
        svunit_ut.teardown();
    endtask

    task automatic edges(int n);
        repeat (n) @(posedge clock);
        @(negedge clock);
    endtask

    task automatic feed(T x);
        u_root.root.in_ch.ch_put(x);
    endtask

    // Take the head of a channel from outside any step.
    function automatic T take_out();
        T x;
        void'(u_root.root.out_ch.ch_try_get(x));
        return x;
    endfunction

    function automatic T take_in();
        T x;
        void'(u_root.root.in_ch.ch_try_get(x));
        return x;
    endfunction

    `SVUNIT_TESTS_BEGIN

    // out full: the step takes nothing, puts and sets nothing, and its state
    // stays. Once out is drained, the same value goes through.
    `SVTEST(stall_has_no_effect)
        feed(8'h11);
        edges(1);
        `FAIL_UNLESS_EQUAL(u_root.root.out_ch.size(), 1)
        `FAIL_UNLESS_EQUAL(u_root.root.dut.state().n, 1)
        feed(8'h22);
        edges(4);
        `FAIL_UNLESS_EQUAL(u_root.root.in_ch.size(), 1)
        `FAIL_UNLESS_EQUAL(u_root.root.out_ch.size(), 1)
        `FAIL_UNLESS_EQUAL(u_root.root.dut.state().n, 1)
        `FAIL_UNLESS_EQUAL(u_root.root.dut.state().last, 8'h11)
        `FAIL_UNLESS_EQUAL(u_root.root.lv_ch.value, 1)
        `FAIL_UNLESS_EQUAL(u_root.root.vo_ch.size(), 1)
        `FAIL_UNLESS_EQUAL(take_out(), 8'h11)
        edges(1);
        `FAIL_UNLESS_EQUAL(u_root.root.in_ch.size(), 0)
        `FAIL_UNLESS_EQUAL(take_out(), 8'h22)
        `FAIL_UNLESS_EQUAL(u_root.root.dut.state().n, 2)
        `FAIL_UNLESS_EQUAL(u_root.root.lv_ch.value, 2)
        `FAIL_UNLESS_EQUAL(u_root.root.vo_ch.size(), 2)
        `FAIL_UNLESS_EQUAL(u_root.root.vo_ch.n_violations, 0)
    `SVTEST_END

    // Two takes in one step: the second sees the next value, and a stall puts
    // both back in their order.
    `SVTEST(two_takes_undone_in_order)
        u_root.root.dut.pair = 1;
        feed(8'h01);
        feed(8'h02);
        edges(1);
        `FAIL_UNLESS_EQUAL(u_root.root.out_ch.size(), 1)
        feed(8'h03);
        feed(8'h04);
        edges(3);
        `FAIL_UNLESS_EQUAL(u_root.root.in_ch.size(), 2)
        `FAIL_UNLESS_EQUAL(take_out(), 8'h03)
        edges(1);
        `FAIL_UNLESS_EQUAL(take_out(), 8'h07)
        `FAIL_UNLESS_EQUAL(u_root.root.dut.state().last, 8'h03)
        feed(8'h05);
        feed(8'h06);
        u_root.root.out_ch.ch_put(8'hff);
        edges(2);
        `FAIL_UNLESS_EQUAL(take_in(), 8'h05)
        `FAIL_UNLESS_EQUAL(take_in(), 8'h06)
    `SVTEST_END

    // Readiness is taken at the start of the cycle: with out one deep and a
    // step draining it every cycle, the space freed by a take is seen from
    // the next edge, so the relay commits every other cycle.
    `SVTEST(ready_at_start_of_cycle)
        u_root.root.dr.on = 1;
        for (int i = 0; i < 6; i++)
            feed(T'(i + 1));
        edges(12);
        `FAIL_UNLESS_EQUAL(u_root.root.dr.got.size(), 6)
        foreach (u_root.root.dr.got[i])
            `FAIL_UNLESS_EQUAL(u_root.root.dr.got[i], T'(i + 1))
        `FAIL_UNLESS_EQUAL(u_root.root.dut.state().n, 6)
    `SVTEST_END

    // ... and every other cycle exactly: the drain takes value k at edge 2k,
    // so 6 values need 12 edges, not 7.
    `SVTEST(one_deep_out_halves_the_rate)
        u_root.root.dr.on = 1;
        for (int i = 0; i < 6; i++)
            feed(T'(i + 1));
        edges(11);
        `FAIL_UNLESS_EQUAL(u_root.root.dr.got.size(), 5)
        edges(1);
        `FAIL_UNLESS_EQUAL(u_root.root.dr.got.size(), 6)
    `SVTEST_END

    `SVUNIT_TESTS_END
endmodule
