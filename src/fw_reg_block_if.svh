
// Addressable register-group API -- the bus-facing face of a register group.
//
// This is the kernel-level register API that rides over the fw_port/fw_export
// deferred-binding wrappers, exactly like fw_clock_domain_if: a bus adapter owns
// a register block and PROVIDES it as an fw_export #(fw_reg_block_if #(W)); a
// CPU/sequence model CONSUMES it through an fw_port #(fw_reg_block_if #(W)) and
// reaches registers by byte offset. Concrete bus protocols (Wishbone, APB, ...)
// are layered on top by protocol-support packages as adapters onto this API.
//
// Width-level access only: `offset` is a byte offset, stride is uniformly W/8,
// there are no byte enables.
interface class fw_reg_block_if #(int W = 32);
    pure virtual function bit [W-1:0] read_val (input int unsigned offset);
    pure virtual task                 write_val(input int unsigned offset,
                                                input bit [W-1:0] v);
    pure virtual function int unsigned size();   // byte span of the group
endclass
