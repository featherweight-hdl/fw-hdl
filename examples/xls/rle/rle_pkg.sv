// Derived from XLS xls/modules/rle/{rle_common,rle_enc,rle_dec}.x (see orig/),
// Copyright The XLS Authors, Apache-2.0 (see ../NOTICE). A line-for-line port
// to the fw-hdl static subset; README.md lists the deviations.
//
// A DSLX proc is an fw_component: its channels are ports, its state is the
// class's properties (initialized as `init` does), and `next` is the body of
// the `forever` loop in run(). recv_if/send_if are a get/put under `if`.
`include "fw_std_macros.svh"

package rle_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;

    // rle_common.x. A DSLX struct is a packed struct, fields in order, the
    // first the most significant (as XLS lays out a struct).
    class rle_common #(int unsigned SYMBOL_WIDTH = 32, int unsigned COUNT_WIDTH = 2);
        typedef struct packed {
            bit [SYMBOL_WIDTH-1:0] symbol;  // symbol
            bit last;                       // flush RLE
        } PlainData;

        // Structure contains compressed (symbol, counter) pairs.
        // Structure is used as an output from RLE encoder and
        // as an input to RLE decoder.
        typedef struct packed {
            bit [SYMBOL_WIDTH-1:0] symbol;  // symbol
            bit [COUNT_WIDTH-1:0] count;    // symbol counter
            bit last;                       // flush RLE
        } CompressedData;
    endclass

    // rle_enc.x
    class RunLengthEncoder #(int unsigned SYMBOL_WIDTH = 32, int unsigned COUNT_WIDTH = 2)
            extends fw_component implements fw_runnable;
        typedef rle_common #(SYMBOL_WIDTH, COUNT_WIDTH)::PlainData EncInData;
        typedef rle_common #(SYMBOL_WIDTH, COUNT_WIDTH)::CompressedData EncOutData;

        fw_port #(fw_get_if #(EncInData)) input_r;
        fw_port #(fw_put_if #(EncOutData)) output_s;

        // RunLengthEncoderState
        // symbol from the previous RunLengthEncoder::next evaluation,
        // valid if prev_count > 0
        bit [SYMBOL_WIDTH-1:0] prev_symbol = '0;
        // symbol count from the previous RunLengthEncoder::next evaluation.
        // zero means that the previous evaluation sent all the data and
        // we start counting from the beginning
        bit [COUNT_WIDTH-1:0] prev_count = '0;
        // flag indicating that the previous symbol was the last one
        // in the transmission
        bit prev_last = 1'b0;

        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);
        endfunction

        function void build();
            input_r = new("input_r", this);
            output_s = new("output_s", this);
        endfunction

        virtual task run();
            forever begin
                EncInData zero_input = '{symbol: '0, last: 1'b0};
                EncInData input_ = zero_input;
                bit prev_symbol_valid, symbol_differ, overflow, do_send;
                bit [SYMBOL_WIDTH-1:0] symbol;
                bit [COUNT_WIDTH-1:0] count;
                bit last;

                if (!prev_last) input_r.t.get(input_);

                prev_symbol_valid = prev_count != '0;
                symbol_differ = prev_symbol_valid && (input_.symbol != prev_symbol);
                overflow = prev_count == '1;  // std::unsigned_max_value<COUNT_WIDTH>()

                if (prev_last) begin
                    symbol = '0;
                    count = '0;
                    last = 1'b0;
                end else if (symbol_differ || overflow) begin
                    symbol = input_.symbol;
                    count = 1;
                    last = input_.last;
                end else begin
                    symbol = input_.symbol;
                    count = prev_count + 1'b1;
                    last = input_.last;
                end

                do_send = prev_last || symbol_differ || overflow;
                if (do_send)
                    output_s.t.put('{symbol: prev_symbol, count: prev_count, last: prev_last});

                prev_symbol = symbol;
                prev_count = count;
                prev_last = last;
            end
        endtask
    endclass

    // rle_dec.x
    class RunLengthDecoder #(int unsigned SYMBOL_WIDTH = 32, int unsigned COUNT_WIDTH = 2)
            extends fw_component implements fw_runnable;
        typedef rle_common #(SYMBOL_WIDTH, COUNT_WIDTH)::CompressedData DecInData;
        typedef rle_common #(SYMBOL_WIDTH, COUNT_WIDTH)::PlainData DecOutData;

        fw_port #(fw_get_if #(DecInData)) input_r;
        fw_port #(fw_put_if #(DecOutData)) output_s;

        // RunLengthDecoderState
        // symbol to be repeated on output
        bit [SYMBOL_WIDTH-1:0] symbol = '0;
        // count of symbols that has to be send
        bit [COUNT_WIDTH-1:0] count = '0;
        // send last when repeat ends
        bit last = 1'b0;

        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);
        endfunction

        function void build();
            input_r = new("input_r", this);
            output_s = new("output_s", this);
        endfunction

        virtual task run();
            forever begin
                DecInData state_input = '{symbol: symbol, count: count, last: last};
                DecInData input_ = state_input;
                bit recv_next_symbol;
                bit [COUNT_WIDTH-1:0] next_count;
                bit done_sending, send_last;

                recv_next_symbol = count == '0;
                if (recv_next_symbol) input_r.t.get(input_);
                if (input_.count == '0) begin
                    assert (0) else $fatal(1, "invalid_count_0");
                    next_count = input_.count;
                end else begin
                    next_count = input_.count - 1'b1;
                end
                done_sending = next_count == '0;
                send_last = input_.last && done_sending;
                output_s.t.put('{symbol: input_.symbol, last: send_last});
                if (send_last) begin
                    symbol = '0;
                    count = '0;
                    last = 1'b0;
                end else begin
                    symbol = input_.symbol;
                    count = next_count;
                    last = input_.last;
                end
            end
        endtask
    endclass

    // The specializations: RunLengthEncoder32/RunLengthDecoder32 are the
    // codegen ones in rle_enc.x/rle_dec.x (COUNT_WIDTH 2, which the overflow
    // tests also use); the tests' common one has COUNT_WIDTH 32.
    typedef RunLengthEncoder #(32, 2)  RunLengthEncoder32;
    typedef RunLengthDecoder #(32, 2)  RunLengthDecoder32;
    typedef RunLengthEncoder #(32, 32) RunLengthEncoder32_32;
    typedef RunLengthDecoder #(32, 32) RunLengthDecoder32_32;

endpackage
