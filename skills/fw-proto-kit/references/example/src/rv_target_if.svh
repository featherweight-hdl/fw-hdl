// Target API: accept a beat delivered by the protocol. The target transactor (a
// port, via rv_target_bridge) calls put(); the connected component implements it
// (via `FW_RV_TARGET_IMP).
interface class rv_target_if #(type T = logic [31:0]);
    pure virtual task put(input T t);
endclass
