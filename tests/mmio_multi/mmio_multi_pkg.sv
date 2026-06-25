
// Multi-FSM MMIO example: one register model drives two independent FSMs (the
// minimal stand-in for an FSM-per-DMA-channel). Proves the SV->RTL front end
// emits the regblock once and wires several FSMs to it.
package mmio_multi_pkg;
    import fw_hdl_pkg::*;

    typedef struct packed { bit [30:0] rsvd; bit go;   } mm_ctrl_t;
    typedef struct packed { bit [30:0] rsvd; bit flag; } mm_status_t;

    `include "multi_regs.svh"    // multi_regs (the shared register model)
    `include "multi_fsm_a.svh"   // FSM A (CTRL_A -> STATUS_A)
    `include "multi_fsm_b.svh"   // FSM B (CTRL_B -> STATUS_B)
    `include "multi_top.svh"     // class-level assembly (for elaboration)
endpackage
