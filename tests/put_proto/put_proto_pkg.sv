// Signal-level demonstration of the std `put` protocol -- class layer. The put
// API (fw_put_if) and the signal bridge (fw_put_xtor_bridge) are built into the
// fw standard library; this package just supplies the demo producer and top.
// fw_hdl_pkg supplies fw_component / fw_port / fw_export; fw_std_pkg supplies
// fw_put_if and fw_put_xtor_bridge (the put transactor interface itself,
// fw_put_xtor_if, is a separate compilation unit listed in the FileSet).
package put_proto_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;

    typedef bit [31:0]      data_t;
    localparam int unsigned N    = 8;
    localparam data_t       BASE = 32'hbeef_0000;

    `include "producer.svh"   // consumes fw_put_if, drives N beats
    `include "put_top.svh"    // instances the producer

endpackage
