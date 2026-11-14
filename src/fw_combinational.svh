// A *combinational* says "this body is combinational logic": comb() reads
// struct-port inputs and the component's own state, and writes comb fields
// (design-sync-rtl §3.2). It registers with its containing component through
// fw_component::add_comb(this), as an fw_steppable uses add_steppable().
//
// At each edge the kernel (sync/fw_sync_kernel) commits the sync fields, then
// calls every comb() of the clock domain until no comb value changes, then
// calls the step()s. comb() may be called any number of times per edge, so it
// must not change state: write comb fields only. A write to a sync field from
// comb() is an error (checked at run time unless FW_SYNC_NO_CHECKS).
interface class fw_combinational;
    pure virtual function void comb();
endclass
