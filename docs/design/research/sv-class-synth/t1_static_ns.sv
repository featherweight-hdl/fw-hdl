// L1: class as a namespace (virtual, DC-style)
virtual class util #(parameter int W = 8);
  static function logic [W-1:0] inc(logic [W-1:0] x); return x + 1; endfunction
endclass
module top(input logic clk, input logic rst, output logic [7:0] q);
  always_ff @(posedge clk) if (rst) q <= '0; else q <= util#(8)::inc(q);
endmodule
