// A 2-bit beat for the controller proofs (F7): the controllers don't depend
// on the payload, so a small one keeps the proofs cheap; f (a * b + c) still
// runs on it.
package fv_types_pkg;
    typedef struct packed {
        logic [1:0] tag;
        logic       a, b, c;
        logic       last;
    } fv_in_t;
    typedef struct packed {
        logic [1:0] tag;
        logic [1:0] y;
        logic       last;
    } fv_mid_t;
endpackage
