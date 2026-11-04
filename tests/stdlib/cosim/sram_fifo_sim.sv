// fw_sram_fifo with its RAM (fw_ram_1r1w_model), as Integrate wires them,
// for the cosim spec fw_channel_sram.yaml.
module sram_fifo_sim #(
    parameter int WIDTH = 8,
    parameter int DEPTH = 4
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
    localparam int AW = (DEPTH - 1 > 1) ? $clog2(DEPTH - 1) : 1;
    logic [AW-1:0]    wa, ra;
    logic             we, re;
    logic [WIDTH-1:0] wd, rd;
    fw_sram_fifo #(.WIDTH(WIDTH), .DEPTH(DEPTH)) u(
        .clk, .rst, .in_data, .in_vld, .in_rdy, .out_data, .out_vld, .out_rdy,
        .ram_wa(wa), .ram_we(we), .ram_wd(wd), .ram_ra(ra), .ram_re(re), .ram_rd(rd));
    fw_ram_1r1w_model #(.WIDTH(WIDTH), .WORDS(DEPTH - 1)) m(.clk, .wa, .we, .wd, .ra, .re, .rd);
endmodule
