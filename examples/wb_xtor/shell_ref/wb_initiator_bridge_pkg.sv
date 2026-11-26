// T0 hand-written reference (docs/design/xtor-shell-plan.md): the bridge,
// the class side of the shell. It implements the transactor's API on the
// same export (t) as wb_initiator, by calling the interface's tasks
// through a virtual interface. It has no pins: they are on the shell.
//
// Hand-off (open, plan §5): fw_object has no path and rt-sv no type
// override yet, so the HVL top assigns vif after elaboration and builds
// the bridge in place of wb_initiator itself.
`include "fw_hdl_macros.svh"

package wb_initiator_bridge_pkg;
    import fw_hdl_pkg::*;
    import wb_pkg::*;

    class wb_initiator_bridge extends fw_component implements wb_if #(32, 32);
        `fw_component_utils(wb_initiator_bridge)
        typedef wb_if #(32, 32)::req_t req_t;
        typedef wb_if #(32, 32)::rsp_t rsp_t;

        fw_export #(wb_if #(32, 32)) t;
        virtual wb_initiator_xtor_if vif;

        virtual function void build();
            t = fw_export #(wb_if #(32, 32))::create("t", this);
        endfunction

        // wb_initiator::access, its crossings carried by the interface.
        virtual task access(output rsp_t rsp, input req_t req);
            vif.reqs_put(req);
            vif.rsps_get(rsp);
        endtask
    endclass
endpackage
