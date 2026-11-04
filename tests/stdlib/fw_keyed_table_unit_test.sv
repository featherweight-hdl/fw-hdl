// fw_keyed_table (src/std/table/fw_keyed_table.svh), 4 slots, 4-bit keys,
// 8-bit values: the per-cycle rules in the class header, one edge at a time.
//
// Each request port has a source that offers its queued requests in order;
// each response has a sink that takes a value when `ready` and keeps it.
// Responses: ins_rsp {ok, full, slot[1:0]}, lkp_rsp {hit, slot[1:0], value}.
`include "svunit_defines.svh"
`include "fw_hdl_macros.svh"

package fw_keyed_table_ut_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;

    typedef class src;
    class src_undo #(type T = int) extends fw_step_undo;
        src #(T) s;
        T        v;
        virtual function void undo();
            s.q.push_front(v);
        endfunction
    endclass

    class src #(type T = int) implements fw_get_nb_if #(T);
        T q[$];
        virtual task get(output T t);
            wait (q.size() > 0);
            void'(try_get(t));
        endtask
        virtual function bit try_get(inout T t);
            if (q.size() == 0)
                return 1'b0;
            if (fw_step_ctx::atomic) begin
                src_undo #(T) u = new;
                u.s = this;
                u.v = q[0];
                fw_step_ctx::record(u);
            end
            t = q.pop_front();
            return 1'b1;
        endfunction
    endclass

    class snk #(type T = int) implements fw_put_step_if #(T);
        bit          ready = 1;
        T            got[$];
        fw_step_sent sent = new;
        virtual task put(input T t);
            $fatal(1, "the table puts with put_or_stall");
        endtask
        virtual function void put_or_stall(input T t);
            if (sent.sent)
                return;
            if (!ready) begin
                fw_step_ctx::stall();
                return;
            end
            got.push_back(t);
            fw_step_ctx::sent(sent);
        endfunction
    endclass

    class kt_top extends fw_component;
        fw_keyed_table #(bit [3:0], bit [7:0], 4) t;
        src #(bit [11:0]) s_ins = new;
        src #(bit [3:0])  s_lkp = new;
        src #(bit [9:0])  s_wr = new;
        src #(bit [1:0])  s_rm = new;
        snk #(bit [3:0])  o_ins = new;
        snk #(bit [10:0]) o_lkp = new;
        fw_export #(fw_get_nb_if #(bit [11:0]))  e_ins;
        fw_export #(fw_get_nb_if #(bit [3:0]))   e_lkp;
        fw_export #(fw_get_nb_if #(bit [9:0]))   e_wr;
        fw_export #(fw_get_nb_if #(bit [1:0]))   e_rm;
        fw_export #(fw_put_step_if #(bit [3:0]))  e_ins_rsp;
        fw_export #(fw_put_step_if #(bit [10:0])) e_lkp_rsp;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            t = new("t", this);
            e_ins = new("e_ins", this, s_ins);
            e_lkp = new("e_lkp", this, s_lkp);
            e_wr = new("e_wr", this, s_wr);
            e_rm = new("e_rm", this, s_rm);
            e_ins_rsp = new("e_ins_rsp", this, o_ins);
            e_lkp_rsp = new("e_lkp_rsp", this, o_lkp);
        endfunction
        function void connect();
            t.ins.connect(e_ins);
            t.lkp.connect(e_lkp);
            t.wr.connect(e_wr);
            t.rm.connect(e_rm);
            t.ins_rsp.connect(e_ins_rsp);
            t.lkp_rsp.connect(e_lkp_rsp);
        endfunction
    endclass
endpackage

