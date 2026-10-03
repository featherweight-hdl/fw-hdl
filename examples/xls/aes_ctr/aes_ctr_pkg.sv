// Derived from XLS xls/modules/aes/aes_ctr.x (see ../aes/orig/), Copyright The
// XLS Authors, Apache-2.0 (see ../NOTICE). A line-for-line port to the fw-hdl
// static subset; README.md lists the deviations.
//
// The proc is an fw_component. A port's payload must be a packed type, so the
// Command struct holds the key as a packed array, and a block crosses a
// channel as a packed PBlock, converted to and from aes_pkg::Block. DSLX lays
// out an array element 0 first (most significant); the static subset takes
// descending packed ranges only, so element k of a DSLX array of n is index
// n-1-k here: key[k] is cmd.key[31 - k].
`include "fw_std_macros.svh"

package aes_ctr_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;
    import aes_pkg::*;

    typedef bit [95:0] InitVector;
    typedef bit [3:0][3:0][7:0] PBlock;   // aes_common::Block, packed: block[i][j] is p[3-i][3-j]

    typedef struct packed {
        // The number of bytes to expect in the incoming message.
        // At present, this number must be a multiple of 128.
        bit [31:0] msg_bytes;
        // The encryption key.
        bit [31:0][7:0] key;          // key[k] is this[31 - k]
        // The width of the encryption key.
        KeyWidth key_width;
        // The initialization vector for the operation.
        InitVector iv;
        // The initial counter value. When used standalone, this should be 0, but
        // when used as part of GCM, we start encrypting the plaintext with a
        // counter value of 2.
        bit [31:0] initial_ctr;
        // The amount by which to increment ctr every cycle. Usually 1, but can be
        // non-unit when part of a parallel GCM implementation.
        bit [31:0] ctr_stride;
    } Command;

    typedef enum bit {
        IDLE = 0,
        PROCESSING = 1
    } Step;

    function automatic Block unpack_block(PBlock p);
        Block b;
        for (int i = 0; i < 4; i++)
            for (int j = 0; j < 4; j++)
                b[i][j] = p[3 - i][3 - j];
        return b;
    endfunction

    function automatic PBlock pack_block(Block b);
        PBlock p;
        for (int i = 0; i < 4; i++)
            for (int j = 0; j < 4; j++)
                p[3 - i][3 - j] = b[i][j];
        return p;
    endfunction

    function automatic Block aes_ctr_encrypt(Key key, KeyWidth key_width, bit [127:0] ctr,
                                             Block block);
        // ctr as u32[4], each word as u8[4]: element 0 most significant.
        Block ctr_block;
        Block ctr_enc;
        Block out;
        for (int i = 0; i < 4; i++)
            for (int j = 0; j < 4; j++)
                ctr_block[i][j] = ctr[127 - 32 * i - 8 * j -: 8];
        ctr_enc = encrypt(key, key_width, ctr_block);
        for (int i = 0; i < 4; i++)
            for (int j = 0; j < 4; j++)
                out[i][j] = ctr_enc[i][j] ^ block[i][j];
        return out;
    endfunction

    class aes_ctr extends fw_component implements fw_runnable;
        fw_port #(fw_get_if #(Command)) command_in;
        fw_port #(fw_get_if #(PBlock)) ptxt_in;
        fw_port #(fw_put_if #(PBlock)) ctxt_out;

        // The recurrent state of the proc (State).
        Step step = IDLE;
        Command command = '0;
        bit [31:0] ctr = '0;
        bit [31:0] blocks_left = '0;

        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);
        endfunction

        function void build();
            command_in = new("command_in", this);
            ptxt_in = new("ptxt_in", this);
            ctxt_out = new("ctxt_out", this);
        endfunction

        virtual task run();
            forever begin
                Command cmd = '0;
                PBlock block = '0;
                bit [31:0] ctr_;
                bit [31:0] blocks_left_;
                bit [127:0] full_ctr;
                Key key;
                Block ctxt;

                if (step == IDLE) command_in.t.get(cmd);
                if (step != IDLE) cmd = command;
                ctr_ = (step == IDLE) ? cmd.initial_ctr : ctr;
                blocks_left_ = (step == IDLE)
                    ? xls_std_pkg::ceil_div_c#(32)::ceil_div(cmd.msg_bytes, 32'd16)
                    : blocks_left;
                full_ctr = {cmd.iv, ctr_};

                if (blocks_left_ != 32'd0) ptxt_in.t.get(block);
                for (int k = 0; k < 32; k++)
                    key[k] = cmd.key[31 - k];
                ctxt = aes_ctr_encrypt(key, cmd.key_width, full_ctr, unpack_block(block));
                ctxt_out.t.put(pack_block(ctxt));

                blocks_left_ = blocks_left_ - 32'd1;
                step = (blocks_left_ == 32'd0) ? IDLE : PROCESSING;

                // We don't have to worry about ctr overflowing (which would result in an
                // invalid encryption, since ctr starts at zero, and the maximum possible
                // number of blocks per command is 2^32 - 1.
                command = cmd;
                ctr = ctr_ + cmd.ctr_stride;
                blocks_left = blocks_left_;
            end
        endtask
    endclass

endpackage
