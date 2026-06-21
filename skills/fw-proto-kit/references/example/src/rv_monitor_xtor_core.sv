// Monitor core: a clocked FSM. It WATCHES the bus (valid/ready/data are inputs --
// it drives nothing on the bus) and, on each observed transfer (valid && ready),
// pushes the beat onto the internal ready/valid link. 1-deep skid like the target
// core; a zero-drop monitor at full bus rate would need a deeper capture path.
module rv_monitor_xtor_core (
    input             clock,
    input             reset,
    output bit [31:0] up_data,             // ready/valid link (to xtor_if)
    output bit        up_valid,
    input             up_ready,
    input             valid,               // bus taps (observed, never driven)
    input             ready,
    input  [31:0]     data
);
    typedef enum bit [0:0] {WATCH, PRESENT} state_t;
    state_t st;
    always @(posedge clock) begin
        if (reset) begin
            st <= WATCH; up_valid <= 1'b0; up_data <= '0;
        end else case (st)
            WATCH:   if (valid && ready) begin        // observed a bus transfer
                         up_data <= data; up_valid <= 1'b1; st <= PRESENT;
                     end
            PRESENT: if (up_valid && up_ready) begin  // link transfer happened
                         up_valid <= 1'b0; st <= WATCH;
                     end
            default: ;
        endcase
    end
endmodule
