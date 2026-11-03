// Initiator core: consumer on the internal link, producer on the pins. It takes
// one link beat, drives it on the pins and holds it until valid && ready, then
// takes the next. Synthesizable,
// and so sized by a width W: yosys's SV front end has no `type` parameters.
// The transactor module passes W = $bits(T).
module fw_rv_initiator_xtor_core #(parameter int W = 32) (
    input                clock,
    input                reset,
    input  logic [W-1:0] up_data,
    input                up_valid,
    output bit           up_ready,
    output logic [W-1:0] data,
    output bit           valid,
    input                ready
);
    typedef enum bit [0:0] {ACCEPT, DRIVE} state_t;
    state_t st;
    always @(posedge clock) begin
        if (reset) begin
            st <= ACCEPT; up_ready <= 1'b1; valid <= 1'b0; data <= '0;
        end else case (st)
            ACCEPT: if (up_valid && up_ready) begin
                        data <= up_data; valid <= 1'b1; up_ready <= 1'b0;
                        st <= DRIVE;
                    end
            DRIVE:  if (valid && ready) begin
                        valid <= 1'b0; up_ready <= 1'b1; st <= ACCEPT;
                    end
            default: ;
        endcase
    end
endmodule
