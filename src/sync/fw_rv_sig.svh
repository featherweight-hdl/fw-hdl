// The ready/valid channel holder: typed `valid` and `data` driven by the
// producer (FWD), `ready` driven by the consumer (BWD). valid and ready are
// reset-forced to 0 (AXI A3.1.2); data is not forced. Each end reaches it
// through its view, fw_rv_sp_out or fw_rv_sp_in.
//
// set_*(): the driver's write; to `nxt` for a sync field, to the value for a
// comb field. get_*(peer): `cur` (or the comb value); with peer=1, the
// reset-force value while the domain is in reset.
class fw_rv_sig #(type T = bit) extends fw_sig_holder;
    fw_sync_field f_valid, f_ready, f_data;

    bit valid_cur, valid_nxt;
    bit ready_cur, ready_nxt;
    T   data_cur,  data_nxt;
    bit valid_kept, ready_kept;
    T   data_kept;

    function new(string name);
        super.new(name);
        f_valid = add_field("valid", 1, FW_SYNC_FWD);
        f_ready = add_field("ready", 1, FW_SYNC_BWD);
        f_data  = add_field("data", $bits(T), FW_SYNC_FWD);
        f_valid.set_force(0);
        f_ready.set_force(0);
    endfunction

    function void set_valid(bit v);
        m_wr(f_valid, valid_cur != v);
        valid_nxt = v;
        if (f_valid.comb) valid_cur = v;
    endfunction
    function void set_ready(bit v);
        m_wr(f_ready, ready_cur != v);
        ready_nxt = v;
        if (f_ready.comb) ready_cur = v;
    endfunction
    function void set_data(T v);
        m_wr(f_data, data_cur != v);
        data_nxt = v;
        if (f_data.comb) data_cur = v;
    endfunction

    function bit get_valid(bit peer = 0);
        return (peer && forced(f_valid)) ? 1'b0 : valid_cur;
    endfunction
    function bit get_ready(bit peer = 0);
        return (peer && forced(f_ready)) ? 1'b0 : ready_cur;
    endfunction
    function T get_data(bit peer = 0);
        return data_cur;
    endfunction

    virtual protected function void m_commit(bit kept);
        if (!f_valid.comb) valid_cur = kept ? valid_kept : valid_nxt;
        if (!f_ready.comb) ready_cur = kept ? ready_kept : ready_nxt;
        if (!f_data.comb)  data_cur  = kept ? data_kept  : data_nxt;
    endfunction
    virtual protected function void m_keep();
        valid_kept = valid_nxt;
        ready_kept = ready_nxt;
        data_kept  = data_nxt;
    endfunction
endclass
