// Canary: Euclid's GCD written the same way as
// gcd_zdc.py's Gcd, so the SV and zuspec-dataclasses front ends can be
// compared node for node. The example's gcd_pkg::gcd_euclidean8 calls
// iterative_div_mod instead of `%`, which is a different program.
package gcd_canary_pkg;

    function automatic bit [7:0] gcd_euclidean(bit [7:0] a, bit [7:0] b);
        // The static subset has no `while`; this `for` desugars to
        // `int i = 0; while (i < 16) begin ... i = i + 1; end`.
        for (int i = 0; i < 16; i = i + 1) begin
            if (b == 0) begin
            end else begin
                bit [7:0] r = a % b;
                a = b;
                b = r;
            end
        end
        return a;
    endfunction

    function automatic bit [7:0] gcd_euclidean8(bit [7:0] a, bit [7:0] b);
        return gcd_euclidean(a, b);
    endfunction

endpackage
