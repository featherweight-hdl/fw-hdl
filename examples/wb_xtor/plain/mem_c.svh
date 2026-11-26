// mem_c: the target's API implementation, a word memory; under +rand,
// 0-2 wait states per access; +mut_mem corrupts read data. Like a UVM
// responder, it only implements the API; the bench gives it to the
// target's bridge with set_p().
class mem_c implements wb_api_pkg::wb_if #(32, 32);
    typedef wb_api_pkg::wb_if #(32, 32)::req_t req_t;
    typedef wb_api_pkg::wb_if #(32, 32)::rsp_t rsp_t;

    local bit [31:0]              m[bit [31:0]];
    local virtual wb_plain_clk_if ck;

    function new(virtual wb_plain_clk_if c);
        ck = c;
    endfunction

    virtual task access(output rsp_t rsp, input req_t req);
        if ($test$plusargs("rand")) repeat ($urandom_range(2)) @(posedge ck.clk);
        rsp.err = 0;
        rsp.dat = 0;
        if (req.we) m[req.adr] = req.dat;
        else if (m.exists(req.adr)) rsp.dat = m[req.adr];
        if (!req.we && $test$plusargs("mut_mem")) rsp.dat ^= 32'h1;
    endtask
endclass
