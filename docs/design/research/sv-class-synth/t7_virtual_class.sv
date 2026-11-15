// abstract base class with pure virtual method, concrete derived
virtual class base;
  pure virtual function logic [7:0] nxt(logic [7:0] x);
endclass
class up extends base;
  virtual function logic [7:0] nxt(logic [7:0] x); return x + 1; endfunction
endclass
module top(input logic clk, input logic rst, output logic [7:0] q);
  up c = new();
  always_ff @(posedge clk) if (rst) q <= 0; else q <= c.nxt(q);
endmodule
