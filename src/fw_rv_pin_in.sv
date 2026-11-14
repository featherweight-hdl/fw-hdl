// Pin bridge, pins to class tree: a pin-level ready/valid producer (valid,
// data in; ready out) feeding a class consumer end. The tree joins it by
// name in connect(): fw_rv_pin #(T)::find(NAME).connect_in(c.in).
// See fw_rv_pin for when values cross. Wakes on its input pins and on every
// holder write, settle and edge (fw_sig_holder::gen).
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
    logic ready_c = 0, ready_s = 0, ready_comb = 0;

    assign ready = ready_comb ? ready_c : ready_s;

    always @(valid or data or fw_sig_holder::gen) begin
        pin.put_fwd(valid, data);
        ready_comb = pin.comb("ready");
        ready_c    = pin.get_ready();
        ready_s   <= pin.get_ready();
    end
endmodule
