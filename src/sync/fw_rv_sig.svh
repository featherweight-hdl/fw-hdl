// The ready/valid channel holder: typed `valid` and `data` driven by the
// producer (FWD), `ready` driven by the consumer (BWD). valid and ready are
// reset-forced to 0 (AXI A3.1.2); data is not forced. Each end reaches it
// through its view, fw_rv_sp_out or fw_rv_sp_in.
//
// set_*(): the driver's write; to `nxt` for a sync field, to the value for a
// comb field. get_*(peer): `cur` (or the comb value); with peer=1, the
// reset-force value while the domain is in reset. From task code, each
// field is a crossing port (fw_sig_holder): at an edge, reads see `*_pre`,
// the value from before it; a write lands at once.
class fw_rv_sig #(type T = bit) extends fw_sig_holder;
    fw_sync_field f_valid, f_ready, f_data;

    bit valid_cur, valid_nxt;
    bit ready_cur, ready_nxt;
    T   data_cur,  data_nxt;
    bit valid_pre, ready_pre;   // *_cur before the last edge (task reads at it)
    T   data_pre;
    bit valid_xb, ready_xb;     // *_cur before the first task write for the next edge
    T   data_xb;

    function new(string name);
        super.new(name);
        f_valid = add_field("valid", 1, FW_SYNC_FWD);
        f_ready = add_field("ready", 1, FW_SYNC_BWD);
        f_data  = add_field("data", $bits(T), FW_SYNC_FWD);
        f_valid.set_force(0);
        f_ready.set_force(0);
    endfunction

    function void set_valid(bit v);
        bit task_wr = (phase == FW_SYNC_PH_RUN);
        bit changed = (valid_cur != v);
        bit first;
        if (task_wr && m_task_wr(f_valid, v == valid_xb, first)) return;
        if (first) valid_xb = valid_cur;
        m_wr(f_valid, changed);
        valid_nxt = v;
        if (f_valid.comb || task_wr) valid_cur = v;
        if (task_wr && changed) m_task_settle();
    endfunction
    function void set_ready(bit v);
        bit task_wr = (phase == FW_SYNC_PH_RUN);
        bit changed = (ready_cur != v);
        bit first;
        if (task_wr && m_task_wr(f_ready, v == ready_xb, first)) return;
        if (first) ready_xb = ready_cur;
        m_wr(f_ready, changed);
        ready_nxt = v;
        if (f_ready.comb || task_wr) ready_cur = v;
        if (task_wr && changed) m_task_settle();
    endfunction
    function void set_data(T v);
        bit task_wr = (phase == FW_SYNC_PH_RUN);
        bit changed = (data_cur != v);
        bit first;
        if (task_wr && m_task_wr(f_data, v == data_xb, first)) return;
        if (first) data_xb = data_cur;
        m_wr(f_data, changed);
        data_nxt = v;
        if (f_data.comb || task_wr) data_cur = v;
        if (task_wr && changed) m_task_settle();
    endfunction

    function bit get_valid(bit peer = 0);
        if (peer && forced(f_valid)) return 1'b0;
        return m_at_edge() ? valid_pre : valid_cur;
    endfunction
    function bit get_ready(bit peer = 0);
        if (peer && forced(f_ready)) return 1'b0;
        return m_at_edge() ? ready_pre : ready_cur;
    endfunction
    function T get_data(bit peer = 0);
        return m_at_edge() ? data_pre : data_cur;
    endfunction

    virtual protected function void m_commit();
        valid_pre = valid_cur;
        ready_pre = ready_cur;
        data_pre  = data_cur;
        if (!f_valid.comb) valid_cur = valid_nxt;
        if (!f_ready.comb) ready_cur = ready_nxt;
        if (!f_data.comb)  data_cur  = data_nxt;
    endfunction
endclass
