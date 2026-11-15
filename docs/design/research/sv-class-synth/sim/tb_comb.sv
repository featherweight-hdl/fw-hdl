`timescale 1ns/1ps
module tb #(parameter int STEP = 1);
  logic clk = 0; logic [7:0] a, y, z; int errs = 0;
  top dut(.clk, .a, .y, .z);
  initial begin
    #200;
    for (int i = 0; i < 256; i += 7) begin a = i; #1;
      if (y !== 8'(i+3) || z !== 8'(i+5)) begin errs++; $display("MISMATCH a=%0d y=%0d z=%0d", i, y, z); end end
    $display("SIMRESULT %s errs=%0d", errs ? "FAIL" : "PASS", errs); $finish;
  end
endmodule
