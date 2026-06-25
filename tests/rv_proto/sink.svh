    // --------------------------------------------------------------
    // Sink: PROVIDES the rv_target_if implementation (via the API macro).
    // --------------------------------------------------------------
    class sink extends fw_component;
        data_t received[$];

        `FW_RV_TARGET_IMP(data_t, sink, in);

        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction

        function void build();
            in = new(this);
        endfunction

        virtual task in_put(input data_t t);
            received.push_back(t);
            $display("[sink]    put  0x%08h @ %0t", t, $time);
        endtask
    endclass
