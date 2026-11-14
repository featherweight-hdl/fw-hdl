module fw_rv_slice_w37(
  input logic clock,
  input logic reset,
  input logic in_valid,
  output logic in_ready,
  input logic [36:0] in_data,
  output logic out_valid,
  input logic out_ready,
  output logic [36:0] out_data
);

  logic skid_valid;
  logic [36:0] skid_data;
  logic in_ready_q;
  logic out_valid_q;

  // [step]
  always_ff @(posedge clock) begin
    if (reset) begin
      out_valid_q <= 0;
      skid_valid <= 0;
      in_ready_q <= 1;
    end else if ((out_ready) || (!out_valid_q)) begin
      if (skid_valid) begin
        out_valid_q <= 1;
        skid_valid <= 0;
      end else begin
        out_valid_q <= in_valid;
      end
      in_ready_q <= 1;
    end else if ((in_valid) && (in_ready_q)) begin
      skid_valid <= 1;
      in_ready_q <= 0;
    end
  end

  // Not reset
  always_ff @(posedge clock) begin
    if ((out_ready) || (!out_valid_q)) begin
      if (skid_valid) begin
        out_data <= skid_data;
      end else if (in_valid) begin
        out_data <= in_data;
      end
    end else if ((in_valid) && (in_ready_q)) begin
      skid_data <= in_data;
    end
  end

  assign in_ready = reset ? 1'd0 : in_ready_q;
  assign out_valid = reset ? 1'd0 : out_valid_q;

endmodule
