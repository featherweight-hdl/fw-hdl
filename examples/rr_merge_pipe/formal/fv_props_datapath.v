// F7 (a), datapath == f: with the sink always ready, the pipelined map's
// out.valid/out.data equal f (the comb map) on the input @SHIFT@ cycles
// earlier (@SHIFT@ = K; a wrong value for the mutant).
module fv_top(input clk, input in_valid, input [@WI@-1:0] in_data);
    localparam S = @SHIFT@;
    reg init = 1'b1;
    reg [3:0] age = 4'd0;
    always @(posedge clk) begin
        init <= 1'b0;
        if (age != 4'd15) age <= age + 4'd1;
    end
    wire in_ready, out_valid;
    wire [@WM@-1:0] out_data, r_out;
    reg  [S:0] dv;
    reg  [@WI@-1:0] dd [0:S];
    integer i;
    always @* begin
        dv[0] = in_valid && !init;
        dd[0] = in_data;
    end
    always @(posedge clk)
        for (i = 1; i <= S; i = i + 1) begin
            dv[i] <= init ? 1'b0 : dv[i-1];
            dd[i] <= dd[i-1];
        end
    fv_wrap w (.clk(clk), .rst(init), .in_valid(in_valid), .in_ready(in_ready),
               .in_data(in_data), .out_valid(out_valid), .out_ready(1'b1),
               .out_data(out_data), .r_in(dd[S]), .r_out(r_out));
    always @* if (age > S) begin
        assert (out_valid == dv[S]);
        if (dv[S]) assert (out_data == r_out);
    end
endmodule
