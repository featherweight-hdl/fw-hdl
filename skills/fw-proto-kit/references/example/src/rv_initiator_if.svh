`ifndef INCLUDED_RV_INITIATOR_IF_SVH
`define INCLUDED_RV_INITIATOR_IF_SVH

// Initiator API: hand a beat to the protocol. send() blocks until the beat has
// been queued for transmission. Implemented (via `FW_RV_INITIATOR_IMP) by the
// initiator bridge, whose export the driver's port connects to.
interface class rv_initiator_if #(type T = logic [31:0]);
    pure virtual task send(input T t);
endclass

`endif /* INCLUDED_RV_INITIATOR_IF_SVH */
