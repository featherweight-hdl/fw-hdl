// Records what its reset domain looks like from live class code, and how the
// run lifecycle treats it: run() counts its starts and ticks, and forks a
// grandchild process that ticks too (so a kill must reach it); reset_state()
// counts its calls.
class rd_leaf extends fw_component implements fw_runnable;
    bit     reset_at_start;
    longint deassert_t = -1;
    bit     started;
    int     n_start, n, n_child, n_reset_state;

    function new(string name, fw_component parent);
        super.new(name, parent);
        add_runnable(this);
    endfunction

    virtual task run();
        n_start++;
        reset_at_start = in_reset();
        started        = 1'b1;
        wait_reset_deassert();
        deassert_t     = $time;
        fork
            forever begin tick(); n_child++; end
        join_none
        forever begin tick(); n++; end
    endtask

    virtual function void reset_state();
        n_reset_state++;
    endfunction
endclass
