// Derived from XLS xls/examples/lfsr.x (see orig/), Copyright The XLS
// Authors, Apache-2.0 (see ../NOTICE). A line-for-line port to the fw-hdl
// static subset; README.md lists the deviations.

package lfsr_pkg;

    // DSLX's parametric `fn lfsr<BIT_WIDTH: u32>` is a static function of a
    // parameterized class: lfsr_c#(7)::lfsr is lfsr<u32:7>.
    class lfsr_c #(int unsigned BIT_WIDTH = 8);
        static function bit [BIT_WIDTH-1:0] lfsr(bit [BIT_WIDTH-1:0] current_value,
                                                 bit [BIT_WIDTH-1:0] tap_mask);
            // Compute the new bit from the taps
            bit new_bit = 1'b0;
            for (int index = 0; index < BIT_WIDTH; index++)
                new_bit = (tap_mask[index] == 1'b0) ? new_bit : new_bit ^ current_value[index];

            // Kick the high bit and insert the new bit
            return {current_value[BIT_WIDTH-2:0], new_bit};
        endfunction
    endclass

    ////////////////////////////////////////////////////////////////////////////
    // Here are a few maximal LFSRs for different bit widths.
    // These are only examples and it is possible to use different bit widths and
    // tap masks.
    // Source: https://en.wikipedia.org/wiki/Linear-feedback_shift_register
    ////////////////////////////////////////////////////////////////////////////

    // 7-bit LFSR with the maximal period of 127
    function automatic bit [6:0] lfsr7(bit [6:0] n);
        return lfsr_c#(7)::lfsr(n, 7'b1100000);
    endfunction

    // 8-bit LFSR with the maximal period of 255
    function automatic bit [7:0] lfsr8(bit [7:0] n);
        return lfsr_c#(8)::lfsr(n, 8'b10111000);
    endfunction

endpackage
