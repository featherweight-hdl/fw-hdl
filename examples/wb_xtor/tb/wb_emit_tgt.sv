// What shell_ref/emit_core.py lowers for the target: wb_target #(32, 32),
// its pins connected up to the top's bundle (the module's Wishbone pins)
// and its crossings lowered to ready/valid ports.
`include "fw_hdl_macros.svh"

package wb_emit_tgt_pkg;
    import fw_hdl_pkg::*;
    import wb_pkg::*;

    // Binds xt.p: the API port is the bridge's (it calls through it from
    // run(), which lowering drops), so nothing here is lowered.
    class api_stub extends fw_component implements wb_if #(32, 32);
        `fw_component_utils(api_stub)
        typedef wb_if #(32, 32)::req_t req_t;
        typedef wb_if #(32, 32)::rsp_t rsp_t;
        fw_export #(wb_if #(32, 32)) t;
        virtual function void build();
            t = fw_export #(wb_if #(32, 32))::create("t", this);
        endfunction
        virtual task access(output rsp_t rsp, input req_t req);
            rsp = '0;
        endtask
    endclass

    class top extends fw_component;
        `fw_component_utils(top)
        fw_clock_domain               clk;
        fw_mirror #(wb_bundle #(32, 32)) wb;
        wb_target #(32, 32)           xt;
        api_stub                      a;
        virtual function void build();
            clk = fw_clock_domain::create("clk", this, fw_clock_kind::root(10ns));
            fw_clock_domain::set(this, clk);
            wb = fw_mirror #(wb_bundle #(32, 32))::create("wb", this);
            xt = wb_target #(32, 32)::create("xt", this);
            a  = api_stub::create("a", this);
        endfunction
        virtual function void connect();
            xt.pins.connect_up(wb);
            xt.p.connect(a.t);
        endfunction
    endclass
endpackage
