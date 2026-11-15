// L3-: inheritance, non-virtual methods, called through derived handle
class base;
  logic [7:0] v;
  function new(); v = 0; endfunction
  function void clr(); v = 0; endfunction
endclass
class up extends base;
  function new(); super.new(); endfunction
  function void step(input logic rst); if (rst) clr(); else v = v + 1; endfunction
endclass
module top(input logic clk, input logic rst, output logic [7:0] q);
  up c = new();
  always_ff @(posedge clk) begin c.step(rst); q <= c.v; end
endmodule
