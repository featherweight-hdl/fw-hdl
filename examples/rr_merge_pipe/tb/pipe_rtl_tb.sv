// pipe_bench on a generated (or hand-written) module with rr_merge_pipe's
// ports. The module and the beat width are chosen at build time:
//   +define+PIPE_DUT=<module>   (default rr_merge_pipe)
//   +define+PIPE_W_16 or PIPE_W_32 (default: W = 8)
//   +define+PIPE_N=<N>          (default 4)
//   +define+PIPE_TP             the module has a TP parameter (the variants)
// and the DUT's out goes to the bench through pipe_mutant (+mutant=<mode>).
`ifndef PIPE_DUT
`define PIPE_DUT rr_merge_pipe
`endif
`ifndef PIPE_N
`define PIPE_N 4
`endif
`define PIPE_STR(x) `"x`"
module pipe_rtl_tb;
    localparam int N = `PIPE_N;
`define PIPE_TYPES(w) typedef pipe_types_pkg::pipe_in``w``_t ti_t; typedef pipe_types_pkg::pipe_mid``w``_t tm_t; typedef pipe_types_pkg::pipe_prod``w``_t tp_t;
`ifdef PIPE_W_16
    `PIPE_TYPES(16)
`elsif PIPE_W_32
    `PIPE_TYPES(32)
`else
    `PIPE_TYPES(8)
`endif

    logic           clk = 0, rst;
    always #5 clk = ~clk;
    logic [N-1:0]   in_valid, in_ready;
    ti_t  [N-1:0]   in_data;
    logic           out_valid, out_ready;
    tm_t            out_data;

    logic           d_valid, d_ready;
    tm_t            d_data;

    pipe_bench #(.N(N), .TI(ti_t), .TM(tm_t), .NAME(`PIPE_STR(`PIPE_DUT))) bench (.*);

`ifdef PIPE_TP
    `PIPE_DUT #(.TI(ti_t), .TP(tp_t), .TM(tm_t), .N(N), .DEPTH(2)) dut (
`else
    `PIPE_DUT #(.TI(ti_t), .TM(tm_t), .N(N), .DEPTH(2)) dut (
`endif
        .clock(clk), .reset(rst),
        .in_valid, .in_ready, .in_data,
        .out_valid(d_valid), .out_ready(d_ready), .out_data(d_data));

    pipe_mutant #(.TM(tm_t)) mutant (
        .clk, .d_valid, .d_ready, .d_data,
        .b_valid(out_valid), .b_ready(out_ready), .b_data(out_data));

    initial begin
        wait (bench.done);
        if (bench.errors != 0) $fatal(1, "FAIL");
        $finish;
    end
endmodule
