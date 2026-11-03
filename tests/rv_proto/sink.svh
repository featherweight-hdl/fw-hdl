    // --------------------------------------------------------------
    // Sink: PROVIDES the fw_rv_target_if implementation (via the API macro).
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

        // Much slower than the pins (100ns a beat; one transfer takes about
        // 30ns), so the target's FIFO fills and ready drops on the pins.
        virtual task in_put(input data_t t);
            #100ns;
            received.push_back(t);
            $display("[sink]    put  0x%0h @ %0t", t, $time);
        endtask
    endclass
