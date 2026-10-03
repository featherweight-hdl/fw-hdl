// SVUnit tests for idct_chen_pkg: the #[test] functions of idct_chen.x (see
// orig/), transcribed (the vectors are copied from it mechanically). They call
// the design through its generated API, so the same file runs at every level.
`include "svunit_defines.svh"

module idct_chen_unit_test;
    import svunit_pkg::svunit_testcase;
    import idct_chen_pkg_api_pkg::*;
    import idct_chen_pkg::row_t;
    import idct_chen_pkg::block_t;

    string name = "idct_chen_ut";
    svunit_testcase svunit_ut;
    idct_chen_pkg_api api;

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

    // #[test] fn idct_row_test()
    // (SVUnit's FAIL_UNLESS_EQUAL uses !==, which unpacked arrays don't have.)
    `SVTEST(idct_row_test)
        row_t input_v, want, got;
        input_v = '{
            23, -1, -2, 0, 0, 0, 0, 0
        };
        want = '{
            152, 166, 186, 203, 207, 199, 185, 174
        };
        api.idct_row(input_v, got);
        `FAIL_UNLESS(got == want)
    `SVTEST_END

    // #[test] fn idct0_test()
    // (SVUnit's FAIL_UNLESS_EQUAL uses !==, which unpacked arrays don't have.)
    `SVTEST(idct0_test)
        block_t input_v, want, got;
        input_v = '{
            23, -1, -2, 0, 0, 0, 0, 0,
            0, 0, 0, 0, 0, 0, 0, 0,
            0, 0, 0, 0, 0, 0, 0, 0,
            0, 0, 0, 0, 0, 0, 0, 0,
            0, 0, 0, 0, 0, 0, 0, 0,
            0, 0, 0, 0, 0, 0, 0, 0,
            0, 0, 0, 0, 0, 0, 0, 0,
            0, 0, 0, 0, 0, 0, 0, 0
        };
        want = '{
            2, 3, 3, 3, 3, 3, 3, 3,
            2, 3, 3, 3, 3, 3, 3, 3,
            2, 3, 3, 3, 3, 3, 3, 3,
            2, 3, 3, 3, 3, 3, 3, 3,
            2, 3, 3, 3, 3, 3, 3, 3,
            2, 3, 3, 3, 3, 3, 3, 3,
            2, 3, 3, 3, 3, 3, 3, 3,
            2, 3, 3, 3, 3, 3, 3, 3
        };
        api.idct(input_v, got);
        `FAIL_UNLESS(got == want)
    `SVTEST_END

    // #[test] fn idct1_test()
    // (SVUnit's FAIL_UNLESS_EQUAL uses !==, which unpacked arrays don't have.)
    `SVTEST(idct1_test)
        block_t input_v, want, got;
        input_v = '{
            13, -7, 0, 0, 0, 0, 0, 0,
            0, 2, 0, 0, 0, 0, 0, 0,
            0, 0, 0, 0, 0, 0, 0, 0,
            0, 0, 0, 0, 0, 0, 0, 0,
            0, 0, 0, 0, 0, 0, 0, 0,
            0, 0, 0, 0, 0, 0, 0, 0,
            0, 0, 0, 0, 0, 0, 0, 0,
            0, 0, 0, 0, 0, 0, 0, 0
        };
        want = '{
            1, 1, 1, 1, 2, 2, 2, 2,
            1, 1, 1, 1, 2, 2, 2, 2,
            1, 1, 1, 1, 2, 2, 2, 3,
            1, 1, 1, 1, 2, 2, 3, 3,
            0, 1, 1, 1, 2, 2, 3, 3,
            0, 0, 1, 1, 2, 2, 3, 3,
            0, 0, 1, 1, 2, 3, 3, 3,
            0, 0, 1, 1, 2, 3, 3, 3
        };
        api.idct(input_v, got);
        `FAIL_UNLESS(got == want)
    `SVTEST_END

    // #[test] fn idct2_test()
    // (SVUnit's FAIL_UNLESS_EQUAL uses !==, which unpacked arrays don't have.)
    `SVTEST(idct2_test)
        block_t input_v, want, got;
        input_v = '{
            -166, -7, -4, -4, 0, 0, 0, 0,
            -2, 0, 0, 0, 0, 0, 0, 0,
            -2, 0, 0, 0, 0, 0, 0, 0,
            0, 0, 0, 0, 0, 0, 0, 0,
            0, 0, 0, 0, 0, 0, 0, 0,
            0, 0, 0, 0, 0, 0, 0, 0,
            0, 0, 0, 0, 0, 0, 0, 0,
            0, 0, 0, 0, 0, 0, 0, 0
        };
        want = '{
            -24, -23, -21, -21, -21, -21, -21, -20,
            -24, -22, -21, -20, -21, -21, -21, -20,
            -23, -22, -21, -20, -20, -21, -20, -20,
            -23, -22, -20, -20, -20, -20, -20, -19,
            -23, -22, -20, -20, -20, -20, -20, -19,
            -23, -22, -20, -20, -20, -20, -20, -19,
            -23, -22, -20, -20, -20, -20, -20, -19,
            -23, -22, -20, -20, -20, -20, -20, -20
        };
        api.idct(input_v, got);
        `FAIL_UNLESS(got == want)
    `SVTEST_END

    // #[test] fn idct3_test()
    // (SVUnit's FAIL_UNLESS_EQUAL uses !==, which unpacked arrays don't have.)
    `SVTEST(idct3_test)
        block_t input_v, want, got;
        input_v = '{
            -240, 8, -11, 47, 26, -6, 0, 5,
            28, -6, 85, 44, -4, -25, 5, 16,
            21, 8, 32, -16, -24, 0, 30, 12,
            -2, 18, 0, -2, 0, 7, 0, -15,
            7, 4, 15, -24, 0, 9, 8, -6,
            4, 9, 0, -5, -6, 0, 0, 0,
            -4, 0, -6, 0, 0, 10, -10, -8,
            6, 0, 0, 0, 0, 0, 0, -8
        };
        want = '{
            21, -10, -26, -61, -43, -17, -22, -8,
            5, -28, -47, -73, -11, -14, -24, -17,
            -14, -31, -61, -45, -5, -18, -22, -34,
            -23, -36, -49, -32, -12, -33, -33, -35,
            -30, -39, -53, -8, -19, -31, -43, -42,
            -41, -43, -50, -4, -15, -33, -44, -66,
            -40, -38, -21, -14, -17, -26, -46, -52,
            -44, -47, -9, -12, -30, -33, -38, -37
        };
        api.idct(input_v, got);
        `FAIL_UNLESS(got == want)
    `SVTEST_END

    `SVUNIT_TESTS_END
endmodule
