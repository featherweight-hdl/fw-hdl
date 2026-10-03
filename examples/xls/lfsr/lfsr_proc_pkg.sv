// Derived from XLS xls/examples/lfsr_proc.x (see orig/), Copyright The XLS
// Authors, Apache-2.0 (see ../NOTICE). A line-for-line port to the fw-hdl
// static subset; README.md lists the deviations.
//
// The proc polls its seed channel (recv_non_blocking), so its seed port is an
// fw_get_nb_if: try_get takes a seed if one is waiting and leaves the state
// alone otherwise.
`include "fw_std_macros.svh"

package lfsr_proc_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;
    import lfsr_pkg::*;

    class user_module #(int unsigned BIT_WIDTH = 8) extends fw_component implements fw_runnable;
        // (uN[BIT_WIDTH], uN[BIT_WIDTH]): (seed, tap_mask), in tuple order
        typedef struct packed {
            bit [BIT_WIDTH-1:0] seed;
            bit [BIT_WIDTH-1:0] tap_mask;
        } seed_and_mask_t;

        fw_port #(fw_put_if #(bit [BIT_WIDTH-1:0])) output_s;
        fw_port #(fw_get_nb_if #(seed_and_mask_t)) seed_and_mask_r;

        // state = (seed, tap_mask)
        seed_and_mask_t state = '{seed: 1, tap_mask: 1};

        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);
        endfunction

        function void build();
            output_s = new("output_s", this);
            seed_and_mask_r = new("seed_and_mask_r", this);
        endfunction

        virtual task run();
            forever begin
                seed_and_mask_t new_state = state;
                bit valid;
                valid = seed_and_mask_r.t.try_get(new_state);
                output_s.t.put(new_state.seed);
                state = '{seed: lfsr_c#(BIT_WIDTH)::lfsr(new_state.seed, new_state.tap_mask),
                          tap_mask: new_state.tap_mask};
            end
        endtask
    endclass

    // The width the test proc spawns.
    typedef user_module #(8) user_module8;

endpackage
