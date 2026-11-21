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
// From the pins (put_fwd/put_bwd): a pin is an input from outside the
// domain, so its value lands at once, in a comb field or a sync field's
// current value alike, and the kernel settles the domain (settle_now): a
// comb path through the tree reaches the other pins in the same time step,
// and the tree's next step() reads the value. Pins that RTL flops drive
// change after the edge's group (in the NBA region); a pin driven by a
// blocking assignment at the edge is a race, as in RTL. To the pins
// (get_*): the current values, reset-forced, which the module drives
// nonblocking after the update and settle, so RTL flops at the edge sample
// the values from before it (sync-task-domains.md §6.3, §6.5 item 9).
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
        bit             now = 0;   // a sync field's current value changed
        if (s == null || s.kernel == null) return;
        if (m_fresh || valid != m_valid) begin
            fw_sig_holder::phase = m_ph(s.f_valid);
            s.set_valid(valid);
            if (!s.f_valid.comb) begin
                now |= (s.valid_cur != valid);
                s.valid_cur = valid;
            end
        end
        if (m_fresh || data != m_data) begin
            fw_sig_holder::phase = m_ph(s.f_data);
            s.set_data(data);
            if (!s.f_data.comb) begin
                now |= (s.data_cur != data);
                s.data_cur = data;
            end
        end
        fw_sig_holder::phase = prev;
        m_fresh = 0;
        m_valid = valid;
        m_data  = data;
        if (fw_sig_holder::comb_changes != n || now) s.kernel.settle_now(s);
    endfunction

    // !into: the pins' ready.
    function void put_bwd(bit ready);
        fw_rv_sig #(T)  s = sig();
        fw_sync_phase_e prev = fw_sig_holder::phase;
        int unsigned    n = fw_sig_holder::comb_changes;
        bit             now = 0;   // a sync field's current value changed
        if (s == null || s.kernel == null) return;
        if (m_fresh || ready != m_ready) begin
            fw_sig_holder::phase = m_ph(s.f_ready);
            s.set_ready(ready);
            if (!s.f_ready.comb) begin
                now |= (s.ready_cur != ready);
                s.ready_cur = ready;
            end
        end
        fw_sig_holder::phase = prev;
        m_fresh = 0;
        m_ready = ready;
        if (fw_sig_holder::comb_changes != n || now) s.kernel.settle_now(s);
    endfunction

    function bit get_valid();
        fw_rv_sig #(T) s = sig();
        if (s == null || s.forced(s.f_valid)) return 0;
        return s.valid_cur;
    endfunction
    function bit get_ready();
        fw_rv_sig #(T) s = sig();
        if (s == null || s.forced(s.f_ready)) return 0;
        return s.ready_cur;
    endfunction
    function T get_data();
        fw_rv_sig #(T) s = sig();
        if (s == null) return '0;
        return s.data_cur;
    endfunction

    // The phase a pin write of field f runs in: comb for a comb field;
    // none for a sync field (a pin is not task code: no crossing-port
    // rules, and this class sets the current value itself).
    protected static function fw_sync_phase_e m_ph(fw_sync_field f);
        return f.comb ? FW_SYNC_PH_COMB : FW_SYNC_PH_NONE;
    endfunction
endclass
