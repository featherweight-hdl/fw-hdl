// Formal SVUnit fixtures (formal-svunit.md): tests on crc32_pkg whose formal
// result is known. test_formal_svunit.py checks each one's status, and for a
// counterexample the failing line and the values.
`include "svunit_defines.svh"

module crc32_formal_unit_test;
    import svunit_pkg::svunit_testcase;
    import crc32_pkg_api_pkg::*;

    string name = "crc32_formal_ut";
    svunit_testcase svunit_ut;
    crc32_pkg_api api;

    class msg;
        rand bit [7:0] m;
        constraint printable { m inside {[8'h20:8'h7E]}; }
    endclass

    class msg_alpha extends msg;
        constraint alpha { m inside {[8'h41:8'h5A]}; }
    endclass

    class msg_override extends msg;
        constraint printable { m inside {[8'h00:8'h1F]}; }     // replaces the base block
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

    // cex: m = 8'h31 ("1")
    `SVTEST(f_one_char_collides)
        bit [7:0] m; bit [31:0] crc;
        repeat (4) begin
            `FAIL_UNLESS(std::randomize(m))
            api.main(m, crc);
            `FAIL_IF(crc == 32'h83DCEFB7)
        end
    `SVTEST_END

    // proven: the constraint excludes "1"
    `SVTEST(p_one_char_excluded)
        bit [7:0] m; bit [31:0] crc;
        `FAIL_UNLESS(std::randomize(m) with { m != 8'h31; })
        api.main(m, crc);
        `FAIL_IF(crc == 32'h83DCEFB7)
    `SVTEST_END

    // vacuous: no m satisfies the constraints
    `SVTEST(v_contradiction)
        bit [7:0] m; bit [31:0] crc;
        `FAIL_UNLESS(std::randomize(m) with { m < 3; m > 5; })
        api.main(m, crc);
        `FAIL_IF(crc == 32'h0)
    `SVTEST_END

    // cex on the second check only: the first one is true for every input
    `SVTEST(f_second_check)
        bit [7:0] m; bit [31:0] crc;
        `FAIL_UNLESS(std::randomize(m) with { m inside {[8'h30:8'h39]}; })
        api.main(m, crc);
        `FAIL_IF(crc == 32'h0)
        if (m > 8'h37)
            `FAIL_UNLESS(crc[0] == 1'b0)
    `SVTEST_END

    // cex: a reachable $fatal is a failure
    `SVTEST(f_fatal)
        bit [7:0] m; bit [31:0] crc;
        void'(std::randomize(m));
        api.main(m, crc);
        if (crc == 32'h83DCEFB7)
            $fatal(1, "crc of 1");
    `SVTEST_END

    // proven: inherited constraint blocks apply
    `SVTEST(p_class_inherited)
        msg_alpha s = new; bit [31:0] crc;
        `FAIL_UNLESS(s.randomize())
        api.main(s.m, crc);
        `FAIL_IF(s.m < 8'h41 || s.m > 8'h5A)
    `SVTEST_END

    // cex: s.m = 8'h5A, the top of the narrowed range
    `SVTEST(f_class_edge)
        msg_alpha s = new; bit [31:0] crc;
        `FAIL_UNLESS(s.randomize() with { m >= 8'h5A; })
        `FAIL_IF(s.m == 8'h5A)
    `SVTEST_END

    // proven: an overriding block replaces the base block of the same name
    `SVTEST(p_class_override)
        msg_override s = new;
        `FAIL_UNLESS(s.randomize())
        `FAIL_IF(s.m > 8'h1F)
    `SVTEST_END

    // proven: dist constrains to the items of nonzero weight
    `SVTEST(p_dist)
        bit [7:0] m; bit [31:0] crc;
        `FAIL_UNLESS(std::randomize(m) with { m dist { 8'h31 := 0, [8'h40:8'h4F] :/ 3 }; })
        api.main(m, crc);
        `FAIL_IF(crc == 32'h83DCEFB7)
    `SVTEST_END

    // proven: implication and if/else constraints
    `SVTEST(p_implication)
        bit [7:0] a, b;
        `FAIL_UNLESS(std::randomize(a, b) with { a > 8'h10 -> b == 8'h1;
                                                  if (a == 8'h0) b == 8'h2; else b != 8'h3; })
        `FAIL_IF(a > 8'h10 && b != 8'h1)
        `FAIL_IF(b == 8'h3)
    `SVTEST_END

    // not formal: `prev` is carried from one iteration to the next
    `SVTEST(n_carried)
        bit [7:0] m, prev; bit [31:0] crc;
        repeat (4) begin
            `FAIL_UNLESS(std::randomize(m))
            `FAIL_IF(m == prev)
            prev = m;
        end
    `SVTEST_END

    // not formal: randomize in a for loop
    `SVTEST(n_for_loop)
        bit [7:0] m;
        for (int i = 0; i < 4; i++)
            `FAIL_UNLESS(std::randomize(m))
    `SVTEST_END

    `SVUNIT_TESTS_END
endmodule
