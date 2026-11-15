// L2: class object inside a submodule instantiated twice -- per-instance state
class acc;
  logic [7:0] v;
  function new(); v = 0; endfunction
  function void add(input logic rst, input logic [7:0] d); if (rst) v = 0; else v = v + d; endfunction
endclass
module sub(input logic clk, input logic rst, input logic [7:0] d, output logic [7:0] q);
  acc a = new();
  always_ff @(posedge clk) begin a.add(rst, d); q <= a.v; end
endmodule
module top(input logic clk, input logic rst, output logic [7:0] q1, output logic [7:0] q2);
  sub u1(.clk, .rst, .d(8'd1), .q(q1));
  sub u2(.clk, .rst, .d(8'd3), .q(q2));
endmodule
