// Blinky DESIGN TOP: the module-level wrapper that connects the pure class tree
// to signal-level pins -- the standard top-level module of an fw-hdl design. It
// exposes clock/reset and the LED output, instances the put transactor interface
// on the LED pin, and uses the `fw_root macros to make `blinky` the elaboration
// root and bind its put port to the transactor bridge. blinky_tb (the
// verification top) instances this and checks the LED.
`include "fw_hdl_macros.svh"

module blinky_top(
    input        clock,
    input        reset,
    output logic led
);
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;
    import blinky_pkg::*;

    // The put transactor interface: blinky's put() registers each value onto led.
    fw_put_xtor_if #(led_t) u_led (.clock(clock), .reset(reset), .out(led));

    // blinky is BOTH the fw_root tree's root and a runnable; bind its put port to
    // the LED bridge over u_led.
    `fw_root_begin(blinky, u_root, clock, reset)
        `fw_root_bind_port(out, u_led, fw_put_xtor_bridge #(led_t))
    `fw_root_end
endmodule
