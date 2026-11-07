// Adapter: the get API from an rv target transactor. A component written
// against fw_get_if (fw_port #(fw_get_if #(T))) reads ready/valid pins
// unchanged: get() takes the next beat from the fw_rv_target_xtor_if, blocking
// while its FIFO is empty. Ready stays low on the pins while the FIFO is full.
// `fw_root_bind_port(dst.in, xtor.u_if, fw_get_from_rv_bridge #(T)).
// The get API over ready/valid tolerates any delay (the binding declares it).
(* fw_latency_insensitive *)
class fw_get_from_rv_bridge #(type T) extends fw_export #(fw_get_if #(T))
        implements fw_get_if #(T);
    virtual fw_rv_target_xtor_if #(T) vif;

    function new(string name, fw_component parent,
                 virtual fw_rv_target_xtor_if #(T) vif);
        super.new(name, parent, this);
        this.vif = vif;
    endfunction

    virtual task get(output T t);
        vif.recv(t);
    endtask
endclass
