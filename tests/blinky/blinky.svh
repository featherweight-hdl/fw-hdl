// Blinking-LED model: a top-level runnable component that drives a put port. Its
// run loop writes the current LED value out the interface, holds it for a large
// number of clock ticks (via this component's clock domain), then flips the
// value. It is unaware that `out` reaches a real pin: blinky_top binds the port
// to an fw_put_xtor_bridge over an fw_put_xtor_if, so each put() registers the
// value onto the LED output with no handshake, and tick() advances the seated
// (root) clock domain.
//
// This component is itself the fw_root tree's root AND a runnable -- fw_root's
// lifecycle orchestrator (fw_component_root::start()) is separate from run(), so
// the root's own run() is forked like any other runnable.
class blinky extends fw_component implements fw_runnable;
    fw_port #(fw_put_if #(led_t)) out;

    function new(string name, fw_component parent);
        super.new(name, parent);
        add_runnable(this);          // opt in to a run() process
    endfunction

    function void build();
        out = new("out", this);
    endfunction

    virtual task run();
        led_t v = 1'b0;
        forever begin
            out.t.put(v);            // out.t resolved at connect; call the API
            tick(BLINK_TICKS);       // hold it for a large number of ticks
            v = ~v;                  // flip
        end
    endtask
endclass
