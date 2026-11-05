module nonansi(clk, rst_n, a, b, y);
  parameter integer W = 4;
  parameter string MODE = "fast";
  localparam integer W2 = W * 2;
  input clk, rst_n;
  input [W-1:0] a;
  input wire [W-1:0] b;
  output reg [W2-1:0] y;
  always @(posedge clk) y <= a * b;
endmodule
