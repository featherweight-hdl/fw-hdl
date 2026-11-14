// One field of a value-carrying struct port (docs: design-sync-rtl §3.2):
// its name, width, which end drives it, and whether the driver's writes are
// sync (seen by the peer from the next edge) or comb (seen at once).
//
// A field may carry a reset-force value: while the holder's reset domain is in
// reset, the peer reads that value instead of the register. It lowers to
// `assign pin = reset ? V : q`. The rv family forces valid and ready to 0.

// Which end of a channel drives a field: FWD is the producer (the out view),
// BWD the consumer (the in view).
typedef enum { FW_SYNC_FWD, FW_SYNC_BWD } fw_sync_dir_e;

// What is running, for the write rules (fw_sig_holder::m_wr): NONE outside
// the run phase (build, tests: unchecked), COMB in comb(), STEP in step(),
// RUN between the kernel's edges (run() processes).
typedef enum { FW_SYNC_PH_NONE, FW_SYNC_PH_COMB, FW_SYNC_PH_STEP,
               FW_SYNC_PH_RUN } fw_sync_phase_e;

class fw_sync_field;
    string        name;
    int           width;
    fw_sync_dir_e dir;
    bit           comb;        // 0: sync (default), 1: comb
    bit           has_force;   // a reset-force value applies
    logic [63:0]  force_val;   // the value, for reports; the holder keeps it typed

    function new(string name, int width, fw_sync_dir_e dir = FW_SYNC_FWD);
        this.name  = name;
        this.width = width;
        this.dir   = dir;
    endfunction

    function void set_force(logic [63:0] v);
        has_force = 1;
        force_val = v;
    endfunction
endclass
