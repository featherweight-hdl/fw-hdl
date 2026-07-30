// D-1: the listener API and the domain tree.
//
// The claims under test are the ones the rest of the facility is built on:
//
//   * a domain IS a listener -- component -> domain -> domain -> sink is one
//     call set, and 1->N fan-out is a listener list, not a second mechanism;
//   * SUBSCRIPTION drives the gate: with nothing subscribed to a kind, sites of
//     that kind are disabled and (G2) their argument expressions never run;
//   * configuration CLAMPS that demand-driven default, per context, resolved
//     once at apply() into one bit per (domain, site) -- never a string compare
//     while the model runs;
//   * a context is BORROWED: valid for the callback, `snapshot()` to keep it.
module dbg_listener_tb;
    import fw_hdl_pkg::*;
    `include "dbg/fw_dbg_macros.svh"

    int errors = 0;

    function automatic void chk(bit cond, string msg);
        if (!cond) begin $display("FAIL: %s", msg); errors++; end
    endfunction

`ifdef FW_TRACE_OFF
    // Compiled out. The API classes still exist -- consumer code that names a
    // sink or a domain must still compile -- but no site emits, so a subscribed
    // listener sees nothing. That IS the check.
    initial begin
        automatic fw_dbg_root      root = new("top");
        automatic fw_dbg_sink_text sink = new();
        root.add_listener(sink);
        root.apply();
        chk(sink.count() == 0, "OFF: nothing emitted");
        chk(fw_dbg_catalog::num_sites() == 0, "OFF: no sites registered");
        if (errors == 0) $display("[dbg_listener] PASS (FW_TRACE_OFF)");
        else begin $display("[dbg_listener] FAIL (%0d errors)", errors); $fatal(1, "FAIL"); end
        $finish;
    end
