// Target core: consumer on the pins, producer on the internal link. It takes
// one pin beat into a 1-deep buffer, presents it on the link and waits for the
// link handshake before taking the next. Synthesizable,
// and so sized by a width W: yosys's SV front end has no `type` parameters.
// The transactor module passes W = $bits(T).
module fw_rv_target_xtor_core #(parameter int W = 32) (
    input                clock,
    input                reset,
    output logic [W-1:0] up_data,
    output bit           up_valid,
    input                up_ready,
    input                valid,
    output bit           ready,
    input  logic [W-1:0] data
);
    typedef enum bit [0:0] {ACCEPT, PRESENT} state_t;
    state_t st;
    always @(posedge clock) begin
        if (reset) begin
            st <= ACCEPT; ready <= 1'b1; up_valid <= 1'b0; up_data <= '0;
        end else case (st)
            ACCEPT:  if (valid && ready) begin
                         up_data <= data; up_valid <= 1'b1; ready <= 1'b0;
                         st <= PRESENT;
                     end
            PRESENT: if (up_valid && up_ready) begin
                         up_valid <= 1'b0; ready <= 1'b1; st <= ACCEPT;
                     end
            default: ;
        endcase
    end
endmodule
