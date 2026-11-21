// The typed half of the F7 harnesses, read through sv2v: the pipelined map
// @MOD@ (one lane) and the comb map pipe_map_in as the reference f, with
// plain vector ports so that the properties (fv_props_*.v, read by yosys
// with -formal: sv2v drops assertions) need no struct types.
module fv_wrap (
    input  logic clk, rst,
    input  logic in_valid,
    output logic in_ready,
    input  logic [$bits(@TI@)-1:0] in_data,
    output logic out_valid,
    input  logic out_ready,
    output logic [$bits(@TM@)-1:0] out_data,
    input  logic [$bits(@TI@)-1:0] r_in,
    output logic [$bits(@TM@)-1:0] r_out
);
    logic r_ready, r_valid;
    @MOD@ #(.TI(@TI@), .TM(@TM@), .N(1)) dut (
        .clock(clk), .reset(rst), .in_valid(in_valid), .in_ready(in_ready),
        .in_data(in_data), .out_valid(out_valid), .out_ready(out_ready), .out_data(out_data));
    pipe_map_in #(.TI(@TI@), .TM(@TM@), .N(1)) ref_f (
        .in_valid(1'b1), .in_ready(r_ready), .in_data(r_in),
        .out_valid(r_valid), .out_ready(1'b1), .out_data(r_out));
endmodule
