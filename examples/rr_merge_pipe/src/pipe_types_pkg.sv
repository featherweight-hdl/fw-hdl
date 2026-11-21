// The beat types of rr_merge_pipe, apart from the classes so that the RTL
// testbench can use them without the fw-hdl class library.
package pipe_types_pkg;
    // Beats, one pair per width W of a, b, c (8, 16, 32). `tag` passes
    // through both maps untouched: the testbench puts {source, seq} there.
    // rr_merge needs a `last` field.
    typedef struct packed {
        logic [7:0]  tag;
        logic [7:0]  a, b, c;
        logic        last;
    } pipe_in8_t;
    typedef struct packed {
        logic [7:0]  tag;
        logic [15:0] y;
        logic        last;
    } pipe_mid8_t;
    typedef struct packed {
        logic [7:0]  tag;
        logic [15:0] a, b, c;
        logic        last;
    } pipe_in16_t;
    typedef struct packed {
        logic [7:0]  tag;
        logic [31:0] y;
        logic        last;
    } pipe_mid16_t;
    typedef struct packed {
        logic [7:0]  tag;
        logic [31:0] a, b, c;
        logic        last;
    } pipe_in32_t;
    typedef struct packed {
        logic [7:0]  tag;
        logic [63:0] y;
        logic        last;
    } pipe_mid32_t;
    // Between the stages of f_in cut in two (K = 2): p = a * b, then y = p + c.
    typedef struct packed {
        logic [7:0]  tag;
        logic [15:0] p;
        logic [7:0]  c;
        logic        last;
    } pipe_prod8_t;
    typedef struct packed {
        logic [7:0]  tag;
        logic [31:0] p;
        logic [15:0] c;
        logic        last;
    } pipe_prod16_t;
    typedef struct packed {
        logic [7:0]  tag;
        logic [63:0] p;
        logic [31:0] c;
        logic        last;
    } pipe_prod32_t;
endpackage
