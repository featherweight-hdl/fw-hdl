
// MMIO worked example -- the minimal MMIO-driven FSM. A software actor writes
// CTRL (the watched register); the hardware FSM sleeps on a watch-set over CTRL
// and, on each change, pulses STATUS.flag through the masked hardware update
// path. This is the smallest design the SV->RTL front end drives end to end
// (FSM SPL + regblock + structural top, all generated from SV).
package mmio_pkg;
    import fw_hdl_pkg::*;

    // CTRL: software sets `go` (RW, watched).  STATUS: hardware drives `flag` (RO to sw).
    typedef struct packed { bit [30:0] rsvd; bit go;   } mmio_ctrl_t;
    typedef struct packed { bit [30:0] rsvd; bit flag; } mmio_status_t;

    `include "mmio_regs.svh"     // mmio_regs (the register model)
    `include "mmio_fsm.svh"      // mmio_fsm  (an MMIO-driven fw_component)
    `include "mmio_top.svh"      // class-level assembly (for elaboration)
endpackage
