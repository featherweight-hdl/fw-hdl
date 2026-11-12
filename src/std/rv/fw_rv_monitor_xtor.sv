// Monitor transactor: the core and the interface joined by the internal
// ready/valid link. Pins: valid, ready, data, all inputs.
module fw_rv_monitor_xtor #(type T = logic [31:0]) (
    input         clock,
    input         reset,
    input         valid,
    input         ready,
    input  T      data
);
    T   up_data;
    bit up_valid;
    bit up_first;
    bit up_xfer;
    bit up_ready;

    fw_rv_monitor_xtor_if #(.T(T)) u_if (
        .clock(clock), .reset(reset),
        .up_data(up_data), .up_valid(up_valid), .up_first(up_first), .up_xfer(up_xfer),
        .up_ready(up_ready)
    );
    fw_rv_monitor_xtor_core #(.W($bits(T))) u_core (
        .clock(clock), .reset(reset),
        .up_data(up_data), .up_valid(up_valid), .up_first(up_first), .up_xfer(up_xfer),
        .up_ready(up_ready),
        .valid(valid), .ready(ready), .data(data)
    );
endmodule
