// Monitor bridge: a consumer of the monitor API. Its run() blocks on the
// fw_rv_monitor_xtor_if for each observed beat and fans it out through the
// non-blocking observe().
class fw_rv_monitor_bridge #(type T) extends fw_port #(fw_rv_monitor_if #(T))
        implements fw_runnable;
    virtual fw_rv_monitor_xtor_if #(T) vif;

    function new(string name, fw_component parent,
                 virtual fw_rv_monitor_xtor_if #(T) vif);
        super.new(name, parent);
        this.vif = vif;
        parent.add_runnable(this);
    endfunction

    virtual task run();
        forever begin
            automatic T beat;
            vif.get(beat);
            t.observe(beat);
        end
    endtask
endclass
