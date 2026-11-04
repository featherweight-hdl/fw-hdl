// A behavioural two-port RAM for simulation: one write and one read per
// cycle, the read data registered (valid the cycle after re, held until the
// next read). These are the ports fw_sram_fifo drives; a real cell is
// reached through a shim module with the same ports, named by the knob's
// `macro:`. A read and a write of the same word in one cycle return the old
// value here; fw_sram_fifo never does that.
module fw_ram_1r1w_model #(
    parameter int WIDTH = 8,
    parameter int WORDS = 2,
    parameter int AW = (WORDS > 1) ? $clog2(WORDS) : 1
) (
    input  logic             clk,
    input  logic [AW-1:0]    wa,
    input  logic             we,
    input  logic [WIDTH-1:0] wd,
    input  logic [AW-1:0]    ra,
    input  logic             re,
    output logic [WIDTH-1:0] rd
);
    logic [WIDTH-1:0] mem [WORDS];

    always_ff @(posedge clk) begin
        if (we)
            mem[wa] <= wd;
        if (re)
            rd <= mem[ra];
    end
endmodule
