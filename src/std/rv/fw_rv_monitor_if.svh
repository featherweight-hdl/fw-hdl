// Monitor API: observe a beat seen on the pins. A function: monitor APIs may
// not block. The monitor bridge (a port) calls observe(); the connected
// subscriber implements it.
interface class fw_rv_monitor_if #(type T);
    pure virtual function void observe(input T t);
endclass
