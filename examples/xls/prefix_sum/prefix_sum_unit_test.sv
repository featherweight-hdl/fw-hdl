// SVUnit tests for prefix_sum_pkg: the #[test] function of prefix_sum.x (see
// orig/), transcribed. They call the design through its generated API, so the
// same file runs at every level.
`include "svunit_defines.svh"

module prefix_sum_unit_test;
    import svunit_pkg::svunit_testcase;
    import prefix_sum_pkg_api_pkg::*;
    import prefix_sum_pkg::values_t;

    string name = "prefix_sum_ut";
    svunit_testcase svunit_ut;
    prefix_sum_pkg_api api;

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

    // #[test] fn prefix_sum_test()
    // (SVUnit's FAIL_UNLESS_EQUAL uses !==, which unpacked arrays don't have;
    // the arrays are compared with ==.)
    `SVTEST(prefix_sum_test)
        values_t values, result, want;

        values = '{default: 16'd1};
        want = '{1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16};
        api.prefix_sum(values, result);
        `FAIL_UNLESS(result == want)

        values = '{1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16};
        want = '{1, 3, 6, 10, 15, 21, 28, 36, 45, 55, 66, 78, 91, 105, 120, 136};
        api.prefix_sum(values, result);
        `FAIL_UNLESS(result == want)
    `SVTEST_END

    `SVUNIT_TESTS_END
endmodule
