`ifndef INCLUDED_RV_MONITOR_IF_SVH
`define INCLUDED_RV_MONITOR_IF_SVH

// Monitor API: observe a beat seen on the bus. NON-BLOCKING (a function) --
// monitor APIs may not block. The monitor transactor (a port, via
// rv_monitor_bridge) calls observe(); the connected subscriber implements it
// (via `FW_RV_MONITOR_IMP).
interface class rv_monitor_if #(type T = logic [31:0]);
    pure virtual function void observe(input T t);
endclass

`endif /* INCLUDED_RV_MONITOR_IF_SVH */
