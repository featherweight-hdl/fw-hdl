// Initiator core: a clocked protocol FSM. ready/valid CONSUMER on the internal
// link, protocol PRODUCER on the pins. It accepts a beat (up_valid && up_ready),
// drives it onto the bus, and waits for the bus handshake (valid && ready) before
// accepting the next. For ready/valid the pins ARE ready/valid, so this is a
// 1-deep skid; a richer protocol (e.g. wishbone) elaborates a larger pin-level
// FSM here while the internal ready/valid link contract is unchanged.
module rv_initiator_xtor_core (
    input             clock,
    input             reset,
    input      [31:0] up_data,             // ready/valid link (from xtor_if)
    input             up_valid,
    output bit        up_ready,
    output bit [31:0] data,                // ready/valid bus pins
    output bit        valid,
    input             ready
);
    typedef enum bit [0:0] {ACCEPT, DRIVE} state_t;
    state_t st;
    always @(posedge clock) begin
        if (reset) begin
            st <= ACCEPT; up_ready <= 1'b1; valid <= 1'b0; data <= '0;
        end else case (st)
            ACCEPT: if (up_valid && up_ready) begin  // link transfer happened
                        data <= up_data; valid <= 1'b1; up_ready <= 1'b0;
                        st <= DRIVE;
                    end
            DRIVE:  if (valid && ready) begin         // bus transfer happened
                        valid <= 1'b0; up_ready <= 1'b1; st <= ACCEPT;
                    end
            default: ;
        endcase
    end
endmodule
