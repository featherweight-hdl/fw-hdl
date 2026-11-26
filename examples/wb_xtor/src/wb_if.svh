// The transaction-level API: one access and its response, with the payload
// types (wb_macros.svh). The bus has one access in flight, so a blocking
// call is enough. Outputs lead.
interface class wb_if #(int AW = 32, int DW = 32);
    typedef `wb_req_t(AW, DW) req_t;
    typedef `wb_rsp_t(DW)     rsp_t;
    pure virtual task access(output rsp_t rsp, input req_t req);
endclass