`else

    // ------------------------------------------------------------------
    // A listener that counts what it is given, per kind.
    // ------------------------------------------------------------------
    class counting_listener extends fw_dbg_listener;
        int n_op, n_state, n_decision, n_sched, n_notice, n_link;
        // proof that the ORIGINATING domain is what gets stamped, not the last
        // hop the event passed through
        string     last_path;
        fw_dbg_rec kept;

        virtual function void on_op(fw_op_ctx op);
            n_op++;
            last_path = (op.ctx() != null) ? op.ctx().path() : "-";
            kept = op.snapshot();          // the sanctioned way to retain
        endfunction
        virtual function void on_state   (fw_state_ctx    st); n_state++;    endfunction
        virtual function void on_decision(fw_decision_ctx d);  n_decision++; endfunction
        virtual function void on_sched   (fw_sched_ctx    sc); n_sched++;    endfunction
        virtual function void on_notice  (fw_notice_ctx   n);  n_notice++;   endfunction
        virtual function void on_link    (fw_link_ctx     l);  n_link++;     endfunction

        function int total();
            return n_op + n_state + n_decision + n_sched + n_notice + n_link;
        endfunction
        function void clear();
            n_op = 0; n_state = 0; n_decision = 0; n_sched = 0; n_notice = 0; n_link = 0;
        endfunction
    endclass

    // A listener that keeps the BORROWED handle -- the mistake G4 exists to
    // catch. Only read back under FW_DBG_DEBUG, where the detector is compiled.
    class hoarding_listener extends fw_dbg_listener;
        fw_op_ctx stolen;
        virtual function void on_op(fw_op_ctx op); stolen = op; endfunction
    endclass

    // ------------------------------------------------------------------
    // The instrumented thing. It knows only a listener handle -- not a domain,
    // not a sink, not the configuration.
    // ------------------------------------------------------------------
    class toy;
        fw_dbg_listener_if dbg;
        int                n_evals;      // how often a payload expression ran

        function new(fw_dbg_listener_if d); dbg = d; endfunction

        // A payload expression with a side effect, standing in for the
        // `regs.csr.read()` and ready-vector builds of the real model.
        function int costly();
            n_evals++;
            return 7;
        endfunction

        function void emit_all();
            `fw_ev_op(dbg, FW_L_OP, "toy.op", FW_OP_BEGUN)
                `fw_field(3)
                `fw_op_tag(3)
            `fw_ev_end

            `fw_ev_state(dbg, FW_L_DETAIL, "toy.state")
                `fw_state_change(32'h0000_0001, 32'h0000_0003, FW_ACTOR_SW, 32'h0000_0004)
            `fw_ev_end

            `fw_ev_decision(dbg, FW_L_OP, "toy.arb")
                `fw_dec_winner(1)
                `fw_dec_cand(0, 2)
                `fw_dec_cand(1, 0)
            `fw_ev_end

            `fw_ev_sched(dbg, FW_L_OP, "toy.block")
                `fw_sched_set(FW_SCHED_BLOCK, 0, FW_DBG_NO_SITE)
            `fw_ev_end

            `fw_ev_link(dbg, FW_L_TXN, "toy.link")
                `fw_link_set(1, 2, FW_REL_WOKE)
            `fw_ev_end

            `fw_note(dbg, "toy.note")
        endfunction

        // One site whose payload is expensive. G2 is about this one.
        function void emit_gated();
            `fw_ev_notice(dbg, FW_SEV_INFO, FW_L_TXN, "toy.gated")
                `fw_field(costly())
            `fw_ev_end
        endfunction

        function void emit_assert(bit ok);
            `fw_assert_begin(dbg, ok, "toy.invariant")
                `fw_field(ok)
            `fw_assert_end
        endfunction
    endclass

    // ------------------------------------------------------------------
    // A three-level debug tree, wired independently of any component tree:
    //     top  <--  top.dma  <--  top.dma.de
    // ------------------------------------------------------------------
    fw_dbg_root   root = new("top");
    fw_dbg_domain mid  = new("dma");
    fw_dbg_domain leaf = new("de");

    initial begin
        automatic counting_listener all_l  = new();
        automatic counting_listener dec_l  = new();
        automatic counting_listener leaf_l = new();
        automatic fw_dbg_sink_text  sink   = new();
        automatic hoarding_listener hoard  = new();
        automatic toy               t;
        automatic int unsigned      sid_arb, sid_state;

        mid.connect_up(root);
        leaf.connect_up(mid);
        mid.do_connect();
        leaf.do_connect();

        t = new(leaf);
        chk(leaf.path() == "top.dma.de", $sformatf("debug path is hierarchical (got '%s')", leaf.path()));

        sid_arb   = fw_dbg_catalog::find("toy.arb").id();
        sid_state = fw_dbg_catalog::find("toy.state").id();

        // ===== 1. nothing subscribed => nothing enabled, nothing evaluated ===
        root.apply();
        chk(leaf.num_enabled() == 0, "no listeners => no site enabled");
        chk(!leaf.enabled(sid_arb),  "DECISION site disabled with nothing subscribed");
        t.emit_all();
        t.emit_gated();
        chk(t.n_evals == 0, "G2: a disabled site does not evaluate its payload");

        // ===== 2. subscribing at the ROOT enables sites at the LEAF ==========
        // An event emitted at the leaf is forwarded upward, so demand anywhere
        // above must light the leaf up. This is what makes "attach a sink at the
        // top and watch the whole subtree" work.
        root.add_listener(all_l, FW_K_ALL, FW_L_TRACE);
        root.apply();
        chk(leaf.enabled(sid_arb), "union: root subscription enables the leaf site");
        t.emit_all();
        chk(all_l.n_op       == 1, "OP delivered");
        chk(all_l.n_state    == 1, "STATE delivered");
        chk(all_l.n_decision == 1, "DECISION delivered");
        chk(all_l.n_sched    == 1, "SCHED delivered");
        chk(all_l.n_notice   == 1, "NOTICE delivered");
        chk(all_l.n_link     == 1, "LINK delivered");

        // the ORIGINATING domain is stamped, not the last hop
        chk(all_l.last_path == "top.dma.de",
            $sformatf("event is tagged with the emitting context (got '%s')", all_l.last_path));

        // snapshot() outlives the callback
        chk(all_l.kept != null && all_l.kept.site_id == fw_dbg_catalog::find("toy.op").id(),
            "snapshot() is the retention boundary");
        chk(all_l.kept.flow.size() == 1 && all_l.kept.flow[0] == 3,
            "flow tag survives into the record");

        // and the gated site now evaluates -- exactly once
        t.emit_gated();
        chk(t.n_evals == 1, "an enabled site evaluates its payload once");

        // ===== 3. kind mask filters delivery =================================
        all_l.clear();
        root.add_listener(dec_l, FW_K_DECISION, FW_L_TRACE);
        root.apply();
        t.emit_all();
        chk(dec_l.n_decision == 1, "kind-masked listener gets its kind");
        chk(dec_l.total()    == 1, "kind-masked listener gets NOTHING else");
        chk(all_l.total()    == 6, "1->N: the other listener still gets everything");

        // ===== 4. a listener on an INNER domain sees only that subtree =======
        leaf_l.clear();
        leaf.add_listener(leaf_l, FW_K_ALL, FW_L_TRACE);
        root.apply();
        begin
            automatic toy t_mid = new(mid);      // emits into top.dma, not the leaf
            all_l.clear();
            t_mid.emit_all();
            chk(all_l.total()  == 6, "root sees events from an inner domain");
            chk(leaf_l.total() == 0, "a leaf listener does NOT see its parent's events");
        end

        // ===== 5. configuration clamps, per context ==========================
        // Demand is unchanged (the root still wants everything); the leaf's
        // clamp is what silences it. Levels are the dial: TXN keeps the boundary
        // story, OP/DETAIL sites go quiet.
        all_l.clear();
        root.cfg("top.dma.de", .level(FW_L_TXN));
        root.apply();
        chk(!leaf.enabled(sid_arb),   "clamp: L_OP site off at L_TXN");
        chk(!leaf.enabled(sid_state), "clamp: L_DETAIL site off at L_TXN");
        chk(mid.enabled(sid_arb),     "clamp applies to the named context only");
        t.emit_all();
        chk(all_l.n_link   == 1, "clamped context still emits at/below its level");
        chk(all_l.n_op     == 0, "clamped context drops the OP site");
        chk(all_l.n_state  == 0, "clamped context drops the STATE site");

        // a glob reaches a subtree; kinds narrow orthogonally to level
        all_l.clear();
        root.clear_cfg();
        root.cfg("top.*", .kinds(FW_K_DECISION | FW_K_SCHED));
        root.apply();
        t.emit_all();
        chk(all_l.n_decision == 1 && all_l.n_sched == 1, "kind clamp keeps its kinds");
        chk(all_l.total()    == 2, "kind clamp drops every other kind");

        // ===== 6. assertions emit only when tripped ==========================
        all_l.clear();
        root.clear_cfg();
        root.apply();
        t.emit_assert(1'b1);
        chk(all_l.n_notice == 0, "a passing assertion emits nothing");
        t.emit_assert(1'b0);
        chk(all_l.n_notice == 1, "a tripped assertion emits one NOTICE");

        // ===== 7. borrowed contexts (G4) =====================================
`ifdef FW_DBG_DEBUG
        root.add_listener(hoard, FW_K_OP, FW_L_TRACE);
        root.apply();
        fw_dbg_ctx::m_poison_fatal = 0;          // detect, do not die
        t.emit_all();
        chk(fw_dbg_ctx::m_use_after_release == 0, "no violation while the callback runs");
        void'(hoard.stolen.stamp());             // the mistake
        chk(fw_dbg_ctx::m_use_after_release == 1,
            "G4: reading a context after its callback returned is detected");
        fw_dbg_ctx::m_poison_fatal = 1;
`endif

        // ===== 8. the text sink renders a legible stream =====================
        $display("--- text sink ---");
        root.clear_cfg();
        root.add_listener(sink, FW_K_ALL, FW_L_TRACE);
        root.apply();
        t.emit_all();
        chk(sink.count() == 6, "text sink saw every event");
        $display("--- end ---");

        if (errors == 0) $display("[dbg_listener] PASS");
        else begin
            $display("[dbg_listener] FAIL (%0d errors)", errors);
            $fatal(1, "[dbg_listener] FAIL");
        end
        $finish;
    end
`endif /* FW_TRACE_OFF */

endmodule
