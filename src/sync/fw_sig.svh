// A one-field port: a single value of type T, driven by one end and read by
// the other. Same rules as fw_rv_sig: set() writes `nxt` (sync) or the value
// (comb); get() is the peer's read, which sees the reset-force value, if one
// is set, while the domain is in reset; get_own() is the driver's read.
// fw_reads/fw_writes name the field each accessor touches (settle weaver).
class fw_sig #(type T = bit) extends fw_sig_holder;
    fw_sync_field f_val;
    T             cur, nxt, kept;
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
        m_wr(f_val, cur != v);
        nxt = v;
        if (f_val.comb) cur = v;
    endfunction

    (* fw_reads = "val" *) function T get();     return forced(f_val) ? force_v : cur; endfunction
    (* fw_reads = "val" *) function T get_own(); return cur; endfunction

    virtual protected function void m_commit(bit kept);
        if (!f_val.comb) cur = kept ? this.kept : nxt;
    endfunction
    virtual protected function void m_keep();
        kept = nxt;
    endfunction
endclass
