// wb_macros.svh: the Wishbone payloads, as struct types of the bus's
// parameters. The API (wb_api_pkg::wb_if) declares its req_t and rsp_t with
// them; RTL that has no classes declares the same layout the same way, and
// packed structs of one layout assign to each other::
//
//     typedef `wb_req_t(32, 32) req_t;
//
// AW is the address width, DW the data width (a whole number of bytes);
// sel has one bit per byte.
`ifndef WB_MACROS_SVH
`define WB_MACROS_SVH

// One request: what the initiator drives, qualified by stb.
`define wb_req_t(AW, DW) \
    struct packed { \
        bit [(AW)-1:0]   adr; \
        bit [(DW)-1:0]   dat; \
        bit [(DW)/8-1:0] sel; \
        bit              we; \
    }

// One response: the read data and the termination (ack unless err).
`define wb_rsp_t(DW) \
    struct packed { \
        bit [(DW)-1:0] dat; \
        bit            err; \
    }

`endif
