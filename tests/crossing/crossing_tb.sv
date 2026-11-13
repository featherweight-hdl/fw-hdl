// Domain crossing analysis (fw_crossing_check). Each case builds a tree, seats
// its root clock and reset, runs build and connect, and calls
// fw_crossing_check::run() -- no $fatal -- then checks what was found.
//
// With +xc_start the testbench instead runs one tree with a crossing error
// through fw_component_root::start(), which reports and $fatals (or, with
// +fw_crossings_nofatal, writes the JSON and continues); the Python suite
// (tests/python/system/test_crossing_sim.py) checks those runs.
module crossing_tb;
    import fw_hdl_pkg::*;
    import xc_pkg::*;

    logic clk_a = 0, clk_b = 0;
    always #5  clk_a = ~clk_a;
    always #7  clk_b = ~clk_b;

    fw_clock_xtor_if u_clk_a(.clock(clk_a), .reset(1'b0));
    fw_clock_xtor_if u_clk_b(.clock(clk_b), .reset(1'b0));
    fw_reset_xtor_if u_rst_a(.clock(clk_a), .reset(1'b0));
    fw_reset_xtor_if u_rst_b(.clock(clk_b), .reset(1'b0));

    fw_clock_xtor_bridge ck_a, ck_b;
    fw_reset_xtor_bridge rs_a, rs_b;

    int errors = 0;
    function automatic void chk(bit cond, string what);
        if (!cond) begin $display("FAIL: %s", what); errors++; end
        else       $display("  ok: %s", what);
    endfunction

    // Seat the root domains, build, connect, check.
    function automatic int run_case(fw_component top, ref fw_crossing found[$]);
        top.clock.connect(ck_a);
        top.reset.connect(rs_a);
        top.do_build();
        top.do_connect();
        found.delete();
        return fw_crossing_check::run(top, found);
    endfunction

    function automatic void show(ref fw_crossing found[$]);
        foreach (found[i]) $display("    %s", found[i].line());
    endfunction

    // The crossings found by one route.
    function automatic void only(ref fw_crossing found[$], input string via, ref fw_crossing out[$]);
        out.delete();
        foreach (found[i]) if (found[i].via == via) out.push_back(found[i]);
    endfunction

    class xc_root_clk2 extends fw_component_root #(xc_top_clk2);
        function new(string name); super.new(name); endfunction
    endclass

    initial begin
        ck_a = new("clk_a", null, u_clk_a);
        ck_b = new("clk_b", null, u_clk_b);
        rs_a = new("rst_a", null, u_rst_a); rs_a.clk.connect(ck_a);
        rs_b = new("rst_b", null, u_rst_b); rs_b.clk.connect(ck_b);
        xc_env::clk_b = ck_b;
        xc_env::rst_a = rs_a;
        xc_env::rst_b = rs_b;

        if ($test$plusargs("xc_start")) begin
            // One run through start(): it reports, and $fatals unless
            // +fw_crossings_nofatal.
            xc_root_clk2 r = new("top");
            r.clock.connect(ck_a);
            r.reset.connect(rs_a);
            fork r.start(); join_none
            while (!r.elaborated) @(posedge clk_a);
            $display("[crossing] start() continued past the check");
            $finish;
        end else begin
            run_cases();
        end
    end

    task automatic run_cases();
        fw_crossing found[$];
        fw_crossing b[$], rs[$];
        int nerr;

        begin   // 1
            xc_top_one t = new("top", null);
            nerr = run_case(t, found); show(found);
            chk(found.size() == 0 && nerr == 0, "one domain: nothing");
        end
        begin   // 2
            xc_top_div t = new("top", null);
            nerr = run_case(t, found); show(found);
            chk(found.size() == 1 && nerr == 0, "/2 child: one crossing, no error");
            if (found.size() == 1)
                chk(found[0].kind == FW_DOMAIN_CLOCK && found[0].rel == FW_DOMAIN_RELATED
                    && found[0].sev == FW_XSEV_INFO && found[0].via == "binding"
                    && found[0].from == "top.a.out" && found[0].to == "top.b.in_ex",
                    "/2 child: clock related binding, info, top.a.out -> top.b.in_ex");
        end
        begin   // 3
            xc_top_clk2 t = new("top", null);
            nerr = run_case(t, found); show(found);
            only(found, "binding", b); only(found, "reset-sync", rs);
            chk(b.size() == 1 && nerr == 2, "second root clock: one binding error (and a reset-sync one)");
            if (b.size() == 1)
                chk(b[0].kind == FW_DOMAIN_CLOCK && b[0].rel == FW_DOMAIN_UNRELATED
                    && b[0].sev == FW_XSEV_ERROR && b[0].from_dom == "clk_b"
                    && b[0].to_dom == "clk_a",
                    "second root clock: clock unrelated binding, error, clk_b -> clk_a");
            // a keeps the root reset, which deasserts on clk_a: an RDC
            chk(rs.size() == 1 && rs[0].from == "top.a" && rs[0].to_dom == "clk_b",
                "second root clock: a's inherited reset is not synchronized to clk_b");
        end
        begin   // 4
            xc_top_soft t = new("top", null);
            nerr = run_case(t, found); show(found);
            chk(found.size() == 1 && nerr == 0, "reg-bit child: one crossing, no error");
            if (found.size() == 1)
                chk(found[0].kind == FW_DOMAIN_RESET && found[0].rel == FW_DOMAIN_RELATED
                    && found[0].sev == FW_XSEV_WARN && found[0].from_dom == "top.ch_rst"
                    && found[0].to_dom == "rst_a" && found[0].waiver == "",
                    "reg-bit child: reset related binding, warn");
        end
        begin   // 4, waived
            xc_top_soft t = new("top", null, 1);
            nerr = run_case(t, found); show(found);
            chk(found.size() == 1 && found[0].sev == FW_XSEV_INFO
                && found[0].waiver == "a drains before ctrl[3] is set",
                "reg-bit child, waived: info with the reason");
        end
        begin   // 5
            xc_top_elem t = new("top", null);
            nerr = run_case(t, found); show(found);
            chk(found.size() == 0, "crossing element: nothing");
        end
        begin   // 5, not declared
            xc_top_elem t = new("top", null, 1);
            nerr = run_case(t, found); show(found);
            chk(found.size() == 2 && nerr == 2 && found[0].via == "component"
                && found[0].from == "top.e.out" && found[0].to == "top.e"
                && found[1].via == "component" && found[1].from == "top.e.out",
                "same element without is_crossing(): component crossings (clock, reset) at top.e.out");
        end
        begin   // 6
            xc_top_sock t = new("top", null);
            bit fwd = 0, back = 0;
            nerr = run_case(t, found); show(found);
            only(found, "binding", b);
            foreach (b[i]) begin
                if (b[i].from == "top.a.s.i" && b[i].to == "top.b.m.i") fwd = 1;
                if (b[i].from == "top.b.m.e" && b[i].to == "top.a.s.e") back = 1;
            end
            chk(b.size() == 2 && fwd && back, "socket: both directions");
        end
        begin   // 7
            xc_top_fwd t = new("top", null);
            nerr = run_case(t, found); show(found);
            chk(found.size() == 1 && found[0].from == "top.w.s.out" && found[0].to == "top.b.in_ex",
                "forwarding parent: only the child's port, not the parent's forwarder");
        end
        begin   // 8
            xc_top_comb t = new("top", null);
            nerr = run_case(t, found); show(found);
            chk(found.size() == 1 && nerr == 1 && found[0].via == "reset-sync"
                && found[0].from == "top.a" && found[0].from_dom == "top.any",
                "combine of unrelated clocks: reset-sync error at top.a");
        end

        if (errors == 0) $display("[crossing] PASS");
        else             $fatal(1, "[crossing] FAIL (%0d errors)", errors);
        $finish;
    endtask
endmodule
