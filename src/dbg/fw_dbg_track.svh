
// ----------------------------------------------------------------------------
// The LIVE view: what every thread is doing *right now*.
//
// Everything else in this facility is a STREAM -- a record of what happened,
// which is exactly the wrong shape for the single most common integration
// question:
//
//     "Nothing is happening. What is everyone waiting for?"
//
// A stream cannot answer that, because the answer is the absence of records.
// The state you need is the state at the moment you ask, so it has to be kept.
// That is this file: a per-thread open-operation stack and blocked-on set,
// maintained as processes run and printed on demand by fw_dbg_dump().
//
// --- Why it is off by default ------------------------------------------------
//
// Maintaining it costs a queue push/pop per operation and per wait -- small,
// but not nothing, and invariant G1 says an unobserved model pays nothing. So
// tracking is gated on one static bit (design §14.14: a hoisted, perfectly
// predicted branch, tested once per operation rather than per field).
//
// Turn it on with `+fw_dbg_track` or fw_dbg_track::set_enabled(1). The honest
// consequence: a hang is self-diagnosing on the *second* run, the same bargain
// a waveform dump makes. What matters is that the second run needs a flag and
// not an afternoon of adding $display calls -- and that report() says so
// out loud rather than printing an empty dump.
//
// --- Why the state is site ids, not strings ----------------------------------
//
// Same rule as the rest of the facility: nothing is formatted until someone
// asks. A frame is {site id, timestamp}; names are resolved out of the catalog
// at report() time, which happens once, when a human is already reading.
// ----------------------------------------------------------------------------

// One open operation, or one wait.
typedef struct {
    int unsigned site;
    longint      since;
} fw_dbg_frame_t;

// Everything known about one process.
class fw_dbg_thread_state;
    int            id;
    fw_dbg_frame_t ops[$];           // open operations, innermost last
    bit            blocked;
    int unsigned   wait_site = FW_DBG_NO_SITE;   // the wait point itself
    int unsigned   waiting_on[$];    // site ids of the wait set
    longint        blocked_since;
endclass

class fw_dbg_track;
    // The gate. One bit, read by every entry point below and by nothing else.
    protected static bit m_on = 0;
    protected static fw_dbg_thread_state m_st[int];

    static function bit  on();                 return m_on;  endfunction
    static function void set_enabled(bit e);   m_on = e;     endfunction

    protected static function fw_dbg_thread_state self();
        int id = fw_dbg_thread::id();
        if (!m_st.exists(id)) begin
            fw_dbg_thread_state s = new();
            s.id = id;
            m_st[id] = s;
        end
        return m_st[id];
    endfunction

    // --- the operation stack -------------------------------------------------
    // Note that a frame for a `forever` loop is never popped. That is not a
    // leak, it is the point: the dump's job is to show what is still open.
    static function void push_op(int unsigned sid);
        fw_dbg_thread_state s;
        fw_dbg_frame_t      f;
        if (!m_on) return;
        s = self();
        f.site  = sid;
        f.since = longint'($time);
        s.ops.push_back(f);
    endfunction

    static function void pop_op();
        fw_dbg_thread_state s;
        if (!m_on) return;
        s = self();
        if (s.ops.size() > 0) void'(s.ops.pop_back());
    endfunction

    // --- the blocked-on set --------------------------------------------------
    // Built incrementally (begin_wait / wait_src ... ) rather than taking the
    // set as one argument, so no queue is copied per wait.
    static function void begin_wait(int unsigned wait_site);
        fw_dbg_thread_state s;
        if (!m_on) return;
        s = self();
        s.blocked       = 1;
        s.wait_site     = wait_site;
        s.blocked_since = longint'($time);
        s.waiting_on.delete();
    endfunction

    static function void wait_src(int unsigned sid);
        fw_dbg_thread_state s;
        if (!m_on) return;
        s = self();
        s.waiting_on.push_back(sid);
    endfunction

    static function void end_wait();
        fw_dbg_thread_state s;
        if (!m_on) return;
        s = self();
        s.blocked   = 0;
        s.wait_site = FW_DBG_NO_SITE;
        s.waiting_on.delete();
    endfunction

    // --- reading it back -----------------------------------------------------
    protected static function string site_name(int unsigned sid);
        fw_dbg_site s = fw_dbg_catalog::site(sid);
        return (s != null) ? s.name() : "?";
    endfunction

    static function int num_threads();  return m_st.size();  endfunction

    static function int num_blocked();
        int n = 0;
        foreach (m_st[i]) if (m_st[i].blocked) n++;
        return n;
    endfunction

    // The whole point of the file, as text. Multi-line, no trailing newline.
    static function string report();
        string  out;
        longint now = longint'($time);

`ifdef FW_TRACE_OFF
        // Nothing feeds the tracker in a compiled-out build, so +fw_dbg_track
        // would produce an empty dump. Say that, rather than send someone off to
        // re-run with a flag that cannot help them.
        return {"fw-hdl: this image was built with FW_TRACE_OFF -- there is no\n",
                "        instrumentation to track. Rebuild without it (and pass\n",
                "        +fw_dbg_track) to use the live thread dump."};
`else
        if (!m_on) begin
            return {"fw-hdl: live tracking is OFF -- nothing was recorded.\n",
                    "        Re-run with +fw_dbg_track (or call fw_dbg_track::set_enabled(1))\n",
                    "        to capture every thread's open operations and blocked-on set."};
        end
`endif

        out = $sformatf("fw-hdl: live thread dump @ %0t -- %0d thread(s), %0d blocked",
                        now, m_st.size(), num_blocked());

        foreach (m_st[i]) begin
            fw_dbg_thread_state s = m_st[i];
            if (s.blocked) begin
                string srcs = "";
                foreach (s.waiting_on[k]) begin
                    srcs = {srcs, (k == 0) ? "" : ", ", site_name(s.waiting_on[k])};
                end
                out = {out, $sformatf("\n  thread %0d  BLOCKED %0t on %s {%s}",
                                      s.id, now - s.blocked_since,
                                      site_name(s.wait_site), srcs)};
            end else begin
                out = {out, $sformatf("\n  thread %0d  runnable", s.id)};
            end
            // Innermost first: that is the frame you look at.
            for (int f = s.ops.size() - 1; f >= 0; f--) begin
                out = {out, $sformatf("\n      #%0d %s  (open %0t)",
                                      f, site_name(s.ops[f].site),
                                      now - s.ops[f].since)};
            end
            if (s.ops.size() == 0) begin
                out = {out, "\n      (no open operations)"};
            end
        end
        return out;
    endfunction
endclass
