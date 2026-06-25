// Initiator bridge -- the PROVIDER side. Holds a virtual transactor-interface
// handle and implements rv_initiator_if via the API's `FW_RV_INITIATOR_IMP macro
// (never hand-rolled). send() redirects to exp_send(), which calls vif.send()
// (i.e. queues the beat into the transactor-interface FIFO). A consumer's port
// (e.g. the driver) connects to the export member `exp`.
class rv_initiator_bridge #(type T = logic [31:0]) extends fw_component;
    virtual rv_initiator_xtor_if vif;

    `FW_RV_INITIATOR_IMP(T, rv_initiator_bridge #(T), exp);

    function new(string name, fw_component parent,
                 virtual rv_initiator_xtor_if vif);
        super.new(name, parent);
        this.vif = vif;
        exp = new(this);
    endfunction

    virtual task exp_send(input T t);
        vif.send(t);
    endtask
endclass
