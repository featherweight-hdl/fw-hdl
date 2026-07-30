// D-4: SCHED events, the live op stack, and fw_dbg_dump().
//
// This is the "seeing nothing" milestone. Every other kind reports something
// that happened; this one reports something that is NOT happening, which is the
// top integration question and the one a log of events structurally cannot
// answer -- because the answer is the absence of records.
//
// Two halves, and the second is the acceptance criterion:
//
//   1. STREAM  -- block{waiting_on} / wake{waker, blocked_for} around a wait, so
//                 a trace shows what a thread stopped for and who restarted it.
//   2. LIVE    -- a deliberately hung model, a watchdog that calls fw_dbg_dump(),
//                 and output that names the blocked thread, the operation it is
//                 inside, and every source it is waiting for.
module dbg_sched_tb;
    import fw_hdl_pkg::*;
    `include "dbg/fw_dbg_macros.svh"

    int errors = 0;

    function automatic void chk(bit cond, string msg);
        if (!cond) begin $display("FAIL: %s", msg); errors++; end
    endfunction

    class fake_clock extends fw_export #(fw_clock_domain_if)
            implements fw_clock_domain_if;
        function new(string name, fw_component parent);
            super.new(name, parent);
            set_imp(this);
        endfunction
        virtual task tick(int n = 1); #(n); endtask
        virtual function longint root_ticks(int n = 1); return n; endfunction
    endclass

    // ---- a bare event source, so the test does not lean on the register model
    // Registers its own instance site: that is the ONLY reason a wake can name
    // it, and the whole difference between "blocked on 2 things" and a diagnosis.
    class doorbell extends fw_component implements fw_awaitable_if;
        protected fw_event_set m_mons[$];
        protected int unsigned m_sid;

        function new(string name, fw_component parent);
            super.new(name, parent);
            `fw_dbg_site_inst(m_sid, name, FW_DBG_SCHED, FW_L_OP)
        endfunction

        virtual function void produce_to(fw_event_set s); m_mons.push_back(s); endfunction
        virtual function int unsigned dbg_site();         return m_sid;        endfunction

        function void ring();
            foreach (m_mons[i]) m_mons[i].notify(this);
        endfunction
    endclass

    // ---- the model: one runnable that waits on two doorbells ---------------
    class waiter extends fw_component implements fw_runnable;
        doorbell     a, b;
        fw_event_set wake;
        int          rounds;

        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);     // used as the root, so it registers with itself
        endfunction

        virtual function void build();
            a = new("bell_a", this);
            b = new("bell_b", this);
        endfunction

        virtual task run();
            wake = new("waiter.wake", this);
            wake.add(a);
            wake.add(b);
            forever begin
                wake.wait_any();
                rounds++;
            end
        endtask
    endclass

