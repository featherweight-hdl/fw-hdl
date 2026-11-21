// The ready/valid get endpoint (sync-task-domains.md §5.1, X4): task code
// calls get(), which raises ready in the cycle it is called and returns the
// beat at the edge where valid && ready holds. ready is low while no get()
// is pending, so nothing is taken early and nothing is buffered. step()
// drops ready after a handshake, as a default that a back-to-back get() at
// that edge overrides (C5).
class fw_rv_get_ep #(type T = bit) extends fw_component
        implements fw_steppable, fw_get_if #(T);
    fw_rv_sp_in #(T)            in;
    fw_export #(fw_get_if #(T)) t;      // the method side

    function new(string name, fw_component parent);
        super.new(name, parent);
        in = new(null, "in", this);
        t  = new("t", this, this);
        add_steppable(this);
    endfunction

    // Drops ready after a handshake, unless a get() at this edge raises it.
    virtual function void step();
        if (in.get_valid() && in.get_ready()) in.set_ready(0);
    endfunction

    // Returns the next beat, at the edge where it is taken.
    virtual task get(output T t);
        in.set_ready(1);
        do clock.get_if().tick(1);
        while (!(in.get_valid() && in.get_ready()));
        t = in.get_data();
    endtask
endclass
