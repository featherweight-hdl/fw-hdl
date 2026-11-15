// L2: array of objects built at elaboration in a loop
class stage;
  logic [7:0] v;
  function new(); v = 0; endfunction
endclass
module top(input logic clk, input logic rst, input logic [7:0] d, output logic [7:0] q);
  stage c[4];
  initial foreach (c[i]) c[i] = new();
  always_ff @(posedge clk) begin
    if (rst) foreach (c[i]) c[i].v = 0;
    else begin c[0].v = d; for (int i = 1; i < 4; i++) c[i].v = c[i-1].v; end
    q <= c[3].v;
  end
endmodule
