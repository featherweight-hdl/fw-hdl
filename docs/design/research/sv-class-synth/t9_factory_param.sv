// L3: implementation chosen at elaboration without base-handle assignment:
// a parameterized wrapper selects the concrete class type
class up;   function logic [7:0] nxt(logic [7:0] x); return x + 1; endfunction endclass
class down; function logic [7:0] nxt(logic [7:0] x); return x - 1; endfunction endclass
module top #(parameter type IMPL = down) (input logic clk, input logic rst, output logic [7:0] q);
  IMPL c = new();
  always_ff @(posedge clk) if (rst) q <= 0; else q <= c.nxt(q);
endmodule
