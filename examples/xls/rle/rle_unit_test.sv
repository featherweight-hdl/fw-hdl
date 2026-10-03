// SVUnit tests for rle_pkg: the #[test_proc] procs of rle_enc.x and rle_dec.x
// (see orig/), transcribed. Each test proc spawns the encoder or decoder at
// the widths it names, sends its stimuli on the input channel, and receives
// and checks the outputs; here each test puts on the component's input port
// and gets from its output port, through the generated API. The test's end
// replaces the `terminator` channel. The same file runs at every level.
`include "svunit_defines.svh"

module rle_unit_test;
    import svunit_pkg::svunit_testcase;
    import rle_pkg_api_pkg::*;
    import rle_pkg::*;

    // The specializations the test procs spawn. (The count-width-2 one is
    // named first: Verilator 5.049 swaps two specializations' nested types
    // depending on the order they are first named; fixed in 5.053.)
    typedef RunLengthEncoder32::EncInData     enc2_in_t;     // count width 2
    typedef RunLengthEncoder32::EncOutData    enc2_out_t;
    typedef RunLengthEncoder32_32::EncInData  enc_in_t;      // count width 32
    typedef RunLengthEncoder32_32::EncOutData enc_out_t;
    typedef RunLengthDecoder32_32::DecInData  dec_in_t;
    typedef RunLengthDecoder32_32::DecOutData dec_out_t;

    string name = "rle_ut";
    svunit_testcase svunit_ut;
    RunLengthEncoder32_32_api enc;      // RunLengthEncoder<32, 32>
    RunLengthEncoder32_api    enc2;     // RunLengthEncoder<32, 2>
    RunLengthDecoder32_32_api dec;      // RunLengthDecoder<32, 32>

    function void build();
        svunit_ut = new(name);
        enc = get_RunLengthEncoder32_32();
        enc2 = get_RunLengthEncoder32();
        dec = get_RunLengthDecoder32_32();
    endfunction

    task setup();
        svunit_ut.setup();
    endtask

    task teardown();
        svunit_ut.teardown();
    endtask

    `SVUNIT_TESTS_BEGIN

    // #[test_proc] proc RunLengthEncoderCountSymbolTest
    `SVTEST(RunLengthEncoderCountSymbolTest)
        bit [31:0] stimuli [4] = '{32'hA, 32'hA, 32'hA, 32'hB};
        bit [31:0] out_symbol [2] = '{32'hA, 32'hB};
        bit [31:0] out_count [2] = '{32'h3, 32'h1};
        enc_in_t stimulus;
        enc_out_t enc_output, expected;
        foreach (stimuli[counter]) begin
            stimulus = '{symbol: stimuli[counter], last: counter == 3};
            enc.input_r_put(stimulus);
        end
        foreach (out_symbol[counter]) begin
            expected = '{symbol: out_symbol[counter], count: out_count[counter],
                         last: counter == 1};
            enc.output_s_get(enc_output);
            `FAIL_UNLESS_EQUAL(enc_output, expected)
        end
    `SVTEST_END

    // #[test_proc] proc RunLengthEncoderOverflowTest (count width 2)
    `SVTEST(RunLengthEncoderOverflowTest)
        bit [31:0] stimuli [14] = '{32'hB, 32'hB, 32'h1, 32'hC, 32'hC, 32'hC, 32'hC,
                                    32'hC, 32'hC, 32'h3, 32'h3, 32'h3, 32'h2, 32'h2};
        bit [31:0] out_symbol [6] = '{32'hB, 32'h1, 32'hC, 32'hC, 32'h3, 32'h2};
        bit [1:0] out_count [6] = '{2'h2, 2'h1, 2'h3, 2'h3, 2'h3, 2'h2};
        enc2_in_t stimulus;
        enc2_out_t enc_output, expected;
        foreach (stimuli[counter]) begin
            stimulus = '{symbol: stimuli[counter], last: counter == 13};
            enc2.input_r_put(stimulus);
        end
        foreach (out_symbol[counter]) begin
            expected = '{symbol: out_symbol[counter], count: out_count[counter],
                         last: counter == 5};
            enc2.output_s_get(enc_output);
            `FAIL_UNLESS_EQUAL(enc_output, expected)
        end
    `SVTEST_END

    // #[test_proc] proc RunLengthEncoderLastAfterLastTest
    `SVTEST(RunLengthEncoderLastAfterLastTest)
        enc_in_t stimulus;
        enc_out_t enc_output, expected;
        stimulus = '{symbol: 32'h1, last: 1'b1};
        enc.input_r_put(stimulus);
        enc.input_r_put(stimulus);
        expected = '{symbol: 32'h1, count: 32'h1, last: 1'b1};
        enc.output_s_get(enc_output);
        `FAIL_UNLESS_EQUAL(enc_output, expected)
        enc.output_s_get(enc_output);
        `FAIL_UNLESS_EQUAL(enc_output, expected)
    `SVTEST_END

    // #[test_proc] proc RunLengthEncoderOverflowWithLastTest (count width 2)
    `SVTEST(RunLengthEncoderOverflowWithLastTest)
        bit [31:0] out_count [2] = '{32'h3, 32'h1};
        enc2_in_t stimulus;
        enc2_out_t enc_output, expected;
        for (int counter = 0; counter < 4; counter++) begin
            stimulus = '{symbol: 32'hC, last: counter == 3};
            enc2.input_r_put(stimulus);
        end
        foreach (out_count[counter]) begin
            expected = '{symbol: 32'hC, count: 2'(out_count[counter]), last: counter == 1};
            enc2.output_s_get(enc_output);
            `FAIL_UNLESS_EQUAL(enc_output, expected)
        end
    `SVTEST_END

    // #[test_proc] proc RunLengthDecoderTransactionTest
    `SVTEST(RunLengthDecoderTransactionTest)
        bit [31:0] in_symbol [6] = '{32'hB, 32'h1, 32'hC, 32'hC, 32'h3, 32'h2};
        bit [31:0] in_count [6] = '{32'h2, 32'h1, 32'h3, 32'h3, 32'h3, 32'h2};
        bit [31:0] outputs [14] = '{32'hB, 32'hB, 32'h1, 32'hC, 32'hC, 32'hC, 32'hC,
                                    32'hC, 32'hC, 32'h3, 32'h3, 32'h3, 32'h2, 32'h2};
        dec_in_t data_in;
        dec_out_t dec_output, data_out;
        foreach (in_symbol[counter]) begin
            data_in = '{symbol: in_symbol[counter], count: in_count[counter],
                        last: counter == 5};
            dec.input_r_put(data_in);
        end
        foreach (outputs[counter]) begin
            data_out = '{symbol: outputs[counter], last: counter == 13};
            dec.output_s_get(dec_output);
            `FAIL_UNLESS_EQUAL(dec_output, data_out)
        end
    `SVTEST_END

    // #[test_proc] proc RunLengthDecoderLastAfterLastTest
    `SVTEST(RunLengthDecoderLastAfterLastTest)
        dec_in_t stimulus;
        dec_out_t dec_output, expected;
        stimulus = '{symbol: 32'h1, count: 32'h1, last: 1'b1};
        dec.input_r_put(stimulus);
        stimulus = '{symbol: 32'h2, count: 32'h1, last: 1'b1};
        dec.input_r_put(stimulus);
        expected = '{symbol: 32'h1, last: 1'b1};
        dec.output_s_get(dec_output);
        `FAIL_UNLESS_EQUAL(dec_output, expected)
        expected = '{symbol: 32'h2, last: 1'b1};
        dec.output_s_get(dec_output);
        `FAIL_UNLESS_EQUAL(dec_output, expected)
    `SVTEST_END

    `SVUNIT_TESTS_END
endmodule
