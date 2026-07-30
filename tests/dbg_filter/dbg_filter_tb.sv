// D-7b: volume control -- the SITE axis and the SUBJECT axis.
//
// Levels and context paths handle "this subsystem, this deep". They do not
// handle the shape that actually floods a trace: ONE site, in ONE context,
// firing every round, about a DIFFERENT endpoint each time. Arbitration is
// exactly that, and it is not an unusual case -- schedulers, crossbars, port
// pickers and credit managers all look like it.
//
// So there are two more axes, and this bench pins down both, including the
// properties that are easy to get subtly wrong:
//
//   * a site glob narrows a directive to matching SITE NAMES, so one noisy site
//     can be quietened without quietening the context it lives in;
//   * a subject mask keeps only the events about chosen ENDPOINTS, and leaves
//     events that name no endpoint completely alone;
//   * "cannot express it" always means ALLOW -- an out-of-range subject is
//     never silently dropped;
//   * a site born after apply() gets the same treatment as one born before it.
module dbg_filter_tb;
    import fw_hdl_pkg::*;
    `include "dbg/fw_dbg_macros.svh"

    int errors = 0;

    function automatic void chk(bit cond, string msg);
        if (!cond) begin $display("FAIL: %s", msg); errors++; end
    endfunction

    function automatic void chk_eq(int got, int exp, string msg);
        if (got != exp) begin
            $display("FAIL: %s (got %0d, expected %0d)", msg, got, exp);
            errors++;
        end
    endfunction

    // ---- the model under observation ---------------------------------------
    // Two sites in ONE component, so every filtering result below is a
    // statement about sites and subjects and NOT about context paths -- which
    // is the whole point of adding these axes.
    class talker extends fw_component;
        // Counts argument evaluations, so the G2 claim ("a disabled site
        // evaluates nothing") stays checkable as the gate grows conditions.
        int evals;

        function new(string name, fw_component parent = null);
            super.new(name, parent);
        endfunction

        function int bump();
            evals++;
            return evals;
        endfunction

        // The arbitration shape: one site, N endpoints.
        function void arb(int ch);
            `fw_ev_decision(dbg_if(), FW_L_OP, "t.arb")
                `fw_subject(ch)
                `fw_field_as("ch", ch)
                `fw_field_as("seq", bump())
                `fw_dec_winner(longint'(ch))
            `fw_ev_end
        endfunction

        // Same context, same level, no endpoint axis. Must survive every
        // subject filter untouched.
        function void tick();
            `fw_ev_state(dbg_if(), FW_L_OP, "t.tick")
                `fw_field_as("n", bump())
            `fw_ev_end
        endfunction

        // A subject the 64-bit mask cannot represent.
        function void far();
            `fw_ev_decision(dbg_if(), FW_L_OP, "t.far")
                `fw_subject(200)
            `fw_ev_end
        endfunction
    endclass

`ifdef FW_TRACE_OFF

    // G1: with the facility compiled out there is nothing to filter, and the
    // control API must still COMPILE -- benches call cfg()/cfg_subjects()
    // unconditionally and are not going to `ifdef` around them.
    initial begin
        automatic fw_dbg_root dbg = new("top");
        automatic talker      t   = new("t");
        dbg.cfg("*", .sites("t.arb"), .level(int'(FW_L_OFF)));
        dbg.cfg_subjects("*", "t.arb", fw_dbg_subj_mask("1,2"));
        dbg.apply();
        t.arb(1); t.tick(); t.far();
        chk_eq(t.evals, 0, "FW_TRACE_OFF: no argument was evaluated");
        chk_eq(dbg.num_enabled(), 0, "FW_TRACE_OFF: nothing is enabled");
        if (errors == 0) $display("[dbg_filter] PASS (FW_TRACE_OFF)");
        else begin $display("[dbg_filter] FAIL (%0d errors)", errors); $fatal(1, "FAIL"); end
        $finish;
    end

`else

    class rec_listener extends fw_dbg_listener;
        fw_dbg_rec recs[$];
        virtual function void on_decision(fw_decision_ctx d); recs.push_back(d.snapshot()); endfunction
        virtual function void on_state   (fw_state_ctx    s); recs.push_back(s.snapshot()); endfunction
        function void clear(); recs.delete(); endfunction

        function int count(string site_name);
            int n = 0;
            foreach (recs[i]) begin
                fw_dbg_site s = fw_dbg_catalog::site(recs[i].site_id);
                if (s != null && s.name() == site_name) n++;
            end
            return n;
        endfunction

        // Which subjects were actually delivered for `site_name`, as a mask.
        function longint subjects_of(string site_name);
            longint m = 0;
            foreach (recs[i]) begin
                fw_dbg_site s = fw_dbg_catalog::site(recs[i].site_id);
                if (s != null && s.name() == site_name && recs[i].subject >= 0
                              && recs[i].subject <= FW_DBG_MAX_SUBJECT)
                    m |= (64'd1 << recs[i].subject);
            end
            return m;
        endfunction
    endclass

    fw_dbg_root dbg = new("top");

    initial begin
        automatic rec_listener log = new();
        automatic talker       t;
        automatic int          before_evals;

        dbg.add_listener(log, FW_K_ALL, FW_L_TRACE);

        // --------------------------------------------------------------------
        // 0. The allow-list parser. It takes text off a command line, so its
        //    failure mode is a filter that silently selects the wrong endpoints
        //    -- worth pinning down directly rather than through behavior.
        // --------------------------------------------------------------------
        chk_eq(int'(fw_dbg_subj_mask("1,2,3")), 32'b1110, "subj_mask list");
        chk_eq(int'(fw_dbg_subj_mask("0-2,7")), 32'b1000_0111, "subj_mask range + single");
        chk_eq(int'(fw_dbg_subj_mask("2")),     32'b100,  "subj_mask singleton");
        chk_eq(int'(fw_dbg_subj_mask("")),      0,        "subj_mask empty selects nothing");
        chk(fw_dbg_subj_mask("0-63") == FW_DBG_SUBJ_ALL,  "subj_mask full range");
        // Out-of-range entries are dropped rather than wrapping into bit 0 --
        // wrapping would silently show the WRONG endpoint, which is worse than
        // showing none.
        chk_eq(int'(fw_dbg_subj_mask("64")),    0,        "subj_mask drops out-of-range");

        // --------------------------------------------------------------------
        // 1. Unfiltered baseline.
        // --------------------------------------------------------------------
        t = new("t");
        t.set_dbg_domain(dbg);
        dbg.apply();

        for (int i = 0; i < 4; i++) t.arb(i);
        t.tick();
        chk_eq(log.count("t.arb"),  4, "baseline: every round delivered");
        chk_eq(log.count("t.tick"), 1, "baseline: the subject-less site delivered");

        // --------------------------------------------------------------------
        // 2. SITE axis: mute one site, and prove its neighbour in the SAME
        //    context is untouched. This is the property a level clamp cannot
        //    give you, and the reason the site glob exists.
        // --------------------------------------------------------------------
        log.clear();
        dbg.cfg("*", .sites("t.arb"), .level(int'(FW_L_OFF)));
        dbg.apply();

        before_evals = t.evals;
        for (int i = 0; i < 4; i++) t.arb(i);
        t.tick();
        chk_eq(log.count("t.arb"),  0, "site mute: the muted site is silent");
        chk_eq(log.count("t.tick"), 1, "site mute: its neighbour still speaks");
        // G2 through the new axis: a site muted by name is fully gated, so its
        // payload expressions never run. Muting must be a saving, not a filter.
        chk_eq(t.evals - before_evals, 1, "site mute: only the live site evaluated arguments");

        // --------------------------------------------------------------------
        // 3. SUBJECT axis: the site stays enabled; only chosen endpoints are
        //    delivered.
        // --------------------------------------------------------------------
        log.clear();
        dbg.clear_cfg();
        dbg.cfg_subjects("*", "t.arb", fw_dbg_subj_mask("1,2"));
        dbg.apply();

        before_evals = t.evals;
        for (int i = 0; i < 4; i++) t.arb(i);
        t.tick();
        chk_eq(log.count("t.arb"), 2, "subject filter: only the selected endpoints");
        chk(log.subjects_of("t.arb") == fw_dbg_subj_mask("1,2"),
            "subject filter: and exactly those endpoints");
        chk_eq(log.count("t.tick"), 1, "subject filter: a subject-less site is unaffected");
        // The honest cost: a subject filter runs AFTER the gate, so the payload
        // was still built. It saves sink and storage work, not emit work. If
        // that is the cost you are trying to remove, mute the site.
        chk_eq(t.evals - before_evals, 5, "subject filter: arguments still evaluated (by design)");

        // --------------------------------------------------------------------
        // 4. A subject the mask cannot represent is ALLOWED through. A filter
        //    is a way to see less; it must never become a way to miss the case
        //    nobody anticipated.
        // --------------------------------------------------------------------
        log.clear();
        t.far();
        chk_eq(log.count("t.far"), 1, "unrepresentable subject is delivered, not dropped");

        // --------------------------------------------------------------------
        // 5. The filter is scoped to the sites the directive names.
        // --------------------------------------------------------------------
        log.clear();
        dbg.clear_cfg();
        dbg.cfg_subjects("*", "t.nothing_matches", fw_dbg_subj_mask("1"));
        dbg.apply();
        for (int i = 0; i < 4; i++) t.arb(i);
        chk_eq(log.count("t.arb"), 4, "a directive naming other sites does not filter this one");

        // --------------------------------------------------------------------
        // 6. Sites born AFTER apply() take the same configuration. The lazy
        //    resolution path is a separate branch from the eager one, and a
        //    filter that quietly stops applying to late sites would be a hole
        //    exactly where someone is looking hardest.
        // --------------------------------------------------------------------
        log.clear();
        dbg.clear_cfg();
        // `late.m*` deliberately matches only ONE of the two sites registered
        // below -- a directive that happened to match both would prove nothing
        // about the glob.
        dbg.cfg("*", .sites("late.m*"), .level(int'(FW_L_OFF)));
        dbg.cfg_subjects("*", "t.arb", fw_dbg_subj_mask("3"));
        dbg.apply();
        begin
            // Registered here, well past apply(), the way an fw_event_set built
            // inside run() is.
            automatic int unsigned sid_late = FW_DBG_NO_SITE;
            automatic int unsigned sid_new  = FW_DBG_NO_SITE;
            `fw_dbg_site_inst(sid_late, "late.muted", FW_DBG_STATE, FW_L_OP)
            `fw_dbg_site_inst(sid_new,  "late.other", FW_DBG_STATE, FW_L_OP)
            chk(!dbg.enabled(sid_late), "late site: matched a mute directive");
            chk( dbg.enabled(sid_new),  "late site: unmatched sites stay enabled");
        end
        for (int i = 0; i < 4; i++) t.arb(i);
        chk_eq(log.count("t.arb"), 1, "late apply: subject filter still in force");

        // --------------------------------------------------------------------
        // 7. Directives are last-match-wins across BOTH axes, so a broad rule
        //    can be narrowed by a specific one -- the shape every real
        //    configuration ends up having.
        // --------------------------------------------------------------------
        log.clear();
        dbg.clear_cfg();
        dbg.cfg("*", .level(int'(FW_L_OFF)));                    // everything off
        dbg.cfg("*", .sites("t.arb"), .level(int'(FW_L_TRACE))); // ...except one site
        dbg.apply();
        for (int i = 0; i < 4; i++) t.arb(i);
        t.tick();
        chk_eq(log.count("t.arb"),  4, "only-this-site: the named site survives");
        chk_eq(log.count("t.tick"), 0, "only-this-site: everything else is off");

        if (errors == 0) $display("[dbg_filter] PASS");
        else begin $display("[dbg_filter] FAIL (%0d errors)", errors); $fatal(1, "FAIL"); end
        $finish;
    end

`endif
endmodule
