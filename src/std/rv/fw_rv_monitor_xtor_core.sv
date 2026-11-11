// Monitor core: watches the pins (all inputs, nothing driven) and pushes one
// link beat for each cycle in which something happened on them:
//   up_first  the first cycle of valid for a transfer (an initiator's "pre")
//   up_xfer   the transfer completed (valid && ready)
// Both are set when a transfer completes in its first cycle. up_data is the
// pin data in that cycle. A 1-deep buffer: an event in a cycle in which the
// previous one has not yet been taken is dropped (the interface's FIFO is
// always ready while it has room, so this needs a full FIFO).
// Synthesizable, and so sized by a width W: yosys's SV front end has no
// `type` parameters. The transactor module passes W = $bits(T).
module fw_rv_monitor_xtor_core #(parameter int W = 32) (
    input                clock,
    input                reset,
    output logic [W-1:0] up_data,
    output bit           up_valid,
    output bit           up_first,
    output bit           up_xfer,
    input                up_ready,
    input                valid,
    input                ready,
    input  logic [W-1:0] data
);
    // Held low while reset is high, from the first reset cycle (the register is
    // only cleared at the first reset edge); e.g. AXI A3.1.2 requires it.
    bit up_valid_q;
    assign up_valid = up_valid_q & !reset;
    bit pending;    // valid seen and not yet accepted: the next valid cycle is not a first
    always @(posedge clock) begin
        if (reset) begin
            pending <= 1'b0; up_valid_q <= 1'b0; up_data <= '0;
            up_first <= 1'b0; up_xfer <= 1'b0;
        end else begin
            if (up_valid_q && up_ready)
                up_valid_q <= 1'b0;
            if (valid) begin
                if ((!pending || ready) && !(up_valid_q && !up_ready)) begin
                    up_valid_q <= 1'b1;
                    up_data  <= data;
                    up_first <= !pending;
                    up_xfer  <= ready;
                end
                pending <= !ready;
            end
        end
    end
endmodule
