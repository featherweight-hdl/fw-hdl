// Initiator transactor: the interface and the core joined by the internal
// ready/valid link. Pins: data, valid (out), ready (in).
module fw_rv_initiator_xtor #(type T = logic [31:0]) (
    input         clock,
    input         reset,
    output T      data,
    output bit    valid,
    input         ready
);
    T   up_data;
    bit up_valid;
    bit up_ready;

    fw_rv_initiator_xtor_if #(.T(T)) u_if (
        .clock(clock), .reset(reset),
        .up_data(up_data), .up_valid(up_valid), .up_ready(up_ready)
    );
    fw_rv_initiator_xtor_core #(.W($bits(T))) u_core (
        .clock(clock), .reset(reset),
        .up_data(up_data), .up_valid(up_valid), .up_ready(up_ready),
        .data(data), .valid(valid), .ready(ready)
    );
endmodule
