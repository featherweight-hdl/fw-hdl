// L2: object built at elaboration, member used as register state
class counter;
  logic [7:0] v;
  function new(); v = 0; endfunction
  function void step(input logic rst); if (rst) v = 0; else v = v + 1; endfunction
endclass
module top(input logic clk, input logic rst, output logic [7:0] q);
  counter c = new();
  always_ff @(posedge clk) begin c.step(rst); q <= c.v; end
endmodule
