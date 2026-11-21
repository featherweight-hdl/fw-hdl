// The emit top for scripts/gen_rtl.py: one class variable per design to lower.
module rr_merge_pipe_emit_top;
    import pipe_types_pkg::*;
    // Package-scoped: each variable is named for its class (the module name).
    rr_merge_pipe_pkg::rr_merge_pipe4_t rr_merge_pipe;
    rr_merge_pipe_pkg::rr_merge_pipe_stall1 #(pipe_in8_t, pipe_prod8_t, pipe_mid8_t, 4, 2) rr_merge_pipe_stall1;
    rr_merge_pipe_pkg::rr_merge_pipe_stall2 #(pipe_in8_t, pipe_prod8_t, pipe_mid8_t, 4, 2) rr_merge_pipe_stall2;
    rr_merge_pipe_pkg::rr_merge_pipe_elastic1 #(pipe_in8_t, pipe_prod8_t, pipe_mid8_t, 4, 2) rr_merge_pipe_elastic1;
    rr_merge_pipe_pkg::rr_merge_pipe_elastic2 #(pipe_in8_t, pipe_prod8_t, pipe_mid8_t, 4, 2) rr_merge_pipe_elastic2;
    rr_merge_pipe_pkg::rr_merge_pipe_credit1 #(pipe_in8_t, pipe_prod8_t, pipe_mid8_t, 4, 2) rr_merge_pipe_credit1;
    rr_merge_pipe_pkg::rr_merge_pipe_credit2 #(pipe_in8_t, pipe_prod8_t, pipe_mid8_t, 4, 2) rr_merge_pipe_credit2;
    rr_merge_pipe_pkg::rr_merge_pipe_skid #(pipe_in8_t, pipe_prod8_t, pipe_mid8_t, 4, 2) rr_merge_pipe_skid;
    rr_merge_pipe_pkg::rr_merge_pipe_out1 #(pipe_in8_t, pipe_prod8_t, pipe_mid8_t, 4, 2) rr_merge_pipe_out1;
endmodule
