`timescale 1ns/1ps
// Checks a delay-line top: q == d delayed by DEPTH clocks.
module tb #(parameter int STEP = 2);
  localparam int DEPTH = STEP;
  logic clk = 0, rst = 1; logic [7:0] d = 0, q; int errs = 0; logic [7:0] hist[$];
  top dut(.clk, .rst, .d, .q);
  always #5 clk = ~clk;
  initial begin
    #200; @(posedge clk); #1 rst = 0;
    for (int n = 0; n < 30; n++) begin
      d = 8'(n * 7 + 1); hist.push_back(d);
      @(posedge clk); #1;
      if (n >= DEPTH - 1 && q !== hist[n - DEPTH + 1]) begin errs++; $display("MISMATCH n=%0d q=%0d exp=%0d", n, q, hist[n-DEPTH+1]); end
    end
    $display("SIMRESULT %s errs=%0d", errs ? "FAIL" : "PASS", errs); $finish;
  end
endmodule
