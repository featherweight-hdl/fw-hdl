// L2: object used only for combinational helper methods with fields set by ctor
class adder;
  int unsigned k;
  function new(int unsigned k); this.k = k; endfunction
  function logic [7:0] f(logic [7:0] x); return x + k[7:0]; endfunction
endclass
module top(input logic clk, input logic [7:0] a, output logic [7:0] y, output logic [7:0] z);
  adder a3 = new(3);
  adder a5 = new(5);
  always_comb begin y = a3.f(a); z = a5.f(a); end
endmodule
