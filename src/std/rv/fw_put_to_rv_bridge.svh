// Adapter: the put API onto an rv initiator transactor. A component written
// against fw_put_if (fw_port #(fw_put_if #(T))) drives ready/valid pins
// unchanged: put() queues the beat on the fw_rv_initiator_xtor_if, blocking
// while its FIFO is full, so no beat is lost when ready is low.
// `fw_root_bind_port(src.out, xtor.u_if, fw_put_to_rv_bridge #(T)).
class fw_put_to_rv_bridge #(type T) extends fw_export #(fw_put_if #(T))
        implements fw_put_if #(T);
    virtual fw_rv_initiator_xtor_if #(T) vif;

    function new(string name, fw_component parent,
                 virtual fw_rv_initiator_xtor_if #(T) vif);
        super.new(name, parent, this);
        this.vif = vif;
    endfunction

    virtual task put(input T t);
        vif.send(t);
    endtask
endclass
