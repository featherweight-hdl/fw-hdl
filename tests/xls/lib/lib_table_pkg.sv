// fw_keyed_table for tests/xls/lib/test_keyed_table.py: the class itself, at
// sizes that fill quickly, one that is not a power of two, and one slot; and
// router-sized ones for the QoR probe.
`include "fw_std_macros.svh"

package lib_table_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;

    typedef fw_keyed_table #(bit [3:0], bit [7:0], 4)  tbl_4;
    typedef fw_keyed_table #(bit [5:0], bit [7:0], 16) tbl_16;
    typedef fw_keyed_table #(bit [3:0], bit [5:0], 5)  tbl_5;
    typedef fw_keyed_table #(bit [3:0], bit [7:0], 1)  tbl_1;
    typedef fw_keyed_table #(bit [3:0], bit [7:0], 8)  tbl_8;

    // About the completion router's entry (12-bit key, 48-bit value), for
    // qor_keyed_table.py.
    typedef fw_keyed_table #(bit [11:0], bit [47:0], 16)  tbl_q16;
    typedef fw_keyed_table #(bit [11:0], bit [47:0], 64)  tbl_q64;
    typedef fw_keyed_table #(bit [11:0], bit [47:0], 256) tbl_q256;
endpackage
