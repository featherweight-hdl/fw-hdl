// The Wishbone bus as a sync struct port: the master drives adr, dat_w, sel,
// we, cyc and stb (FWD); the target drives dat_r, ack, err and rty (BWD).
// The master's end is wb_sp_out, the target's wb_sp_in. Same rules as
// fw_rv_sig (set_x() writes `nxt` for a sync field, the value for a comb
// one; from task code each field is a crossing port), without reset-force.
// The lowering reads the fields from new() and their widths from <f>_cur:
// the lowered ports are <port>_<f> (wb_adr, wb_ack, ...).

// One field: its values, its write and its read.
`define WB_SIG_FIELD(T, f) \
    T f``_cur, f``_nxt, f``_pre, f``_xb; \
    function void set_``f(T v); \
        bit task_wr = (phase == FW_SYNC_PH_RUN); \
        bit changed = (f``_cur != v); \
        bit first; \
        if (task_wr && m_task_wr(f_``f, v == f``_xb, first)) return; \
        if (first) f``_xb = f``_cur; \
        m_wr(f_``f, changed); \
        f``_nxt = v; \
        if (f_``f.comb || task_wr) f``_cur = v; \
        if (task_wr && changed) m_task_settle(); \
    endfunction \
    function T get_``f(); \
        return m_at_edge() ? f``_pre : f``_cur; \
    endfunction

`define WB_SIG_COMMIT(f) \
    f``_pre = f``_cur; \
    if (!f_``f.comb) f``_cur = f``_nxt;

typedef bit [wb_types_pkg::WB_AW-1:0] wb_adr_t;
typedef bit [wb_types_pkg::WB_DW-1:0] wb_dat_t;
typedef bit [wb_types_pkg::WB_SW-1:0] wb_sel_t;

class wb_sig extends fw_sig_holder;
    fw_sync_field f_adr, f_dat_w, f_sel, f_we, f_cyc, f_stb;
    fw_sync_field f_dat_r, f_ack, f_err, f_rty;

    `WB_SIG_FIELD(wb_adr_t, adr)
    `WB_SIG_FIELD(wb_dat_t, dat_w)
    `WB_SIG_FIELD(wb_sel_t, sel)
    `WB_SIG_FIELD(bit, we)
    `WB_SIG_FIELD(bit, cyc)
    `WB_SIG_FIELD(bit, stb)
    `WB_SIG_FIELD(wb_dat_t, dat_r)
    `WB_SIG_FIELD(bit, ack)
    `WB_SIG_FIELD(bit, err)
    `WB_SIG_FIELD(bit, rty)

    function new(string name);
        super.new(name);
        f_adr   = add_field("adr", $bits(wb_adr_t), FW_SYNC_FWD);
        f_dat_w = add_field("dat_w", $bits(wb_dat_t), FW_SYNC_FWD);
        f_sel   = add_field("sel", $bits(wb_sel_t), FW_SYNC_FWD);
        f_we    = add_field("we", 1, FW_SYNC_FWD);
        f_cyc   = add_field("cyc", 1, FW_SYNC_FWD);
        f_stb   = add_field("stb", 1, FW_SYNC_FWD);
        f_dat_r = add_field("dat_r", $bits(wb_dat_t), FW_SYNC_BWD);
        f_ack   = add_field("ack", 1, FW_SYNC_BWD);
        f_err   = add_field("err", 1, FW_SYNC_BWD);
        f_rty   = add_field("rty", 1, FW_SYNC_BWD);
    endfunction

    virtual protected function void m_commit();
        `WB_SIG_COMMIT(adr)
        `WB_SIG_COMMIT(dat_w)
        `WB_SIG_COMMIT(sel)
        `WB_SIG_COMMIT(we)
        `WB_SIG_COMMIT(cyc)
        `WB_SIG_COMMIT(stb)
        `WB_SIG_COMMIT(dat_r)
        `WB_SIG_COMMIT(ack)
        `WB_SIG_COMMIT(err)
        `WB_SIG_COMMIT(rty)
    endfunction
endclass

// A view's accessors: set_<f> for the fields its end drives, get_<f> for all.
`define WB_SP_SET(T, f) \
    (* fw_writes = `"f`" *) function void set_``f(T v); sig.set_``f(v); endfunction
`define WB_SP_GET(T, f) \
    (* fw_reads = `"f`" *) function T get_``f(); return sig.get_``f(); endfunction
`define WB_SP_VIEW_COMMON \
    wb_sig sig; \
    static function wb_sig m_mk(wb_sig sig, string name); \
        if (sig == null) sig = new(name); \
        return sig; \
    endfunction \
    virtual protected function void m_set_holder(fw_sig_holder h); \
        if (!$cast(sig, h)) \
            $fatal(1, "fw-hdl: %s: holder \"%s\" is not a wb_sig", full_name(), h.name); \
    endfunction \
    `WB_SP_GET(wb_adr_t, adr) \
    `WB_SP_GET(wb_dat_t, dat_w) \
    `WB_SP_GET(wb_sel_t, sel) \
    `WB_SP_GET(bit, we) \
    `WB_SP_GET(bit, cyc) \
    `WB_SP_GET(bit, stb) \
    `WB_SP_GET(wb_dat_t, dat_r) \
    `WB_SP_GET(bit, ack) \
    `WB_SP_GET(bit, err) \
    `WB_SP_GET(bit, rty)

typedef class wb_sp_in;

// The master's end.
class wb_sp_out extends fw_sync_port;
    `WB_SP_VIEW_COMMON

    function new(wb_sig sig = null, string name = "", fw_component owner = null);
        super.new(name, owner, FW_SYNC_FWD, m_mk(sig, name));
        $cast(this.sig, holder());
    endfunction

    // A sibling's target end.
    function void connect(wb_sp_in peer);
        m_connect(peer);
    endfunction

    // The parent's master end, which this end drives through.
    function void connect_up(wb_sp_out outer);
        m_connect_up(outer);
    endfunction

    `WB_SP_SET(wb_adr_t, adr)
    `WB_SP_SET(wb_dat_t, dat_w)
    `WB_SP_SET(wb_sel_t, sel)
    `WB_SP_SET(bit, we)
    `WB_SP_SET(bit, cyc)
    `WB_SP_SET(bit, stb)
endclass

// The target's end.
class wb_sp_in extends fw_sync_port;
    `WB_SP_VIEW_COMMON

    function new(wb_sig sig = null, string name = "", fw_component owner = null);
        super.new(name, owner, FW_SYNC_BWD, m_mk(sig, name));
        $cast(this.sig, holder());
    endfunction

    // A sibling's master end.
    function void connect(wb_sp_out peer);
        m_connect(peer);
    endfunction

    // The parent's target end, which this end drives through.
    function void connect_up(wb_sp_in outer);
        m_connect_up(outer);
    endfunction

    `WB_SP_SET(wb_dat_t, dat_r)
    `WB_SP_SET(bit, ack)
    `WB_SP_SET(bit, err)
    `WB_SP_SET(bit, rty)
endclass
