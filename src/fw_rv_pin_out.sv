// Pin bridge, class tree to pins: a class producer end driving a pin-level
// ready/valid consumer (valid, data out; ready in). The tree joins it by
// name in connect(): fw_rv_pin #(T)::find(NAME).connect_out(c.out).
// See fw_rv_pin for when values cross. Wakes on its input pin and on every
// holder write, settle and edge (fw_sig_holder::gen).
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
    logic valid_c = 0, valid_s = 0, valid_comb = 0;
    T     data_c = '0, data_s = '0;
    logic data_comb = 0;

    assign valid = valid_comb ? valid_c : valid_s;
    assign data  = data_comb  ? data_c  : data_s;

    always @(ready or fw_sig_holder::gen) begin
        pin.put_bwd(ready);
        valid_comb = pin.comb("valid");
        data_comb  = pin.comb("data");
        valid_c    = pin.get_valid();
        data_c     = pin.get_data();
        valid_s   <= pin.get_valid();
        data_s    <= pin.get_data();
    end
endmodule
