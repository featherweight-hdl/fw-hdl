// A supplied FIFO module for a channel inside a group, with the ports XLS's
// multi-proc codegen gives it (knob `storage: {bind: wrapper, module:
// st_xls_wrap}`): fw_xls_fifo_wrapper under another name.
module st_xls_wrap #(
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
    fw_xls_fifo_wrapper #(.Width(Width), .Depth(Depth), .EnableBypass(EnableBypass),
                          .RegisterPushOutputs(RegisterPushOutputs),
                          .RegisterPopOutputs(RegisterPopOutputs)) u(.*);
endmodule
