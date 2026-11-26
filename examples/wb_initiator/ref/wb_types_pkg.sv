// Vendored from fw-proto-wb (src/wb_types_pkg.sv, the working tree on 2026-11-21: commit 0e535ea plus
// uncommitted edits). The request and response beats of both the classes (src/) and the
// reference core.
// Wishbone bus payload types -- a SEPARATE, synthesizable package so BOTH the
// class layer (wb_proto_pkg) and the signal-level transactor modules/cores can
// share one definition of the request/response structs. It contains ONLY
// localparams and packed structs (no classes, no queues), so yosys can read it
// for the back-to-back formal proof. (A bare `.svh` of typedefs would collide at
// $unit scope when included by several compilation units; a package is the
// SV-correct way to share types.)
package wb_types_pkg;

    // Fixed widths for the first cut (design O-1): 32-bit port, byte granularity.
    // Widening is a change here plus the localparams below -- not an API change.
    localparam int unsigned WB_AW = 32;          // address width
    localparam int unsigned WB_DW = 32;          // data width
    localparam int unsigned WB_SW = WB_DW / 8;   // SEL width (byte granularity)

    // Request beat: everything the master drives, qualified by STB (RULE 3.60).
    // NOTE (impl deviation from design O-4): tags are OMITTED while disabled --
    // a 0-width packed member (`logic [WB_TW-1:0]` with WB_TW==0) is illegal SV,
    // so tags are added as real fields only when a tagged variant is built.
    typedef struct packed {
        logic [WB_AW-1:0] adr;       // address
        logic [WB_DW-1:0] dat;       // WRITE data (don't-care on reads)
        logic [WB_SW-1:0] sel;       // byte/granule selects
        logic             we;        // 1=write, 0=read
        logic             cyc_hold;  // keep CYC_O asserted after this beat's ACK
                                     //   (block/RMW chaining); 0 => classic single
    } wb_req_t;

    // Response beat: ACK is implicit (a completed xfer with !err && !rty);
    // RULE 3.45 makes the three terminations mutually exclusive.
    typedef struct packed {
        logic [WB_DW-1:0] dat;       // READ data (valid at termination, RULE 3.65)
        logic             err;       // ERR termination
        logic             rty;       // RTY termination
    } wb_rsp_t;

    // Monitor record: one completed phase (request + its response).
    typedef struct packed {
        wb_req_t req;
        wb_rsp_t rsp;
    } wb_xfer_t;

    // Packed widths carried over the internal ready/valid links. Computed
    // explicitly (not via $bits(type), which yosys's reader rejects) so the same
    // package reads cleanly under read_verilog -formal for the back-to-back proof.
    localparam int unsigned WB_REQ_W  = WB_AW + WB_DW + WB_SW + 1 /*we*/ + 1 /*cyc_hold*/;
    localparam int unsigned WB_RSP_W  = WB_DW + 1 /*err*/ + 1 /*rty*/;
    localparam int unsigned WB_XFER_W = WB_REQ_W + WB_RSP_W;

endpackage
