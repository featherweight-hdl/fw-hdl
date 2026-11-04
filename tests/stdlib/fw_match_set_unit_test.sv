// fw_match_set (src/std/match/fw_match_set.svh): hits, any and first on
// directed sets of 4 byte slots, and on one slot.
`include "svunit_defines.svh"

module fw_match_set_unit_test;
    import svunit_pkg::svunit_testcase;
    import fw_std_pkg::*;

    typedef fw_match_set #(4, bit [7:0]) ms4;
    typedef fw_match_set #(1, bit [7:0]) ms1;

    string name = "fw_match_set_ut";
    svunit_testcase svunit_ut;

    bit [3:0][7:0] keys;

    function void build();
        svunit_ut = new(name);
    endfunction

    task setup();
        svunit_ut.setup();
        keys = {8'h44, 8'h33, 8'h22, 8'h11};    // slot i holds 8'h11 * (i + 1)
    endtask

    task teardown();
        svunit_ut.teardown();
    endtask

    `SVUNIT_TESTS_BEGIN

    // No slot valid: nothing hits, whatever the slots hold.
    `SVTEST(empty_set)
        `FAIL_UNLESS_EQUAL(ms4::hits(keys, 4'b0000, 8'h22), 4'b0000)
        `FAIL_UNLESS_EQUAL(ms4::any(keys, 4'b0000, 8'h22), 1'b0)
        `FAIL_UNLESS_EQUAL(ms4::first(keys, 4'b0000, 8'h22), 2'd0)
    `SVTEST_END

    // A hit in each slot, alone.
    `SVTEST(hit_each_slot)
        for (int i = 0; i < 4; i++) begin
            bit [7:0] q = 8'h11 * (i + 1);
            `FAIL_UNLESS_EQUAL(ms4::hits(keys, 4'b1111, q), 4'b0001 << i)
            `FAIL_UNLESS_EQUAL(ms4::any(keys, 4'b1111, q), 1'b1)
            `FAIL_UNLESS_EQUAL(ms4::first(keys, 4'b1111, q), 2'(i))
        end
        `FAIL_UNLESS_EQUAL(ms4::any(keys, 4'b1111, 8'h55), 1'b0)
    `SVTEST_END

    // A value held by an invalid slot only does not hit.
    `SVTEST(invalid_slot_never_hits)
        `FAIL_UNLESS_EQUAL(ms4::hits(keys, 4'b1011, 8'h33), 4'b0000)
        `FAIL_UNLESS_EQUAL(ms4::any(keys, 4'b1011, 8'h33), 1'b0)
    `SVTEST_END

    // A value held by several slots hits each; first is the lowest valid.
    `SVTEST(repeated_value)
        keys = {8'h22, 8'h33, 8'h22, 8'h22};
        `FAIL_UNLESS_EQUAL(ms4::hits(keys, 4'b1111, 8'h22), 4'b1011)
        `FAIL_UNLESS_EQUAL(ms4::first(keys, 4'b1111, 8'h22), 2'd0)
        `FAIL_UNLESS_EQUAL(ms4::first(keys, 4'b1110, 8'h22), 2'd1)
        `FAIL_UNLESS_EQUAL(ms4::first(keys, 4'b1100, 8'h22), 2'd3)
    `SVTEST_END

    // One slot.
    `SVTEST(one_slot)
        `FAIL_UNLESS_EQUAL(ms1::any(8'h5a, 1'b1, 8'h5a), 1'b1)
        `FAIL_UNLESS_EQUAL(ms1::any(8'h5a, 1'b0, 8'h5a), 1'b0)
        `FAIL_UNLESS_EQUAL(ms1::any(8'h5a, 1'b1, 8'h5b), 1'b0)
        `FAIL_UNLESS_EQUAL(ms1::first(8'h5a, 1'b1, 8'h5a), 1'b0)
    `SVTEST_END

    `SVUNIT_TESTS_END
endmodule
