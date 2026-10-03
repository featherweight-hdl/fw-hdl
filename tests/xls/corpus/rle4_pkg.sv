// One specialization per file (T7: the typedef names the specialization).
// They are separate because Verilator 5.049 gives both specializations' port
// payload the same `pkt_t` (the W=4 one, 12 bits) when both are elaborated in
// one build with the fw port/export classes; compiled alone, each is right.
package rle4_pkg;
    typedef rle_pkg::rle_enc #(4) rle_enc4_t;
endpackage
