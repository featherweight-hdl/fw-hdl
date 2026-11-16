// Hand-written reference RTL for the rr_merge example (LOWERING.md L1, L9e).
// It describes what the classes describe (src/rr_arbiter.svh, src/rr_fifo.svh,
// src/rr_merge.svh), written as ordinary RTL:
//   - the classes' parameters (type T, N, DEPTH) and interface: clock, reset
//     (active high, synchronous), one port per ready/valid field, a port array
//     as a packed array per field (in_valid[N], in_data[N] of T);
//   - the classes' state, by name and width (ptr, locked, owner; mem, wr, rd,
//     count, and the FIFO's registered out_valid/out_data);
//   - the classes' update rules: comb() as continuous logic, step() as one
//     always_ff, with values that step() reads after writing them (the FIFO's
//     rd and count, the head after a push) computed as next-state wires.
// T is a packed struct with a `last` member (rr_merge_ref_pkg::rr_beat_t by
// default, {data[7:0], last}).

// Several modules and a package in one file, on purpose.
/* verilator lint_off DECLFILENAME */

package rr_merge_ref_pkg;
    typedef struct packed {
        logic [7:0] data;
        logic       last;
    } rr_beat_t;
endpackage

// Round-robin arbiter and mux with packet lock (rr_arbiter #(T, N)).
// The grant is the owner while locked, else the first valid input from ptr
// on, else ptr. A beat taken locks the grant until its `last`, which moves
// ptr past the granted input.
module rr_arbiter_ref #(
    parameter type T = rr_merge_ref_pkg::rr_beat_t,
    parameter int  N = 4
) (
    input  logic         clock,
    input  logic         reset,
    input  logic [N-1:0] in_valid,
    output logic [N-1:0] in_ready,
    input  T     [N-1:0] in_data,
    output logic         out_valid,
    input  logic         out_ready,
    output T             out_data
);
    typedef logic [$clog2(N)-1:0] idx_t;

    idx_t ptr;      // first input to look at when not locked
    logic locked;   // mid-packet: the grant stays on owner
    idx_t owner;

    // grant(): the scan from ptr, first valid wins.
    idx_t grant;
    always_comb begin
        logic found;
        idx_t i;
        grant = ptr;
        found = locked;
        if (locked) grant = owner;
        for (int k = 0; k < N; k++) begin
            i = idx_t'((ptr + k) % N);
            if (!found && in_valid[i]) begin
                grant = i;
                found = 1'b1;
            end
        end
    end

    // comb()
    assign out_valid = in_valid[grant];
    assign out_data  = in_data[grant];
    always_comb
        for (int i = 0; i < N; i++) in_ready[i] = (idx_t'(i) == grant) && out_ready;

    // step()
    always_ff @(posedge clock) begin
        if (reset) begin
            ptr    <= '0;
            locked <= 1'b0;
            owner  <= '0;
        end else if (out_valid && out_ready) begin
            locked <= !out_data.last;
            owner  <= grant;
            if (out_data.last) ptr <= idx_t'((grant + 1) % N);
        end
    end
endmodule

// DEPTH-entry FIFO with a registered output (rr_fifo #(T, DEPTH)).
// count holds the entries, the head (out_data) included. step() pushes into
// mem[wr], pops by advancing rd, updates count, then shows the new head:
// out_valid = count' != 0 and, if so, out_data = mem'[rd'], which is in_data
// when this edge's push lands on rd'.
module rr_fifo_ref #(
    parameter type T     = rr_merge_ref_pkg::rr_beat_t,
    parameter int  DEPTH = 2
) (
    input  logic clock,
    input  logic reset,
    input  logic in_valid,
    output logic in_ready,
    input  T     in_data,
    output logic out_valid,
    input  logic out_ready,
    output T     out_data
);
    typedef logic [$clog2(DEPTH)-1:0]   ptr_t;
    typedef logic [$clog2(DEPTH+1)-1:0] count_t;

    T       mem [DEPTH];
    ptr_t   wr, rd;
    count_t count;
    logic   out_valid_q;

    // out.valid is reset-forced to 0 (the holder's set_force(0)).
    assign out_valid = reset ? 1'b0 : out_valid_q;

    // comb()
    assign in_ready = count < count_t'(DEPTH) || out_ready;

    // step()
    wire    push     = in_valid && in_ready;
    wire    pop      = out_valid_q && out_ready;
    ptr_t   rd_next;
    count_t count_next;
    assign rd_next    = pop ? ptr_t'((rd + 1) % DEPTH) : rd;
    assign count_next = count + push - pop;

    always_ff @(posedge clock) begin
        if (reset) begin
            wr          <= '0;
            rd          <= '0;
            count       <= '0;
            out_valid_q <= 1'b0;
        end else begin
            if (push) begin
                mem[wr] <= in_data;
                wr      <= ptr_t'((wr + 1) % DEPTH);
            end
            rd          <= rd_next;
            count       <= count_next;
            out_valid_q <= count_next != 0;
            if (count_next != 0)
                out_data <= (push && wr == rd_next) ? in_data : mem[rd_next];
        end
    end
endmodule

// The merger: in[N] -> rr_arbiter_ref -> rr_fifo_ref -> out (rr_merge #(T, N, DEPTH)).
module rr_merge_ref #(
    parameter type T     = rr_merge_ref_pkg::rr_beat_t,
    parameter int  N     = 4,
    parameter int  DEPTH = 2
) (
    input  logic         clock,
    input  logic         reset,
    input  logic [N-1:0] in_valid,
    output logic [N-1:0] in_ready,
    input  T     [N-1:0] in_data,
    output logic         out_valid,
    input  logic         out_ready,
    output T             out_data
);
    logic arb_out_valid, arb_out_ready;
    T     arb_out_data;

    rr_arbiter_ref #(.T(T), .N(N)) arb (
        .clock(clock), .reset(reset),
        .in_valid(in_valid), .in_ready(in_ready), .in_data(in_data),
        .out_valid(arb_out_valid), .out_ready(arb_out_ready), .out_data(arb_out_data));

    rr_fifo_ref #(.T(T), .DEPTH(DEPTH)) fifo (
        .clock(clock), .reset(reset),
        .in_valid(arb_out_valid), .in_ready(arb_out_ready), .in_data(arb_out_data),
        .out_valid(out_valid), .out_ready(out_ready), .out_data(out_data));
endmodule
