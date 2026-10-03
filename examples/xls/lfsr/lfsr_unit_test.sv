// SVUnit tests for lfsr_pkg: the #[test] functions of lfsr.x (see orig/),
// transcribed. They call the design through its generated API, so the same
// file runs at every level.
`include "svunit_defines.svh"

module lfsr_unit_test;
    import svunit_pkg::svunit_testcase;
    import lfsr_pkg_api_pkg::*;

    string name = "lfsr_ut";
    svunit_testcase svunit_ut;
    lfsr_pkg_api api;

    function void build();
        svunit_ut = new(name);
        api = get();
    endfunction

    task setup();
        svunit_ut.setup();
    endtask

    task teardown();
        svunit_ut.teardown();
    endtask

    `SVUNIT_TESTS_BEGIN

    // #[test] fn lfsr7_test()
    `SVTEST(lfsr7_test)
        bit [6:0] got;
        bit [6:0] value;
        // Trivial test.
        api.lfsr7(7'd0, got); `FAIL_UNLESS_EQUAL(got, 7'd0)

        // Test a few values.
        api.lfsr7(7'd1, got);   `FAIL_UNLESS_EQUAL(got, 7'd2)
        api.lfsr7(7'd104, got); `FAIL_UNLESS_EQUAL(got, 7'd80)
        api.lfsr7(7'd31, got);  `FAIL_UNLESS_EQUAL(got, 7'd62)
        api.lfsr7(7'd67, got);  `FAIL_UNLESS_EQUAL(got, 7'd7)
        api.lfsr7(7'd9, got);   `FAIL_UNLESS_EQUAL(got, 7'd18)
        api.lfsr7(7'd107, got); `FAIL_UNLESS_EQUAL(got, 7'd86)
        api.lfsr7(7'd108, got); `FAIL_UNLESS_EQUAL(got, 7'd88)
        api.lfsr7(7'd88, got);  `FAIL_UNLESS_EQUAL(got, 7'd49)

        // test that the cycle works
        value = 7'd1;
        for (int i = 0; i < 127; i++)
            api.lfsr7(value, value);
        `FAIL_UNLESS_EQUAL(value, 7'd1)
    `SVTEST_END

    // #[test] fn lfsr8_test()
    `SVTEST(lfsr8_test)
        bit [7:0] got;
        bit [7:0] value;
        // Trivial test.
        api.lfsr8(8'd0, got); `FAIL_UNLESS_EQUAL(got, 8'd0)

        // Test a few values.
        api.lfsr8(8'd1, got);   `FAIL_UNLESS_EQUAL(got, 8'd2)
        api.lfsr8(8'd37, got);  `FAIL_UNLESS_EQUAL(got, 8'd75)
        api.lfsr8(8'd6, got);   `FAIL_UNLESS_EQUAL(got, 8'd12)
        api.lfsr8(8'd155, got); `FAIL_UNLESS_EQUAL(got, 8'd55)
        api.lfsr8(8'd10, got);  `FAIL_UNLESS_EQUAL(got, 8'd21)
        api.lfsr8(8'd214, got); `FAIL_UNLESS_EQUAL(got, 8'd172)
        api.lfsr8(8'd176, got); `FAIL_UNLESS_EQUAL(got, 8'd97)
        api.lfsr8(8'd237, got); `FAIL_UNLESS_EQUAL(got, 8'd219)

        // Test that the cycle works.
        value = 8'd1;
        for (int i = 0; i < 255; i++)
            api.lfsr8(value, value);
        `FAIL_UNLESS_EQUAL(value, 8'd1)
    `SVTEST_END

    `SVUNIT_TESTS_END
endmodule
