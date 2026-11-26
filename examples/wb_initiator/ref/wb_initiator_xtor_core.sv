// Vendored from fw-proto-wb (src/wb_initiator_xtor_core.sv, the working tree on 2026-11-21: commit 0e535ea plus
// uncommitted edits, the two-state core). The reference that the lowered wb_init_core is
// checked equivalent to (scripts/equiv.sh). Not used by the class model.
// Initiator core: a clocked Wishbone MASTER, reduced to TWO states -- "not waiting
// for a termination" and "waiting" (`waiting`, which is exactly stb_o asserted).
// Per the classic single/block cycle it asserts CYC/STB and holds the qualified
// signals stable (RULE 3.60) until ACK|ERR|RTY.
//
// The response is delivered COMBINATIONALLY on the termination cycle (rsp_valid =
// waiting && term), and the phase is HELD (stb stays asserted) until that response
// is actually consumed (rsp_ready). That couples phase-end to response-consumption,
// so no response can ever be dropped and no response register / WB_RESP bubble is
// needed. Phases stay classic STB-DELIMITED (a new request is accepted only while
// idle, so STB drops between phases and the bus is single-outstanding) -- the
// back-to-back formal proof's phase model holds unchanged. Still clocked +
// queue-free, so yosys can reason about it in that proof.
module wb_initiator_xtor_core
    import wb_types_pkg::*;
(
    input            clock,
    input            reset,
    // request link (from xtor_if): ready/valid CONSUMER
    input  wb_req_t  req_data,
    input            req_valid,
    output           req_ready,
    // response link (to xtor_if): ready/valid PRODUCER
    output wb_rsp_t  rsp_data,
    output           rsp_valid,
    input            rsp_ready,
    // Wishbone MASTER pins
    output bit [WB_AW-1:0] adr_o,
    output bit [WB_DW-1:0] dat_o,
    output bit [WB_SW-1:0] sel_o,
    output bit             we_o,
    output bit             cyc_o,
    output bit             stb_o,
    input      [WB_DW-1:0] dat_i,
    input                  ack_i,
    input                  err_i,
    input                  rty_i
);
    bit  waiting;                       // a bus phase is in progress (== stb_o)
    bit  hold;                          // cyc_hold of the in-flight phase
    wire term = ack_i || err_i || rty_i;

    // Response presented combinationally on the termination cycle; held (via stb)
    // until consumed, so the rsp-link contract holds with no response register.
    assign rsp_valid = waiting && term;
    assign rsp_data  = '{dat: dat_i, err: err_i, rty: rty_i};

    // Accept a new request only while idle (STB-delimited, single-outstanding).
    // Independent of req_valid, as a ready/valid producer requires.
    assign req_ready = !waiting;
    wire   phase_done = waiting && term && rsp_ready;  // response consumed this cycle
    wire   launch     = req_valid && req_ready;        // a new phase starts (from idle)

    always @(posedge clock) begin
        if (reset) begin
            waiting <= 1'b0;
            hold    <= 1'b0;
            adr_o   <= '0;
            dat_o   <= '0;
            sel_o   <= '0;
            we_o    <= 1'b0;
            cyc_o   <= 1'b0;            // RULE 3.20: CYC/STB negated under reset
            stb_o   <= 1'b0;
        end else if (launch) begin      // launch a phase from idle
            adr_o   <= req_data.adr;
            dat_o   <= req_data.dat;
            sel_o   <= req_data.sel;
            we_o    <= req_data.we;
            cyc_o   <= 1'b1;
            stb_o   <= 1'b1;
            hold    <= req_data.cyc_hold;
            waiting <= 1'b1;
        end else if (phase_done) begin  // response consumed, nothing else to start
            stb_o   <= 1'b0;
            cyc_o   <= hold;            // hold CYC for a block/RMW chain
            waiting <= 1'b0;
        end
        // else: waiting && !phase_done -- hold stb + the qualified signals stable
    end
endmodule
