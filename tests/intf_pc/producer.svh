// Consumes the std put API through a port. A runnable: it registers itself so
// do_run() forks its run(), which resolves the bound implementation and drives
// four beats through it. (No clock needed -- this provider is pure TLM, so
// put() returns immediately; the same component bound to a signal-level
// fw_put_xtor_bridge would instead advance one clock per put.)
class producer extends fw_component implements fw_runnable;
    fw_port #(fw_put_if #(data_t)) out;

    function new(string name, fw_component parent);
        super.new(name, parent);
        add_runnable(this);
    endfunction

    function void build();
        out = new("out", this);
    endfunction

    virtual task run();
        for (int i = 0; i < 4; i++) begin
            automatic data_t v = 32'hdead_0000 + i;
            $display("[producer] put 0x%08h", v);
            out.t.put(v);            // out.t resolved at connect
        end
    endtask
endclass
