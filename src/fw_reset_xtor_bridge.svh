typedef class fw_component;

// The ROOT reset domain: bridges the reset-domain API to a reset pin through a
// fw_reset_xtor_if virtual interface (active high; an active-low device pin is
// inverted where it enters the root, e.g. `fw_root_begin(top, u_root, aclk,
// !aresetn)`).
//
// Like the clock bridge it is both the export a component's `reset` port
// connects to and the imp it resolves. Its deassertion is aligned to the clock
// bound to `clk` (fw_root binds the root clock domain); its assertion is
// asynchronous (fw_root reacts to `posedge reset`).
//
// Because fw_root tears the tree down on reset, live class code never sees the
// root reset domain asserted: in_reset() is 0 whenever anything runs. The root
// domain is still the source that derived reset domains extend, and the reset
// formal and lowering take as the design reset.
class fw_reset_xtor_bridge extends fw_export #(fw_reset_domain_if)
        implements fw_reset_domain_if;
    virtual fw_reset_xtor_if vif;
    // The clock deassertion is synchronous to. Parentless: wired explicitly.
    fw_port #(fw_clock_domain_if) clk;

    function new(string name, fw_component parent, virtual fw_reset_xtor_if vif);
        super.new(name, parent, this);   // register `this` as the export's imp
        set_ambient();                   // domain plumbing, not a data binding
        this.vif = vif;
        clk      = new("clk", null);
    endfunction

    virtual function bit in_reset();
        return vif.in_reset();
    endfunction

    virtual task wait_assert();
        vif.wait_assert();
    endtask

    virtual task wait_deassert();
        vif.wait_deassert();
    endtask

    virtual function bit is_async();
        return 1'b1;
    endfunction

    virtual function fw_clock_domain_if sync_clock();
        return clk.is_connected() ? clk.get_if() : null;
    endfunction

    // --- fw_domain_if: a root reset domain -----------------------------------
    virtual function fw_domain_kind_e domain_kind();   return FW_DOMAIN_RESET; endfunction
    virtual function string           domain_name();   return full_name();     endfunction
    virtual function int              domain_nsrc();   return 0;               endfunction
    virtual function fw_domain_if     domain_src(int i); return null;          endfunction
    virtual function fw_domain_if     domain_equiv();  return this;            endfunction
endclass
