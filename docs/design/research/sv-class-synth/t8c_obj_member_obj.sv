// L2: object containing other objects (composition), built in constructors
class reg8;
  logic [7:0] v;
  function new(); v = 0; endfunction
endclass
class pipe2;
  reg8 a, b;
  function new(); a = new(); b = new(); endfunction
  function void step(input logic rst, input logic [7:0] d);
    if (rst) begin a.v = 0; b.v = 0; end else begin b.v = a.v; a.v = d; end
  endfunction
endclass
module top(input logic clk, input logic rst, input logic [7:0] d, output logic [7:0] q);
  pipe2 p = new();
  always_ff @(posedge clk) begin p.step(rst, d); q <= p.b.v; end
endmodule
