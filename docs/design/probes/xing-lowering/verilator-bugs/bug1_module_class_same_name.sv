// A module and a package class with the same name, both parameterized and
// both specialized with the same parameter value. Legal SV: modules are in
// the definitions name space, classes in the package's. Expected: prints
// "R 1". Observed (Verilator 5.055): Internal Error, V3Ast.h:1173 "AstNode
// is not of expected type, but instead has type 'MODULE'" at the module.
// Fine if the specializations differ (foo #(int) c), if either one is not
// parameterized, or if the module keeps its defaults.
package p;
  class foo #(type T = bit);
    int x;
    function new(); x = 1; endfunction
  endclass
endpackage

module foo #(parameter type T = bit) (input logic clk, output logic o);
  always_ff @(posedge clk) o <= ~o;
endmodule

module top;
  bit clk;
  logic o;
  foo #(.T(byte)) u(.clk(clk), .o(o));
  p::foo #(byte) c;
  initial begin
    c = new;
    $display("R %0d", c.x);
    $finish;
  end
endmodule
