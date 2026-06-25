
// Read-gated MMIO example: the FSM reads a CTRL field and conditionally drives
// STATUS (the reg_device shape). Exercises read() -> hwif_out input and an `if`
// gating the hardware update.
package mmio_gated_pkg;
    import fw_hdl_pkg::*;

    // CTRL: software sets `go` and `arm` (both RW, watched).
    typedef struct packed { bit [29:0] rsvd; bit arm; bit go; } gctrl_t;
    typedef struct packed { bit [30:0] rsvd; bit flag;         } gstatus_t;

    `include "gated_regs.svh"    // gated_regs (the register model)
    `include "gated_fsm.svh"     // gated_fsm  (read-gated update)
    `include "gated_top.svh"     // class-level assembly (for elaboration)
endpackage
