`timescale 1ns/1ps
// Checks a counter-style top: after reset, q == STEP*N (mod 256) after N clocks.
module tb;
  parameter int STEP = 1;
  logic clk = 0, rst = 1; logic [7:0] q; int errs = 0;
  top dut(.clk, .rst, .q);
  always #5 clk = ~clk;
  initial begin
    #200; @(posedge clk); #1 rst = 0;  // wait out glbl GSR (100ns)
    for (int n = 1; n <= 20; n++) begin
      @(posedge clk); #1;
      if (q !== 8'(STEP*n)) begin errs++; $display("MISMATCH n=%0d q=%0d exp=%0d", n, q, 8'(STEP*n)); end
    end
    $display("SIMRESULT %s errs=%0d", errs ? "FAIL" : "PASS", errs); $finish;
  end
endmodule
