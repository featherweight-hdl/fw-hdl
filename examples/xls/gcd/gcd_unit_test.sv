// SVUnit tests for gcd_pkg: the #[test] functions of gcd.x (see orig/),
// transcribed. They call the design through its generated API, so the same
// file runs at every level. gcd.x's #[quickcheck] (Euclid == binary) is not a
// test here: equiv proves it for every 8-bit input (see flow.yaml).
`include "svunit_defines.svh"

module gcd_unit_test;
    import svunit_pkg::svunit_testcase;
    import gcd_pkg_api_pkg::*;

    string name = "gcd_ut";
    svunit_testcase svunit_ut;
    gcd_pkg_api api;

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

    // #[test] fn gcd_euclidean_test()
    `SVTEST(gcd_euclidean_test)
        bit [7:0] got;
        api.gcd_euclidean8(8'd48, 8'd18, got); `FAIL_UNLESS_EQUAL(got, 8'd6)
        api.gcd_euclidean8(8'd18, 8'd48, got); `FAIL_UNLESS_EQUAL(got, 8'd6)
    `SVTEST_END

    // #[test] fn gcd_binary_test()
    `SVTEST(gcd_binary_test)
        bit [7:0] got;
        api.gcd_binary8(8'd48, 8'd18, got); `FAIL_UNLESS_EQUAL(got, 8'd6)
        api.gcd_binary8(8'd18, 8'd48, got); `FAIL_UNLESS_EQUAL(got, 8'd6)
    `SVTEST_END

    `SVUNIT_TESTS_END
endmodule