`ifdef FW_TRACE_OFF
    fw_component_root #(waiter) root = new("top");

    initial begin
        automatic fake_clock ck = new("clk", root);
        root.clock.connect(ck);
        root.start();
        #1;
        // G1: the wait behaves identically with every site removed.
        root.a.ring();  #1;
        root.b.ring();  #1;
        chk(root.rounds == 2,                 "OFF: the wait still wakes");
        chk(fw_dbg_catalog::num_sites() == 0, "OFF: no sites registered");
        root.fw_dbg_dump();                   // must be harmless, not fatal
        if (errors == 0) $display("[dbg_sched] PASS (FW_TRACE_OFF)");
        else begin $display("[dbg_sched] FAIL (%0d errors)", errors); $fatal(1, "FAIL"); end
        $finish;
    end
`else

    class rec_listener extends fw_dbg_listener;
        fw_dbg_rec recs[$];
        virtual function void on_sched(fw_sched_ctx sc); recs.push_back(sc.snapshot()); endfunction
        function void clear(); recs.delete(); endfunction
        // The nth (0-based) record of sub-kind `k`, or null.
        function fw_dbg_rec nth(fw_sched_kind_e k, int idx = 0);
            int n = 0;
            foreach (recs[i]) begin
                if (recs[i].sched_kind == k) begin
                    if (n == idx) return recs[i];
                    n++;
                end
            end
            return null;
        endfunction
        function int count(fw_sched_kind_e k);
            int n = 0;
            foreach (recs[i]) if (recs[i].sched_kind == k) n++;
            return n;
        endfunction
    endclass

    fw_dbg_root                 dbg  = new("top");
    fw_component_root #(waiter) root = new("top");

    // The site ids the assertions compare against, resolved once after start().
    int unsigned sid_a, sid_b, sid_wake;

    initial begin
        automatic rec_listener     log  = new();
        automatic fw_dbg_sink_text sink = new();
        automatic fake_clock       ck   = new("clk", root);
        automatic fw_dbg_rec       r;

        root.clock.connect(ck);
        dbg.add_listener(log,  FW_K_ALL, FW_L_TRACE);
        dbg.add_listener(sink, FW_K_ALL, FW_L_TRACE);
        root.set_dbg_domain(dbg);

        // Tracking is opt-in (see fw_dbg_track.svh). A test that wants the live
        // view asks for it, exactly as a run would with +fw_dbg_track.
        fw_dbg_track::set_enabled(1);

        root.start();
        #1;

        sid_a    = fw_dbg_catalog::find("bell_a").id();
        sid_b    = fw_dbg_catalog::find("bell_b").id();
        sid_wake = fw_dbg_catalog::find("waiter.wake").id();

        $display("--- scheduling ---");

        // ===== 1. a block names its whole wait set ==========================
        // The waiter is already parked in wait_any() at this point.
        r = log.nth(FW_SCHED_BLOCK);
        chk(r != null,                    "entering a wait is reported");
        if (r != null) begin
            chk(r.site_id == sid_wake,    "the block is attributed to the wait point");
            // fields: [blocked_for, waker, sources...]
            chk(r.fields.size() == 4,     "the block carries both sources");
            chk(r.fields[2] == longint'(sid_a),     "...naming the first by site");
            chk(r.fields[3] == longint'(sid_b),     "...and the second");
        end

        // ===== 2. the wake names WHO woke it ================================
        log.clear();
        #9;
        root.b.ring();
        #1;
        r = log.nth(FW_SCHED_WAKE);
        chk(r != null,                    "leaving a wait is reported");
        if (r != null) begin
            chk(r.fields[1] == longint'(sid_b),     "the wake names the source that fired");
            chk(r.fields[1] != longint'(sid_a),     "...and not the one that did not");
            chk(r.fields[0] == 10,        "the wake carries how long the thread was blocked");
        end
        chk(root.rounds == 1,             "the consumer actually ran");

        // ===== 3. the other producer, to prove it is not a fixed answer =====
        log.clear();
        root.a.ring();
        #1;
        r = log.nth(FW_SCHED_WAKE);
        chk(r != null && r.fields[1] == longint'(sid_a),
            "a wake from the other source names the other source");
        chk(root.rounds == 2,             "...and the consumer ran again");

        // ===== 4. the LIVE view: what is everyone waiting for right now =====
        // Nothing is being rung, so the waiter is parked. This is the state a
        // stream cannot report, because the model is producing no records.
        #10;
        begin
            automatic string d = fw_dbg_track::report();
            $display("--- fw_dbg_dump() while hung ---");
            root.fw_dbg_dump();
            chk(fw_dbg_track::num_blocked() >= 1, "the dump sees a blocked thread");
            // Everything a person needs to act: the wait point, both things it
            // could be woken by, and which run() the thread is inside.
            chk(dbg_has(d, "BLOCKED"),      "the dump says the thread is blocked");
            chk(dbg_has(d, "waiter.wake"),  "...at which wait point");
            chk(dbg_has(d, "bell_a"),       "...waiting on the first source");
            chk(dbg_has(d, "bell_b"),       "...and the second");
            chk(dbg_has(d, "top.run"),      "...inside which component's run()");
        end

        // ===== 5. tracking off means SAYING so, not an empty dump ===========
        begin
            automatic string d;
            fw_dbg_track::set_enabled(0);
            d = fw_dbg_track::report();
            chk(dbg_has(d, "+fw_dbg_track"),
                "with tracking off the dump explains how to turn it on");
            fw_dbg_track::set_enabled(1);
        end

        // ===== 6. levels: SCHED is trimmable like anything else =============
        log.clear();
        dbg.cfg("top", .level(FW_L_TXN));
        dbg.apply();
        root.a.ring();
        #1;
        chk(log.count(FW_SCHED_WAKE)  == 0, "block/wake are clamped away at L_TXN");
        chk(log.count(FW_SCHED_BLOCK) == 0, "...both of them");
        chk(root.rounds == 3,               "...while the model runs exactly as before");

        $display("--- end ---");

        if (errors == 0) $display("[dbg_sched] PASS");
        else begin
            $display("[dbg_sched] FAIL (%0d errors)", errors);
            $fatal(1, "[dbg_sched] FAIL");
        end
        $finish;
    end

    // Substring search -- SystemVerilog has no built-in.
    function automatic bit dbg_has(string hay, string needle);
        if (needle.len() > hay.len()) return 0;
        for (int i = 0; i <= hay.len() - needle.len(); i++) begin
            if (hay.substr(i, i + needle.len() - 1) == needle) return 1;
        end
        return 0;
    endfunction
`endif /* FW_TRACE_OFF */

endmodule
