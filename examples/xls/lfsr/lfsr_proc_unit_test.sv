// SVUnit test for lfsr_proc_pkg: the #[test_proc] of lfsr_proc.x (see orig/),
// transcribed, with one deviation (README.md).
//
// The proc polls for a new seed on each activation. Upstream's test expects
// it to see the seed on the activation right after the test sends it: the
// scheduling of the DSLX interpreter. In hardware the proc runs every clock
// and the send takes at least one, so values from the old seed come first. A
// polling design is not a Kahn process network, and no level has to share
// the interpreter's interleaving. So after each send, the test accepts outputs
// that continue the old sequence (checked value by value, at most
// MAX_LAG of them) until the new seed appears. From there it checks
// upstream's values exactly.
`include "svunit_defines.svh"

module lfsr_proc_unit_test;
    import svunit_pkg::svunit_testcase;
    import lfsr_proc_pkg_api_pkg::*;
    import lfsr_proc_pkg::*;
    import lfsr_pkg::*;

    typedef user_module8::seed_and_mask_t seed_t;

    // Outputs of the old sequence allowed before a new seed takes effect.
    // Neither seed the test sends occurs in the first MAX_LAG values of the
    // sequence it replaces, so the first match is the new seed's.
    localparam int MAX_LAG = 8;

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

    // Receives until the output is `seed`. Each value before it must be the
    // next value of the old sequence (prev under the old tap mask).
    task automatic recv_until_seed(bit [7:0] seed, bit [7:0] prev,
                                   bit [7:0] old_mask, output bit [7:0] value);
        int lag = 0;
        m.output_s_get(value);
        while (value != seed && lag < MAX_LAG) begin
            `FAIL_UNLESS_EQUAL(value, lfsr_c#(8)::lfsr(prev, old_mask))
            prev = value;
            lag++;
            m.output_s_get(value);
        end
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
        recv_until_seed(seed.seed, value, 8'd1, value);  // old: init (1, 1)
        `FAIL_UNLESS_EQUAL(value, 8'd1)
        m.output_s_get(value); `FAIL_UNLESS_EQUAL(value, 8'd2)
        m.output_s_get(value); `FAIL_UNLESS_EQUAL(value, 8'd4)
        m.output_s_get(value); `FAIL_UNLESS_EQUAL(value, 8'd8)
        m.output_s_get(value); `FAIL_UNLESS_EQUAL(value, 8'd17)

        seed = '{seed: 8'd237, tap_mask: 8'b10111000};
        m.seed_and_mask_r_put(seed);
        recv_until_seed(seed.seed, value, 8'b10111000, value);
        `FAIL_UNLESS_EQUAL(value, 8'd237)
        m.output_s_get(value); `FAIL_UNLESS_EQUAL(value, 8'd219)
    `SVTEST_END

    `SVUNIT_TESTS_END
endmodule
