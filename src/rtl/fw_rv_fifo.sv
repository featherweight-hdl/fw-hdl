// The RTL form of an fw_channel #(T, DEPTH) (xls-phase2.md §4, INT-2):
// a ready/valid channel between two blocks.
//
//   DEPTH == 0  a wire: in and out are the same handshake, as a rendezvous is.
//               Safe to chain because a block's valid never depends on its
//               ready (true of XLS-generated blocks), so no loop can form.
//   DEPTH >= 1  a FIFO holding up to DEPTH values. in_rdy depends only on the
//               FIFO's own state, so it breaks the ready path between blocks.
//
// A value moves on a cycle where valid and ready are both high. Reset is
// synchronous and active high, the XLS codegen default the integration uses.
module fw_rv_fifo #(
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
    if (DEPTH == 0) begin : g_wire
        assign out_data = in_data;
        assign out_vld  = in_vld;
        assign in_rdy   = out_rdy;
    end else begin : g_fifo
        localparam int AW = (DEPTH > 1) ? $clog2(DEPTH) : 1;
        logic [WIDTH-1:0] mem [DEPTH];
        logic [AW-1:0]    rd, wr;
        logic [AW:0]      count;

        wire push = in_vld && in_rdy;
        wire pop  = out_vld && out_rdy;

        assign in_rdy   = (count != DEPTH[AW:0]);
        assign out_vld  = (count != '0);
        assign out_data = mem[rd];

        function automatic logic [AW-1:0] next(logic [AW-1:0] p);
            return (p == AW'(DEPTH - 1)) ? '0 : p + 1'b1;
        endfunction

        always_ff @(posedge clk) begin
            if (rst) begin
                rd    <= '0;
                wr    <= '0;
                count <= '0;
            end else begin
                if (push) begin
                    mem[wr] <= in_data;
                    wr      <= next(wr);
                end
                if (pop)
                    rd <= next(rd);
                count <= count + (AW+1)'(push) - (AW+1)'(pop);
            end
        end
    end
endmodule
