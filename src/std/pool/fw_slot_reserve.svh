// fw_slot_reserve -- admission against N slots: a request reserves k of
// them, and a release frees them. It counts slots, it does not name them.
//
//   rsv  {k, value}: reserve k slots (fw_get_nb_if);
//   gnt  {k, value}, valid-only: the reservation made (fw_valid_put_if);
//   rel  k: free k slots (fw_get_nb_if, always taken).
//
// k is 1 to K, and K <= N. T is the value a request carries through, so the
// class can sit in-line and admit a stream; T = bit for a bare request.
//
// A step cannot look at a request without taking it, so the class holds
// one: rsv is ready while the hold is empty or is granted this cycle.
//
// Per cycle (step):
//   observes  the free count and the hold at the start of the cycle;
//   consumes  at most one request and one release;
//   grant     in order. The held request is granted once k slots are free;
//             a request taken with the hold empty is granted in the same
//             cycle if k are free, else held. While a request is held,
//             rsv is not ready, so the requests behind it wait even if they
//             are smaller, and a full reserve back-pressures the requester;
//   release   frees its slots from the next cycle;
//   misuse    a release of more slots than are reserved frees them all;
//   same-cycle valid  never decides a grant: rsv's ready is a function of
//             registered state, and rel is always ready, so a release never
//             waits behind a request.
// The grant is valid-only because the class never stalls; a stalling grant
// would hold up releases too. At reset all N slots are free.
class fw_slot_reserve #(int N = 16, int K = 4, type T = bit) extends fw_component
        implements fw_steppable;
    localparam int KB = $clog2(K + 1);
    localparam int CB = $clog2(N + 1);
    localparam int W = $bits(T);

    fw_port #(fw_get_nb_if #(bit [KB+W-1:0]))    rsv;
    fw_port #(fw_valid_put_if #(bit [KB+W-1:0])) gnt;
    fw_port #(fw_get_nb_if #(bit [KB-1:0]))      rel;

    // Slots reserved and not yet freed; the held request.
    protected bit [CB-1:0]   m_used;
    protected bit [KB+W-1:0] m_hold;
    protected bit            m_hv;

    function new(string name, fw_component parent);
        super.new(name, parent);
        add_steppable(this);
    endfunction

    function void build();
        rsv = new("rsv", this);
        gnt = new("gnt", this);
        rel = new("rel", this);
    endfunction

    virtual function void step();
        bit [KB+W-1:0] x, g;
        bit [KB-1:0]   r;
        bit [CB-1:0]   fr, add, sub;
        bit            gv, rdy, hv;
        fr = CB'(N) - m_used;
        if (m_hv && fr >= CB'(m_hold[KB+W-1:W])) begin
            gv = 1'b1;
            g = m_hold;
        end
        rdy = !m_hv || gv;
        hv = m_hv && !gv;
        if (rdy && rsv.t.try_get(x)) begin
            if (!gv && fr >= CB'(x[KB+W-1:W])) begin
                gv = 1'b1;
                g = x;
            end else begin
                m_hold = x;
                hv = 1'b1;
            end
        end
        m_hv = hv;
        if (gv) begin
            gnt.t.put(g);
            add = CB'(g[KB+W-1:W]);
        end
        if (rel.t.try_get(r))
            sub = (CB'(r) > m_used) ? m_used : CB'(r);
        m_used = m_used + add - sub;
    endfunction
endclass
