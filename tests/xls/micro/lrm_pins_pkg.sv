// Constructs where Verilator 5.049 does not follow the LRM, so the
// Verilator-based suites can't check them. test_micro_fn.py pins each one
// against hand-computed LRM values (interpreter and XLS only).
package lrm_pins_pkg;

    // A 1-bit operand with the unsized literal 1 is 32 bits wide (LRM 11.6.1):
    // b ~^ 1 is 'hffff_fffe or 'hffff_ffff, never 0, so the condition is true.
    // Verilator evaluates these at 1 bit when they are a ?: or if condition.
    function automatic bit [7:0] c_xnor(bit b);
        return (b ~^ 1) ? 8'd7 : 8'd3;
    endfunction

    function automatic bit [7:0] c_not_xor(bit b);
        return (~(b ^ 1)) ? 8'd7 : 8'd3;
    endfunction

    function automatic bit [7:0] c_if_xnor(bit b);
        if (b ~^ 1)
            return 8'd7;
        return 8'd3;
    endfunction

    // The two functions the 100k fuzz campaign flagged (seed 9001, batches 50
    // and 89), verbatim.
    function automatic bit signed [31:0] fz973(bit [30:0] a0);
        return ((signed'((a0 ? a0 : a0)) >> ((1 ~^ a0[10]) ? (~^a0) : (18'sh2bc42 != 15'sh2133))) >>> 21'(a0));
    endfunction

    function automatic bit signed [8:0] fz174(bit signed [11:0] a0, bit [15:0] a1, bit [1:0] a2);
        return ((((a0 & a1) >= {1{7'ha}}) ~^ 1) ? ({1{(a1[3] && a2)}} + (|(+a1))) : {((a1 || a0) << (a0 || a2[1:0])), {2{a0[6:0]}}, ((~&a1) + (a0[7:1] ? a0 : a0[4]))});
    endfunction

endpackage
