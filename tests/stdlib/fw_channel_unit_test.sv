// fw_channel (src/std/fw_channel.svh) between steps, and in process form.
//
// `prod`, an all-or-nothing step, takes a value from the test's source and
// puts it on `ch` with put_or_stall; with `tee` set it also puts it on the
// one-deep `side`, so a full `side` stalls the step after its put on `ch`
// went.
// `cons`, a plain step, takes one value from `ch` per edge while `on`, and
// records the edge. Values are checked in order and once each
// (fw_order_check), and `ch` never holds more than DEPTH after an edge.
`include "svunit_defines.svh"
`include "fw_hdl_macros.svh"

package fw_channel_ut_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;
    import fw_order_pkg::*;

    typedef bit [7:0] T;

    typedef class src;
    class src_undo extends fw_step_undo;
        src s;
        T   v;
        virtual function void undo();
            s.q.push_front(v);
        endfunction
    endclass

    class src implements fw_get_nb_if #(T);
        T              q[$];
        fw_order_check chk;
        function void offer(T v);
            q.push_back(v);
            chk.enter(v, 0, 0, v);
        endfunction
        virtual task get(output T t);
            wait (q.size() > 0);
            void'(try_get(t));
        endtask
        virtual function bit try_get(inout T t);
            if (q.size() == 0)
                return 1'b0;
            if (fw_step_ctx::atomic) begin
                src_undo u = new;
                u.s = this;
                u.v = q[0];
                fw_step_ctx::record(u);
            end
            t = q.pop_front();
            return 1'b1;
        endfunction
    endclass

    class prod extends fw_atomic_step;
        fw_port #(fw_get_nb_if #(T))   in;
        fw_port #(fw_put_step_if #(T)) out;
        fw_port #(fw_put_step_if #(T)) side;
        bit tee;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            in = new("in", this);
            out = new("out", this);
            side = new("side", this);
        endfunction
        virtual function void step();
            T x;
            if (in.t.try_get(x)) begin
                out.t.put_or_stall(x);
                if (tee)
                    side.t.put_or_stall(x);
            end
        endfunction
    endclass

    class cons extends fw_component implements fw_steppable;
        fw_port #(fw_get_nb_if #(T)) in;
        bit            on;
        int            edge_n;
        T              got[$];
        int            at[$];
        fw_order_check chk;
        function new(string name, fw_component parent);
            super.new(name, parent);
            add_steppable(this);
        endfunction
        function void build();
            in = new("in", this);
        endfunction
        virtual function void step();
            T x;
            if (on && in.t.try_get(x)) begin
                got.push_back(x);
                at.push_back(edge_n);
                chk.leave(x, x);
            end
            edge_n++;
        endfunction
    endclass

    class ch_ut_top #(int D = 1) extends fw_component;
        prod                p;
        cons                c;
        src                 s = new;
        fw_channel #(T, D)  ch;
        fw_channel #(T, 1)  side;
        fw_channel #(T, 0)  rv;       // process form only
        fw_order_check      order;
        fw_export #(fw_get_nb_if #(T)) es;

        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            order = new("order");
            order.quiet = 1;
            s.chk = order;
            p = new("p", this);
            c = new("c", this);
            c.chk = order;
            ch = new("ch", this);
            side = new("side", this);
            rv = new("rv", this);
            es = new("es", this, s);
        endfunction
        function void connect();
            p.in.connect(es);
            p.out.connect(ch.put_step_ex);
            p.side.connect(side.put_step_ex);
            c.in.connect(ch.get_nb_ex);
        endfunction
    endclass
    typedef ch_ut_top #(1) d1_top;
    typedef ch_ut_top #(2) d2_top;
endpackage

