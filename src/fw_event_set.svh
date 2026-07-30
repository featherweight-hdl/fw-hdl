
typedef class fw_awaitable_if;   // forward: add() wires a source's production in
typedef class fw_component;      // forward: an optional owner, for the debug context

// fw_event_set -- the MONITOR side: a list of event sources you wait on.
//
// Build it with add() (pull-style look-and-feel), then wait_any() blocks until any
// member's "event occurred". Internally this is a PUSH: add() wires each source to
// signal() this set when it fires, so wait_any() is a single @event -- O(1), with
// no per-wait fork. That produce/monitor split is also what lowers to synthesizable
// RTL: each source's "fired" pulse drives this set's event (the OR of its members),
// and a wait site is a process sensitive to it.
//
// We do not report which source fired TO THE CONSUMER; the consumer re-evaluates
// its own state on wake. (fw_reg_set is the register-specific primitive that
// tracks which moved.) The waker IS reported to the observer, because "who woke
// me" is irrecoverable from a stream that only shows the wake.
//
// --- Observability ----------------------------------------------------------
//
// A wait is where a model stops, so it is where debug most often starts. Give the
// set a name and an owning component:
//
//     m_wake = new("de.wake", this);
//
// and it registers one instance site and emits `block{waiting_on}` / `wake{waker,
// blocked_for}` around the wait -- plus, when +fw_dbg_track is on, it maintains
// the live blocked-on set that fw_dbg_dump() prints. Both arguments are optional;
// an unnamed set behaves exactly as before.
class fw_event_set implements fw_dbg_contextual;
    protected event              m_any;
    protected string             m_name;
    protected fw_awaitable_if    m_src[$];    // the wait set, for naming
    protected fw_awaitable_if    m_waker;     // who fired most recently
    protected fw_dbg_listener_if m_dbg;
    protected int unsigned       m_sid = FW_DBG_NO_SITE;

    // `name` is the wait point's identity in the catalog; `parent` supplies the
    // debug context. A set is often created inside run() -- after do_build() has
    // handed out contexts -- so the context is PULLED here as well as registered
    // for the push. Whichever arrives is the same handle.
    function new(string name = "", fw_component parent = null);
        m_name = (name == "") ? "wait" : name;
        `fw_dbg_site_inst(m_sid, m_name, FW_DBG_SCHED, FW_L_OP)
        if (parent != null) begin
            m_dbg = parent.dbg_if();
            parent.add_contextual(this);
        end
    endfunction

    virtual function void set_dbg_context(fw_dbg_listener_if l);
        m_dbg = l;
    endfunction

    function string       name();      return m_name;  endfunction
    function int unsigned dbg_site();  return m_sid;   endfunction

    // Pull-style API: add a source to wait on. Wires the source (produce_to) to
    // signal this set when it fires, and remembers it so the wait can be named.
    function void add(fw_awaitable_if a);
        m_src.push_back(a);
        a.produce_to(this);
    endfunction

    // Called by a member source when its event occurs (the push).
    //
    // `src` is mandatory -- there is no default. A source that does not say who
    // it is turns every wake into "something happened", which is the report you
    // already had. Making it required means the compiler, not a silent
    // degradation, finds the callers.
    //
    // Honest limitation: if two sources fire in the same time step before the
    // waiting process resumes, the LAST one is reported. The set has a single
    // event and a single resumption; there is no wake per source to attribute.
    function void notify(fw_awaitable_if src);
        m_waker = src;
        -> m_any;
    endfunction

    // The wait/monitor site: block until any member's event occurs.
    //
    // The instrumentation is bracketed by `ifndef FW_TRACE_OFF rather than left
    // to the macros because the *timestamp* is part of it: `blocked_for` needs a
    // reading taken before the block, and a compiled-out build must not take it.
    // What remains under FW_TRACE_OFF is `@(m_any)` and nothing else.
    task wait_any();
`ifndef FW_TRACE_OFF
        longint t0 = longint'($time);
        m_waker = null;

        `fw_ev_sched_at(m_dbg, m_sid)
            `fw_sched_set(FW_SCHED_BLOCK, 0, FW_DBG_NO_SITE)
            foreach (m_src[i]) begin
                `fw_sched_src(m_src[i].dbg_site())
            end
        `fw_ev_end

        if (fw_dbg_track::on()) begin
            fw_dbg_track::begin_wait(m_sid);
            foreach (m_src[i]) fw_dbg_track::wait_src(m_src[i].dbg_site());
        end
`endif

        @(m_any);

`ifndef FW_TRACE_OFF
        if (fw_dbg_track::on()) fw_dbg_track::end_wait();

        `fw_ev_sched_at(m_dbg, m_sid)
            `fw_sched_set(FW_SCHED_WAKE, longint'($time) - t0,
                          (m_waker != null) ? m_waker.dbg_site() : FW_DBG_NO_SITE)
        `fw_ev_end
`endif
    endtask
endclass
