// L3: base handle constructed directly with a derived type: base c = down::new()
class base;
  logic [7:0] v;
  function new(); v = 0; endfunction
  virtual function logic [7:0] nxt(logic [7:0] x); return x + 1; endfunction
endclass
class down extends base;
  function new(); super.new(); endfunction
  virtual function logic [7:0] nxt(logic [7:0] x); return x - 1; endfunction
endclass
module top(input logic clk, input logic rst, output logic [7:0] q);
  base c = down::new();
  always_ff @(posedge clk) begin if (rst) c.v = 0; else c.v = c.nxt(c.v); q <= c.v; end
endmodule
