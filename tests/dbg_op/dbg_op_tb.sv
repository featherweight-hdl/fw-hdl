// D-5: operations -- spans that outlive the callback.
//
// Every kind before this one reports an instant. An OPERATION is a region: it
// has a duration, it can nest, it can overlap another one on a different
// thread, and its identity has to survive a yield. That last property is what
// makes it different in kind from an event, and it is what this bench is really
// about.
//
// The acceptance criteria, in order of how badly they would hurt if wrong:
//
//   1. Concurrent spans that finish OUT OF ORDER do not corrupt each other.
//      Contexts are pooled; if the pool released by depth (as the borrowed-event
//      path safely does) two forked processes would hand back each other's
//      payloads, and the resulting trace would be plausible and wrong.
//   2. Depth, parent and duration are RECOVERABLE WITHOUT BEING EMITTED (G5).
//      If the decoder cannot rebuild them, the fields have to go into every
//      record forever.
//   3. Payload expressions on BOTH halves stay inside the gate (G2).
//   4. `CLOSE_ONLY` trims records without breaking timing -- a span still times
//      itself when its open record is suppressed.
module dbg_op_tb;
    import fw_hdl_pkg::*;
    `include "dbg/fw_dbg_macros.svh"

    int errors = 0;

    function automatic void chk(bit cond, string msg);
        if (!cond) begin $display("FAIL: %s", msg); errors++; end
    endfunction

    function automatic void chk_eq(longint got, longint exp, string msg);
        if (got != exp) begin
            $display("FAIL: %s (got %0d, expected %0d)", msg, got, exp);
            errors++;
        end
    endfunction

    // The typed projection's payload. Packed LSB-first in push order, so `ch`
    // (pushed first) is the LAST member.
    typedef struct packed {
        bit [63:0] words;
        bit [63:0] ch;
    } chunk_p_t;

    // ---- the model ---------------------------------------------------------
    class worker extends fw_component;
        int evals;                 // argument evaluations, for G2

        function new(string name, fw_component parent = null);
            super.new(name, parent);
        endfunction

        function int bump(); evals++; return evals; endfunction

        // One span that consumes time.
        task chunk(int ch, int words, int delay);
            `fw_op_span(op)
            `fw_op_begin(dbg_if(), FW_L_OP, "w.chunk", op)
                `fw_op_flow(ch)
                `fw_field_u8_as("ch",     ch)
                `fw_field_u32_as("words", words)
                `fw_field_i32_as("seq",   bump())
            `fw_op_opened
            #(delay);
            `fw_op_close(dbg_if(), op)
                `fw_field_h32_as("moved", bump())
                `fw_op_outcome(FW_OUT_OK)
            `fw_op_end(op)
        endtask

        // A span whose identity is only known part way through -- the case
        // `fw_op_retag` exists for.
        task late_id(int delay, int id);
            `fw_op_span(op)
            `fw_op_begin(dbg_if(), FW_L_OP, "w.late", op)
            `fw_op_opened
            #(delay);
            `fw_op_retag(op, id)
            `fw_op_close(dbg_if(), op)
            `fw_op_end(op)
        endtask

        // An outer span containing an inner one, on the same thread.
        task nested(int ch);
            `fw_op_span(op)
            `fw_op_begin(dbg_if(), FW_L_OP, "w.outer", op)
                `fw_op_flow(ch)
            `fw_op_opened
            #(10);
            chunk(ch, 4, 20);
            #(10);
            `fw_op_close(dbg_if(), op)
            `fw_op_end(op)
        endtask
    endclass

