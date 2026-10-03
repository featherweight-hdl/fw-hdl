// SVUnit test for rle_pkg::rle_loopback -- NOT upstream. The encoder feeds the
// decoder (xls-examples.md E9's composition), so whatever goes in comes back
// out, symbol for symbol, with `last` on the final one. At `rtl` and `gates`
// the top is the one fw.hdl.spl.Integrate builds from the two XLS blocks'
// signatures, joined by a channel.
`include "svunit_defines.svh"

module rle_loop_unit_test;
    import svunit_pkg::svunit_testcase;
    import rle_loop_api_pkg::*;
    import rle_pkg::*;

    typedef RunLengthEncoder32::EncInData  in_t;
    typedef RunLengthDecoder32::DecOutData out_t;

    string name = "rle_loop_ut";
    svunit_testcase svunit_ut;
    rle_loopback_api loop;

    function void build();
        svunit_ut = new(name);
        loop = get_rle_loopback();
    endfunction

    task setup();
        svunit_ut.setup();
    endtask

    task teardown();
        svunit_ut.teardown();
    endtask

    task automatic roundtrip(bit [31:0] symbols [$]);
        in_t stimulus;
        out_t got, expected;
        foreach (symbols[i]) begin
            stimulus = '{symbol: symbols[i], last: i == symbols.size() - 1};
            loop.input_r_put(stimulus);
        end
        foreach (symbols[i]) begin
            expected = '{symbol: symbols[i], last: i == symbols.size() - 1};
            loop.output_s_get(got);
            `FAIL_UNLESS_EQUAL(got, expected)
        end
    endtask

    `SVUNIT_TESTS_BEGIN

    // The stimulus of upstream's RunLengthEncoderOverflowTest: runs longer
    // than the count width (2 bits) allows, so the encoder splits them.
    `SVTEST(identity_with_overflowing_runs)
        roundtrip('{32'hB, 32'hB, 32'h1, 32'hC, 32'hC, 32'hC, 32'hC,
                    32'hC, 32'hC, 32'h3, 32'h3, 32'h3, 32'h2, 32'h2});
    `SVTEST_END

    `SVTEST(identity_single_symbol)
        roundtrip('{32'h5});
    `SVTEST_END

    `SVTEST(identity_all_different)
        roundtrip('{32'h1, 32'h2, 32'h3, 32'h4, 32'h5});
    `SVTEST_END

    `SVUNIT_TESTS_END
endmodule
