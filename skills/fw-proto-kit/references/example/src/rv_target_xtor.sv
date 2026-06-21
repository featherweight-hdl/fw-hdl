// Target transactor module: instances the core + transactor-interface and wires
// them with the plain ready/valid link nets, exposing clock/reset + the
// ready/valid bus pins. Reach `u_if` from a testbench to bind the bridge's
// virtual interface.
module rv_target_xtor (
    input             clock,
    input             reset,
    input         valid,
    output bit        ready,
    input  [31:0] data
);
    bit [31:0] up_data;
    bit        up_valid;
    bit        up_ready;

    rv_target_xtor_if u_if (
        .clock(clock), .reset(reset),
        .up_data(up_data), .up_valid(up_valid), .up_ready(up_ready)
    );
    rv_target_xtor_core u_core (
        .clock(clock), .reset(reset),
        .up_data(up_data), .up_valid(up_valid), .up_ready(up_ready),
        .valid(valid), .ready(ready), .data(data)
    );
endmodule
