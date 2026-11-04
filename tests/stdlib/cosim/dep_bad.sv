// Two wrong dependency trackers for tests/stdlib/test_cosim.py, with
// fw_dep_tracker's ports: MODE 0 never makes a dependent wait (ok all
// ones); MODE 1 never releases one (a dependent that waits stays waiting).
module dep_bad #(parameter int MODE = 0) (
    input  logic       clk,
    input  logic       rst,
    input  logic [2:0] ent,
    input  logic       ent_vld,
    output logic       ent_rdy,
    input  logic [1:0] ret,
    input  logic       ret_vld,
    output logic       ret_rdy,
    output logic [3:0] ok
);
    assign ent_rdy = 1'b1;
    assign ret_rdy = 1'b1;
    logic [3:0] live, wait_q;
    always_ff @(posedge clk) begin
        if (rst) begin
            live <= '0;
            wait_q <= '0;
        end else begin
            if (ret_vld)
                live[ret] <= 1'b0;
            if (ent_vld && !ent[2])
                live[ent[1:0]] <= 1'b1;
            if (ent_vld && ent[2])
                wait_q[ent[1:0]] <= |live;
        end
    end
    assign ok = (MODE == 0) ? 4'hf : ~wait_q;
endmodule
