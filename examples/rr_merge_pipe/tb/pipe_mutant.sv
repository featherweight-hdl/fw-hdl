// A stream between the DUT's out and pipe_bench that breaks it on purpose,
// once, at about the K-th beat (+mutant=<mode>, +mutant_at=<K>, default 100),
// to show that each bench check fires. Mode 0 passes through.
//   1  f wrong:   the beat's y is off by one          -> content check
//   2  drop:      the beat is taken from the DUT and not passed on -> order/loss
//   3  reorder:   a non-last beat is held back and passed on after the next
//                 beat of its packet                  -> order check
//   4  protocol:  data changes while out is stalled   -> protocol monitor
module pipe_mutant #(parameter type TM = pipe_types_pkg::pipe_mid8_t) (
    input  logic clk,
    input  logic d_valid, output logic d_ready, input  TM d_data,
    output logic b_valid, input  logic b_ready, output TM b_data
);
    int unsigned mode, at, n;
    int unsigned st;      // mode 3: 0 waiting, 1 holding, 2 emitting, 3 done
    bit          stall_q, flipped;
    TM           held;
    initial begin
        if (!$value$plusargs("mutant=%d", mode)) mode = 0;
        if (!$value$plusargs("mutant_at=%d", at)) at = 100;
    end
    always_comb begin
        b_valid = d_valid;
        b_data  = d_data;
        d_ready = b_ready;
        case (mode)
            1: if (n == at) b_data.y = d_data.y + 1;
            2: if (n == at) begin
                b_valid = 0;
                d_ready = 1;
            end
            3: if (st == 0 && n >= at && d_valid && !d_data.last) begin
                b_valid = 0;
                d_ready = 1;
            end else if (st == 2) begin
                b_valid = 1;
                b_data  = held;
                d_ready = 0;
            end
            4: if (n >= at && stall_q && !flipped) b_data.y = d_data.y ^ 1;
            default: ;
        endcase
    end
    always @(posedge clk) begin
        if (d_valid && d_ready) n++;
        if (mode == 3) begin
            if (st == 0 && n >= at && d_valid && !d_data.last) begin
                held = d_data;
                st   = 1;
            end else if (st == 1 && b_valid && b_ready) st = 2;
            else if (st == 2 && b_valid && b_ready) st = 3;
        end
        if (mode == 4 && n >= at && stall_q) flipped = 1;
        stall_q = b_valid && !b_ready;
    end
endmodule
