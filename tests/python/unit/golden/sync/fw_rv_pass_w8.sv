module fw_rv_pass_w8(
  input logic in_valid,
  output logic in_ready,
  input logic [7:0] in_data,
  output logic out_valid,
  input logic out_ready,
  output logic [7:0] out_data
);

  // [comb]
  always_comb begin
    out_valid = in_valid;
    out_data = in_data;
    in_ready = out_ready;
  end

endmodule
