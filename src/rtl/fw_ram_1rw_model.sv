// A behavioural single-port RAM for simulation: one access per cycle, a read
// (en && !we) or a write (en && we); the read data registered (valid the
// cycle after the read, held until the next read). These are the ports an
// fw_sp_mem member's block drives; a real cell is reached through a shim
// module with the same ports, named by the knob's `macro:`. As with a real
// cell, a word not yet written reads as unknown; rd is 0 until the first
// read.
module fw_ram_1rw_model #(
    parameter int WIDTH = 8,
    parameter int WORDS = 2,
    parameter int AW = (WORDS > 1) ? $clog2(WORDS) : 1
) (
    input  logic             clk,
    input  logic             en,
    input  logic             we,
    input  logic [AW-1:0]    a,
    input  logic [WIDTH-1:0] wd,
    output logic [WIDTH-1:0] rd = '0
);
    logic [WIDTH-1:0] mem [WORDS];

    always_ff @(posedge clk) begin
        if (en && we)
            mem[a] <= wd;
        if (en && !we)
            rd <= mem[a];
    end
endmodule
