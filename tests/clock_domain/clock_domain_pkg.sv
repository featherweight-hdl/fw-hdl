// Clock-domain demo -- class layer. The hardware-description classes live here,
// one per .svh, included into this package (interface/module units, like the
// fw_root instance, stay in the testbench). fw_hdl_pkg supplies fw_component /
// fw_port / fw_export / fw_clock_domain.
package clock_domain_pkg;
    import fw_hdl_pkg::*;

    `include "cd_leaf.svh"
    `include "cd_sub.svh"   // uses cd_leaf
    `include "cd_top.svh"   // uses cd_leaf, cd_sub

endpackage
