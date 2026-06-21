// ======================================================================
// Back-to-back FORMAL verification component for the ready/valid kit.
//
// This wires the kit's two PROTOCOL CORES -- rv_initiator_xtor_core and
// rv_target_xtor_core -- directly together over the ready/valid bus and lets
// SymbiYosys prove the connection. The cores are the kit's real RTL: they are
// clocked FSMs (synthesizable), so yosys can reason about them. (The
// transactor-INTERFACES use SV-queue FIFOs and are not synthesizable, so the
// formal harness drives/drains the cores' internal ready/valid LINK directly --
// exactly the link the transactor-interface would otherwise sit on.)
//
//   free src --up link--> [initiator core] --bus--> [target core] --up link--> free snk
//
// The producer feeding the initiator and the consumer draining the target are
// free formal inputs, so the solver explores every legal interleaving and every
// pattern of bus backpressure. Proven properties:
//   1. BUS CONTRACT  -- the initiator core (bus producer) holds valid and data
//      stable whenever the target stalls (the ready/valid handshake rule).
//   2. LINK CONTRACT -- the target core (up-link producer) likewise holds its
//      up_valid/up_data stable while the sink stalls.
//   3. DATA INTEGRITY -- every beat handed to the initiator leaves the target
//      exactly once, in order, unchanged (anyconst-index method): the back-to-
//      back pair is a lossless, in-order channel.
//
// Run:  dfm run rv.proto.formal.fv
// ======================================================================

module rv_proto_fv (
    input  wire        clock,
    input  wire        reset,
    // free producer feeding the initiator's internal ready/valid link
    input  wire        src_valid,
    input  wire [31:0] src_data,
    // free consumer draining the target's internal ready/valid link
    input  wire        snk_ready
);
    // initiator core: up-link CONSUMER (fed by src), bus PRODUCER
    wire        i_up_ready;
    wire [31:0] bus_data;
    wire        bus_valid;
    wire        bus_ready;

    rv_initiator_xtor_core u_init (
        .clock   (clock),
        .reset   (reset),
        .up_data (src_data),
        .up_valid(src_valid),
        .up_ready(i_up_ready),
        .data    (bus_data),
        .valid   (bus_valid),
        .ready   (bus_ready)
    );

    // target core: bus CONSUMER, up-link PRODUCER (drained by snk)
    wire [31:0] t_up_data;
    wire        t_up_valid;

    rv_target_xtor_core u_targ (
        .clock   (clock),
        .reset   (reset),
        .up_data (t_up_data),
        .up_valid(t_up_valid),
        .up_ready(snk_ready),
        .valid   (bus_valid),
        .ready   (bus_ready),
        .data    (bus_data)
    );

`ifdef FORMAL
    // Formal preamble: mask the first cycle and start in reset.
    reg f_past_valid = 1'b0;
    always @(posedge clock)
        f_past_valid <= 1'b1;
    always @(*)
        if (!f_past_valid)
            assume (reset);

    // Handshake events along the path.
    wire in_xfer  = src_valid  && i_up_ready;   // beat enters the initiator
    wire out_xfer = t_up_valid && snk_ready;    // beat leaves the target

    // ------------------------------------------------------------------
    // (1) BUS CONTRACT: initiator core holds valid + data stable while the
    //     target is not ready.
    // ------------------------------------------------------------------
    always @(posedge clock)
        if (f_past_valid && !$past(reset))
            if ($past(bus_valid) && !$past(bus_ready)) begin
                assert (bus_valid);
                assert (bus_data == $past(bus_data));
            end

    // ------------------------------------------------------------------
    // (2) LINK CONTRACT: target core holds up_valid + up_data stable while the
    //     sink is not ready.
    // ------------------------------------------------------------------
    always @(posedge clock)
        if (f_past_valid && !$past(reset))
            if ($past(t_up_valid) && !$past(snk_ready)) begin
                assert (t_up_valid);
                assert (t_up_data == $past(t_up_data));
            end

    // ------------------------------------------------------------------
    // (3) DATA INTEGRITY end to end, via an arbitrary tracked beat position.
    //     Capture the data of the f_idx-th beat that enters the initiator, then
    //     require the f_idx-th beat leaving the target to match it -- proving no
    //     loss, no duplication, in order, no corruption.
    // ------------------------------------------------------------------
    localparam int CW = 5;                  // counter width (no wrap within depth)

    (* anyconst *) reg [CW-1:0] f_idx;
    reg [CW-1:0] in_cnt, out_cnt;
    reg [31:0]   f_data;
    reg          f_have;

    always @(posedge clock)
        if (reset) begin
            in_cnt  <= '0;
            out_cnt <= '0;
            f_have  <= 1'b0;
        end else begin
            if (in_xfer) begin
                if (in_cnt == f_idx) begin
                    f_data <= src_data;
                    f_have <= 1'b1;
                end
                in_cnt <= in_cnt + 1'b1;
            end
            if (out_xfer)
                out_cnt <= out_cnt + 1'b1;
        end

    always @(posedge clock)
        if (!reset)
            if (out_xfer && (out_cnt == f_idx)) begin
                assert (f_have);                 // it must have entered first
                assert (t_up_data == f_data);    // ... and be unchanged
            end

    // Cover (checked in 'cover' mode): a tracked beat can traverse the pair end
    // to end -- guards against a vacuously-passing proof.
    always @(posedge clock)
        cover (!reset && out_xfer && (out_cnt == f_idx) && f_have);
`endif
endmodule
