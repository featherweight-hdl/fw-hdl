// fw_credit_tx specializations under test (tests/xls/lib/test_credit_tx.py).
`include "fw_std_macros.svh"

package lib_credit_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;

    // One VC: the credit_tx template's shape.
    typedef fw_credit_tx #(bit [7:0], 4)                                     ctx_1;
    // One VC, four credits per value.
    typedef fw_credit_tx #(bit [7:0], 8, 1, 0, FW_CREDIT_POOL_FIRST, 4)      ctx_1c4;
    // Three VCs, one reserved credit each, pool first.
    typedef fw_credit_tx #(bit [7:0], 6, 3, 1, FW_CREDIT_POOL_FIRST, 1)      ctx_3p;
    // Three VCs, two reserved credits each, VC first, two credits per value.
    typedef fw_credit_tx #(bit [7:0], 9, 3, 2, FW_CREDIT_VC_FIRST, 2)        ctx_3v;
    // Fewer credits than the reserves: VC 0 and 1 get one each, VC 2 none.
    typedef fw_credit_tx #(bit [7:0], 2, 3, 1, FW_CREDIT_POOL_FIRST, 1)      ctx_3s;
    // Four VCs (a power of two), no reserve.
    typedef fw_credit_tx #(bit [5:0], 5, 4, 0, FW_CREDIT_VC_FIRST, 1)        ctx_4;
endpackage
