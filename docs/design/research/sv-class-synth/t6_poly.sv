// L3: base handle holding derived object (factory-style polymorphism, fixed at elaboration)
class base;
  logic [7:0] v;
  function new(); v = 0; endfunction
  virtual function logic [7:0] nxt(logic [7:0] x); return x + 1; endfunction
endclass
class down extends base;
  function new(); super.new(); endfunction
  virtual function logic [7:0] nxt(logic [7:0] x); return x - 1; endfunction
endclass
module top #(parameter bit DOWN = 1) (input logic clk, input logic rst, output logic [7:0] q);
  base c;
  initial begin
    down d;
    if (DOWN) begin d = new(); c = d; end else c = new();
  end
  always_ff @(posedge clk) begin if (rst) c.v = 0; else c.v = c.nxt(c.v); q <= c.v; end
endmodule
