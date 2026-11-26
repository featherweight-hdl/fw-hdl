// drv_c: makes N accesses through the initiator's API (writes, then reads
// of the same addresses) and checks the read data; under +rand, idles
// 0-2 edges between accesses. Like a UVM driver, it only holds the API.
class drv_c;
    typedef wb_api_pkg::wb_if #(32, 32) api_t;
    typedef api_t::req_t req_t;
    typedef api_t::rsp_t rsp_t;

    local api_t                   api;
    local virtual wb_plain_clk_if ck;
    int                           edges;    // edges taken by the N accesses
    string                        err;      // the first mismatch; "" if none

    function new(api_t a, virtual wb_plain_clk_if c);
        api = a;
        ck = c;
    endfunction

    static function bit [31:0] data(int i);
        return 32'h1000_0000 * (i % 4 + 1) + i;
    endfunction

    task run();
        bit rnd = $test$plusargs("rand");
        int t0 = 0;
        @(posedge ck.clk);
        fork forever @(posedge ck.clk) t0++; join_none
        for (int i = 0; i < N; i++) begin
            req_t q;
            rsp_t r;
            bit w = i < N / 2;
            q.adr = 32'(4 * (i % (N / 2)));
            q.dat = w ? data(i) : 32'h0;
            q.sel = 4'hf;
            q.we  = w;
            api.access(r, q);
            if (!w && err == "" && (r.err || r.dat != data(i - N / 2)))
                $sformat(err, "access %0d: read %h, expected %h", i, r.dat, data(i - N / 2));
            if (rnd) repeat ($urandom_range(2)) @(posedge ck.clk);
        end
        edges = t0;
    endtask
endclass
