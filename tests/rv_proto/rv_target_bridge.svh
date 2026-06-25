    class rv_target_bridge #(type T) extends fw_port #(rv_target_if #(T))
            implements fw_runnable;
        virtual rv_target_xtor_if vif;

        function new(string name, fw_component parent,
                     virtual rv_target_xtor_if vif);
            super.new(name, parent);
            this.vif = vif;
            parent.add_runnable(this);   // active port: opt in to run()
        endfunction

        virtual task run();
            forever begin
                automatic T beat;
                #17ns;                 // idle: ready low -> backpressure
                vif.recv(beat);
                t.put(beat);           // t (resolved sink api) bound at connect
            end
        endtask
    endclass
