`timescale 1ns/1ps
module tb #(parameter int STEP = 1);
  logic clk = 0, rst = 1; logic [7:0] q1, q2; int errs = 0;
  top dut(.clk, .rst, .q1, .q2);
  always #5 clk = ~clk;
  initial begin
    #200; @(posedge clk); #1 rst = 0;  // wait out glbl GSR (100ns)
    for (int n = 1; n <= 20; n++) begin @(posedge clk); #1;
      if (q1 !== 8'(n) || q2 !== 8'(3*n)) begin errs++; $display("MISMATCH n=%0d q1=%0d q2=%0d", n, q1, q2); end end
    $display("SIMRESULT %s errs=%0d", errs ? "FAIL" : "PASS", errs); $finish;
  end
endmodule
