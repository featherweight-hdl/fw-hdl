// What shell_ref/emit_core.py lowers for the target: wb_target #(32, 32),
// its pins connected up to the top's bundle (the module's Wishbone pins)
// and its crossings lowered to ready/valid ports. xt.p stays unbound: only
// xt's run() calls through it, and run() only hands off, so lowering drops
// it (it is the bridge's; protocols.md, "Resolution"). Lowering needs a
// reset domain (domains.md, "Lookup"): rst, which wb_target doesn't use.
`include "fw_hdl_macros.svh"

package wb_emit_tgt_pkg;
    import fw_hdl_pkg::*;
    import wb_pkg::*;

    class top extends fw_component;
        `fw_component_utils(top)
        fw_clock_domain               clk;
        fw_reset_domain               rst;
        fw_mirror #(wb_bundle #(32, 32)) wb;
        wb_target #(32, 32)           xt;
        virtual function void build();
            clk = fw_clock_domain::create("clk", this, fw_clock_kind::root(10ns));
            rst = fw_reset_domain::create("rst", this,
                                          fw_reset_kind::root(fw_reset_kind::SYNC, clk));
            fw_clock_domain::set(this, clk);
            fw_reset_domain::set(this, rst);
            wb = fw_mirror #(wb_bundle #(32, 32))::create("wb", this);
            xt = wb_target #(32, 32)::create("xt", this);
        endfunction
        virtual function void connect();
            xt.pins.connect_up(wb);
        endfunction
    endclass
endpackage
