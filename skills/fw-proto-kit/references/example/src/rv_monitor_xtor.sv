// Monitor transactor module: core + interface wired by the plain ready/valid
// link. Taps the bus (valid/ready/data inputs) and drives nothing on it. Reach
// `u_if` from a testbench to bind the bridge's virtual interface.
module rv_monitor_xtor (
    input             clock,
    input             reset,
    input         valid,
    input         ready,
    input  [31:0] data
);
    bit [31:0] up_data;
    bit        up_valid;
    bit        up_ready;

    rv_monitor_xtor_if u_if (
        .clock(clock), .reset(reset),
        .up_data(up_data), .up_valid(up_valid), .up_ready(up_ready)
    );
    rv_monitor_xtor_core u_core (
        .clock(clock), .reset(reset),
        .up_data(up_data), .up_valid(up_valid), .up_ready(up_ready),
        .valid(valid), .ready(ready), .data(data)
    );
endmodule
