// Target core: a clocked protocol FSM. protocol CONSUMER on the pins, ready/valid
// PRODUCER on the internal link. It accepts a bus beat (valid && ready) into a
// 1-deep buffer, presents it on the link, and waits for the link handshake
// (up_valid && up_ready) before accepting the next bus beat.
module rv_target_xtor_core (
    input             clock,
    input             reset,
    output bit [31:0] up_data,             // ready/valid link (to xtor_if)
    output bit        up_valid,
    input             up_ready,
    input             valid,               // ready/valid bus pins
    output bit        ready,
    input  [31:0]     data
);
    typedef enum bit [0:0] {ACCEPT, PRESENT} state_t;
    state_t st;
    always @(posedge clock) begin
        if (reset) begin
            st <= ACCEPT; ready <= 1'b1; up_valid <= 1'b0; up_data <= '0;
        end else case (st)
            ACCEPT:  if (valid && ready) begin        // bus transfer happened
                         up_data <= data; up_valid <= 1'b1; ready <= 1'b0;
                         st <= PRESENT;
                     end
            PRESENT: if (up_valid && up_ready) begin  // link transfer happened
                         up_valid <= 1'b0; ready <= 1'b1; st <= ACCEPT;
                     end
            default: ;
        endcase
    end
endmodule
