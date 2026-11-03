// The extern RTL for mixed_pkg::ext_neg: out = ~in, through a one-entry
// register. Ready and valid both come from the register, so the block's
// boundary is registered and valid never depends on ready.
module ext_neg_rtl (
    input  logic       clk,
    input  logic       rst,
    input  logic [7:0] in,
    input  logic       in_vld,
    output logic       in_rdy,
    output logic [7:0] out,
    output logic       out_vld,
    input  logic       out_rdy
);
    logic       full;
    logic [7:0] d;
    assign in_rdy  = !full;
    assign out     = d;
    assign out_vld = full;
    always_ff @(posedge clk) begin
        if (rst) begin
            full <= 1'b0;
            d    <= '0;
        end else if (full) begin
            if (out_rdy) full <= 1'b0;
        end else if (in_vld) begin
            d    <= ~in;
            full <= 1'b1;
        end
    end
endmodule
