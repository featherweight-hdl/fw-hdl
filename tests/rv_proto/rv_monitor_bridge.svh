    //   * The MONITOR bridge is a CONSUMER like the target: it extends
    //     fw_port #(rv_monitor_if) and runs an active loop. It BLOCKS on
    //     vif.get(beat) (the transactor-interface's blocking method) and then
    //     fans the beat out via the NON-BLOCKING monitor API observe().
    class rv_monitor_bridge #(type T) extends fw_port #(rv_monitor_if #(T))
            implements fw_runnable;
        virtual rv_monitor_xtor_if vif;

        function new(string name, fw_component parent,
                     virtual rv_monitor_xtor_if vif);
            super.new(name, parent);
            this.vif = vif;
            parent.add_runnable(this);   // active port: opt in to run()
        endfunction

        virtual task run();
            forever begin
                automatic T beat;
                vif.get(beat);         // blocking: next observed beat
                t.observe(beat);       // t (resolved subscriber api) bound at connect
            end
        endtask
    endclass
