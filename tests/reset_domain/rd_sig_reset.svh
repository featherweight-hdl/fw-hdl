// A bench-local ROOT reset domain over a bit the testbench sets (the
// fake_clock pattern), so a source's assertion is observable to live class
// code -- which the fw_root reset domain never is (reset tears the tree down).
// Deassertion is aligned to the clock bound to `clk`.
class rd_sig_reset extends fw_export #(fw_reset_domain_if)
        implements fw_reset_domain_if;
    bit                           level;
    fw_port #(fw_clock_domain_if) clk;

    function new(string name, fw_component parent, bit init = 1'b0);
        super.new(name, parent, this);
        set_ambient();
        clk   = new("clk", null);
        level = init;
    endfunction

    function void set(bit v);
        level = v;
    endfunction

    virtual function bit in_reset();
        return level;
    endfunction
    virtual task wait_assert();
        while (!level) clk.get_if().tick(1);
    endtask
    virtual task wait_deassert();
        while (level) clk.get_if().tick(1);
    endtask
    virtual function bit is_async(); return 1'b0; endfunction
    virtual function fw_clock_domain_if sync_clock();
        return clk.is_connected() ? clk.get_if() : null;
    endfunction

    virtual function fw_domain_kind_e domain_kind(); return FW_DOMAIN_RESET; endfunction
    virtual function string domain_name(); return full_name(); endfunction
    virtual function int domain_nsrc(); return 0; endfunction
    virtual function fw_domain_if domain_src(int i); return null; endfunction
    virtual function fw_domain_if domain_equiv(); return this; endfunction
endclass
