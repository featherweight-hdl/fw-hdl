// Pin bridge, class tree to pins: a class producer end driving a pin-level
// ready/valid consumer (valid, data out; ready in). The tree joins it by
// name in connect(): fw_rv_pin #(T)::find(NAME).connect_out(c.out).
// See fw_rv_pin for when values cross. Wakes on its input pin and on every
// holder write, settle and edge (fw_sig_holder::gen), and drives valid and
// data nonblocking from the tree's current values.
module fw_rv_pin_out #(
    parameter type   T    = bit,
    parameter string NAME = ""
) (
    output logic valid,
    output T     data,
    input  logic ready
);
    import fw_hdl_pkg::*;

    fw_rv_pin #(T) pin = new(NAME, 0);
    logic valid_r = 0;
    T     data_r = '0;

    assign valid = valid_r;
    assign data  = data_r;

    always @(ready or fw_sig_holder::gen) begin
        pin.put_bwd(ready);
        valid_r <= pin.get_valid();
        data_r  <= pin.get_data();
    end
endmodule
