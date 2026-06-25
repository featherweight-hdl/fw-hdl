    // Initiator API: hand a beat to the protocol (blocks until accepted).
    interface class rv_initiator_if #(type T);
        pure virtual task send(input T t);
    endclass
