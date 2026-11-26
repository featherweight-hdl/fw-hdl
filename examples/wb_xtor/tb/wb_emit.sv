// What scripts/emit_rtl.py lowers to RTL: wb_initiator #(32, 32), its pins
// connected up to the top's bundle (the module's Wishbone pins) and its
// crossings lowered to the top's xi_reqs_* / xi_rsps_* ready/valid ports.
`include "fw_hdl_macros.svh"

package wb_emit_pkg;
    import fw_hdl_pkg::*;
    import wb_pkg::*;

    class top extends fw_component;
        `fw_component_utils(top)
        fw_clock_domain               clk;
        fw_bundle #(wb_bundle #(32, 32)) wb;
        wb_initiator #(32, 32)        xi;
        virtual function void build();
            clk = fw_clock_domain::create("clk", this, fw_clock_kind::root(10ns));
            fw_clock_domain::set(this, clk);
            wb = fw_bundle #(wb_bundle #(32, 32))::create("wb", this);
            xi = wb_initiator #(32, 32)::create("xi", this);
        endfunction
        virtual function void connect();
            xi.pins.connect_up(wb);
        endfunction
    endclass
endpackage
