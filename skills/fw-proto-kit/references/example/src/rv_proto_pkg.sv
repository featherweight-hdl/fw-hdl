// Ready/valid protocol kit -- class layer. The transactor SV interfaces and
// modules (rv_*_xtor*.sv) are separate compilation units (an interface/module
// cannot live in a package); they are listed alongside this file in the FileSet.
//
// Macros are included BEFORE the package so they are visible where the bridges
// use them. fw_hdl_pkg supplies fw_component / fw_port / fw_export.
`include "rv_proto_macros.svh"

package rv_proto_pkg;
    import fw_hdl_pkg::*;

    // API interface-classes (each ships a `FW_RV_*_IMP macro, see rv_proto_macros).
    `include "rv_initiator_if.svh"
    `include "rv_target_if.svh"
    `include "rv_monitor_if.svh"

    // Bridge classes -- hold a virtual transactor-interface and implement/consume
    // the API. They reference the transactor SV interfaces by their (unmangled)
    // names, so those interfaces must be compiled in the same image.
    `include "rv_initiator_bridge.svh"
    `include "rv_target_bridge.svh"
    `include "rv_monitor_bridge.svh"

endpackage
