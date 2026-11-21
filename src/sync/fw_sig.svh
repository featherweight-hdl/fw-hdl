// A one-field port: a single value of type T, driven by one end and read by
// the other. Same rules as fw_rv_sig: set() writes `nxt` (sync) or the value
// (comb); get() is the peer's read, which sees the reset-force value, if one
// is set, while the domain is in reset; get_own() is the driver's read.
// From task code, a crossing port (fw_sig_holder): at an edge, reads see
// `pre`, the value from before it; a write lands at once.
// fw_reads/fw_writes name the field each accessor touches (settle weaver).
class fw_sig #(type T = bit) extends fw_sig_holder;
    fw_sync_field f_val;
    T             cur, nxt;
    T             pre;      // cur before the last edge (task reads at it)
    T             xbase;    // cur before the first task write for the next edge
    T             force_v;

    function new(string name);
        super.new(name);
        f_val = add_field("val", $bits(T), FW_SYNC_FWD);
    endfunction

    function void set_reset_force(T v);
        force_v = v;
        f_val.has_force = 1;   // force_val is untyped; T may be wider
    endfunction

    (* fw_writes = "val" *)
    function void set(T v);
        bit task_wr = (phase == FW_SYNC_PH_RUN);
        bit changed = (cur != v);
        bit first;
        if (task_wr && m_task_wr(f_val, v == xbase, first)) return;
        if (first) xbase = cur;
        m_wr(f_val, changed);
        nxt = v;
        if (f_val.comb || task_wr) cur = v;
        if (task_wr && changed) m_task_settle();
    endfunction

    (* fw_reads = "val" *) function T get();     return forced(f_val) ? force_v : get_own(); endfunction
    (* fw_reads = "val" *) function T get_own(); return m_at_edge() ? pre : cur; endfunction

    virtual protected function void m_commit();
        pre = cur;
        if (!f_val.comb) cur = nxt;
    endfunction
endclass
