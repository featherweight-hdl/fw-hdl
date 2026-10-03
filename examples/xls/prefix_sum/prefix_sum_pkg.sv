// Derived from XLS xls/examples/prefix_sum.x (see orig/), Copyright The XLS
// Authors, Apache-2.0 (see ../NOTICE). A line-for-line port to the fw-hdl
// static subset; README.md lists the deviations.

package prefix_sum_pkg;

    localparam int unsigned ARRAY_SIZE = 16;

    typedef bit [15:0] values_t [ARRAY_SIZE];

    // Function that implements the Hillis-Steele parallel prefix sum algorithm.
    // https://en.wikipedia.org/wiki/Prefix_sum#Algorithm_1:_Shorter_span,_more_parallel
    // An adder chain would use (n-1) adders and add (n-1) adder delays.
    // This implementation uses ~(n lg n) adders, but only adds (lg n) adder delays.
    function automatic values_t prefix_sum(values_t values);
        values_t c = values;
        for (int i = 0; i < $clog2(ARRAY_SIZE); i++) begin   // std::flog2(ARRAY_SIZE)
            int unsigned lookback = 1 << i;
            values_t updated = c;
            for (int j = 0; j < ARRAY_SIZE; j++)
                if (j >= lookback) updated[j] = c[j] + c[j - lookback];
            c = updated;
        end
        return c;
    endfunction

endpackage
