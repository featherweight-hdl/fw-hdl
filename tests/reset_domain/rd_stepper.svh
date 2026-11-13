// Synchronous-level code: step() is called on every edge, in reset or not, and
// reads in_reset() itself (as an always block has a reset branch).
class rd_stepper extends fw_component implements fw_steppable;
    int n_steps, n_steps_in_reset;

    function new(string name, fw_component parent);
        super.new(name, parent);
        add_steppable(this);
    endfunction

    virtual function void step();
        n_steps++;
        if (in_reset()) n_steps_in_reset++;
    endfunction
endclass
