// A hand-written three-input round-robin arbiter, standing in for a supplied
// reference module in the fw_arbiter cosim spec. Its interface differs from
// fw-hdl's lowering on purpose: other port names, an active-low reset, and a
// grant made over same-cycle valids (ready is the grant, the same cycle).
//
// LOCK = 1 keeps a grant while out is stalled. LOCK = 0 re-arbitrates every
// cycle, so a later arrival can change out while it is valid: the cosim spec
// runs it to show the protocol check catching that.
module ref_arb3 #(parameter int LOCK = 1) (
    input  logic       clk_i,
    input  logic       rst_ni,
    input  logic [7:0] req0_data, req1_data, req2_data,
    input  logic       req0_valid, req1_valid, req2_valid,
    output logic       req0_ready, req1_ready, req2_ready,
    output logic [9:0] gnt_data,
    output logic       gnt_valid,
    input  logic       gnt_ready
);
    logic [2:0] v, g, rot;
    logic [1:0] last, lk;
    logic       held;
    logic [7:0] d [3];

    assign v = {req2_valid, req1_valid, req0_valid};
    assign d[0] = req0_data;
    assign d[1] = req1_data;
    assign d[2] = req2_data;

    // Round robin from the input after the last one taken.
    always_comb begin
        g = '0;
        for (int k = 1; k <= 3; k++) begin
            int i;
            i = (int'(last) + k) % 3;
            if (g == '0 && v[i]) g[i] = 1'b1;
        end
        if (LOCK && held) g = 3'b1 << lk;
    end

    always_comb begin
        gnt_data = '0;
        for (int i = 0; i < 3; i++)
            if (g[i]) gnt_data = {2'(i), d[i]};
    end
    assign gnt_valid = |(g & v);
    assign {req2_ready, req1_ready, req0_ready} = g & {3{gnt_ready}};

    always_ff @(posedge clk_i) begin
        if (!rst_ni) begin
            last <= 2'd2;
            held <= 1'b0;
            lk <= '0;
        end else begin
            held <= gnt_valid && !gnt_ready;
            for (int i = 0; i < 3; i++)
                if (g[i]) begin
                    lk <= 2'(i);
                    if (gnt_ready && v[i]) last <= 2'(i);
                end
        end
    end
endmodule
