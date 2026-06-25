// Producer/consumer demo of the std `put` protocol -- class layer. The put API
// (fw_put_if) and its impl macro (`FW_PUT_IMP) are built into the fw standard
// library (fw_std_pkg / fw_std_macros.svh), so this demo carries no protocol of
// its own -- just the two components. The macro file is included first so it is
// visible where consumer uses it. fw_hdl_pkg supplies fw_component / fw_port /
// fw_export; fw_std_pkg supplies fw_put_if.
`include "fw_std_macros.svh"

package intf_pc_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;

    typedef bit [31:0] data_t;

    `include "producer.svh"   // consumes fw_put_if
    `include "consumer.svh"   // provides fw_put_if (via `FW_PUT_IMP)
    `include "pc_top.svh"     // instances + connects producer/consumer

endpackage
