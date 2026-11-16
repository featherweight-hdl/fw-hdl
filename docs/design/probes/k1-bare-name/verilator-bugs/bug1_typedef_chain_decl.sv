// Bug 1: a class-scoped typedef reached through a class-local typedef of
// the specialization fails to resolve in a declaration.
// Expected: prints 16 (pyslang agrees).
// Observed with Verilator 5.055: %Error: Package/class for ':: reference' not found: 'this_t'
// The same chain inside $bits() in a localparam resolves correctly.
package p;
  class C #(int W = 8);
    typedef C #(W) this_t;
    typedef logic [W-1:0] w_t;
  endclass
endpackage
module top;
  p::C#(16)::this_t::w_t chained;
  initial begin $display("%0d", $bits(chained)); $finish; end
endmodule
