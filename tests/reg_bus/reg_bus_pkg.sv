
// M3 bus-integration demo -- class layer. A CPU reaches a device's register
// block by offset through an fw_port #(fw_reg_block_if); the device provides the
// block as an fw_export and drives status from its hardware side. fw_hdl_pkg
// supplies fw_component / fw_port / fw_export and the register model.
package reg_bus_pkg;
    import fw_hdl_pkg::*;

    // CTRL: software sets `go` (RW). STATUS: hardware drives done/payload (RO to sw).
    typedef struct packed { bit [30:0] rsvd; bit go;   } ctrl_t;
    typedef struct packed { bit [30:0] payload; bit done; } status_t;

    `include "reg_device.svh"    // provides fw_reg_block_if (export)
    `include "reg_cpu.svh"       // consumes fw_reg_block_if (port)
    `include "reg_bus_top.svh"   // instances + connects
endpackage
