// Initiator API: hand a beat to the ready/valid protocol. Blocks until the
// transactor has queued it (not until the far end accepts it).
(* fw_latency_insensitive *)   // ready/valid: any delay
interface class fw_rv_initiator_if #(type T);
    pure virtual task send(input T t);
endclass
