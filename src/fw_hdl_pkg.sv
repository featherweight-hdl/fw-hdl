
package fw_hdl_pkg;
    `include "fw_elaboratable.svh"
    `include "fw_runnable.svh"
    // Deferred-binding wrappers and the clock-domain API must precede
    // fw_component, which now holds an fw_port #(fw_clock_domain_if) `clock`.
    `include "fw_if_base.svh"
    `include "fw_clock_domain_if.svh"
    `include "fw_export.svh"
    `include "fw_port.svh"
    `include "fw_clock_domain.svh"
    `include "fw_clock_xtor_bridge.svh"
    `include "fw_component.svh"
    `include "fw_component_param.svh"
    `include "fw_component_root.svh"
    `include "fw_component_root_param.svh"

    // Register model -- a core modeling aspect, so it lives in the kernel
    // alongside the component/port/export/clock-domain machinery (it is "just
    // another API" carried over fw_port/fw_export, like fw_clock_domain_if). The
    // interface classes come first; fw_reg_base forward-declares fw_reg_set (the
    // register and its watch-set are mutually referential).
    `include "fw_reg_rd_if.svh"     // hardware read provider hook
    `include "fw_reg_wr_if.svh"     // hardware write observer hook
    `include "fw_reg_val_if.svh"    // untyped (value-level) register API
    `include "fw_reg_block_if.svh"  // addressable group API (bus-facing)
    `include "fw_reg_base.svh"      // register state machine (untyped)
    `include "fw_reg.svh"           // typed register over a packed struct
    `include "fw_reg_set.svh"       // hierarchical watch-set (wait_change)
    `include "fw_reg_block.svh"     // register group: offsets, decode

endpackage
