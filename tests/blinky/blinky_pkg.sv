// Blinky example -- class layer. A blinking-LED model built on the std `put`
// protocol: a behavioral, top-level runnable component writes a 1-bit value,
// waits, and flips it. The put API (fw_put_if) and signal bridge
// (fw_put_xtor_bridge) come from fw_std_pkg; fw_hdl_pkg supplies fw_component /
// fw_port and the clock-domain tick() used to time the blink.
package blinky_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;

    typedef logic           led_t;        // the 1-bit LED
    localparam int unsigned BLINK_TICKS = 100;   // ticks the LED is held each phase

    `include "blinky.svh"      // top-level runnable LED driver (consumes fw_put_if)

endpackage
