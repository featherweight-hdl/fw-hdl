// Target bridge: a consumer of the target API. It is an active port: its run()
// takes each beat from the fw_rv_target_xtor_if and calls put() on the bound
// export. `fw_root_bind_export(chk.in, xtor.u_if, fw_rv_target_bridge #(T)).
class fw_rv_target_bridge #(type T) extends fw_port #(fw_rv_target_if #(T))
        implements fw_runnable;
    virtual fw_rv_target_xtor_if #(T) vif;

    function new(string name, fw_component parent,
                 virtual fw_rv_target_xtor_if #(T) vif);
        super.new(name, parent);
        this.vif = vif;
        parent.add_runnable(this);
    endfunction

    virtual task run();
        forever begin
            automatic T beat;
            vif.recv(beat);
            t.put(beat);
        end
    endtask
endclass
