// SVUnit tests for crc32_pkg: the #[test] functions of crc32.x (see orig/),
// transcribed. They call the design through its API, crc32_pkg_api, which is
// generated from crc32_pkg.sv. Nothing here says what answers the calls: this
// one file runs against the SV model, the XLS RTL and the gate-level netlist
// (README.md).
`include "svunit_defines.svh"

module crc32_unit_test;
    import svunit_pkg::svunit_testcase;
    import crc32_pkg_api_pkg::*;

    string name = "crc32_ut";
    svunit_testcase svunit_ut;
    crc32_pkg_api api;

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

    // #[test]
    // fn crc32_one_char() { assert_eq(u32:0x83DCEFB7, main('1')) }
    `SVTEST(crc32_one_char)
        bit [31:0] crc;
        api.main("1", crc);
        `FAIL_UNLESS_EQUAL(crc, 32'h83DCEFB7)
    `SVTEST_END

    `SVUNIT_TESTS_END
endmodule
