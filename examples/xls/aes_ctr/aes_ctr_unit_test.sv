// SVUnit test for aes_ctr_pkg: the #[test_proc] aes_ctr_test_128 of aes_ctr.x
// (see ../aes/orig/), transcribed. It sends commands and plaintext blocks to
// the proc and checks the blocks it sends back, through the generated
// component API, so the same file runs at every level.
`include "svunit_defines.svh"

module aes_ctr_unit_test;
    import svunit_pkg::svunit_testcase;
    import aes_ctr_pkg_api_pkg::*;
    import aes_pkg::*;
    import aes_ctr_pkg::*;

    string name = "aes_ctr_ut";
    svunit_testcase svunit_ut;
    aes_ctr_api ctr;

    function void build();
        svunit_ut = new(name);
        ctr = get_aes_ctr();
    endfunction

    task setup();
        svunit_ut.setup();
    endtask

    task teardown();
        svunit_ut.teardown();
    endtask

    // A Block literal as the packed PBlock a channel carries.
    function automatic PBlock blk(bit [7:0] b00, bit [7:0] b01, bit [7:0] b02, bit [7:0] b03,
                                  bit [7:0] b10, bit [7:0] b11, bit [7:0] b12, bit [7:0] b13,
                                  bit [7:0] b20, bit [7:0] b21, bit [7:0] b22, bit [7:0] b23,
                                  bit [7:0] b30, bit [7:0] b31, bit [7:0] b32, bit [7:0] b33);
        Block b;
        b[0] = '{b00, b01, b02, b03};
        b[1] = '{b10, b11, b12, b13};
        b[2] = '{b20, b21, b22, b23};
        b[3] = '{b30, b31, b32, b33};
        return pack_block(b);
    endfunction

    // Command { msg_bytes, key, key_width: KEY_128, iv, initial_ctr: 0, ctr_stride: 1 }
    function automatic Command command(bit [31:0] msg_bytes);
        Command cmd = '0;
        cmd.msg_bytes = msg_bytes;
        // Key:[u8:0x00, ..., u8:0x0f, ...]: a DSLX `...` repeats the last element.
        for (int k = 0; k < 32; k++)
            cmd.key[31 - k] = (k < 16) ? 8'(k) : 8'h0f;
        cmd.key_width = KEY_128;
        // u8[12]:[0x10, ..., 0x1b] as InitVector
        cmd.iv = 96'h10111213_14151617_18191a1b;
        cmd.initial_ctr = 32'd0;
        cmd.ctr_stride = 32'd1;
        return cmd;
    endfunction

    `SVUNIT_TESTS_BEGIN

    // #[test_proc] proc aes_ctr_test_128
    `SVTEST(aes_ctr_test_128)
        PBlock ctxt;

        ctr.command_in_put(command(32'd32));
        ctr.ptxt_in_put(blk(8'h20, 8'h21, 8'h22, 8'h23, 8'h24, 8'h25, 8'h26, 8'h27,
                            8'h28, 8'h29, 8'h2a, 8'h2b, 8'h2c, 8'h2d, 8'h2e, 8'h2f));
        ctr.ctxt_out_get(ctxt);
        `FAIL_UNLESS_EQUAL(ctxt, blk(8'h27, 8'h6a, 8'hec, 8'h41, 8'hfd, 8'ha9, 8'h9f, 8'h26,
                                     8'h34, 8'hc5, 8'h43, 8'h73, 8'hc7, 8'h99, 8'hd2, 8'h19))

        ctr.ptxt_in_put(blk(8'h30, 8'h31, 8'h32, 8'h33, 8'h34, 8'h35, 8'h36, 8'h37,
                            8'h38, 8'h39, 8'h3a, 8'h3b, 8'h3c, 8'h3d, 8'h3e, 8'h3f));
        ctr.ctxt_out_get(ctxt);
        `FAIL_UNLESS_EQUAL(ctxt, blk(8'h3e, 8'he6, 8'h17, 8'ha9, 8'he9, 8'h25, 8'h27, 8'hd6,
                                     8'h61, 8'he9, 8'h34, 8'h5a, 8'h8d, 8'haf, 8'h6a, 8'h2f))

        // Command #2.
        ctr.command_in_put(command(32'd16));
        ctr.ptxt_in_put(blk(8'h20, 8'h21, 8'h22, 8'h23, 8'h24, 8'h25, 8'h26, 8'h27,
                            8'h28, 8'h29, 8'h2a, 8'h2b, 8'h2c, 8'h2d, 8'h2e, 8'h2f));
        ctr.ctxt_out_get(ctxt);
        `FAIL_UNLESS_EQUAL(ctxt, blk(8'h27, 8'h6a, 8'hec, 8'h41, 8'hfd, 8'ha9, 8'h9f, 8'h26,
                                     8'h34, 8'hc5, 8'h43, 8'h73, 8'hc7, 8'h99, 8'hd2, 8'h19))

        // Now test decryption! Just do a single block.
        ctr.command_in_put(command(32'd16));
        ctr.ptxt_in_put(blk(8'h27, 8'h6a, 8'hec, 8'h41, 8'hfd, 8'ha9, 8'h9f, 8'h26,
                            8'h34, 8'hc5, 8'h43, 8'h73, 8'hc7, 8'h99, 8'hd2, 8'h19));
        ctr.ctxt_out_get(ctxt);
        `FAIL_UNLESS_EQUAL(ctxt, blk(8'h20, 8'h21, 8'h22, 8'h23, 8'h24, 8'h25, 8'h26, 8'h27,
                                     8'h28, 8'h29, 8'h2a, 8'h2b, 8'h2c, 8'h2d, 8'h2e, 8'h2f))
    `SVTEST_END

    `SVUNIT_TESTS_END
endmodule
