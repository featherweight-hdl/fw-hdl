// SVUnit tests for fir_dot_pkg: the fixed-point #[test] functions of
// fir_filter.x and dot_product.x (see orig/), transcribed. The float32 tests
// are not ported (no SV apfloat yet). They call the design through its
// generated API, so the same file runs at every level.
`include "svunit_defines.svh"

module fir_dot_unit_test;
    import svunit_pkg::svunit_testcase;
    import fir_dot_pkg_api_pkg::*;
    import fir_dot_pkg::*;

    string name = "fir_dot_ut";
    svunit_testcase svunit_ut;
    fir_dot_pkg_api api;

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

    // #[test] fn fir_filter_fixed_test()
    `SVTEST(fir_filter_fixed_test)
        s32x6_t samples;
        s32x4_t coefficients;
        s32x3_t result, want;
        samples = '{1, 2, 3, 4, 5, 6};
        coefficients = '{10, 11, -12, -13};
        want = '{36, 32, 28};
        api.fir_filter_fixed_4_6(samples, coefficients, result);
        `FAIL_UNLESS(result == want)
    `SVTEST_END

    // #[test] fn dot_product_fixed_test()
    `SVTEST(dot_product_fixed_test)
        s32x4_t a32, b32;
        s8x2_t a8, b8;
        bit signed [31:0] r32;
        bit signed [7:0] r8;

        a32 = '{1, 2, 3, 4};
        b32 = '{5, 6, 7, 8};
        api.dot_product_fixed_32_4(a32, b32, r32);
        `FAIL_UNLESS_EQUAL(r32, 32'sd70)

        a8 = '{1, 2};
        b8 = '{5, 6};
        api.dot_product_fixed_8_2(a8, b8, r8);
        `FAIL_UNLESS_EQUAL(r8, 8'sd17)
    `SVTEST_END

    `SVUNIT_TESTS_END
endmodule