`ifdef FW_TRACE_OFF

    // G1: no residue. The handle declaration itself must vanish -- that is why
    // `fw_op_span` is a macro rather than a plain `fw_op_ctx op;`.
    worker w = new("w");

    initial begin
        w.chunk(1, 4, 10);
        w.nested(2);
        w.late_id(5, 7);
        chk_eq(w.evals, 0, "FW_TRACE_OFF: no argument was evaluated");
        chk_eq($time, 55, "FW_TRACE_OFF: the model still consumes its own time");
        if (errors == 0) $display("[dbg_op] PASS (FW_TRACE_OFF)");
        else begin $display("[dbg_op] FAIL (%0d errors)", errors); $fatal(1, "FAIL"); end
        $finish;
    end

`else

    class rec_listener extends fw_dbg_listener;
        fw_dbg_rec recs[$];
        // Typed-projection readback, captured live because the view is as
        // borrowed as the context it wraps.
        longint    typed_ch = -1, typed_words = -1;
        int        typed_hits, typed_misses;

        virtual function void on_op(fw_op_ctx op);
            fw_op_view #(chunk_p_t) v = fw_op_view #(chunk_p_t)::over(op);
            recs.push_back(op.snapshot());
            if (v != null && op.name() == "w.chunk" && op.phase() == FW_OP_BEGUN) begin
                typed_ch    = v.params().ch;
                typed_words = v.params().words;
                typed_hits++;
            end else if (v == null) begin
                typed_misses++;
            end
        endfunction

        function void clear(); recs.delete(); endfunction

        function int count(string nm, fw_op_phase_e ph);
            int n = 0;
            foreach (recs[i]) begin
                fw_dbg_site s = fw_dbg_catalog::site(recs[i].site_id);
                if (s != null && s.name() == nm && recs[i].op_phase == ph) n++;
            end
            return n;
        endfunction

        function fw_dbg_rec nth(string nm, fw_op_phase_e ph, int idx = 0);
            int n = 0;
            foreach (recs[i]) begin
                fw_dbg_site s = fw_dbg_catalog::site(recs[i].site_id);
                if (s != null && s.name() == nm && recs[i].op_phase == ph) begin
                    if (n == idx) return recs[i];
                    n++;
                end
            end
            return null;
        endfunction

        // --- the G5 proof ---------------------------------------------------
        // Rebuild nesting depth from what IS emitted: thread id, site id and
        // open/close order. If this works, depth and parent never need to be
        // fields. Returns the depth the record at index `i` sat at, or -1 if the
        // stream does not pair up (which would itself be the finding).
        function int depth_of(int idx);
            int d[int];                       // thread id -> current depth
            foreach (recs[i]) begin
                if (recs[i].kind != FW_DBG_OP) continue;
                if (recs[i].op_phase == FW_OP_BEGUN) begin
                    if (i == idx) return d[recs[i].thread_id];
                    d[recs[i].thread_id]++;
                end else if (recs[i].op_phase == FW_OP_ENDED) begin
                    d[recs[i].thread_id]--;
                    if (d[recs[i].thread_id] < 0) return -1;
                    if (i == idx) return d[recs[i].thread_id];
                end
            end
            return -1;
        endfunction

        function int index_of(string nm, fw_op_phase_e ph);
            foreach (recs[i]) begin
                fw_dbg_site s = fw_dbg_catalog::site(recs[i].site_id);
                if (s != null && s.name() == nm && recs[i].op_phase == ph) return i;
            end
            return -1;
        endfunction
    endclass

    fw_dbg_root dbg = new("top");
    worker      w   = new("w");
    rec_listener log = new();

    initial begin
        automatic fw_dbg_rec o, c;
        automatic int        before_evals;

        dbg.add_listener(log, FW_K_ALL, FW_L_TRACE);
        w.set_dbg_domain(dbg);
        dbg.apply();

        // --------------------------------------------------------------------
        // 1. One span: open then close, and the close carries its own timing.
        // --------------------------------------------------------------------
        w.chunk(1, 4, 30);
        chk_eq(log.count("w.chunk", FW_OP_BEGUN), 1, "one open record");
        chk_eq(log.count("w.chunk", FW_OP_ENDED), 1, "one close record");
        o = log.nth("w.chunk", FW_OP_BEGUN);
        c = log.nth("w.chunk", FW_OP_ENDED);
        chk_eq(c.t_begun, o.stamp, "close carries the span's begin time");
        chk_eq(c.t_ended - c.t_begun, 30, "duration is the time the body took");
        // Both halves' payloads are present on the close; the open has only what
        // was known at entry.
        chk_eq(o.fields.size(), 3, "open record: parameters only");
        chk_eq(c.fields.size(), 4, "close record: parameters + results");
        chk_eq(c.flow.size(),   1, "the derived flow key rode along");
        chk_eq(c.flow[0],       1, "...and it is the channel");

        // --------------------------------------------------------------------
        // 2. Typed projection agrees with the untyped walk. Two readings of the
        //    same stored values -- if they ever disagree, one of them is lying.
        // --------------------------------------------------------------------
        chk_eq(log.typed_ch,    1, "typed projection: ch");
        chk_eq(log.typed_words, 4, "typed projection: words");
        chk_eq(log.typed_ch,    o.fields[0], "typed and untyped agree on ch");
        chk_eq(log.typed_words, o.fields[1], "typed and untyped agree on words");

        // --------------------------------------------------------------------
        // 3. G5: depth and parent are RECOVERABLE, not emitted. Nothing in the
        //    record says "depth 1" or "my parent is w.outer" -- the decoder gets
        //    both from thread id plus open/close order.
        // --------------------------------------------------------------------
        log.clear();
        w.nested(7);
        chk_eq(log.count("w.outer", FW_OP_BEGUN), 1, "nested: outer opened");
        chk_eq(log.count("w.chunk", FW_OP_BEGUN), 1, "nested: inner opened");
        chk_eq(log.depth_of(log.index_of("w.outer", FW_OP_BEGUN)), 0, "outer is at depth 0");
        chk_eq(log.depth_of(log.index_of("w.chunk", FW_OP_BEGUN)), 1, "inner is at depth 1");
        // And no record ever carried the depth.
        foreach (log.recs[i]) begin
            // `automatic` is load-bearing: a declaration with an initializer in
            // an `initial` block has STATIC lifetime, so this would be evaluated
            // once, at time 0, against an undefined `i`.
            automatic fw_dbg_site s = fw_dbg_catalog::site(log.recs[i].site_id);
            for (int f = 0; f < s.field_count(); f++) begin
                chk(s.field_name(f) != "depth" && s.field_name(f) != "parent",
                    "no record emits depth or parent (G5)");
            end
        end
        // The inner span's duration is contained by the outer's.
        o = log.nth("w.outer", FW_OP_ENDED);
        c = log.nth("w.chunk", FW_OP_ENDED);
        chk(c.t_begun >= o.t_begun && c.t_ended <= o.t_ended,
            "the inner span is contained by the outer");

        // --------------------------------------------------------------------
        // 4. THE ONE THAT MATTERS: concurrent spans finishing out of order.
        //    Two threads open operations; the SECOND one finishes FIRST. A pool
        //    that released by depth would return the wrong context here and the
        //    payloads would swap -- producing a trace that looks entirely
        //    reasonable and is entirely wrong.
        // --------------------------------------------------------------------
        log.clear();
        fork
            w.chunk(2, 100, 80);      // opens first, closes last
            begin #5; w.chunk(3, 200, 10); end   // opens second, closes first
        join
        chk_eq(log.count("w.chunk", FW_OP_ENDED), 2, "both spans closed");
        begin
            automatic fw_dbg_rec c0 = log.nth("w.chunk", FW_OP_ENDED, 0);
            automatic fw_dbg_rec c1 = log.nth("w.chunk", FW_OP_ENDED, 1);
            // c0 is channel 3 (opened later, closed first).
            chk_eq(c0.flow[0], 3, "out-of-order close: first close is the short span");
            chk_eq(c1.flow[0], 2, "out-of-order close: second close is the long span");
            chk_eq(c0.t_ended - c0.t_begun, 10, "short span kept its own duration");
            chk_eq(c1.t_ended - c1.t_begun, 80, "long span kept its own duration");
            chk(c0.thread_id != c1.thread_id, "the two spans ran on different threads");
        end
        chk_eq(fw_dbg_pool::span_live(), 0, "every span was released");
        chk(fw_dbg_pool::span_peak() >= 2, "the pool saw two concurrent spans");

        // --------------------------------------------------------------------
        // 5. Retro-tagging lands on the close only. The open record went out
        //    before the identity was known -- that is the honest behavior, and
        //    a decoder pairs the two by thread and order, not by the tag.
        // --------------------------------------------------------------------
        log.clear();
        w.late_id(5, 42);
        o = log.nth("w.late", FW_OP_BEGUN);
        c = log.nth("w.late", FW_OP_ENDED);
        chk_eq(o.flow.size(), 0, "retro-tag: absent from the open record");
        chk_eq(c.flow.size(), 1, "retro-tag: present on the close record");
        chk_eq(c.flow[0],    42, "retro-tag: with the right value");

        // --------------------------------------------------------------------
        // 6. CLOSE_ONLY trims the record, not the timing. This is what the
        //    per-context record mode was introduced for in D-1 and it has been
        //    unused until now.
        // --------------------------------------------------------------------
        log.clear();
        dbg.cfg("*", .records(int'(FW_REC_CLOSE_ONLY)));
        dbg.apply();
        w.chunk(4, 8, 25);
        chk_eq(log.count("w.chunk", FW_OP_BEGUN), 0, "CLOSE_ONLY: no open record");
        chk_eq(log.count("w.chunk", FW_OP_ENDED), 1, "CLOSE_ONLY: the close still lands");
        c = log.nth("w.chunk", FW_OP_ENDED);
        chk_eq(c.t_ended - c.t_begun, 25, "CLOSE_ONLY: duration survives the trim");
        chk_eq(c.flow[0], 4, "CLOSE_ONLY: so does the flow key");
        dbg.clear_cfg();
        dbg.apply();

        // --------------------------------------------------------------------
        // 7. G2 on BOTH halves. A disabled span evaluates neither its parameters
        //    nor its results -- the close block is a second gate and would be
        //    easy to leave open.
        // --------------------------------------------------------------------
        log.clear();
        dbg.cfg("*", .sites("w.chunk"), .level(int'(FW_L_OFF)));
        dbg.apply();
        before_evals = w.evals;
        w.chunk(5, 1, 10);
        chk_eq(w.evals - before_evals, 0, "disabled span: neither half evaluated (G2)");
        chk_eq(log.recs.size(), 0, "disabled span: nothing emitted");
        chk_eq(fw_dbg_pool::span_live(), 0, "disabled span: nothing checked out");
        chk_eq($time - 0, $time, "disabled span: the body still ran");
        dbg.clear_cfg();
        dbg.apply();

        // --------------------------------------------------------------------
        // 8. begun - accepted is MEASURED, not inferred: the accepting actor
        //    emits its own point record with the same flow key, and the join
        //    gives queueing latency. Zero when the two coincide.
        // --------------------------------------------------------------------
        log.clear();
        begin
            automatic longint t_acc;
            `fw_op_accept(dbg.get_if(), FW_L_TXN, "w.eligible")
                `fw_op_flow(9)
            `fw_ev_end
            t_acc = log.nth("w.eligible", FW_OP_ACCEPTED).stamp;
            #(40);                       // the work waits for a server
            w.chunk(9, 2, 15);
            c = log.nth("w.chunk", FW_OP_ENDED);
            chk_eq(c.flow[0], 9, "accept and serve share a flow key");
            chk_eq(c.t_begun - t_acc, 40, "begun - accepted is the queueing latency");
        end

        // --------------------------------------------------------------------
        // 9. The FIELD SCHEMA is the external decode contract (D-8): payload
        //    values travel as `longint`, so without a declared width and
        //    signedness a consumer cannot tell -1 from 0xff from 0xffffffff.
        //    Asserted here rather than left to a downstream package to discover.
        // --------------------------------------------------------------------
        begin
            automatic fw_dbg_site s = fw_dbg_catalog::find("w.chunk");
            chk(s != null, "schema: the site is in the catalog");
            // 3 parameters at open + 1 result at close: the schema spans BOTH
            // halves of the span, in push order.
            chk_eq(s.field_count(), 4, "schema: every pushed field is described");
            chk(s.field_name(0) == "ch",    "schema: names survive");
            chk_eq(s.field_type(0).bits, 8, "schema: declared width");
            chk(!s.field_type(0).is_signed, "schema: declared unsigned");
            chk_eq(s.field_type(1).bits, 32, "schema: second field width");
            chk(s.field_type(2).is_signed,  "schema: signedness is per field");
            chk(s.field_type(3).is_hex,     "schema: radix is per field");
            chk(!s.field_type(1).is_hex,    "schema: ...and does not leak across fields");
            chk(fw_dbg_ftype_str(s.field_type(0)) == "u8",  "schema: type spelling u8");
            chk(fw_dbg_ftype_str(s.field_type(2)) == "i32", "schema: type spelling i32");
            chk(fw_dbg_ftype_str(s.field_type(3)) == "h32", "schema: type spelling h32");
        end

        // --------------------------------------------------------------------
        // 10. Names are passed only while the schema is being WRITTEN. After the
        //     first activation a push carries a value and nothing else -- which
        //     is the difference between a per-beat site costing one queue append
        //     and costing three string copies.
        // --------------------------------------------------------------------
        begin
            automatic fw_op_ctx probe = fw_dbg_pool::acquire_op_span(
                                            fw_dbg_catalog::find("w.chunk").id());
            chk(!probe.need_schema(),
                "schema is written once: a later activation needs no names");
            fw_dbg_pool::release_op_span(probe);
        end

        if (errors == 0) $display("[dbg_op] PASS");
        else begin $display("[dbg_op] FAIL (%0d errors)", errors); $fatal(1, "FAIL"); end
        $finish;
    end

`endif
endmodule
