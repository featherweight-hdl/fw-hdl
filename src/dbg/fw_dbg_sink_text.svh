
// A human-readable sink for simulation: one line per event.
//
//     1240 dma.de        [OP]       BEGUN service_chunk(ch=1 n=8)
//     1240 dma.de        [DECISION] arb winner=1 cand=[0(r2) 1* 2(r1)]
//     1244 dma.rf.csr    [STATE]    csr 0x00000001 -> 0x00000003 by FW_ACTOR_SW
//
// Rendering happens HERE, at the sink, off the producer's critical path -- and
// only for events that are actually enabled. Every name in the output comes from
// the site catalog, so the emitter never touched a string.
class fw_dbg_sink_text extends fw_dbg_listener;
    protected string m_prefix;
    protected int    m_count;

    function new(string prefix = "");
        m_prefix = prefix;
    endfunction

    function int count(); return m_count; endfunction

    protected function void put(fw_dbg_ctx c, string kind, string body);
        fw_dbg_domain d = c.ctx();
        m_count++;
        // The subject is rendered even though it is usually also a payload field:
        // it is the axis `+fw_dbg_subj` filters on, and a filter you cannot see
        // the input to is one you cannot aim.
        $display("%s%6t %-14s [%-8s] %s%s",
                 m_prefix, c.stamp(), (d != null) ? d.path() : "-", kind,
                 (c.subject() >= 0) ? $sformatf("{%0d} ", c.subject()) : "", body);
    endfunction

    virtual function void on_op      (fw_op_ctx       op); put(op, "OP",       op.to_str()); endfunction
    virtual function void on_state   (fw_state_ctx    st); put(st, "STATE",    st.to_str()); endfunction
    virtual function void on_decision(fw_decision_ctx d);  put(d,  "DECISION", d.to_str());  endfunction
    virtual function void on_sched   (fw_sched_ctx    sc); put(sc, "SCHED",    sc.to_str()); endfunction
    virtual function void on_notice  (fw_notice_ctx   n);  put(n,  "NOTICE",   n.to_str());  endfunction
    virtual function void on_link    (fw_link_ctx     l);  put(l,  "LINK",     l.to_str());  endfunction
endclass
