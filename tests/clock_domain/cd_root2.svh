// A second, unrelated ROOT clock domain (domain_nsrc() == 0), for the
// relate() checks. Never ticked here; a real one would be bridged from a
// second clock pin.
class cd_root2 extends fw_export #(fw_clock_domain_if)
        implements fw_clock_domain_if;
    function new(string name, fw_component parent);
        super.new(name, parent, this);
        set_ambient();
    endfunction
    virtual task tick(int n = 1); #(n); endtask
    virtual function longint root_ticks(int n = 1); return n; endfunction
    virtual function fw_domain_kind_e domain_kind(); return FW_DOMAIN_CLOCK; endfunction
    virtual function string domain_name(); return full_name(); endfunction
    virtual function int domain_nsrc(); return 0; endfunction
    virtual function fw_domain_if domain_src(int i); return null; endfunction
    virtual function fw_domain_if domain_equiv(); return this; endfunction
endclass
