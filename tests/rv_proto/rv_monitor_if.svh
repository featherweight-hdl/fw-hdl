    // Monitor API: observe a beat seen on the bus. NON-BLOCKING (a function) --
    // monitor APIs may not block. The monitor transactor (a port) calls
    // observe(); the connected subscriber implements it.
    interface class rv_monitor_if #(type T);
        pure virtual function void observe(input T t);
    endclass
