// A FIFO with pins a wrapper ties or leaves open: a debug enable and a mode
// input, and a debug output.
module q_dbg #(parameter int W = 8) (
    input  logic         clk,
    input  logic         rst,
    input  logic [W-1:0] in_data,
    input  logic         in_vld,
    output logic         in_rdy,
    output logic [W-1:0] out_data,
    output logic         out_vld,
    input  logic         out_rdy,
    input  logic         dbg_en,
    input  logic [1:0]   mode,
    output logic [W-1:0] dbg_q
);
    fw_rv_fifo #(.WIDTH(W), .DEPTH(2)) u (.*);
    assign dbg_q = dbg_en && mode != 2'd0 ? in_data : '0;
endmodule
