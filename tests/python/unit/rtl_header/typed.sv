// A header with a type parameter, a signed port and a define-dependent width.
`ifndef TYPED_W
`define TYPED_W 3
`endif
module typed #(parameter type T = logic [7:0], parameter int N = 2) (
    input  logic               clk,
    input  T                   d,
    output logic signed [`TYPED_W-1:0] s,
    output logic [N-1:0][3:0]  q
);
endmodule
