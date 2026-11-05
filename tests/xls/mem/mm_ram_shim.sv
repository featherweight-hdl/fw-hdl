// A stand-in for a RAM cell's shim, for tests/xls/test_sp_mem.py: the ports
// of fw_ram_1rw_model, around it.
module mm_ram_shim #(
    parameter int WIDTH = 8,
    parameter int WORDS = 2,
    parameter int AW = (WORDS > 1) ? $clog2(WORDS) : 1
) (
    input  logic             clk,
    input  logic             en,
    input  logic             we,
    input  logic [AW-1:0]    a,
    input  logic [WIDTH-1:0] wd,
    output logic [WIDTH-1:0] rd
);
    fw_ram_1rw_model #(.WIDTH(WIDTH), .WORDS(WORDS)) u_ram(.*);
endmodule
