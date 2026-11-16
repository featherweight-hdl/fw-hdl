// Bug 2: a localparam set from $bits() of a parameterized class typedef,
// then used in a generate-if, crashes Verilator.
// Expected: prints 8 (pyslang agrees).
// Observed with Verilator 5.055: "%Error: Verilator internal fault", exit 139.
// Without the generate-if, it builds and prints 8.
package p;
  class C #(int W = 8);
    typedef C #(W) this_t;
    typedef logic [W-1:0] w_t;
  endclass
endpackage
module top;
  localparam int B8 = $bits(p::C#(8)::w_t);
  if (B8 != 8) begin : g_bad $error("bad"); end
  initial begin $display("%0d", B8); $finish; end
endmodule
