// F7 (b), the stall controller (K = @K@, 2-bit payload) over free in_valid,
// in_data and out_ready:
//   - order, no loss, no duplication, content: for any index j (anyconst),
//     the j-th beat out is f of the j-th beat in;
//   - occupancy: beats in minus beats out is 0..K;
//   - no throughput lost while the sink is ready: out.ready -> in.ready;
//   - out protocol: a stalled beat stays (valid held, data stable).
// The input protocol is assumed (a stalled input beat stays).
module fv_top(input clk, input in_valid, input [@WI@-1:0] in_data, input out_ready);
    reg init = 1'b1;
    always @(posedge clk) init <= 1'b0;
    wire in_ready, out_valid;
    wire [@WM@-1:0] out_data, fx;
    (* anyconst *) reg [3:0] j;
    reg [3:0] cin = 4'd0, cout = 4'd0;
    reg got = 1'b0;
    reg [@WI@-1:0] xq;
    always @(posedge clk) if (!init) begin
        if (in_valid && in_ready) begin
            if (cin == j) begin
                xq  <= in_data;
                got <= 1'b1;
            end
            cin <= cin + 4'd1;
        end
        if (out_valid && out_ready) cout <= cout + 4'd1;
    end
    fv_wrap w (.clk(clk), .rst(init), .in_valid(in_valid), .in_ready(in_ready),
               .in_data(in_data), .out_valid(out_valid), .out_ready(out_ready),
               .out_data(out_data), .r_in(xq), .r_out(fx));
    reg i_stalled = 1'b0, o_stalled = 1'b0;
    reg [@WI@-1:0] i_d;
    reg [@WM@-1:0] o_d;
    always @(posedge clk) begin
        i_stalled <= !init && in_valid && !in_ready;
        i_d       <= in_data;
        o_stalled <= !init && out_valid && !out_ready;
        o_d       <= out_data;
    end
    wire [3:0] occ = cin - cout;
    always @* if (!init) begin
        if (i_stalled) assume (in_valid && in_data == i_d);
        assert (occ <= @K@);
        if (out_valid && out_ready && cout == j) assert (got && out_data == fx);
        if (out_ready) assert (in_ready);
        if (o_stalled) assert (out_valid && out_data == o_d);
    end
endmodule