module fw_channel_unit_test;
    import svunit_pkg::svunit_testcase;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;
    import fw_channel_ut_pkg::*;

    string name = "fw_channel_ut";
    svunit_testcase svunit_ut;

    reg clock = 0, reset = 1;
    always #5 clock = ~clock;

    `fw_root_begin(d1_top, u_d1, clock, reset)
    `fw_root_end
    `fw_root_begin(d2_top, u_d2, clock, reset)
    `fw_root_end

    function void build();
        svunit_ut = new(name);
    endfunction

    task setup();
        svunit_ut.setup();
        reset = 1;
        repeat (2) @(posedge clock);
        reset = 0;
        wait (u_d1.root != null && u_d1.root.elaborated);
        wait (u_d2.root != null && u_d2.root.elaborated);
        @(negedge clock);
        most1 = 0;
        most2 = 0;
    endtask

    task teardown();
        svunit_ut.teardown();
    endtask

    int most1, most2;       // the most each ch has held after an edge

    task automatic edges(int n);
        repeat (n) begin
            @(posedge clock);
            @(negedge clock);
            if (u_d1.root.ch.size() > most1) most1 = u_d1.root.ch.size();
            if (u_d2.root.ch.size() > most2) most2 = u_d2.root.ch.size();
        end
    endtask

    `SVUNIT_TESTS_BEGIN

    // Nothing offered: a step's try_get finds nothing and the channel stays
    // empty.
    `SVTEST(empty)
        u_d1.root.c.on = 1;
        edges(4);
        `FAIL_UNLESS_EQUAL(u_d1.root.c.got.size(), 0)
        `FAIL_UNLESS_EQUAL(u_d1.root.ch.size(), 0)
    `SVTEST_END

    // A value put at an edge is taken at the next one, never the same one.
    `SVTEST(latency_one)
        u_d2.root.c.on = 1;
        u_d2.root.s.offer(8'h5a);
        edges(3);
        `FAIL_UNLESS_EQUAL(u_d2.root.c.got.size(), 1)
        `FAIL_UNLESS_EQUAL(u_d2.root.c.got[0], 8'h5a)
        `FAIL_UNLESS_EQUAL(u_d2.root.c.at[0], u_d2.root.c.edge_n - 2)
    `SVTEST_END

    // A value offered every edge: DEPTH 1 passes one every other edge (a
    // full channel refuses a put even at an edge that takes), DEPTH 2 one
    // every edge. Order holds and nothing is lost.
    `SVTEST(rate_by_depth)
        u_d1.root.c.on = 1;
        u_d2.root.c.on = 1;
        for (int i = 0; i < 6; i++) begin
            u_d1.root.s.offer(T'(i + 1));
            u_d2.root.s.offer(T'(i + 1));
        end
        edges(14);
        `FAIL_UNLESS_EQUAL(u_d1.root.c.got.size(), 6)
        `FAIL_UNLESS_EQUAL(u_d2.root.c.got.size(), 6)
        for (int i = 1; i < 6; i++) begin
            `FAIL_UNLESS_EQUAL(u_d1.root.c.at[i] - u_d1.root.c.at[i - 1], 2)
            `FAIL_UNLESS_EQUAL(u_d2.root.c.at[i] - u_d2.root.c.at[i - 1], 1)
        end
        u_d1.root.order.finish();
        u_d2.root.order.finish();
        `FAIL_UNLESS_EQUAL(u_d1.root.order.n_errors, 0)
        `FAIL_UNLESS_EQUAL(u_d2.root.order.n_errors, 0)
        // Streaming, each holds one value after an edge: DEPTH 2 needs its
        // second place only for the put at an edge that also takes.
        `FAIL_UNLESS_EQUAL(most1, 1)
        `FAIL_UNLESS_EQUAL(most2, 1)
    `SVTEST_END

    // The consumer stops: the producer fills DEPTH and then stalls, so the
    // rest stay with the source. Once the consumer resumes, all of them come
    // through in order.
    `SVTEST(backpressure)
        for (int i = 0; i < 5; i++)
            u_d2.root.s.offer(T'(8'h10 + i));
        edges(5);
        `FAIL_UNLESS_EQUAL(u_d2.root.ch.size(), 2)
        `FAIL_UNLESS_EQUAL(u_d2.root.s.q.size(), 3)
        u_d2.root.c.on = 1;
        edges(6);
        `FAIL_UNLESS_EQUAL(u_d2.root.c.got.size(), 5)
        foreach (u_d2.root.c.got[i])
            `FAIL_UNLESS_EQUAL(u_d2.root.c.got[i], T'(8'h10 + i))
        u_d2.root.order.finish();
        `FAIL_UNLESS_EQUAL(u_d2.root.order.n_errors, 0)
        `FAIL_UNLESS_EQUAL(most2, 2)
    `SVTEST_END

    // A step that puts on ch and then stalls on `side`: its put on ch is
    // undone, and the value stays with the source.
    `SVTEST(stalled_put_is_undone)
        T x;
        u_d2.root.p.tee = 1;
        u_d2.root.side.ch_put(8'hee);         // side full
        u_d2.root.s.offer(8'h01);
        edges(3);
        `FAIL_UNLESS_EQUAL(u_d2.root.ch.size(), 0)
        `FAIL_UNLESS_EQUAL(u_d2.root.s.q.size(), 1)
        `FAIL_UNLESS_EQUAL(u_d2.root.s.q[0], 8'h01)
        void'(u_d2.root.side.ch_try_get(x));  // side has space again
        edges(1);
        `FAIL_UNLESS_EQUAL(u_d2.root.ch.size(), 1)
        `FAIL_UNLESS_EQUAL(u_d2.root.side.size(), 1)
    `SVTEST_END

    // Process form: a FIFO put blocks while DEPTH values wait; a rendezvous
    // put returns only once its value is taken.
    `SVTEST(process_form)
        T x;
        bit done;
        fork begin
            u_d2.root.ch.ch_put(8'h01);
            u_d2.root.ch.ch_put(8'h02);
            u_d2.root.ch.ch_put(8'h03);
            done = 1;
        end join_none
        #1;
        `FAIL_UNLESS_EQUAL(done, 0)
        `FAIL_UNLESS_EQUAL(u_d2.root.ch.size(), 2)
        u_d2.root.ch.ch_get(x);
        #1;
        `FAIL_UNLESS_EQUAL(done, 1)
        `FAIL_UNLESS_EQUAL(x, 8'h01)
        done = 0;
        fork begin
            u_d2.root.rv.ch_put(8'h77);
            done = 1;
        end join_none
        #3;
        `FAIL_UNLESS_EQUAL(done, 0)
        u_d2.root.rv.ch_get(x);
        #1;
        `FAIL_UNLESS_EQUAL(done, 1)
        `FAIL_UNLESS_EQUAL(x, 8'h77)
    `SVTEST_END

    `SVUNIT_TESTS_END
endmodule
