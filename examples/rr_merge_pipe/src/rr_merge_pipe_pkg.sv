// rr_merge with a map on each side: the vehicle for micro-pipelining
// feasibility (docs/design/micro-pipelining-feasibility.md). rr_merge's
// classes are included from ../rr_merge/src, unchanged (importing
// rr_merge_pkg instead weaves, but fw_settle then can't summarize the port
// calls of rr_merge_pkg's classes specialized with a type from here); the
// beat types are in pipe_types_pkg.
`include "fw_hdl_macros.svh"

package rr_merge_pipe_pkg;
    import fw_hdl_pkg::*;
    import pipe_types_pkg::*;

    // rr_merge's default beat type (its classes' default T), as in rr_merge_pkg.
    typedef struct packed {
        logic [7:0] data;
        logic       last;
    } rr_beat_t;

    `include "rr_arbiter.svh"
    `include "rr_fifo.svh"
    `include "rr_merge.svh"
    `include "pipe_map_in.svh"
    `include "pipe_map_out.svh"
    `include "rr_merge_pipe.svh"

    // The answer key (F3).
    `include "pipe_map_in_key.svh"
    `include "pipe_stage_key.svh"
    `include "rr_merge_pipe_key.svh"

    // The configuration the class testbench builds (named for the weave).
    typedef rr_merge_pipe #(pipe_in8_t, pipe_mid8_t, 4, 2) rr_merge_pipe4_t;
endpackage
