// SVUnit tests for crc32_pkg: the #[test] functions of crc32.x (see orig/),
// transcribed. They call the design through its API, crc32_pkg_api, which is
// generated from crc32_pkg.sv. Nothing here says what answers the calls: this
// one file runs against the SV model, the XLS RTL and the gate-level netlist
// (README.md).
//
// The tests with free inputs also run formally (formal-svunit.md): their
// std::randomize / randomize() inputs become symbolic, the constraints
// assumptions, and every FAIL_* a proof obligation, so a proof covers every
// input the constraints allow. Dynamically each draws `FW_SAMPLES samples.
`include "svunit_defines.svh"

`ifndef FW_SAMPLES
`define FW_SAMPLES 64
`endif

module crc32_unit_test;
    import svunit_pkg::svunit_testcase;
    import crc32_pkg_api_pkg::*;

    string name = "crc32_ut";
    svunit_testcase svunit_ut;
    crc32_pkg_api api;

    // A message byte: printable ASCII.
    class crc_msg;
        rand bit [7:0] m;
        constraint printable { m inside {[8'h20:8'h7E]}; }
    endclass

    // Narrowed by a subclass; the base class's constraint still applies.
    class crc_msg_alpha extends crc_msg;
        constraint alpha { m inside {[8'h41:8'h5A]}; }
    endclass

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

    // A CRC is affine over GF(2): crc(a) ^ crc(b) ^ crc(c) == crc(a ^ b ^ c),
    // for all a, b, c. What XLS proves with #[quickcheck] and
    // prove_quickcheck_main, as an SVUnit test.
    `SVTEST(crc32_affine)
        bit [7:0]  a, b, c;
        bit [31:0] ca, cb, cc, cabc;
        repeat (`FW_SAMPLES) begin
            `FAIL_UNLESS(std::randomize(a, b, c))
            api.main(a, ca);
            api.main(b, cb);
            api.main(c, cc);
            api.main(a ^ b ^ c, cabc);
            `FAIL_UNLESS_EQUAL(ca ^ cb ^ cc, cabc)
        end
    `SVTEST_END

    // No printable character has a CRC of 0. The constraint is an assumption.
    `SVTEST(crc32_printable_nonzero)
        bit [7:0]  m;
        bit [31:0] crc;
        repeat (`FW_SAMPLES) begin
            `FAIL_UNLESS(std::randomize(m) with { m inside {[8'h20:8'h7E]}; })
            api.main(m, crc);
            `FAIL_IF(crc == 32'h0)
        end
    `SVTEST_END

    // The same through a class: its constraint blocks, the inherited ones
    // too, and the inline `with` are all assumptions.
    `SVTEST(crc32_alpha_distinct)
        crc_msg_alpha s = new;
        bit [31:0]    crc;
        repeat (`FW_SAMPLES) begin
            `FAIL_UNLESS(s.randomize() with { m != 8'h51; })
            api.main(s.m, crc);
            `FAIL_IF(crc == 32'h0)
            `FAIL_IF(crc == 32'h83DCEFB7)     // the CRC of "1", not a letter
        end
    `SVTEST_END

    `SVUNIT_TESTS_END
endmodule
