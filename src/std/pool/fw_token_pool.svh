// fw_token_pool -- N tokens (0 .. N-1), each held by at most one owner.
//
//   req  a value to tag: taken only while a token is free (fw_get_nb_if);
//   tok  {token, value}, valid-only: the token granted with the request's
//        value, in the cycle the request is taken (fw_valid_put_if);
//   rel  a token put back: always taken (fw_get_nb_if).
//
// T is the value a request carries through, so the pool can sit in-line and
// tag a stream; a bare allocator uses T = bit and ignores it.
//
// Per cycle (step):
//   observes  the free tokens at the start of the cycle;
//   consumes  at most one request and one release;
//   grant     the lowest free token. With none free, req is not ready, so
//             an exhausted pool back-pressures the requester;
//   release   the token is free from the next cycle, so it is never granted
//             in the cycle it comes back;
//   misuse    putting back a token that is free does nothing;
//   same-cycle valid  never decides a grant: req is ready while a token is
//             free and rel always, both functions of registered state, so a
//             release never waits behind a request.
// The grant is valid-only because the pool never stalls: a requester that
// asked takes its token. A stalling grant would hold up releases too.
//
// The lowest free token is found with a prefix OR in log2(N) steps, so the
// cycle stays shallow as N grows. At reset every token is free.
class fw_token_pool #(int N = 16, type T = bit) extends fw_component implements fw_steppable;
    localparam int TB = (N > 1) ? $clog2(N) : 1;
    localparam int W = $bits(T);

    fw_port #(fw_get_nb_if #(T))                 req;
    fw_port #(fw_valid_put_if #(bit [TB+W-1:0])) tok;
    fw_port #(fw_get_nb_if #(bit [TB-1:0]))      rel;

    // Token i is held.
    protected bit [N-1:0] m_held;

    function new(string name, fw_component parent);
        super.new(name, parent);
        add_steppable(this);
    endfunction

    function void build();
        req = new("req", this);
        tok = new("tok", this);
        rel = new("rel", this);
    endfunction

    virtual function void step();
        bit [N-1:0]  fr, m, oh, g, rm;
        bit [TB-1:0] sl, r;
        T            x;
        fr = ~m_held;
        if (|fr && req.t.try_get(x)) begin
            // The lowest free token: fr less every token above a free one.
            m = fr;
            for (int j = 0; j < TB; j++)
                m = m | (m << (1 << j));
            oh = fr & ~(m << 1);
            sl = '0;
            for (int i = 0; i < N; i++)
                sl = sl | (oh[i] ? TB'(i) : TB'(0));
            tok.t.put({sl, x});
            g = oh;
        end
        if (rel.t.try_get(r))
            for (int i = 0; i < N; i++)
                rm[i] = m_held[i] && r == TB'(i);
        m_held = (m_held & ~rm) | g;
    endfunction
endclass
