    // Initiator bridge: a PROVIDER of the initiator API, so the bridge IS an
    // fw_export (not a component). The driver's port connects directly to it --
    // `drv.out.connect(bridge)` -- and send() drives the beat onto the
    // transactor interface. As an export ADAPTER it extends fw_export directly
    // rather than using `FW_RV_INITIATOR_IMP (which is for COMPONENTS that
    // publish an API through an internal export member).
    class rv_initiator_bridge #(type T) extends fw_export #(rv_initiator_if #(T))
            implements rv_initiator_if #(T);
        virtual rv_initiator_xtor_if vif;

        function new(string name, fw_component parent,
                     virtual rv_initiator_xtor_if vif);
            super.new(name, parent, this);   // the export's imp is the bridge
            this.vif = vif;
        endfunction

        virtual task send(input T t);
            vif.send(t);
        endtask
    endclass
