// Pin bridge, pins to class tree: a pin-level ready/valid producer (valid,
// data in; ready out) feeding a class consumer end. The tree joins it by
// name in connect(): fw_rv_pin #(T)::find(NAME).connect_in(c.in).
// See fw_rv_pin for when values cross. Wakes on its input pins and on every
// holder write, settle and edge (fw_sig_holder::gen), and drives ready
// nonblocking from the tree's current value.
module fw_rv_pin_in #(
    parameter type   T    = bit,
    parameter string NAME = ""
) (
    input  logic valid,
    input  T     data,
    output logic ready
);
    import fw_hdl_pkg::*;

    fw_rv_pin #(T) pin = new(NAME, 1);
    logic ready_r = 0;

    assign ready = ready_r;

    always @(valid or data or fw_sig_holder::gen) begin
        pin.put_fwd(valid, data);
        ready_r <= pin.get_ready();
    end
endmodule
