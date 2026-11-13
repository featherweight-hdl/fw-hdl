typedef class fw_component;

// A reset domain controlled by a REGISTER BIT (a soft reset), derived from a
// source reset domain: in reset while the source is, or while the bit is set
// (active_low = 1: while the bit is clear -- an enable bit).
//
//     ch_rst = new("ch_rst", this, regs.ctrl, 3);  // build(): ctrl[3] = 1 resets ch
//     ...
//     ch_rst.src.connect(this.reset);              // connect(): root reset OR ctrl[3]
//     ch.reset.connect(ch_rst);                    // ch's subtree follows it
//
// The components in it follow it (docs/reference/clocking.md, "The run
// lifecycle"): setting the bit kills their run()s at the next tick of the
// domain's clock, clearing it starts them again.
//
// in_reset() reads read_val(), the register's canonical value (a read provider
// wins), so hardware and software agree on it. It lowers to logic:
// `src_reset | (reg_q[bit] ^ active_low)`.
//
// Assumption: the register is written in the clock domain `src` is synchronous
// to (software writes arrive as write_val() at a tick of that clock). A
// register written from another clock needs a synchronized reset domain (not
// built yet).
class fw_reg_reset_domain #(int W = 32) extends fw_export #(fw_reset_domain_if)
        implements fw_reset_domain_if;
    // The reset this one extends; normally the owner's. Parentless: wired in
    // the owner's connect(). Unbound: the bit alone.
    fw_port #(fw_reset_domain_if) src;

    protected fw_reg_base #(W) m_reg;
    protected int unsigned     m_bit;
    protected bit              m_active_low;

    function new(string name, fw_component parent, fw_reg_base #(W) r,
                 int unsigned bit_idx, bit active_low = 1'b0);
        super.new(name, parent, this);   // register `this` as the export's imp
        set_ambient();                   // domain plumbing, not a data binding
        src          = new("src", null);
        m_reg        = r;
        m_bit        = bit_idx;
        m_active_low = active_low;
    endfunction

    // The register bit's contribution alone.
    function bit bit_in_reset();
        bit [W-1:0] v;
        v = m_reg.read_val();
        return v[m_bit] ^ m_active_low;
    endfunction

    virtual function bit in_reset();
        if (src.is_connected() && src.get_if().in_reset()) return 1'b1;
        return bit_in_reset();
    endfunction

    // The waits tick the domain's clock: its sync_clock(), or with no source
    // the owner's clock.
    protected function fw_clock_domain_if wait_clock();
        fw_clock_domain_if c;
        fw_component       o;
        c = sync_clock();
        if (c != null) return c;
        o = ep_owner();
        return o.clock.get_if();
    endfunction

    virtual task wait_assert();
        fw_clock_domain_if c;
        if (in_reset()) return;
        c = wait_clock();
        while (!in_reset()) c.tick(1);
    endtask

    virtual task wait_deassert();
        fw_clock_domain_if c;
        if (!in_reset()) return;
        c = wait_clock();
        while (in_reset()) c.tick(1);
    endtask

    virtual function bit is_async();
        return src.is_connected() ? src.get_if().is_async() : 1'b0;
    endfunction

    virtual function fw_clock_domain_if sync_clock();
        return src.is_connected() ? src.get_if().sync_clock() : null;
    endfunction

    // --- fw_domain_if: derived from src --------------------------------------
    virtual function fw_domain_kind_e domain_kind(); return FW_DOMAIN_RESET; endfunction
    virtual function string           domain_name(); return full_name();     endfunction
    virtual function int              domain_nsrc(); return src.is_connected() ? 1 : 0; endfunction
    virtual function fw_domain_if     domain_src(int i);
        fw_reset_domain_if s;
        if (i != 0 || !src.is_connected()) return null;
        s = src.get_if();
        return s;
    endfunction
    virtual function fw_domain_if     domain_equiv(); return this; endfunction
endclass
