// Target API: accept a beat delivered by the ready/valid protocol. The target
// bridge (a port) calls put(); the connected component implements it. While
// put() blocks, the transactor's receive FIFO fills and ready drops on the pins.
interface class fw_rv_target_if #(type T);
    pure virtual task put(input T t);
endclass
