// X0 construct micro-tests: one pure function per row of the semantics matrix
// (xls-phase0.md §3). Each runs on Verilator (the normative SV reference) and,
// through the static front end and zuspec-be-xls, in the XLS IR interpreter.
// The row is in the function name.
package micro_fn_pkg;

    typedef struct packed {
        bit [3:0] hi;
        bit [2:0] mid;
        bit       lo;
    } s8_t;

    typedef enum bit [1:0] { A, B, C } e_t;

    localparam bit [7:0] TBL [6] = '{8'h10, 8'h21, 8'h32, 8'h43, 8'h54, 8'h65};

    // E1: + - * wrap at the context width
    function automatic bit [7:0] e1_add(bit [7:0] a, bit [7:0] b);
        return a + b;
    endfunction
    function automatic bit [8:0] e1_add_ext(bit [7:0] a, bit [7:0] b);
        return a + b;                      // 9-bit context: the carry is kept
    endfunction
    function automatic bit [7:0] e1_sub(bit [7:0] a, bit [7:0] b);
        return a - b;
    endfunction
    function automatic bit [15:0] e1_mul(bit [7:0] a, bit [7:0] b);
        return a * b;                      // 16-bit context
    endfunction
    function automatic bit signed [15:0] e1_smul(bit signed [7:0] a, bit signed [7:0] b);
        return a * b;
    endfunction
    function automatic bit [15:0] e1_mixed(bit signed [7:0] a, bit [7:0] b);
        return a * b;                      // one unsigned operand: a is zero-extended
    endfunction

    // E2: division, guarded (D-1)
    function automatic bit [7:0] e2_div(bit [7:0] a, bit [7:0] b);
        if (b != 0) return a / b;
        return 8'hff;
    endfunction
    function automatic bit [7:0] e2_mod(bit [7:0] a, bit [7:0] b);
        return (b != 0) ? a % b : 8'd0;
    endfunction
    function automatic bit signed [7:0] e2_sdiv(bit signed [7:0] a, bit signed [7:0] b);
        if (b != 0) return a / b;
        return 0;
    endfunction
    function automatic bit signed [7:0] e2_smod(bit signed [7:0] a, bit signed [7:0] b);
        if (b != 0) return a % b;
        return 0;
    endfunction

    // E3: bitwise
    function automatic bit [7:0] e3_bits(bit [7:0] a, bit [7:0] b);
        return (a & b) | (~a ^ b);
    endfunction

    // E4, E5: shifts
    function automatic bit [7:0] e4_shl(bit [7:0] a, bit [3:0] n);
        return a << n;
    endfunction
    function automatic bit [7:0] e4_shr(bit [7:0] a, bit [3:0] n);
        return a >> n;
    endfunction
    function automatic bit [7:0] e5_ashr(bit signed [7:0] a, bit [3:0] n);
        return a >>> n;
    endfunction
    function automatic bit [11:0] e5_ashr_ext(bit signed [7:0] a, bit [3:0] n);
        return a >>> n;                    // extended to 12 bits before the shift
    endfunction
    function automatic bit [7:0] e5_ashr_unsigned(bit [7:0] a, bit [3:0] n);
        return a >>> n;                    // unsigned operand: logical
    endfunction

    // E6: comparison signedness
    function automatic bit [3:0] e6_cmp(bit signed [7:0] a, bit [7:0] b, bit signed [7:0] c);
        return {a < b, a < c, a >= c, a == c};
    endfunction

    // E7, E8: logical and reduction
    function automatic bit [2:0] e7_logic(bit [3:0] a, bit [3:0] b);
        return {a && b, a || b, !a};
    endfunction
    function automatic bit [5:0] e8_red(bit [4:0] a);
        return {&a, |a, ^a, ~&a, ~|a, ~^a};
    endfunction

    // E9: conditional
    function automatic bit [7:0] e9_sel(bit [1:0] c, bit [7:0] a, bit [7:0] b);
        return c ? a : b + 8'd1;
    endfunction

    // E10: concatenation and replication
    function automatic bit [15:0] e10_cat(bit [3:0] a, bit [3:0] b);
        return {a, b, {2{a[1:0]}}, 4'h9};
    endfunction

    // E11, E12, E13: bit, part and indexed part selects (out of range reads 0)
    function automatic bit [3:0] e11_bit(bit [7:0] x, bit [2:0] i, int j);
        return {x[3], x[i], x[j], x[7]};
    endfunction
    function automatic bit [7:0] e12_part(bit [15:0] x);
        return {x[11:8], x[3:0]};
    endfunction
    function automatic bit [3:0] e13_idx_up(bit [15:0] x, int i);
        return x[i +: 4];
    endfunction
    function automatic bit [3:0] e13_idx_dn(bit [15:0] x, bit [4:0] i);
        return x[i -: 4];
    endfunction

    // E14: size and sign casts
    function automatic bit [15:0] e14_cast(bit signed [3:0] a, bit [3:0] b);
        return {8'(a), 8'(b)};             // a size cast keeps a's signedness
    endfunction
    function automatic bit [7:0] e14_signed(bit [3:0] a);
        return 8'(signed'(a));
    endfunction
    function automatic bit [3:0] e14_trunc(bit [11:0] a);
        return 4'(a >> 4);
    endfunction

    // E15, E16: packed struct fields and patterns
    function automatic bit [7:0] e15_field(s8_t s);
        s8_t t;
        t = s;
        t.mid = s.hi[2:0];
        t.lo = ~s.lo;
        return {t.hi, t.mid, t.lo};
    endfunction
    function automatic s8_t e16_pat(bit [3:0] h, bit [2:0] m);
        return '{hi: h, mid: m, lo: 1'b1};
    endfunction

    // E17, E18: unpacked arrays (out of bounds: read 0, write nothing)
    function automatic bit [7:0] e17_tbl(bit [2:0] i);
        return TBL[i];
    endfunction
    function automatic bit [7:0] e18_arr(bit [7:0] a0, bit [7:0] a1, bit [1:0] wi, bit [1:0] ri);
        bit [7:0] arr [3];
        arr[0] = a0;
        arr[1] = a1;
        arr[2] = a0 ^ a1;
        arr[wi] = 8'hee;
        return arr[ri];
    endfunction

    // E19: calls
    function automatic bit [7:0] e19_call(bit [7:0] x);
        return e1_add(e3_bits(x, 8'h0f), 8'd3);
    endfunction

    // E20: an unsized literal makes the context 32 bits wide
    function automatic bit [7:0] e20_lit(bit [7:0] x);
        return (x + 1) >> 1;               // x = 255: 256 >> 1 = 128, no wrap
    endfunction

    // T5: packed array elements
    function automatic bit [7:0] t5_pk(bit [31:0] w, bit [1:0] i);
        bit [3:0][7:0] p;
        p = w;
        p[0] = p[3];
        return p[i];
    endfunction

    // T6: enum
    function automatic bit [1:0] t6_enum(bit [1:0] x);
        e_t e;
        e = e_t'(x);
        case (e)
            A:       return 2'd3;
            B, C:    return 2'(e) + 2'd1;
            default: return 2'd0;
        endcase
    endfunction

    // S3: case, first match wins
    function automatic bit [3:0] s3_case(bit [3:0] x);
        bit [3:0] r;
        case (x)
            4'd0:       r = 4'd1;
            4'd1, 4'd2: r = 4'd2;
            4'd2:       r = 4'd9;
            default:    r = x;
        endcase
        return r;
    endfunction

    // S4: constant-bound loops
    function automatic bit [3:0] s4_pop(bit [7:0] x);
        bit [3:0] n = 0;
        for (int i = 0; i < 8; i++)
            if (x[i]) n++;
        return n;
    endfunction
    function automatic bit [7:0] s4_rev(bit [7:0] x);
        bit [7:0] r;
        for (int i = 7; i >= 0; i -= 1)
            r[7 - i] = x[i];
        return r;
    endfunction

    // S6: early return and return through the function name
    function automatic bit [7:0] s6_early(bit [7:0] x);
        if (x == 0) return 8'd1;
        if (x[0]) begin
            x += 8'd2;
            return x;
        end
        s6_early = x * 8'd3;
    endfunction

    // S8: increment and compound assignment
    function automatic bit [7:0] s8_ops(bit [7:0] x);
        x++;
        x += 3;
        x <<= 1;
        x ^= 8'h55;
        return x;
    endfunction

endpackage
