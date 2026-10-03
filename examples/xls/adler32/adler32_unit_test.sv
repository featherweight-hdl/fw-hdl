// SVUnit tests for adler32_pkg: the #[test] functions of adler32.x (see orig/),
// transcribed. They call the design through its generated API, so the same
// file runs at every level.
`include "svunit_defines.svh"

module adler32_unit_test;
    import svunit_pkg::svunit_testcase;
    import adler32_pkg_api_pkg::*;

    string name = "adler32_ut";
    svunit_testcase svunit_ut;
    adler32_pkg_api api;

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

    // #[test] fn adler32_one_char_test()
    `SVTEST(adler32_one_char_test)
        bit [31:0] got;
        api.main(8'h00, got); `FAIL_UNLESS_EQUAL(got, 32'h0010001)  // dec 0
        api.main(8'h30, got); `FAIL_UNLESS_EQUAL(got, 32'h0310031)  // '0'
        api.main(8'h61, got); `FAIL_UNLESS_EQUAL(got, 32'h0620062)  // 'a'
        api.main(8'h7e, got); `FAIL_UNLESS_EQUAL(got, 32'h07f007f)  // '~' (dec 126)
        api.main(8'h7f, got); `FAIL_UNLESS_EQUAL(got, 32'h0800080)  // 'DEL' (dec 127)
        api.main(8'hFf, got); `FAIL_UNLESS_EQUAL(got, 32'h1000100)  // dec 255
    `SVTEST_END

    `SVUNIT_TESTS_END
endmodule
