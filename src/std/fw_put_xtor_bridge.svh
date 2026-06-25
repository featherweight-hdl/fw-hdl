
// The signal-level provider of the put API.
//
// A producer component holds an `fw_port #(fw_put_if #(T))` and calls put(t),
// unaware of how the value reaches the wire. This bridge is the export that
// port resolves to: it IS its own imp (extends fw_export and implements
// fw_put_if), and put() drives the beat onto an fw_put_xtor_if -- which
// registers it on the output with no handshake. Construct it over a live
// module-scope fw_put_xtor_if and bind it to the producer's port (e.g. via
// `fw_root_bind_port). The pure class (TLM) provider is instead `FW_PUT_IMP.
class fw_put_xtor_bridge #(type T) extends fw_export #(fw_put_if #(T))
        implements fw_put_if #(T);
    virtual interface fw_put_xtor_if #(T) vif;

    function new(string name, fw_component parent,
                 virtual interface fw_put_xtor_if #(T) vif);
        super.new(name, parent, this);   // the export's imp is the bridge
        this.vif = vif;
    endfunction

    virtual task put(input T t);
        vif.put(t);
    endtask

endclass
