
// Featherweight standard protocol library -- the std layer on top of the
// fw_hdl_pkg kernel. fw_hdl_pkg supplies the deferred-binding mechanism
// (fw_component / fw_port / fw_export / clock domain); this package supplies the
// reusable, transaction-level protocol APIs that ride over it: put/get (no
// handshake), request/response, and the put transactor bridge.
//
// SystemVerilog packages don't nest, so this separate package -- imported
// alongside fw_hdl_pkg -- is how the kernel/std-library layering is expressed.
// One-way dependency: fw_std_pkg imports fw_hdl_pkg, never the reverse.
package fw_std_pkg;
    import fw_hdl_pkg::*;

    // Transaction-level protocol APIs (interface classes).
    `include "fw_put_if.svh"      // put(t)            -- write to an output, no handshake
    `include "fw_get_if.svh"      // get(t)            -- sample an input, no handshake
    `include "fw_reqrsp_if.svh"   // call(out, in)     -- blocking request/response

    // Signal-level bridge for the put protocol: holds a virtual
    // fw_put_xtor_if (a separate compilation unit) and implements fw_put_if.
    `include "fw_put_xtor_bridge.svh"

endpackage
