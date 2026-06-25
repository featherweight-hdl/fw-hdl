    // --------------------------------------------------------------
    // Driver: consumes the initiator API through a port.
    // --------------------------------------------------------------
    class driver extends fw_component implements fw_runnable;
        fw_port #(rv_initiator_if #(data_t)) out;

        function new(string name, fw_component parent);
            super.new(name, parent);
            parent.add_runnable(this);   // active component: opt in to run()
        endfunction

        function void build();
            out = new("out", this);
        endfunction

        virtual task run();
            for (int unsigned i = 0; i < N; i++) begin
                automatic data_t v = 32'hcafe_0000 + i;
                out.t.send(v);       // out.t resolved at connect
                $display("[driver]  sent 0x%08h @ %0t", v, $time);
            end
        endtask
    endclass
