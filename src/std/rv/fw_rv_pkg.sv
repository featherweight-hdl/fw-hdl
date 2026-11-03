// Ready/valid protocol kit, class layer. The transactor interfaces and modules
// (fw_rv_*_xtor*.sv) are separate compilation units listed beside this file;
// the bridges name them, so they must be compiled in the same image.
//
// Payloads are `type T` throughout, pins included. Verilator rule (5.052): an
// interface used as a module port is declared without parameters, e.g.
// `fw_rv_initiator_xtor_if port`; a parameterized port spelling crashes it.
//
// The macros are included before the package so components that import it can
// use them.
`include "fw_rv_macros.svh"

package fw_rv_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;

    // API interface classes (each ships an `FW_RV_*_IMP macro).
    `include "fw_rv_initiator_if.svh"
    `include "fw_rv_target_if.svh"
    `include "fw_rv_monitor_if.svh"

    // Bridges: hold a virtual transactor interface and provide or consume an API.
    `include "fw_rv_initiator_bridge.svh"
    `include "fw_rv_target_bridge.svh"
    `include "fw_rv_monitor_bridge.svh"

    // Adapters: the std put/get APIs onto the rv transactors.
    `include "fw_put_to_rv_bridge.svh"
    `include "fw_get_from_rv_bridge.svh"
endpackage
