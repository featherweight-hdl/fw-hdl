// Initiator bridge: the provider of the initiator API over a live
// fw_rv_initiator_xtor_if. It is its own imp (an export adapter), so a
// component's port binds straight to it: `fw_root_bind_port(drv.out,
// xtor.u_if, fw_rv_initiator_bridge #(T)).
class fw_rv_initiator_bridge #(type T) extends fw_export #(fw_rv_initiator_if #(T))
        implements fw_rv_initiator_if #(T);
    virtual fw_rv_initiator_xtor_if #(T) vif;

    function new(string name, fw_component parent,
                 virtual fw_rv_initiator_xtor_if #(T) vif);
        super.new(name, parent, this);
        this.vif = vif;
    endfunction

    virtual task send(input T t);
        vif.send(t);
    endtask
endclass
