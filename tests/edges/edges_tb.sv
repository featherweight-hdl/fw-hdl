// Edge drivers, groups and release (sync-task-domains.md §6.5, step X2a;
// fw-hdl-spec semantics/processes.md, "Edges" and "The edge"). Built and run
// by tests/python/system/test_edges_sim.py; prints PASS or FAIL lines.
//
//   phase    a ÷2 domain's edges are the root's even edges, from time 0,
//            whoever ticks it and whenever it starts (X0.2, restated)
//   group    a ÷2 step() at a shared edge reads its source's register from
//            before the edge (both domains in one group)
//   release  a task ticking an owned root resumes after its edge's update
//   late     the kernel launched between edges, mid-run: the ÷2 phase holds
//   period   a period root's edges are at k * period, from any start
//   p33      a 3.3 ns period at 1 ps: every edge once, none drifts
//   delay    a delay ending at an owned period root's edge, then tick(1):
//            the next edge (a computed edge comes before the delay)
//   x        a clock starting at X, and 0 -> X -> 1, give one edge each
`timescale 1ns/1ps
package edges_pkg;
    import fw_hdl_pkg::*;
    typedef bit [7:0] ebyte_t;

    // Root domain: o.data is the number of edges stepped.
    class e_cnt extends fw_component implements fw_steppable;
        fw_rv_sp_out #(ebyte_t) o;
        ebyte_t n;
        function new(string name, fw_component parent);
            super.new(name, parent);
            o = new(null, "o", this);
            add_steppable(this);
        endfunction
        virtual function void step();
            n++;
            o.set_data(n);
        endfunction
    endclass

    // A ÷2 domain: logs its source's register and the time at each edge.
    class e_div extends fw_component implements fw_steppable;
        fw_rv_sp_in #(ebyte_t) i;
        ebyte_t  got[$];
        realtime at[$];
        function new(string name, fw_component parent);
            super.new(name, parent);
            i = new(null, "i", this);
            add_steppable(this);
        endfunction
        virtual function void step();
            got.push_back(i.get_data());
            at.push_back($realtime);
        endfunction
    endclass

    // The period root's own sync participant, so a kernel owns that root.
    class e_pcnt extends fw_component implements fw_steppable;
        int unsigned n;
        function new(string name, fw_component parent);
            super.new(name, parent);
            add_steppable(this);
        endfunction
        virtual function void step(); n++; endfunction
    endclass
endpackage

module edges_tb;
    import fw_hdl_pkg::*;
    import edges_pkg::*;

    int errors;

    task automatic check(string what, bit ok, string got = "");
        if (!ok) begin
            errors++;
            $display("FAIL: %s %s", what, got);
        end
    endtask

    // Root clock: rises at 5, 15, 25, ... (edge k at 10k - 5).
    logic clk = 0, rst = 0;
    always #5 clk = ~clk;
    fw_clock_xtor_if cif(.clock(clk), .reset(rst));

    // Period roots.
    fw_clock_period_xtor #(.PERIOD(10ns))  pxt();
    fw_clock_period_xtor #(.PERIOD(3.3ns)) p33();

    // A clock that starts at X: rises (X -> 1) at 2 and (0 -> 1) at 10, and
    // goes 0 -> X -> 1 at 15, 17, 20: three edges.
    logic clk_x;
    initial begin
        #2  clk_x = 1;
        #3  clk_x = 0;
        #5  clk_x = 1;
        #3  clk_x = 0;
        #2  clk_x = 0;
        #2  clk_x = 'x;
        #3  clk_x = 1;
        #3  clk_x = 0;
    end
    fw_clock_xtor_if xif(.clock(clk_x), .reset(rst));

    fw_component                top;
    fw_clock_xtor_bridge        rb, xb;
    fw_clock_period_xtor_bridge pb, qb;
    fw_clock_domain             d2;
    e_cnt                       cnt;
    e_div                       dv;
    e_pcnt                      pc;
    fw_sync_kernel              k;

    initial begin
        realtime ta[$], tb[$], tc[$], pa[$], pp[$], q[$], tx[$];
        realtime rel_t;
        ebyte_t  rel_n;
        top = new("top", null);
        rb  = new("rb", top, cif);
        xb  = new("xb", top, xif);
        pb  = new("pb", top, pxt.u_if);
        qb  = new("qb", top, p33.u_if);
        d2  = new("d2", top, 2);
        d2.src.connect(rb);
        cnt = new("cnt", top);
        dv  = new("dv", top);
        pc  = new("pc", top);
        cnt.clock.connect(rb);
        dv.clock.connect(d2);
        pc.clock.connect(pb);
        cnt.o.connect(dv.i);
        k = new("top");
        k.elaborate(top);

        fork
            // phase: from time 0, from just after root edge 1, from 20.
            repeat (3) begin d2.tick(1); ta.push_back($realtime); end
            begin rb.tick(1); repeat (3) begin d2.tick(1); tb.push_back($realtime); end end
            begin #20; repeat (3) begin d2.tick(1); tc.push_back($realtime); end end
            // period: from 0 and from 3.
            repeat (3) begin pb.tick(1); pa.push_back($realtime); end
            begin #3; repeat (3) begin pb.tick(1); pp.push_back($realtime); end end
            // p33
            repeat (30) begin qb.tick(1); q.push_back($realtime); end
            // x
            repeat (3) begin xb.tick(1); tx.push_back($realtime); end
            // late: the kernel is launched at 23, between root edges.
            begin #23; k.launch(); end
        join

        // release: at an owned root's edge, the task sees that edge's update.
        rb.tick(1);
        rel_t = $realtime;
        rel_n = cnt.o.sig.data_cur;
        // delay: 200 is period edge 20; tick(1) then goes to edge 21.
        #(200 - $realtime);
        pb.tick(1);
        check("delay: tick(1) after a delay ending at a period edge",
              $realtime == 210, $sformatf("@%0t", $realtime));
        // Run on so the ÷2 domain has several edges.
        #100;

        if ($test$plusargs("show")) begin
            foreach (ta[i]) $display("ta %0d %0t", i, ta[i]);
            foreach (tb[i]) $display("tb %0d %0t", i, tb[i]);
            foreach (tc[i]) $display("tc %0d %0t", i, tc[i]);
        end
        foreach (ta[i]) check("phase A", ta[i] == 15 + 20 * i, $sformatf("@%0t", ta[i]));
        foreach (tb[i]) check("phase B", tb[i] == 15 + 20 * i, $sformatf("@%0t", tb[i]));
        foreach (tc[i]) check("phase C", tc[i] == 35 + 20 * i, $sformatf("@%0t", tc[i]));
        foreach (pa[i]) check("period A", pa[i] == 10 * (i + 1), $sformatf("@%0t", pa[i]));
        foreach (pp[i]) check("period B", pp[i] == 10 * (i + 1), $sformatf("@%0t", pp[i]));
        foreach (q[i]) begin
            automatic realtime t = 3.3 * (i + 1);
            check("p33", q[i] > t - 0.0006 && q[i] < t + 0.0006,
                  $sformatf("edge %0d @%0t, not %0t", i + 1, q[i], t));
        end
        check("x: edges", xif.n_edges == 3, $sformatf("%0d", xif.n_edges));
        check("x: times", tx.size() == 3 && tx[0] == 2 && tx[1] == 10 && tx[2] == 20,
              $sformatf("%0d: @%0t @%0t @%0t", tx.size(), tx[0], tx[1], tx[2]));
        // The kernel steps cnt from root edge 3 (25) on, so at root edge e
        // it has stepped e - 2 times; the task at rel_t sees that edge's
        // update.
        check("release", rel_n == int'((rel_t + 5) / 10) - 2,
              $sformatf("@%0t n=%0d", rel_t, rel_n));
        // ÷2 edges after the launch: root edges 4, 6, ... (35, 55, ...); at
        // each, the source's register from before the edge: 1, 3, 5, ...
        check("late: edges", dv.at.size() >= 5, $sformatf("%0d", dv.at.size()));
        foreach (dv.at[i]) begin
            check("late", dv.at[i] == 35 + 20 * i, $sformatf("@%0t", dv.at[i]));
            check("group", dv.got[i] == 1 + 2 * i,
                  $sformatf("edge %0d: %0d", i, dv.got[i]));
        end
        check("period root stepped", pc.n >= 5, $sformatf("%0d", pc.n));

        if (errors == 0) $display("PASS: edges");
        else             $display("FAIL: edges: %0d errors", errors);
        $finish;
    end
endmodule
