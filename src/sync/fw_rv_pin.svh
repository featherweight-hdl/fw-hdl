// The class half of a ready/valid pin bridge (design-sync-rtl §3.3, "Mixed
// SV/RTL simulation"): the end, in a class tree, of a channel whose other
// end is pins. The module half (fw_rv_pin_in, fw_rv_pin_out) makes one under
// its NAME; the tree finds it by that name in connect() and joins it to a
// view of its own (connect_in/connect_out), which makes a fresh end for
// each tree (fw_root builds a new tree at each reset release).
//
// into = 1: the pins are the producer (they drive valid and data, the tree
// drives ready). into = 0: the pins are the consumer.
//
// From the pins (put_fwd/put_bwd): a comb field is written in the comb
// phase and the kernel settles the domain at once (settle_now), so a comb
// path through the tree reaches the other pins in the same time step. A
// sync field is written to nxt and committed at the next edge; a change at
// an edge before the kernel's commit lands after that edge (the early-write
// guard). To the pins (get_*): a comb field's value, and a sync field's nxt,
// which the module drives nonblocking (so the RTL sees it after the edge,
// as the tree does after the next commit). Both are reset-forced.
class fw_rv_pin #(type T = bit);
    string            name;
    bit               into;
    fw_rv_sp_out #(T) o;     // into: the pins' end in the tree
    fw_rv_sp_in  #(T) i;     // !into

    protected bit m_fresh;   // nothing pushed into this end's holder yet
    protected bit m_valid, m_ready;
    protected T   m_data;

    static fw_rv_pin #(T) m_reg[string];

    function new(string name, bit into);
        this.name = name;
        this.into = into;
        if (m_reg.exists(name)) $fatal(1, "fw-hdl: pin bridge \"%s\" made twice", name);
        m_reg[name] = this;
    endfunction

    static function fw_rv_pin #(T) find(string name);
        if (!m_reg.exists(name)) $fatal(1, "fw-hdl: no pin bridge \"%s\"", name);
        return m_reg[name];
    endfunction

    // The tree's consumer end p takes valid/data from the pins.
    function void connect_in(fw_rv_sp_in #(T) p);
        if (!into) $fatal(1, "fw-hdl: pin bridge \"%s\" is a consumer: use connect_out()", name);
        o = new(null, name);
        p.connect(o);
        m_fresh = 1;
    endfunction

    // The tree's producer end p drives valid/data to the pins.
    function void connect_out(fw_rv_sp_out #(T) p);
        if (into) $fatal(1, "fw-hdl: pin bridge \"%s\" is a producer: use connect_in()", name);
        i = new(null, name);
        p.connect(i);
        m_fresh = 1;
    endfunction

    // The current holder; null before connect.
    function fw_rv_sig #(T) sig();
        if (into) return (o == null) ? null : o.sig;
        return (i == null) ? null : i.sig;
    endfunction

    // into: the pins' valid and data. Does nothing before the kernel has
    // elaborated the tree.
    function void put_fwd(bit valid, T data);
        fw_rv_sig #(T)  s = sig();
        fw_sync_phase_e prev = fw_sig_holder::phase;
        int unsigned    n = fw_sig_holder::comb_changes;
        if (s == null || s.kernel == null) return;
        if (m_fresh || valid != m_valid) begin
            fw_sig_holder::phase = m_ph(s.f_valid);
            s.set_valid(valid);
        end
        if (m_fresh || data != m_data) begin
            fw_sig_holder::phase = m_ph(s.f_data);
            s.set_data(data);
        end
        fw_sig_holder::phase = prev;
        m_fresh = 0;
        m_valid = valid;
        m_data  = data;
        if (fw_sig_holder::comb_changes != n) s.kernel.settle_now(s);
    endfunction

    // !into: the pins' ready.
    function void put_bwd(bit ready);
        fw_rv_sig #(T)  s = sig();
        fw_sync_phase_e prev = fw_sig_holder::phase;
        int unsigned    n = fw_sig_holder::comb_changes;
        if (s == null || s.kernel == null) return;
        if (m_fresh || ready != m_ready) begin
            fw_sig_holder::phase = m_ph(s.f_ready);
            s.set_ready(ready);
        end
        fw_sig_holder::phase = prev;
        m_fresh = 0;
        m_ready = ready;
        if (fw_sig_holder::comb_changes != n) s.kernel.settle_now(s);
    endfunction

    function bit comb(string fname);
        fw_rv_sig #(T) s = sig();
        return s != null && s.field(fname).comb;
    endfunction

    function bit get_valid();
        fw_rv_sig #(T) s = sig();
        if (s == null || s.forced(s.f_valid)) return 0;
        return s.f_valid.comb ? s.valid_cur : s.valid_nxt;
    endfunction
    function bit get_ready();
        fw_rv_sig #(T) s = sig();
        if (s == null || s.forced(s.f_ready)) return 0;
        return s.f_ready.comb ? s.ready_cur : s.ready_nxt;
    endfunction
    function T get_data();
        fw_rv_sig #(T) s = sig();
        if (s == null) return '0;
        return s.f_data.comb ? s.data_cur : s.data_nxt;
    endfunction

    // The phase a pin write of field f runs in: comb for a comb field, run
    // (with its early-write guard) for a sync field.
    protected static function fw_sync_phase_e m_ph(fw_sync_field f);
        return f.comb ? FW_SYNC_PH_COMB : FW_SYNC_PH_RUN;
    endfunction
endclass
