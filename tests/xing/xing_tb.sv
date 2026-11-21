// Crossing ports (sync-task-domains.md §6.6, step X3; fw-hdl-spec
// semantics/processes.md, "Crossings"): task code reading and writing sync
// fields. Built and run by tests/python/system/test_xing_sim.py; prints PASS
// or FAIL lines. The cases follow the spec's xing_* conformance scenarios.
//
//   sample   at an edge, a read returns the value from before it, even after
//            a write at the edge; between edges, the current value (C2)
//   drive    a write at an edge is read by the next edge's step()s (C3)
//   twice    two task writes sampled by one edge: FW-E-XING-DRIVE-TWICE,
//            the second ignored, from one thread (a, b) or two (e); one
//            per edge is fine (c); a second write by the same thread in
//            the same time step that restores the value from before the
//            first undoes it (u) (C5)
//   default  a step()'s default (drop valid after a handshake) and a task's
//            put at the same edge: the put wins; back-to-back puts with one
//            stall, no idle cycle and no repeated beat (C5)
`timescale 1ns/1ps
package xing_pkg;
    import fw_hdl_pkg::*;
    typedef bit [7:0] xbyte_t;

    // The ports that task code drives (a, b, c, e, u), and their reader.
    class x_out extends fw_component;
        fw_rv_sp_out #(xbyte_t) a, b, c, e, u;
        function new(string name, fw_component parent);
            super.new(name, parent);
            a = new(null, "a", this);
            b = new(null, "b", this);
            c = new(null, "c", this);
            e = new(null, "e", this);
            u = new(null, "u", this);
        endfunction
    endclass

    // Logs a, b, c, e and u at each edge (what the step()s read).
    class x_log extends fw_component implements fw_steppable;
        fw_rv_sp_in #(xbyte_t) a, b, c, e, u;
        xbyte_t ga[$], gb[$], gc[$], ge[$], gu[$];
        function new(string name, fw_component parent);
            super.new(name, parent);
            a = new(null, "a", this);
            b = new(null, "b", this);
            c = new(null, "c", this);
            e = new(null, "e", this);
            u = new(null, "u", this);
            add_steppable(this);
        endfunction
        virtual function void step();
            ga.push_back(a.get_data());
            gb.push_back(b.get_data());
            gc.push_back(c.get_data());
            ge.push_back(e.get_data());
            gu.push_back(u.get_data());
        endfunction
    endclass

    // The initiator: its step() drops valid after a handshake (the
    // default); put() raises it (the task's drive) and returns at the
    // handshake edge.
    class x_drv extends fw_component implements fw_steppable;
        fw_rv_sp_out #(xbyte_t) out;
        function new(string name, fw_component parent);
            super.new(name, parent);
            out = new(null, "out", this);
            add_steppable(this);
        endfunction
        virtual function void step();
            if (out.get_valid() && out.get_ready()) out.set_valid(0);
        endfunction
        task put(xbyte_t d);
            out.set_valid(1);
            out.set_data(d);
            do clock.get_if().tick(1);
            while (!(out.get_valid() && out.get_ready()));
        endtask
    endclass

    // Takes a beat on valid and ready; ready is comb, low for the cycle
    // after the sink's third edge (a one-cycle stall). Logs valid and data
    // at each edge, and the beats.
    class x_snk extends fw_component implements fw_steppable, fw_combinational;
        fw_rv_sp_in #(xbyte_t) in;
        int unsigned c;
        bit          s;
        bit          gv[$];
        xbyte_t      gd[$], beats[$];
        int unsigned beat_e[$];
        function new(string name, fw_component parent);
            super.new(name, parent);
            in = new(null, "in", this);
            add_steppable(this);
            add_comb(this);
        endfunction
        virtual function void comb();
            in.set_ready(in.get_valid() && !s);
        endfunction
        virtual function void step();
            gv.push_back(in.get_valid());
            gd.push_back(in.get_data());
            if (in.get_valid() && in.get_ready()) begin
                beats.push_back(in.get_data());
                beat_e.push_back(gv.size());
            end
            s = (c == 3);
            c++;
        endfunction
    endclass
endpackage

module xing_tb;
    import fw_hdl_pkg::*;
    import xing_pkg::*;

    int errors;

    task automatic check(string what, bit ok, string got = "");
        if (!ok) begin
            errors++;
            $display("FAIL: %s %s", what, got);
        end
    endtask

    // Edge k at 10k - 5.
    logic clk = 0, rst = 0;
    always #5 clk = ~clk;
    fw_clock_xtor_if cif(.clock(clk), .reset(rst));

    fw_component         top;
    fw_clock_xtor_bridge rb;
    x_out                o;
    x_log                lg;
    x_drv                d;
    x_snk                k;
    fw_sync_kernel       kern;

    initial begin
        xbyte_t at_a, at_b, mid_b;
        top  = new("top", null);
        rb   = new("rb", top, cif);
        o    = new("o", top);
        lg   = new("lg", top);
        d    = new("d", top);
        k    = new("k", top);
        o.clock.connect(rb);
        lg.clock.connect(rb);
        d.clock.connect(rb);
        k.clock.connect(rb);
        o.a.connect(lg.a);
        o.b.connect(lg.b);
        o.c.connect(lg.c);
        o.e.connect(lg.e);
        o.u.connect(lg.u);
        d.out.connect(k.in);
        k.in.sig.set_comb("ready");
        kern = new("top");
        kern.elaborate(top);
        fw_sig_holder::fatal_on_rule = 0;
        kern.launch();

        fork
            begin   // twice, sample, drive
                rb.tick(3);                    // edge 3 (25)
                o.a.set_data(1);
                at_a = o.a.get_data();         // before edge 3: 0
                o.a.set_data(2);               // FW-E-XING-DRIVE-TWICE, ignored
                o.b.set_data(1);
                at_b = o.b.get_data();
                o.c.set_data(1);
                o.e.set_data(1);               // e: one of two threads
                o.u.set_data(1);
                o.u.set_data(0);               // restores 0: undoes 1
                o.u.set_data(5);               // the edge's only write of u
                #5;                            // 30, between edges 3 and 4
                mid_b = o.b.get_data();        // current: 1
                o.b.set_data(2);               // sampled by edge 4 too: ignored
                rb.tick(1);                    // edge 4
                o.c.set_data(2);               // sampled by edge 5: fine
            end
            begin   // twice: a second thread writes e at edge 3
                rb.tick(3);
                o.e.set_data(3);
            end
            begin   // default
                rb.tick(3);
                for (int i = 1; i <= 3; i++) d.put(xbyte_t'(i));
            end
        join
        rb.tick(3);                            // to edge 7, then 2 more
        rb.tick(2);

        check("sample: at the edge, after a write", at_a == 0, $sformatf("%0d", at_a));
        check("sample: at the edge", at_b == 0, $sformatf("%0d", at_b));
        check("sample: between edges", mid_b == 1, $sformatf("%0d", mid_b));
        check("twice: errors", fw_sig_holder::rule_errs == 3,
              $sformatf("%0d: %s", fw_sig_holder::rule_errs, fw_sig_holder::rule_err));
        check("twice: id", fw_sig_holder::rule_err.substr(0, 20) == "FW-E-XING-DRIVE-TWICE",
              fw_sig_holder::rule_err);
        // lg's step()s at edges 1..5 (index e - 1).
        check("drive/twice: edges", lg.ga.size() >= 5, $sformatf("%0d", lg.ga.size()));
        foreach (lg.ga[i]) if (i < 5) begin
            check("drive/twice: a", lg.ga[i] == ((i >= 3) ? 1 : 0),
                  $sformatf("edge %0d: %0d", i + 1, lg.ga[i]));
            check("drive/twice: b", lg.gb[i] == ((i >= 3) ? 1 : 0),
                  $sformatf("edge %0d: %0d", i + 1, lg.gb[i]));
            check("drive/twice: c", lg.gc[i] == ((i == 4) ? 2 : (i == 3) ? 1 : 0),
                  $sformatf("edge %0d: %0d", i + 1, lg.gc[i]));
            // e: whichever thread wrote first
            check("drive/twice: e", (i < 3) ? lg.ge[i] == 0 : (lg.ge[i] == 1 || lg.ge[i] == 3),
                  $sformatf("edge %0d: %0d", i + 1, lg.ge[i]));
            check("undo: u", lg.gu[i] == ((i >= 3) ? 5 : 0),
                  $sformatf("edge %0d: %0d", i + 1, lg.gu[i]));
        end
        // default: valid and data at edges 1..8, as the spec's trace; beats
        // 1, 2, 3 at edges 4, 6, 7.
        check("default: edges", k.gv.size() >= 8, $sformatf("%0d", k.gv.size()));
        for (int i = 0; i < 8 && i < k.gv.size(); i++) begin
            automatic bit     ev = (i >= 3 && i <= 6);
            automatic xbyte_t ed = (i < 3) ? 0 : (i == 3) ? 1 : (i <= 5) ? 2 : 3;
            check("default: valid", k.gv[i] == ev, $sformatf("edge %0d: %0d", i + 1, k.gv[i]));
            check("default: data", k.gd[i] == ed, $sformatf("edge %0d: %0d", i + 1, k.gd[i]));
        end
        check("default: beats", k.beats.size() == 3 && k.beats[0] == 1 && k.beats[1] == 2
              && k.beats[2] == 3 && k.beat_e[0] == 4 && k.beat_e[1] == 6 && k.beat_e[2] == 7,
              $sformatf("%0d beats", k.beats.size()));

        if (errors == 0) $display("PASS: xing");
        else             $display("FAIL: xing: %0d errors", errors);
        $finish;
    end
endmodule
