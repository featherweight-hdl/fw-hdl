// Ready/valid kit test, class layer: a driver, a sink and an observer over the
// kit in src/std/rv (fw_rv_pkg). The payload type is chosen at compile time:
//   default         logic [31:0]
//   +define+RV_W8   logic [7:0]
//   +define+RV_STRUCT a packed struct
`include "fw_rv_macros.svh"

package rv_proto_pkg;
    import fw_hdl_pkg::*;
    import fw_rv_pkg::*;

`ifdef RV_STRUCT
    typedef struct packed {
        logic [3:0]  tag;
        logic [11:0] value;
        logic        last;
    } data_t;
`elsif RV_W8
    typedef logic [7:0]  data_t;
`else
    typedef logic [31:0] data_t;
`endif
    localparam int unsigned N = 8;

    // Beat i of the stream, distinct for each i at every payload type.
    function automatic data_t beat(int unsigned i);
`ifdef RV_STRUCT
        data_t b;
        b.tag = 4'(i); b.value = 12'h0a0 + 12'(i); b.last = (i == N - 1);
        return b;
`else
        return data_t'(32'hcafe_0000 + i);
`endif
    endfunction

    `include "driver.svh"
    `include "sink.svh"
    `include "observer.svh"
    `include "rv_top.svh"
endpackage