module fw_keyed_table_unit_test;
    import svunit_pkg::svunit_testcase;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;
    import fw_keyed_table_ut_pkg::*;

    string name = "fw_keyed_table_ut";
    svunit_testcase svunit_ut;

    reg clock = 0, reset = 1;
    always #5 clock = ~clock;

    `fw_root_begin(kt_top, u_kt, clock, reset)
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

    function automatic bit [11:0] kv(bit [3:0] k, bit [7:0] v);
        return {k, v};
    endfunction
    function automatic bit [3:0] ins_ok(bit [1:0] slot);
        return {2'b10, slot};
    endfunction
    function automatic bit [10:0] hit(bit [1:0] slot, bit [7:0] v);
        return {1'b1, slot, v};
    endfunction
    localparam bit [3:0]  DUP = 4'b0000;
    localparam bit [3:0]  FULL = 4'b0100;
    localparam bit [10:0] MISS = 11'b0;

    // Install keys 1..n with values 8'h10 + key, one per edge.
    task automatic fill(int n);
        for (int k = 1; k <= n; k++)
            u_kt.root.s_ins.q.push_back(kv(k, 8'h10 + k));
        edges(n);
    endtask

    task setup();
        svunit_ut.setup();
        reset = 1;
        repeat (2) @(posedge clock);
        reset = 0;
        wait (u_kt.root != null && u_kt.root.elaborated);
        @(negedge clock);
        // Empty the table the earlier test left: remove every slot.
        u_kt.root.o_ins.ready = 1;
        u_kt.root.o_lkp.ready = 1;
        for (int i = 0; i < 4; i++)
            u_kt.root.s_rm.q.push_back(i);
        edges(6);
        u_kt.root.o_ins.got.delete();
        u_kt.root.o_lkp.got.delete();
    endtask

    task teardown();
        svunit_ut.teardown();
    endtask

    `SVUNIT_TESTS_BEGIN

    // An install takes slot 0; a lookup at a later edge finds it, another
    // key misses.
    `SVTEST(install_then_lookup)
        u_kt.root.s_ins.q.push_back(kv(3, 8'h33));
        edges(1);
        u_kt.root.s_lkp.q.push_back(3);
        u_kt.root.s_lkp.q.push_back(5);
        edges(2);
        `FAIL_UNLESS_EQUAL(u_kt.root.o_ins.got.size(), 1)
        `FAIL_UNLESS_EQUAL(u_kt.root.o_ins.got[0], ins_ok(0))
        `FAIL_UNLESS_EQUAL(u_kt.root.o_lkp.got.size(), 2)
        `FAIL_UNLESS_EQUAL(u_kt.root.o_lkp.got[0], hit(0, 8'h33))
        `FAIL_UNLESS_EQUAL(u_kt.root.o_lkp.got[1], MISS)
    `SVTEST_END

    // A live key is refused as a duplicate; with every slot live, a new key
    // is refused as full. Neither changes the table.
    `SVTEST(duplicate_and_full)
        fill(4);
        u_kt.root.s_ins.q.push_back(kv(2, 8'hee));
        u_kt.root.s_ins.q.push_back(kv(9, 8'h99));
        edges(2);
        u_kt.root.s_lkp.q.push_back(2);
        edges(1);
        `FAIL_UNLESS_EQUAL(u_kt.root.o_ins.got.size(), 6)
        for (int i = 0; i < 4; i++)
            `FAIL_UNLESS_EQUAL(u_kt.root.o_ins.got[i], ins_ok(i))
        `FAIL_UNLESS_EQUAL(u_kt.root.o_ins.got[4], DUP)
        `FAIL_UNLESS_EQUAL(u_kt.root.o_ins.got[5], FULL)
        `FAIL_UNLESS_EQUAL(u_kt.root.o_lkp.got[0], hit(1, 8'h12))
    `SVTEST_END

    // A removed slot is the lowest free one, so the next install takes it.
    `SVTEST(lowest_free_reused)
        fill(4);
        u_kt.root.s_rm.q.push_back(2);
        u_kt.root.s_rm.q.push_back(1);
        edges(2);
        u_kt.root.s_ins.q.push_back(kv(7, 8'h77));
        edges(1);
        `FAIL_UNLESS_EQUAL(u_kt.root.o_ins.got[4], ins_ok(1))
    `SVTEST_END

    // One edge with all four requests sees the table as it was at the start
    // of the edge: the lookup gets the value from before the write, the
    // install finds the table full though slot 0 is removed, and the key it
    // would have installed misses. At the next edge slot 0 is free.
    `SVTEST(same_edge_sees_the_start)
        fill(4);
        u_kt.root.s_lkp.q.push_back(2);
        u_kt.root.s_wr.q.push_back({2'd1, 8'hee});
        u_kt.root.s_rm.q.push_back(0);
        u_kt.root.s_ins.q.push_back(kv(9, 8'h99));
        edges(1);
        `FAIL_UNLESS_EQUAL(u_kt.root.o_lkp.got[0], hit(1, 8'h12))
        `FAIL_UNLESS_EQUAL(u_kt.root.o_ins.got[4], FULL)
        u_kt.root.s_lkp.q.push_back(2);
        u_kt.root.s_ins.q.push_back(kv(9, 8'h99));
        edges(1);
        `FAIL_UNLESS_EQUAL(u_kt.root.o_lkp.got[1], hit(1, 8'hee))
        `FAIL_UNLESS_EQUAL(u_kt.root.o_ins.got[5], ins_ok(0))
    `SVTEST_END

    // lkp_rsp is not ready: the install's response goes at the first edge
    // and only then; nothing is installed or taken until lkp_rsp is ready,
    // so the lookup, at the same edge as the install, misses.
    `SVTEST(response_sent_once)
        u_kt.root.o_lkp.ready = 0;
        u_kt.root.s_ins.q.push_back(kv(4, 8'h44));
        u_kt.root.s_lkp.q.push_back(4);
        edges(3);
        `FAIL_UNLESS_EQUAL(u_kt.root.o_ins.got.size(), 1)
        `FAIL_UNLESS_EQUAL(u_kt.root.o_ins.got[0], ins_ok(0))
        `FAIL_UNLESS_EQUAL(u_kt.root.s_ins.q.size(), 1)
        `FAIL_UNLESS_EQUAL(u_kt.root.s_lkp.q.size(), 1)
        u_kt.root.o_lkp.ready = 1;
        edges(1);
        `FAIL_UNLESS_EQUAL(u_kt.root.o_ins.got.size(), 1)
        `FAIL_UNLESS_EQUAL(u_kt.root.o_lkp.got.size(), 1)
        `FAIL_UNLESS_EQUAL(u_kt.root.o_lkp.got[0], MISS)
        `FAIL_UNLESS_EQUAL(u_kt.root.s_ins.q.size(), 0)
        u_kt.root.s_lkp.q.push_back(4);
        edges(1);
        `FAIL_UNLESS_EQUAL(u_kt.root.o_lkp.got[1], hit(0, 8'h44))
    `SVTEST_END

    // A write or remove that names a free slot does nothing.
    `SVTEST(free_slot_untouched)
        fill(1);
        u_kt.root.s_wr.q.push_back({2'd2, 8'hee});
        u_kt.root.s_rm.q.push_back(3);
        edges(1);
        u_kt.root.s_ins.q.push_back(kv(5, 8'h55));
        u_kt.root.s_lkp.q.push_back(1);
        edges(1);
        `FAIL_UNLESS_EQUAL(u_kt.root.o_ins.got[1], ins_ok(1))
        `FAIL_UNLESS_EQUAL(u_kt.root.o_lkp.got[0], hit(0, 8'h11))
    `SVTEST_END

    `SVUNIT_TESTS_END
endmodule
