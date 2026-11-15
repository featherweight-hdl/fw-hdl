// L2: one object per generate iteration (shift register of class objects)
class stage;
  logic [7:0] v;
  function new(); v = 0; endfunction
endclass
module top(input logic clk, input logic rst, input logic [7:0] d, output logic [7:0] q);
  logic [7:0] w [5];
  assign w[0] = d;
  for (genvar i = 0; i < 4; i++) begin : g
    stage s = new();
    always_ff @(posedge clk) begin if (rst) s.v = 0; else s.v = w[i]; end
    always_comb w[i+1] = s.v;  // class members cannot appear in continuous assign
  end
  assign q = w[4];
endmodule
