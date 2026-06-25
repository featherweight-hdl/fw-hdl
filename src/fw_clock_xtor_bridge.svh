
typedef class fw_component;

// The ROOT clock domain: the base case of the domain chain.
//
// It bridges the clock-domain API to the signal-level world by wrapping a
// fw_clock_xtor_if virtual interface (driven by an actual clock/reset). Like a
// derived domain it is both the export a port connects to and the imp it
// resolves, so fw_root can do `root.clock.connect(<this>)` to seat the whole
// tree's default domain. Being the root, root_ticks() is the identity: n ticks
// of the root domain ARE n root clocks.
class fw_clock_xtor_bridge extends fw_export #(fw_clock_domain_if)
        implements fw_clock_domain_if;
    virtual fw_clock_xtor_if vif;

    function new(string name, fw_component parent, virtual fw_clock_xtor_if vif);
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
