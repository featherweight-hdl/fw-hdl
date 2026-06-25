module blinky(
  input logic clock,
  input logic reset,
  output logic led
);

  logic v;
  logic state;
  logic [7:0] count;

  // [_blinky]
  always @(posedge clock) begin
    if (reset) begin
      led <= 0;
      v <= 0;
      state <= 0;
      count <= 0;
    end else if (state == 0) begin
      led <= v;
      state <= 1;
      count <= 99;
    end else if (count[7]) begin
      v <= ~v;
      state <= 0;
    end else begin
      count <= (count - 1);
    end
  end

endmodule
