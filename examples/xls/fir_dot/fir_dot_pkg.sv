// Derived from XLS xls/examples/fir_filter.x and xls/examples/dot_product.x
// (see orig/), Copyright The XLS Authors, Apache-2.0 (see ../NOTICE). The
// fixed-point halves only (the float32 halves need an SV apfloat). A
// line-for-line port to the fw-hdl static subset; README.md lists the
// deviations.

package fir_dot_pkg;

    // fir_filter.x: fir_filter_fixed<NUM_TAPS, NUM_SAMPLES,
    //                                NUM_OUTPUTS = {NUM_SAMPLES - NUM_TAPS + u32:1}>
    class fir_c #(int unsigned NUM_TAPS = 4, int unsigned NUM_SAMPLES = 6,
                  int unsigned NUM_OUTPUTS = NUM_SAMPLES - NUM_TAPS + 1);
        typedef bit signed [31:0] samples_t [NUM_SAMPLES];
        typedef bit signed [31:0] coefficients_t [NUM_TAPS];
        typedef bit signed [31:0] outputs_t [NUM_OUTPUTS];

        static function outputs_t fir_filter_fixed(samples_t samples,
                                                   coefficients_t coefficients);
            outputs_t fir_output = '{default: 0};

            // Convolve filter coefficients over sample array.
            for (int out_idx = 0; out_idx < NUM_OUTPUTS; out_idx++) begin
                // Compute a single output datapoint.
                bit signed [31:0] point_output = 0;
                for (int tap_idx = 0; tap_idx < NUM_TAPS; tap_idx++) begin
                    int unsigned sample_idx = out_idx + NUM_TAPS - tap_idx - 1;
                    bit signed [31:0] product = coefficients[tap_idx] * samples[sample_idx];
                    point_output = point_output + product;
                end
                fir_output[out_idx] = point_output;
            end
            return fir_output;
        endfunction
    endclass

    // dot_product.x: dot_product_fixed<BITCOUNT, VECTOR_LENGTH>
    class dot_c #(int unsigned BITCOUNT = 32, int unsigned VECTOR_LENGTH = 4);
        typedef bit signed [BITCOUNT-1:0] vector_t [VECTOR_LENGTH];

        static function bit signed [BITCOUNT-1:0] dot_product_fixed(vector_t a, vector_t b);
            bit signed [BITCOUNT-1:0] acc = '0;
            for (int idx = 0; idx < VECTOR_LENGTH; idx++) begin
                bit signed [BITCOUNT-1:0] partial_product = a[idx] * b[idx];
                acc = acc + partial_product;
            end
            return acc;
        endfunction
    endclass

    // The sizes upstream's tests use. Not in the DSLX: a DSLX test calls the
    // parametric functions directly, which SV cannot.
    typedef bit signed [31:0] s32x6_t [6];
    typedef bit signed [31:0] s32x4_t [4];
    typedef bit signed [31:0] s32x3_t [3];
    typedef bit signed [7:0]  s8x2_t  [2];

    function automatic s32x3_t fir_filter_fixed_4_6(s32x6_t samples, s32x4_t coefficients);
        return fir_c#(4, 6)::fir_filter_fixed(samples, coefficients);
    endfunction

    function automatic bit signed [31:0] dot_product_fixed_32_4(s32x4_t a, s32x4_t b);
        return dot_c#(32, 4)::dot_product_fixed(a, b);
    endfunction

    function automatic bit signed [7:0] dot_product_fixed_8_2(s8x2_t a, s8x2_t b);
        return dot_c#(8, 2)::dot_product_fixed(a, b);
    endfunction

endpackage
