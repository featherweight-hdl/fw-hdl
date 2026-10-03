// Derived from XLS xls/examples/gcd.x (see orig/), Copyright The XLS Authors,
// Apache-2.0 (see ../NOTICE). A line-for-line port to the fw-hdl static
// subset; README.md lists the deviations.

package gcd_pkg;

    // DSLX's parametric functions (`<N: u32, DN: u32 = {N * u32:2}>`) are
    // static functions of a parameterized class.
    class gcd_c #(int unsigned N = 8, int unsigned DN = N * 2);
        typedef xls_std_pkg::div_mod_c #(N, N) div_mod_t;

        // The tuple (uN[N], uN[N], uN[N]) of gcd_binary_match.
        typedef struct packed {
            bit [N-1:0] a;
            bit [N-1:0] b;
            bit [N-1:0] d;
        } abd_t;

        // https://en.wikipedia.org/wiki/Greatest_common_divisor#Euclidean_algorithm
        static function bit [N-1:0] gcd_euclidean(bit [N-1:0] a, bit [N-1:0] b);
            for (int i = 0; i < DN; i++) begin
                if (b == '0) begin
                    // (a, b)
                end else begin
                    bit [N-1:0] r = div_mod_t::iterative_div_mod(a, b).r;
                    a = b;
                    b = r;
                end
            end
            return a;
        endfunction

        static function abd_t gcd_binary_match(bit [N-1:0] a, bit [N-1:0] b, bit [N-1:0] d);
            abd_t r;
            case ({a[0], b[0]})
                2'b01: r = '{a: b, b: a >> 1, d: d};
                2'b10: r = '{a: a, b: b >> 1, d: d};
                2'b00: r = '{a: a >> 1, b: b >> 1, d: d + 1'b1};
                2'b11: r = '{a: (a - b) >> 1, b: b, d: d};
            endcase
            return r;
        endfunction

        // https://en.wikipedia.org/wiki/Greatest_common_divisor#Binary_GCD_algorithm
        static function bit [N-1:0] gcd_binary(bit [N-1:0] a, bit [N-1:0] b);
            abd_t s = '{a: a, b: b, d: '0};
            for (int i = 0; i < DN; i++) begin
                if (s.a == s.b)
                    ;
                else if (s.a < s.b)
                    s = gcd_binary_match(s.b, s.a, s.d);
                else
                    s = gcd_binary_match(s.a, s.b, s.d);
            end
            return s.a << s.d;
        endfunction
    endclass

    // The width upstream's tests use (u8). Not in gcd.x: a DSLX test calls
    // the parametric functions directly, which SV cannot.
    function automatic bit [7:0] gcd_euclidean8(bit [7:0] a, bit [7:0] b);
        return gcd_c#(8)::gcd_euclidean(a, b);
    endfunction

    function automatic bit [7:0] gcd_binary8(bit [7:0] a, bit [7:0] b);
        return gcd_c#(8)::gcd_binary(a, b);
    endfunction

endpackage
