
// A no-op listener base: override only the one method you care about.
//
// The interface class is what the emit path talks to; this class is what users
// extend. A coverage collector that only wants arbitration decisions overrides
// `on_decision` and inherits six empty bodies -- it does not have to know the
// other kinds exist.
//
// `enabled()` defaults to true because a plain listener does no gating of its
// own: gating lives in the DOMAIN's enable table, computed at `apply()` from the
// union of its listeners' declared interest. A listener that wants finer control
// than "these kinds, up to this level" can override this.
virtual class fw_dbg_listener implements fw_dbg_listener_if;
    virtual function void on_op      (fw_op_ctx       op); endfunction
    virtual function void on_state   (fw_state_ctx    st); endfunction
    virtual function void on_decision(fw_decision_ctx d);  endfunction
    virtual function void on_sched   (fw_sched_ctx    sc); endfunction
    virtual function void on_notice  (fw_notice_ctx   n);  endfunction
    virtual function void on_link    (fw_link_ctx     l);  endfunction

    virtual function bit enabled(int unsigned site_id);
        return 1'b1;
    endfunction

    // As with `enabled()`: a plain listener does no gating of its own. Subject
    // masks are configured on a DOMAIN and resolved at apply().
    virtual function bit enabled_subj(int unsigned site_id, int subject);
        return 1'b1;
    endfunction

    // Record mode is a property of a CONTEXT, not of a listener. A plain
    // listener takes what it is given.
    virtual function bit emit_open();
        return 1'b1;
    endfunction
endclass
