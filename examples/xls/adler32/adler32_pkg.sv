// Derived from XLS xls/examples/adler32/adler32.x (see orig/), Copyright The
// XLS Authors, Apache-2.0 (see ../NOTICE). A line-for-line port to the fw-hdl
// static subset; README.md lists the deviations.

package adler32_pkg;

    function automatic bit [31:0] adler32_seq(bit [7:0] buf_);
        bit [31:0] a = 32'd1;
        bit [31:0] b = 32'd0;
        // Iterate only over input of length 1, for now.
        for (int i = 0; i < 1; i++) begin
            a = (a + 32'(buf_)) % 32'd65521;
            b = (b + a) % 32'd65521;
        end
        return (b << 16) | a;
    endfunction

    function automatic bit [31:0] main(bit [7:0] message);
        return adler32_seq(message);
    endfunction

endpackage
