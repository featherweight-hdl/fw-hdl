// The ready/valid put endpoint (sync-task-domains.md §5.1, X4): task code
// calls put(), which drives valid and data in the cycle it is called and
// returns at the edge where valid && ready holds. Nothing is buffered and no
// cycle is added. step() drops valid after a handshake, as a default that a
// back-to-back put() at that edge overrides, so valid stays high (C5).
//
// put() writes the port from the caller's thread: two callers putting for
// one edge are FW-E-XING-DRIVE-TWICE, as two beats in one cycle would be.
class fw_rv_put_ep #(type T = bit) extends fw_component
        implements fw_steppable, fw_put_if #(T);
    fw_rv_sp_out #(T)           out;
    fw_export #(fw_put_if #(T)) t;      // the method side

    function new(string name, fw_component parent);
        super.new(name, parent);
        out = new(null, "out", this);
        t   = new("t", this, this);
        add_steppable(this);
    endfunction

    // Drops valid after a handshake, unless a put() at this edge raises it.
    virtual function void step();
        if (out.get_valid() && out.get_ready()) out.set_valid(0);
    endfunction

    // Offers d and returns at the edge where it is accepted.
    virtual task put(input T t);
        out.set_valid(1);
        out.set_data(t);
        do clock.get_if().tick(1);
        while (!(out.get_valid() && out.get_ready()));
    endtask
endclass
