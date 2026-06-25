    // --------------------------------------------------------------
    // Top: a PURE component. It instances driver + sink + observer and owns
    // their API ports/exports, but knows NOTHING about the signal-level
    // transactors or their virtual interfaces. All bridge construction and
    // module-scope binding lives in rv_top_bind below, so rv_top stays reusable
    // and independent of this testbench's signal plumbing.
    // --------------------------------------------------------------
    class rv_top extends fw_component;
        driver   drv;
        sink     chk;
        observer obs;

        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction

        function void build();
            // Just create the immediate children; do_build() recurses into
            // them top-down, so no manual child.build() calls here.
            drv = new("drv", this);
            chk = new("chk", this);
            obs = new("obs", this);
        endfunction
    endclass
