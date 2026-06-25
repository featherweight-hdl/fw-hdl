// Ready/valid protocol demo -- class layer. The hardware-description classes (the
// API interface-classes, the transactor bridges, and the components) live here,
// one per .svh, included into this package. The signal-level transactor
// interfaces/modules are separate compilation units in rv_proto_xtors.sv. The
// API impl macros are included before the package so they are visible where sink
// and observer use them. fw_hdl_pkg supplies fw_component / fw_port / fw_export.
`include "rv_proto_macros.svh"

package rv_proto_pkg;
    import fw_hdl_pkg::*;

    typedef logic [31:0]    data_t;
    localparam int unsigned N = 8;

    // API interface-classes (the class-level contract for each role).
    `include "rv_initiator_if.svh"
    `include "rv_target_if.svh"
    `include "rv_monitor_if.svh"

    // Bridge classes -- hold a virtual transactor-interface (from
    // rv_proto_xtors.sv) and implement/consume the API.
    `include "rv_initiator_bridge.svh"
    `include "rv_target_bridge.svh"
    `include "rv_monitor_bridge.svh"

    // Components: the pure class-layer testbench tree.
    `include "driver.svh"     // uses rv_initiator_if, data_t, N
    `include "sink.svh"       // provides rv_target_if  (via `FW_RV_TARGET_IMP)
    `include "observer.svh"   // provides rv_monitor_if (via `FW_RV_MONITOR_IMP)
    `include "rv_top.svh"     // instances driver/sink/observer

endpackage
