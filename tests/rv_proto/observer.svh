    // --------------------------------------------------------------
    // Observer: PROVIDES the rv_monitor_if implementation (via the API macro).
    // A passive subscriber -- records every beat the monitor publishes.
    // --------------------------------------------------------------
    class observer extends fw_component;
        data_t seen[$];

        `FW_RV_MONITOR_IMP(data_t, observer, mon);

        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction

        function void build();
            mon = new(this);
        endfunction

        virtual function void mon_observe(input data_t t);
            seen.push_back(t);
            $display("[monitor] observed 0x%08h @ %0t", t, $time);
        endfunction
    endclass
