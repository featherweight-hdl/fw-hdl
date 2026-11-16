// The emit top for fw.hdl.sync.Emit: one class variable per class to lower.
module rr_merge_emit_top;
    import rr_merge_pkg::*;
    rr_merge4_t                       rr_merge;
    rr_arbiter #(rr_beat_t, 4)        rr_arbiter4;
    rr_fifo #(rr_beat_t, 2)           rr_fifo2;
endmodule
