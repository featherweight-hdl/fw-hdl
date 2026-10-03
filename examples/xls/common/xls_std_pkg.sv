// SV ports of the DSLX standard library (xls/dslx/stdlib/std.x) functions the
// examples call. Derived from XLS, Copyright The XLS Authors, Apache-2.0 (see
// ../NOTICE). A parametric DSLX function is a static function of a
// parameterized class; a DSLX tuple is a packed struct, fields in tuple order.

package xls_std_pkg;

    // std::iterative_div_mod<N, M>(n: uN[N], d: uN[M]) -> (uN[N], uN[M])
    // Unsigned division by long division; dividing by 0 gives all 1s for the
    // quotient and n for the remainder (as std.x documents).
    class div_mod_c #(int unsigned N = 32, int unsigned M = 32);
        typedef struct packed {
            bit [N-1:0] q;
            bit [M-1:0] r;
        } result_t;

        static function result_t iterative_div_mod(bit [N-1:0] n, bit [M-1:0] d);
            // Zero extend divisor by 1 bit.
            bit [M:0] divisor = (M+1)'(d);
            bit [N-1:0] q = '0;
            bit [M-1:0] r = '0;
            for (int i = 0; i < N; i++) begin
                // Shift the next bit of n into r.
                bit [M:0] r1 = {r, n[N - 1 - i]};
                if (r1 >= divisor) begin
                    q = {q[N-2:0], 1'b1};
                    r1 = r1 - divisor;
                end else begin
                    q = {q[N-2:0], 1'b0};
                end
                // Remove the MSB of r; guaranteed to be 0 because r < d.
                r = r1[M-1:0];
            end
            return '{q: q, r: r};
        endfunction
    endclass

    // std::rotr<N>(x: bits[N], y: bits[N]) -> bits[N]
    class rotr_c #(int unsigned N = 32);
        static function bit [N-1:0] rotr(bit [N-1:0] x, bit [N-1:0] y);
            bit [N-1:0] y_mod = y % N'(N);
            return (x >> y_mod) | (x << (N'(N) - y_mod));
        endfunction
    endclass

    // std::ceil_div<N>(x: uN[N], y: uN[N]) -> uN[N]
    class ceil_div_c #(int unsigned N = 32);
        static function bit [N-1:0] ceil_div(bit [N-1:0] x, bit [N-1:0] y);
            // DSLX defines x / 0 as all ones, so `usual` is all ones + 1 = 0
            // there. The static subset makes the divisor guard explicit (D-1).
            bit [N-1:0] usual = (y != 0) ? (x - 1'b1) / y + 1'b1 : '0;
            return (x > 0) ? usual : '0;
        endfunction
    endclass

    // std::round_up_to_nearest(x: u32, y: u32) -> u32
    function automatic bit [31:0] round_up_to_nearest(bit [31:0] x, bit [31:0] y);
        return 32'(ceil_div_c#(32)::ceil_div(x, y) * y);
    endfunction

endpackage
