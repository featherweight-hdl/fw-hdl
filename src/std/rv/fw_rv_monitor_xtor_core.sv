// Monitor core: watches the pins (all inputs, nothing driven) and pushes each
// observed transfer (valid && ready) onto the internal link. A 1-deep buffer:
// a zero-drop monitor at full pin rate would need a deeper capture path.
// Synthesizable, and so sized by a width W: yosys's SV front end has no
// `type` parameters. The transactor module passes W = $bits(T).
module fw_rv_monitor_xtor_core #(parameter int W = 32) (
    input                clock,
    input                reset,
    output logic [W-1:0] up_data,
    output bit           up_valid,
    input                up_ready,
    input                valid,
    input                ready,
    input  logic [W-1:0] data
);
    typedef enum bit [0:0] {WATCH, PRESENT} state_t;
    state_t st;
    always @(posedge clock) begin
        if (reset) begin
            st <= WATCH; up_valid <= 1'b0; up_data <= '0;
        end else case (st)
            WATCH:   if (valid && ready) begin
                         up_data <= data; up_valid <= 1'b1; st <= PRESENT;
                     end
            PRESENT: if (up_valid && up_ready) begin
                         up_valid <= 1'b0; st <= WATCH;
                     end
            default: ;
        endcase
    end
endmodule
