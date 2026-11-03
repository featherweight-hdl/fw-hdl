// Target transactor: the core and the interface joined by the internal
// ready/valid link. Pins: valid (in), ready (out), data (in).
module fw_rv_target_xtor #(type T = logic [31:0]) (
    input         clock,
    input         reset,
    input         valid,
    output bit    ready,
    input  T      data
);
    T   up_data;
    bit up_valid;
    bit up_ready;

    fw_rv_target_xtor_if #(.T(T)) u_if (
        .clock(clock), .reset(reset),
        .up_data(up_data), .up_valid(up_valid), .up_ready(up_ready)
    );
    fw_rv_target_xtor_core #(.W($bits(T))) u_core (
        .clock(clock), .reset(reset),
        .up_data(up_data), .up_valid(up_valid), .up_ready(up_ready),
        .valid(valid), .ready(ready), .data(data)
    );
endmodule
