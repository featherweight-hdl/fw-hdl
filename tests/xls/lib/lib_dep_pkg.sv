// fw_dep_tracker for tests/xls/lib/test_dep_tracker.py: sizes that fill
// quickly, one that is not a power of two, one producer; and the target's
// size for the QoR probe.
`include "fw_std_macros.svh"

package lib_dep_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;

    typedef fw_dep_tracker #(4, 4) dep_4_4;
    typedef fw_dep_tracker #(8, 6) dep_8_6;
    typedef fw_dep_tracker #(1, 2) dep_1_2;
    typedef fw_dep_tracker #(5, 3) dep_5_3;

    typedef fw_dep_tracker #(32, 32) dep_q32;
    typedef fw_dep_tracker #(64, 64) dep_q64;
endpackage
