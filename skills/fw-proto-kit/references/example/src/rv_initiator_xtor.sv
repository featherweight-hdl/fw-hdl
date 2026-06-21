// Initiator transactor module: instances the transactor-interface + core and
// wires them with the plain ready/valid link nets, exposing clock/reset + the
// ready/valid bus pins. Reach `u_if` from a testbench to bind the bridge's
// virtual interface.
module rv_initiator_xtor (
    input             clock,
    input             reset,
    output bit [31:0] data,
    output bit        valid,
    input         ready
);
    bit [31:0] up_data;
    bit        up_valid;
    bit        up_ready;

    rv_initiator_xtor_if u_if (
        .clock(clock), .reset(reset),
        .up_data(up_data), .up_valid(up_valid), .up_ready(up_ready)
    );
    rv_initiator_xtor_core u_core (
        .clock(clock), .reset(reset),
        .up_data(up_data), .up_valid(up_valid), .up_ready(up_ready),
        .data(data), .valid(valid), .ready(ready)
    );
endmodule
