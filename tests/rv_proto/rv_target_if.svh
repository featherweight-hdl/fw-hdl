    // Target API: accept a beat delivered by the protocol. The target
    // transactor (a port) calls put(); the connected component implements it.
    interface class rv_target_if #(type T);
        pure virtual task put(input T t);
    endclass
