// Miter: the generated rr_merge (rtl/gen/rr_merge.sv) against the
// hand-written rr_merge_ref (rtl/rr_merge_ref.sv) on the same inputs, at N
// inputs and FIFO depth DEPTH, with a 9-bit beat ({data[7:0], last}). Both are
// read through sv2v (yosys's reader has no `parameter type`), which turns
// in_data into a flat vector of N beats. ready, valid and data must match
// every cycle.
module rr_merge_miter #(parameter int N = 4, parameter int DEPTH = 2) (
    input logic           clock, reset,
    input logic [N-1:0]   in_valid,
    input logic [N*9-1:0] in_data,
    input logic           out_ready
);
    logic [N-1:0] g_ready, r_ready;
    logic         g_valid, r_valid;
    logic [8:0]   g_data, r_data;

    rr_merge #(.N(N), .DEPTH(DEPTH)) gen (
        .clock(clock), .reset(reset),
        .in_valid(in_valid), .in_ready(g_ready), .in_data(in_data),
        .out_valid(g_valid), .out_ready(out_ready), .out_data(g_data));
    rr_merge_ref #(.N(N), .DEPTH(DEPTH)) ref (
        .clock(clock), .reset(reset),
        .in_valid(in_valid), .in_ready(r_ready), .in_data(in_data),
        .out_valid(r_valid), .out_ready(out_ready), .out_data(r_data));

    always @* begin
        assert (g_ready == r_ready);
        assert (g_valid == r_valid);
        assert (g_data == r_data);
    end
endmodule
