// Round-robin stream merger: N ready/valid inputs merged into one output,
// whole packets at a time (a winner keeps the grant until its `last` beat),
// through a small FIFO. See ../README.md.
`include "fw_hdl_macros.svh"

package rr_merge_pkg;
    import fw_hdl_pkg::*;

    // One beat. Any T given to the classes below needs a `last` field.
    typedef struct packed {
        logic [7:0] data;
        logic       last;
    } rr_beat_t;

    `include "rr_arbiter.svh"
    `include "rr_fifo.svh"
    `include "rr_merge.svh"

    // The configuration the testbench builds. The weavers see only the
    // specializations named in the woven sources, so it is named here.
    typedef rr_merge #(rr_beat_t, 4, 2) rr_merge4_t;
endpackage
