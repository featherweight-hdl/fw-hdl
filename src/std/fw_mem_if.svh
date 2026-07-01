// Protocol-INDEPENDENT memory-access API. User/test logic and models written
// against fw_mem_if do not change when the underlying protocol is swapped -- a
// per-protocol adapter (e.g. the Wishbone wb_mem_initiator / wb_mem_target in
// fw-proto-wb) bridges it to the bus. This is the "std mem API": one blocking
// read/write pair, addressed, byte-strobed, with an escalated bus-error bit.
//
// Outputs lead (fw-api-kit "Parameter order"): read "data = read(addr)".
//   ADDR/DATA/STRB : address / data / byte-strobe types.
//   err            : escalated bus error (ERR termination, or RTY budget exhausted
//                    in adapters that retry).
interface class fw_mem_if #(type ADDR = logic [31:0],
                            type DATA = logic [31:0],
                            type STRB = logic [3:0]);
    // Write `data` (qualified by `strb`) to `addr`; err=1 on bus error.
    pure virtual task write(output bit err, input ADDR addr, input DATA data,
                            input STRB strb);
    // Read `addr` into `data`; err=1 on bus error.
    pure virtual task read(output DATA data, output bit err, input ADDR addr);
endclass
