// T5 hand-written reference (docs/design/xtor-shell-plan.md): the target's
// bridge, the class side of its shell. It holds the transactor's port (p)
// and runs wb_target::run(), its crossings carried by the interface: the
// consumer provides the API implementation and never sees the shell. It
// has no pins: they are on the shell.
//
// Hand-off (open, plan §5): as wb_initiator_bridge, the HVL top assigns vif
// after elaboration (run() starts only once the top's initial block
// yields).
`include "fw_hdl_macros.svh"

package wb_target_bridge_pkg;
    import fw_hdl_pkg::*;
    import wb_pkg::*;

    class wb_target_bridge extends fw_component implements fw_run_if;
        `fw_component_utils(wb_target_bridge)
        typedef wb_if #(32, 32)::req_t req_t;
        typedef wb_if #(32, 32)::rsp_t rsp_t;

        fw_port #(wb_if #(32, 32)) p;
        virtual wb_target_xtor_if vif;

        virtual function void build();
            p = fw_port #(wb_if #(32, 32))::create("p", this);
        endfunction

        // wb_target::run, its crossings carried by the interface.
        virtual task run();
            wb_if #(32, 32) i = p.get_if();
            req_t r;
            rsp_t s;
            forever begin
                vif.reqs_get(r);
                i.access(s, r);
                vif.rsps_put(s);
            end
        endtask
    endclass
endpackage
