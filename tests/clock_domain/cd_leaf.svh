// A leaf that exercises whatever clock domain it is given. On run() it ticks K
// times and records the elapsed simulation time, so the testbench can confirm
// the tick cadence tracks the domain's ratio to the root. It also caches
// root_ticks(1) (the trace-up query) for a direct ratio check.
class cd_leaf extends fw_component implements fw_runnable;
    int     k;        // number of ticks to perform
    longint ratio;    // root_ticks(1), cached at run()
    longint span;     // sim time elapsed across the k ticks
    bit     done;

    function new(string name, fw_component parent, int k = 4);
        super.new(name, parent);
        this.k = k;
        add_runnable(this);   // opt into the run phase
    endfunction

    virtual task run();
        longint t0;
        ratio = root_ticks(1);
        t0    = $time;
        repeat (k) tick();
        span  = $time - t0;
        done  = 1'b1;
    endtask
endclass
