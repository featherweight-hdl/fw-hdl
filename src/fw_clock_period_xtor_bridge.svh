
typedef class fw_component;

// The edge driver of a period root: edge k at k * period from time 0,
// computed by its interface.
class fw_edge_driver_period extends fw_edge_driver;
    virtual fw_clock_period_xtor_if vif;

    function new(virtual fw_clock_period_xtor_if vif);
        this.vif = vif;
    endfunction

    virtual function longint unsigned edges();
        return vif.edges();
    endfunction

    virtual task wait_edge(longint unsigned k);
        vif.wait_edge(k);
    endtask

    // An edge due now counts as passed even before the kernel releases it:
    // a computed edge comes before a delay ending at its time (C4).
    protected virtual function longint unsigned m_pos();
        longint unsigned e = edges();
        return (e > released) ? e : released;
    endfunction
endclass

// The ROOT clock domain backed by a PERIOD transactor (no signal clock). The
// delay-based analogue of fw_clock_xtor_bridge: it wraps a fw_clock_period_xtor_if
// virtual interface, whose edges are computed (edge k at k*PERIOD from time 0)
// rather than seen on a net. tick() counts them through the edge driver.
// Like a derived domain it is both the export a child's `clock` port connects to
// and the imp it resolves, so fw_root/fw_component_root can do
// `root.clock.connect(<this>)` to seat the whole tree's default domain. Being the
// root, root_ticks() is the identity: n ticks of the root domain ARE n root cycles.
class fw_clock_period_xtor_bridge extends fw_export #(fw_clock_domain_if)
        implements fw_clock_domain_if, fw_edge_source;
    virtual fw_clock_period_xtor_if vif;
    protected fw_edge_driver_period m_drv;

    function new(string name, fw_component parent, virtual fw_clock_period_xtor_if vif);
        super.new(name, parent, this);   // register `this` as the export's imp
        set_ambient();                   // domain plumbing, not a data binding
        this.vif = vif;
        m_drv = new(vif);
    endfunction

    // Once a sync kernel owns the root, by release count (fw_edge_driver);
    // before, n edges from now on the interface, the form the elaborator
    // (fe/elab) reads.
    virtual task tick(int n = 1);
        if (m_drv.owned) m_drv.tick(1, n);
        else             vif.tick(n);    // tick(0) -> #0
    endtask

    virtual function fw_edge_driver edge_driver();
        return m_drv;
    endfunction

    virtual function longint root_ticks(int n = 1);
        return n;                        // I am the root domain
    endfunction

    // --- fw_domain_if: a root clock domain -----------------------------------
    virtual function fw_domain_kind_e domain_kind();   return FW_DOMAIN_CLOCK; endfunction
    virtual function string           domain_name();   return full_name();     endfunction
    virtual function int              domain_nsrc();   return 0;               endfunction
    virtual function fw_domain_if     domain_src(int i); return null;          endfunction
    virtual function fw_domain_if     domain_equiv();  return this;            endfunction
endclass
