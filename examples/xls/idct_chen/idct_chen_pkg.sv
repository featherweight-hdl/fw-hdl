// Derived from XLS xls/examples/jpeg/idct_chen.x (see orig/), Copyright The
// XLS Authors, Apache-2.0 (see ../NOTICE). A line-for-line port to the fw-hdl
// static subset; README.md lists the deviations.
//
// The porting trap: DSLX's `>>` on an s32 is an *arithmetic* shift (DSLX picks
// the shift from the type). SV's `>>` is always logical, so every right shift
// of a signed value here is `>>>`.

package idct_chen_pkg;

    localparam int unsigned COEFF_PER_MCU = 64;
    localparam bit [7:0] COEFF_PER_MCU_U8 = 8'd64;
    localparam bit signed [31:0] W1 = 2841;  // 2048*sqrt(2)*cos(1*pi/16)
    localparam bit signed [31:0] W2 = 2676;  // 2048*sqrt(2)*cos(2*pi/16)
    localparam bit signed [31:0] W3 = 2408;  // 2048*sqrt(2)*cos(3*pi/16)
    localparam bit signed [31:0] W5 = 1609;  // 2048*sqrt(2)*cos(5*pi/16)
    localparam bit signed [31:0] W6 = 1108;  // 2048*sqrt(2)*cos(6*pi/16)
    localparam bit signed [31:0] W7 = 565;   // 2048*sqrt(2)*cos(7*pi/16)
    localparam bit signed [31:0] R2 = 181;   // 256/sqrt(2)

    typedef bit signed [31:0] row_t [8];
    typedef bit signed [31:0] block_t [COEFF_PER_MCU];

    // Performs an 8-point 1D IDCT.
    //
    // This uses fixed point scaling factors that are burned in to the computation.
    function automatic row_t idct_row(row_t s);
        bit signed [31:0] w1pw7 = W1 + W7;
        bit signed [31:0] w1mw7 = W1 - W7;
        bit signed [31:0] w2pw6 = W2 + W6;
        bit signed [31:0] w2mw6 = W2 - W6;
        bit signed [31:0] w3pw5 = W3 + W5;
        bit signed [31:0] w3mw5 = W3 - W5;
        bit signed [31:0] x0 = (s[0] << 11) + 128;
        bit signed [31:0] x1 = s[4] << 11;
        bit signed [31:0] x2 = s[6];
        bit signed [31:0] x3 = s[2];
        bit signed [31:0] x4 = s[1];
        bit signed [31:0] x5 = s[7];
        bit signed [31:0] x6 = s[5];
        bit signed [31:0] x7 = s[3];
        bit signed [31:0] x8;
        row_t result;

        // Stage 1.
        x8 = W7 * (x4 + x5);
        x4 = x8 + w1mw7 * x4;
        x5 = x8 - w1pw7 * x5;
        x8 = W3 * (x6 + x7);
        x6 = x8 - w3mw5 * x6;
        x7 = x8 - w3pw5 * x7;

        // Stage 2.
        x8 = x0 + x1;
        x0 = x0 - x1;
        x1 = W6 * (x3 + x2);
        x2 = x1 - w2pw6 * x2;
        x3 = x1 + w2mw6 * x3;
        x1 = x4 + x6;
        x4 = x4 - x6;
        x6 = x5 + x7;
        x5 = x5 - x7;

        // Stage 3.
        x7 = x8 + x3;
        x8 = x8 - x3;
        x3 = x0 + x2;
        x0 = x0 - x2;
        x2 = (R2 * (x4 + x5) + 128) >>> 8;
        x4 = (R2 * (x4 - x5) + 128) >>> 8;

        // Stage 4.
        result = '{
            (x7 + x1) >>> 8,
            (x3 + x2) >>> 8,
            (x0 + x4) >>> 8,
            (x8 + x6) >>> 8,
            (x8 - x6) >>> 8,
            (x0 - x4) >>> 8,
            (x3 - x2) >>> 8,
            (x7 - x1) >>> 8
        };
        return result;
    endfunction

    // Extracts a row (8 adjacent values) from a 64-value coefficient array.
    function automatic row_t get_row(block_t a, bit [7:0] rowno);
        row_t r;
        for (int k = 0; k < 8; k++)
            r[k] = a[8'(8'd8 * rowno + 8'(k))];
        return r;
    endfunction

    // Runs a row-wise IDCT over each of the 8-element rows of f.
    function automatic block_t idct_rows(block_t f);
        row_t row0 = idct_row(get_row(f, 8'd0));
        row_t row1 = idct_row(get_row(f, 8'd1));
        row_t row2 = idct_row(get_row(f, 8'd2));
        row_t row3 = idct_row(get_row(f, 8'd3));
        row_t row4 = idct_row(get_row(f, 8'd4));
        row_t row5 = idct_row(get_row(f, 8'd5));
        row_t row6 = idct_row(get_row(f, 8'd6));
        row_t row7 = idct_row(get_row(f, 8'd7));
        block_t out;
        // row0 ++ row1 ++ row2 ++ row3 ++ row4 ++ row5 ++ row6 ++ row7
        for (int k = 0; k < 8; k++) begin
            out[k]      = row0[k];
            out[8 + k]  = row1[k];
            out[16 + k] = row2[k];
            out[24 + k] = row3[k];
            out[32 + k] = row4[k];
            out[40 + k] = row5[k];
            out[48 + k] = row6[k];
            out[56 + k] = row7[k];
        end
        return out;
    endfunction

    // Performs an 8-point 1D IDCT.
    //
    // This is nearly identical to the above, but uses slightly different fixed
    // point.
    function automatic row_t idct_col(row_t s);
        bit signed [31:0] w1pw7 = W1 + W7;
        bit signed [31:0] w1mw7 = W1 - W7;
        bit signed [31:0] w2pw6 = W2 + W6;
        bit signed [31:0] w2mw6 = W2 - W6;
        bit signed [31:0] w3pw5 = W3 + W5;
        bit signed [31:0] w3mw5 = W3 - W5;

        // Prescale.
        bit signed [31:0] y0 = (s[0] << 8) + 8192;
        bit signed [31:0] y1 = s[4] << 8;
        bit signed [31:0] y2 = s[6];
        bit signed [31:0] y3 = s[2];
        bit signed [31:0] y4 = s[1];
        bit signed [31:0] y5 = s[7];
        bit signed [31:0] y6 = s[5];
        bit signed [31:0] y7 = s[3];
        bit signed [31:0] y8;
        row_t result;

        // Stage 1.
        y8 = W7 * (y4 + y5) + 4;
        y4 = (y8 + w1mw7 * y4) >>> 3;
        y5 = (y8 - w1pw7 * y5) >>> 3;
        y8 = W3 * (y6 + y7) + 4;
        y6 = (y8 - w3mw5 * y6) >>> 3;
        y7 = (y8 - w3pw5 * y7) >>> 3;

        // Stage 2.
        y8 = y0 + y1;
        y0 = y0 - y1;
        y1 = W6 * (y3 + y2) + 4;
        y2 = (y1 - w2pw6 * y2) >>> 3;
        y3 = (y1 + w2mw6 * y3) >>> 3;
        y1 = y4 + y6;
        y4 = y4 - y6;
        y6 = y5 + y7;
        y5 = y5 - y7;

        // Stage 3.
        y7 = y8 + y3;
        y8 = y8 - y3;
        y3 = y0 + y2;
        y0 = y0 - y2;
        y2 = (R2 * (y4 + y5) + 128) >>> 8;
        y4 = (R2 * (y4 - y5) + 128) >>> 8;

        // Stage 4.
        result = '{
            (y7 + y1) >>> 14,
            (y3 + y2) >>> 14,
            (y0 + y4) >>> 14,
            (y8 + y6) >>> 14,
            (y8 - y6) >>> 14,
            (y0 - y4) >>> 14,
            (y3 - y2) >>> 14,
            (y7 - y1) >>> 14
        };
        return result;
    endfunction

    // Extracts a column (8 strided values) from a 64-value coefficient array.
    function automatic row_t get_col(block_t a, bit [7:0] colno);
        row_t c;
        for (int k = 0; k < 8; k++)
            c[k] = a[8'(8'd8 * 8'(k) + colno)];
        return c;
    endfunction

    // Runs a column-wise IDCT over each of the 8-element columns of f.
    function automatic block_t idct_cols(block_t f);
        row_t col0 = idct_col(get_col(f, 8'd0));
        row_t col1 = idct_col(get_col(f, 8'd1));
        row_t col2 = idct_col(get_col(f, 8'd2));
        row_t col3 = idct_col(get_col(f, 8'd3));
        row_t col4 = idct_col(get_col(f, 8'd4));
        row_t col5 = idct_col(get_col(f, 8'd5));
        row_t col6 = idct_col(get_col(f, 8'd6));
        row_t col7 = idct_col(get_col(f, 8'd7));
        block_t accum = '{default: 0};
        // Concatenate the columns.
        for (int i = 0; i < COEFF_PER_MCU_U8; i++) begin
            bit [7:0] iu = 8'(i);
            bit signed [31:0] val;
            case (iu & 8'd7)
                8'd0: val = col0[iu >> 3];
                8'd1: val = col1[iu >> 3];
                8'd2: val = col2[iu >> 3];
                8'd3: val = col3[iu >> 3];
                8'd4: val = col4[iu >> 3];
                8'd5: val = col5[iu >> 3];
                8'd6: val = col6[iu >> 3];
                8'd7: val = col7[iu >> 3];
                default: begin
                    assert (0) else $fatal(1, "invalid_column_index");
                    val = 0;
                end
            endcase
            accum[iu] = val;
        end
        return accum;
    endfunction

    function automatic block_t idct(block_t f);
        return idct_cols(idct_rows(f));
    endfunction

endpackage
