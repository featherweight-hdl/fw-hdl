typedef class fw_component;

// A COMBINED reset domain: in reset while any of its n sources is.
//
//     any = new("any", this, 2);          // build()
//     any.src[0].connect(this.reset);     // connect()
//     any.src[1].connect(wdog.rst_out);   // another reset domain (an export)
//     ip.reset.connect(any);
//
// is_async() is the OR of the sources'. sync_clock() is the sources' common
// clock when they all deassert on the SAME clock, else null: its deassertion
// is then synchronized to nothing, which the crossing check reports where the
// domain is used. A one-source combine is a named pass-through (it behaves as,
// and relates SAME to, its source), the analogue of a divide-by-1 clock domain.
//
// in_reset() lowers to the OR of the sources' in_reset().
class fw_reset_combine extends fw_export #(fw_reset_domain_if)
        implements fw_reset_domain_if;
    fw_port #(fw_reset_domain_if) src[];   // parentless: wired in the owner's connect()
    protected event               m_any;   // a source asserted (wait_assert, no common clock)

    function new(string name, fw_component parent, int n = 2);
        super.new(name, parent, this);   // register `this` as the export's imp
        set_ambient();                   // domain plumbing, not a data binding
        src = new[n];
        foreach (src[i]) src[i] = new($sformatf("src[%0d]", i), null);
    endfunction

    virtual function bit in_reset();
        foreach (src[i]) begin
            if (src[i].is_connected() && src[i].get_if().in_reset()) return 1'b1;
        end
        return 1'b0;
    endfunction

    virtual function bit is_async();
        foreach (src[i]) begin
            if (src[i].is_connected() && src[i].get_if().is_async()) return 1'b1;
        end
        return 1'b0;
    endfunction

    virtual function fw_clock_domain_if sync_clock();
        fw_clock_domain_if c, ci;
        bit                first = 1'b1;
        foreach (src[i]) begin
            if (!src[i].is_connected()) continue;
            ci = src[i].get_if().sync_clock();
            if (ci == null) return null;
            if (first) begin
                c     = ci;
                first = 1'b0;
            end else if (fw_domains::relate(c, ci) != FW_DOMAIN_SAME) begin
                return null;
            end
        end
        return c;
    endfunction

    // With a common clock, a tick loop on it. Without one, on the sources'
    // own waits.
    virtual task wait_deassert();
        fw_clock_domain_if c;
        if (!in_reset()) return;
        c = sync_clock();
        if (c != null) begin
            while (in_reset()) c.tick(1);
        end else begin
            while (in_reset()) begin
                foreach (src[i]) begin
                    if (src[i].is_connected() && src[i].get_if().in_reset())
                        src[i].get_if().wait_deassert();
                end
            end
        end
    endtask

    virtual task wait_assert();
        fw_clock_domain_if c;
        if (in_reset()) return;
        c = sync_clock();
        if (c != null) begin
            while (!in_reset()) c.tick(1);
        end else begin
            // One waiter per source; the first to see its source assert ends
            // the wait. Inside its own fork...join, so `disable fork` ends only
            // the waiters, not the caller's other children (a supervisor's
            // run()s).
            fork
                begin
                    foreach (src[i]) begin
                        automatic int k = i;
                        if (src[k].is_connected()) begin
                            fork
                                begin
                                    src[k].get_if().wait_assert();
                                    -> m_any;
                                end
                            join_none
                        end
                    end
                    @(m_any);
                    disable fork;
                end
            join
        end
    endtask

    // --- fw_domain_if: derived from the sources ------------------------------
    virtual function fw_domain_kind_e domain_kind(); return FW_DOMAIN_RESET; endfunction
    virtual function string           domain_name(); return full_name();     endfunction
    virtual function int              domain_nsrc(); return src.size();      endfunction
    virtual function fw_domain_if     domain_src(int i);
        fw_reset_domain_if s;
        if (i < 0 || i >= src.size() || !src[i].is_connected()) return null;
        s = src[i].get_if();
        return s;
    endfunction
    virtual function fw_domain_if     domain_equiv();
        fw_domain_if s;
        if (src.size() != 1) return this;
        s = domain_src(0);
        return (s != null) ? s.domain_equiv() : this;
    endfunction
endclass
