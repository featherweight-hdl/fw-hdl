// An fw_channel #(T, DEPTH) bound to a RAM (knob `storage: {bind: sram}`):
// the same handshake as fw_rv_fifo, cycle for cycle, with most of the
// values held in a two-port RAM (one write and one 1-cycle read per cycle)
// outside this module, on the ram_* ports. Integrate instantiates the RAM
// named by the knob's `macro:` beside it (fw_ram_1r1w_model in sim).
//
// Why the timing is fw_rv_fifo's: in_rdy and out_vld come from the same
// count, and the head is always in a two-entry output stage in flops, so
// out_data never waits on a RAM read. Values enter the output stage
// directly while the RAM is empty and the stage has room; otherwise they go
// to the RAM, and a read is issued whenever the stage has room for its data
// (counting the read in flight), which keeps the stage fed at one value per
// cycle. Order: output stage, then the read in flight, then the RAM.
//
// The RAM has DEPTH - 1 words. The head is never in it, so it holds at most
// DEPTH - 1 values, and a write never meets the read in the same word.
// DEPTH must be at least 3; below that flops are smaller anyway.
module fw_sram_fifo #(
    parameter int WIDTH = 8,
    parameter int DEPTH = 3,
    // Derived: the RAM's words and address width. Not set by the user.
    parameter int RAM_WORDS = DEPTH - 1,
    parameter int RAM_AW = (RAM_WORDS > 1) ? $clog2(RAM_WORDS) : 1
) (
    input  logic              clk,
    input  logic              rst,
    input  logic [WIDTH-1:0]  in_data,
    input  logic              in_vld,
    output logic              in_rdy,
    output logic [WIDTH-1:0]  out_data,
    output logic              out_vld,
    input  logic              out_rdy,
    // to the RAM
    output logic [RAM_AW-1:0] ram_wa,
    output logic              ram_we,
    output logic [WIDTH-1:0]  ram_wd,
    output logic [RAM_AW-1:0] ram_ra,
    output logic              ram_re,
    input  logic [WIDTH-1:0]  ram_rd
);
    if (DEPTH < 3) begin : g_bad_depth
        $error("fw_sram_fifo: DEPTH must be at least 3 (bind smaller channels to flops)");
    end

    localparam int AW = $clog2(DEPTH);

    logic [AW:0]        count;      // values held, as fw_rv_fifo counts them
    logic [WIDTH-1:0]   ob0, ob1;   // output stage; ob0 is the head
    logic [1:0]         oc;         // values in the output stage
    logic               fl;         // a RAM read in flight: ram_rd is valid now
    logic [RAM_AW-1:0]  rp, wp;     // RAM read and write words
    logic [RAM_AW:0]    rc;         // values in the RAM

    wire push = in_vld && in_rdy;
    wire pop  = out_vld && out_rdy;

    // What the output stage holds at the end of this cycle before anything
    // new is put in it: what it held, less a pop, plus the read in flight.
    wire [1:0] kept  = oc - {1'b0, pop};
    wire [1:0] fed   = kept + {1'b0, fl};
    wire       room  = (fed <= 2'd1);
    wire       issue = (rc != '0) && room;      // read the next RAM value
    wire       direct = push && (rc == '0) && room;
    wire       to_ram = push && !direct;

    wire [AW:0] inc = {{AW{1'b0}}, push};
    wire [AW:0] dec = {{AW{1'b0}}, pop};
    wire [RAM_AW:0] rinc = {{RAM_AW{1'b0}}, to_ram};
    wire [RAM_AW:0] rdec = {{RAM_AW{1'b0}}, issue};

    assign in_rdy   = (count != DEPTH[AW:0]);
    assign out_vld  = (count != '0);
    assign out_data = ob0;

    assign ram_we = to_ram;
    assign ram_wa = wp;
    assign ram_wd = in_data;
    assign ram_re = issue;
    assign ram_ra = rp;

    function automatic logic [RAM_AW-1:0] next(logic [RAM_AW-1:0] p);
        if (p == RAM_WORDS - 1)
            next = '0;
        else
            next = p + 1'b1;
    endfunction

    // The output stage after this cycle: shift out a pop, then append the
    // read in flight, then a direct push, in that order.
    logic [WIDTH-1:0] n0, n1;
    always_comb begin
        n0 = pop ? ob1 : ob0;
        n1 = ob1;
        if (fl) begin
            if (kept == 2'd0) n0 = ram_rd;
            else              n1 = ram_rd;
        end
        if (direct) begin
            if (fed == 2'd0) n0 = in_data;
            else             n1 = in_data;
        end
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            count <= '0;
            oc    <= '0;
            fl    <= 1'b0;
            rp    <= '0;
            wp    <= '0;
            rc    <= '0;
        end else begin
            count <= count + inc - dec;
            oc    <= fed + {1'b0, direct};
            fl    <= issue;
            rc    <= rc + rinc - rdec;
            if (to_ram)
                wp <= next(wp);
            if (issue)
                rp <= next(rp);
        end
        ob0 <= n0;
        ob1 <= n1;
    end
endmodule
