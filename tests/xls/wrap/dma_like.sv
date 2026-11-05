// A module shaped like vendor IP, for fw-hdl wrap: a command stream in, a
// valid-only completion out (no back-pressure), configuration and status
// levels, a debug output and a scan input. Its own names and an active-low
// reset.
//
// A command is taken when the engine is idle and enabled; cfg_burst + 1
// cycles later the completion gives the command's low byte, once.
module dma_like #(
    parameter int DW = 16,
    parameter int BW = 3
) (
    input  logic          aclk,
    input  logic          aresetn,
    input  logic [DW-1:0] cmd_data,
    input  logic          cmd_valid,
    output logic          cmd_ready,
    output logic [7:0]    done,
    output logic          done_vld,
    input  logic          cfg_en,
    input  logic [BW-1:0] cfg_burst,
    output logic          status_busy,
    output logic [2:0]    dbg_state,
    input  logic          scan_en
);
    logic [BW:0] count;
    logic [7:0]  tag;

    assign cmd_ready   = !status_busy && cfg_en && !scan_en;
    assign dbg_state   = {status_busy, done_vld, cmd_ready};

    always_ff @(posedge aclk or negedge aresetn) begin
        if (!aresetn) begin
            status_busy <= 1'b0;
            done_vld    <= 1'b0;
            done        <= '0;
            count       <= '0;
            tag         <= '0;
        end else begin
            done_vld <= 1'b0;
            if (cmd_valid && cmd_ready) begin
                status_busy <= 1'b1;
                tag         <= cmd_data[7:0];
                count       <= {1'b0, cfg_burst};
            end else if (status_busy) begin
                if (count == 0) begin
                    status_busy <= 1'b0;
                    done_vld    <= 1'b1;
                    done        <= tag;
                end else begin
                    count <= count - 1'b1;
                end
            end
        end
    end
endmodule
