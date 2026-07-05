
typedef class fw_component;

// The ROOT clock domain backed by a PERIOD transactor (no signal clock). The
// delay-based analogue of fw_clock_xtor_bridge: it wraps a fw_clock_period_xtor_if
// virtual interface whose tick(n) is a `#(n*PERIOD)` delay rather than n posedges.
// Like a derived domain it is both the export a child's `clock` port connects to
// and the imp it resolves, so fw_root/fw_component_root can do
// `root.clock.connect(<this>)` to seat the whole tree's default domain. Being the
// root, root_ticks() is the identity: n ticks of the root domain ARE n root cycles.
class fw_clock_period_xtor_bridge extends fw_export #(fw_clock_domain_if)
        implements fw_clock_domain_if;
    virtual fw_clock_period_xtor_if vif;

    function new(string name, fw_component parent, virtual fw_clock_period_xtor_if vif);
        super.new(name, parent, this);   // register `this` as the export's imp
        this.vif = vif;
    endfunction

    virtual task tick(int n = 1);
        vif.tick(n);                     // tick(0) -> #0, handled by the xtor if
    endtask

    virtual function longint root_ticks(int n = 1);
        return n;                        // I am the root domain
    endfunction
endclass
