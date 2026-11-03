// The FIFO XLS multi-proc codegen instantiates for an in-package channel
// (codegen_main --multi_proc --fifo_module=fw_xls_fifo_wrapper), with the
// parameter and port names XLS uses. It is fw_rv_fifo, so a channel inside a
// multi-proc block behaves as one between blocks does: no bypass, ready and
// valid from registered state. Depth 0 with bypass is a wire.
//
// EnableBypass with Depth > 0 is refused: fw_rv_fifo has no bypass, and a
// silent latency change would break the latency report. The register flags
// need nothing more, since fw_rv_fifo's outputs are already registered.
module fw_xls_fifo_wrapper #(
    parameter int Width = 8,
    parameter int Depth = 1,
    parameter bit EnableBypass = 1'b0,
    parameter bit RegisterPushOutputs = 1'b0,
    parameter bit RegisterPopOutputs = 1'b0
) (
    input  logic             clk,
    input  logic             rst,
    input  logic [Width-1:0] push_data,
    input  logic             push_valid,
    output logic             push_ready,
    output logic [Width-1:0] pop_data,
    output logic             pop_valid,
    input  logic             pop_ready
);
    if (Depth == 0) begin : g_wire
        if (!EnableBypass) begin : g_bad
            $error("fw_xls_fifo_wrapper: Depth 0 needs EnableBypass");
        end
        assign pop_data   = push_data;
        assign pop_valid  = push_valid;
        assign push_ready = pop_ready;
    end else begin : g_fifo
        if (EnableBypass) begin : g_bad
            $error("fw_xls_fifo_wrapper: EnableBypass with Depth > 0 is not supported");
        end
        fw_rv_fifo #(.WIDTH(Width), .DEPTH(Depth)) u_fifo (
            .clk(clk), .rst(rst),
            .in_data(push_data), .in_vld(push_valid), .in_rdy(push_ready),
            .out_data(pop_data), .out_vld(pop_valid), .out_rdy(pop_ready));
    end
endmodule
