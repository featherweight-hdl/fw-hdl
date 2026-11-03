// The credit check on a valid-only channel's FIFO (fw.hdl.spl.Integrate puts
// one on each fw_valid_channel). The producer has no ready pin, so a value
// offered while the FIFO is full is lost: a credit violation, reported here.
// Under ASSERT_ON only; it has no outputs.
module fw_valid_check #(
    parameter string NAME = "channel"
) (
    input logic clk,
    input logic rst,
    input logic vld,
    input logic rdy
);
`ifdef ASSERT_ON
    always_ff @(posedge clk) begin
        if (!rst && vld && !rdy)
            $error("fw_valid_check %s: offered while full (a credit violation)", NAME);
    end
`endif
endmodule
