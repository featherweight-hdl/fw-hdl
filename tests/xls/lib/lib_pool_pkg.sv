// fw_token_pool and fw_slot_reserve for tests/xls/lib/test_token_pool.py:
// sizes that run out quickly, one that is not a power of two, one token, and
// a carried value; and larger pools for the QoR probe.
`include "fw_std_macros.svh"

package lib_pool_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;

    typedef fw_token_pool #(4)              pool_4;
    typedef fw_token_pool #(5, bit [5:0])   pool_5;
    typedef fw_token_pool #(1, bit [3:0])   pool_1;
    typedef fw_token_pool #(16, bit [7:0])  pool_16;

    typedef fw_slot_reserve #(8, 4)              rsv_8;
    typedef fw_slot_reserve #(6, 3, bit [5:0])   rsv_6;
    typedef fw_slot_reserve #(4, 4, bit [3:0])   rsv_4;

    typedef fw_token_pool #(64, bit [31:0])  pool_q64;
    typedef fw_token_pool #(256, bit [31:0]) pool_q256;
endpackage
