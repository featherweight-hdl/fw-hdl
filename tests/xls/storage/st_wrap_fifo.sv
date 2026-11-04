// A supplied FIFO wrapper for test_storage_binding.py (knob `storage:
// {bind: wrapper, module: st_wrap_fifo}`): fw_rv_fifo's ports and
// parameters, built on fw_rv_fifo.
module st_wrap_fifo #(
    parameter int WIDTH = 8,
    parameter int DEPTH = 1
) (
    input  logic             clk,
    input  logic             rst,
    input  logic [WIDTH-1:0] in_data,
    input  logic             in_vld,
    output logic             in_rdy,
    output logic [WIDTH-1:0] out_data,
    output logic             out_vld,
    input  logic             out_rdy
);
    fw_rv_fifo #(.WIDTH(WIDTH), .DEPTH(DEPTH)) u(.*);
endmodule
