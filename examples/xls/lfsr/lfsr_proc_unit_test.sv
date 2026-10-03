// SVUnit test for lfsr_proc_pkg: the #[test_proc] of lfsr_proc.x (see orig/),
// transcribed.
//
// Unlike every other test in these examples, this one depends on timing. The
// proc polls for a new seed on each activation, and the expected values
// assume it sees the seed on the activation right after the test sends it:
// the scheduling of the DSLX interpreter. A design that polls is not a Kahn
// process network, so no level is obliged to reproduce that interleaving;
// README.md reports which levels do.
`include "svunit_defines.svh"

module lfsr_proc_unit_test;
    import svunit_pkg::svunit_testcase;
    import lfsr_proc_pkg_api_pkg::*;
    import lfsr_proc_pkg::*;

    typedef user_module8::seed_and_mask_t seed_t;

    string name = "lfsr_proc_ut";
    svunit_testcase svunit_ut;
    user_module8_api m;

    function void build();
        svunit_ut = new(name);
        m = get_user_module8();
    endfunction

    task setup();
        svunit_ut.setup();
    endtask

    task teardown();
        svunit_ut.teardown();
    endtask

    `SVUNIT_TESTS_BEGIN

    // #[test_proc] proc test (renamed: SVUnit's macros declare a `test`)
    `SVTEST(lfsr_proc_test)
        bit [7:0] value;
        seed_t seed;

        m.output_s_get(value);
        `FAIL_UNLESS_EQUAL(value, 8'd1)

        seed = '{seed: 8'd1, tap_mask: 8'b10111000};
        m.seed_and_mask_r_put(seed);
        m.output_s_get(value); `FAIL_UNLESS_EQUAL(value, 8'd1)
        m.output_s_get(value); `FAIL_UNLESS_EQUAL(value, 8'd2)
        m.output_s_get(value); `FAIL_UNLESS_EQUAL(value, 8'd4)
        m.output_s_get(value); `FAIL_UNLESS_EQUAL(value, 8'd8)
        m.output_s_get(value); `FAIL_UNLESS_EQUAL(value, 8'd17)

        seed = '{seed: 8'd237, tap_mask: 8'b10111000};
        m.seed_and_mask_r_put(seed);
        m.output_s_get(value); `FAIL_UNLESS_EQUAL(value, 8'd237)
        m.output_s_get(value); `FAIL_UNLESS_EQUAL(value, 8'd219)
    `SVTEST_END

    `SVUNIT_TESTS_END
endmodule
