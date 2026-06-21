`ifndef INCLUDED_RV_MONITOR_BRIDGE_SVH
`define INCLUDED_RV_MONITOR_BRIDGE_SVH

// Monitor bridge -- a CONSUMER like the target. Extends fw_port #(rv_monitor_if)
// and runs an active loop: it BLOCKS on vif.get(t) (the transactor-interface's
// blocking method) and then fans the beat out via the NON-BLOCKING monitor API
// observe(). Connect this port to the subscriber that implements rv_monitor_if.
class rv_monitor_bridge #(type T = logic [31:0]) extends fw_port #(rv_monitor_if #(T));
    virtual rv_monitor_xtor_if vif;

    function new(string name, fw_component parent,
                 virtual rv_monitor_xtor_if vif);
        super.new(name, parent);
        this.vif = vif;
    endfunction

    task run();
        rv_monitor_if #(T) api = get_if();
        forever begin
            automatic T t;
            vif.get(t);            // blocking: next observed beat
            api.observe(t);        // non-blocking: publish to subscriber
        end
    endtask
endclass

`endif /* INCLUDED_RV_MONITOR_BRIDGE_SVH */
