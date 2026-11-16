// The merger: rr_arbiter into rr_fifo. Its ports are pass-throughs to the
// children's (connect_up), so it has no comb() or step() of its own.
//
//   in[0..N-1] --> arb --> fifo --> out
//
// Comb path, all in one time step: out.ready -> fifo.in.ready ->
// arb.in[g].ready. Latency in -> out: one edge (the FIFO's output register).
class rr_merge #(type T = rr_beat_t, int N = 4, int DEPTH = 2) extends fw_component;
    typedef rr_merge #(T, N, DEPTH) this_t;
    `fw_component_param_utils(this_t)

    fw_rv_sp_in  #(T) in[N];
    fw_rv_sp_out #(T) out;

    rr_arbiter #(T, N)  arb;
    rr_fifo #(T, DEPTH) fifo;

    function void build();
        foreach (in[i]) in[i] = new(null, $sformatf("in[%0d]", i), this);
        out  = new(null, "out", this);
        arb  = rr_arbiter #(T, N)::type_id::create("arb", this);
        fifo = rr_fifo #(T, DEPTH)::type_id::create("fifo", this);
    endfunction

    function void connect();
        foreach (in[i]) arb.in[i].connect_up(in[i]);
        arb.out.connect(fifo.in);
        fifo.out.connect_up(out);
    endfunction
endclass
