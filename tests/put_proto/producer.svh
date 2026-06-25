// Consumes the std put API through a port and drives N beats. It is unaware of
// whether the bound provider is pure TLM or a signal-level transactor; here the
// testbench binds it to an fw_put_xtor_bridge, so each put() advances one clock
// and registers the value onto the bus -- with no handshake (put is fire-and-
// forget: the producer never waits for a consumer).
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
        for (int unsigned i = 0; i < N; i++) begin
            automatic data_t v = BASE + i;
            $display("[producer] put 0x%08h", v);
            out.t.put(v);            // out.t resolved at connect
        end
    endtask
endclass
