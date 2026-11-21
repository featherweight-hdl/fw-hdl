// More of the answer key (§3.4): a skid buffer for a connection, and the
// output map pipelined.

// A skid buffer: the realization `skid` of a connection (no function).
// in.ready is a register (no skid entry held), so it cuts the ready chain
// through the connection; one beat per cycle; latency one edge.
class pipe_skid #(type T = pipe_mid8_t) extends fw_component
        implements fw_combinational, fw_steppable;
    typedef pipe_skid #(T) this_t;
    `fw_component_param_utils(this_t)

    (* fw_sp_comb = "ready" *)       fw_rv_sp_in  #(T) in;
    (* fw_sp_comb = "valid, data" *) fw_rv_sp_out #(T) out;

    bit s1_v;
    T   s1_d;
    bit s1_sv;
    T   s1_sd;

    function void build();
        in  = new(null, "in", this);
        out = new(null, "out", this);
    endfunction

    virtual function void comb();
        out.set_valid(s1_v);
        out.set_data(s1_d);
        in.set_ready(!s1_sv);
    endfunction

    virtual function void step();
        if (in_reset()) begin
            s1_v  = 0;
            s1_sv = 0;
            return;
        end
        if (!s1_v || out.get_ready()) begin
            if (s1_sv) begin
                s1_v  = 1;
                s1_d  = s1_sd;
                s1_sv = 0;
            end else begin
                s1_v = in.get_valid();
                s1_d = in.get_data();
            end
        end else if (in.get_valid() && !s1_sv) begin
            s1_sv = 1;
            s1_sd = in.get_data();
        end
    endfunction
endclass

// f_out with a stall register after it (out-1: pipelined after the merge).
class pipe_map_out_stall1 #(type TM = pipe_mid8_t) extends fw_component
        implements fw_combinational, fw_steppable;
    typedef pipe_map_out_stall1 #(TM) this_t;
    `fw_component_param_utils(this_t)

    (* fw_sp_comb = "ready" *)       fw_rv_sp_in  #(TM) in;
    (* fw_sp_comb = "valid, data" *) fw_rv_sp_out #(TM) out;

    bit s1_v;
    TM  s1_d;

    function void build();
        in  = new(null, "in", this);
        out = new(null, "out", this);
    endfunction

    function TM f(TM x);
        TM y;
        y.tag  = x.tag;
        y.y    = x.y ^ (x.y >> 3);
        y.last = x.last;
        return y;
    endfunction

    virtual function void comb();
        out.set_valid(s1_v);
        out.set_data(s1_d);
        in.set_ready(!s1_v || out.get_ready());
    endfunction

    virtual function void step();
        if (in_reset()) begin
            s1_v = 0;
            return;
        end
        if (!s1_v || out.get_ready()) begin
            s1_v = in.get_valid();
            s1_d = f(in.get_data());
        end
    endfunction
endclass

// rr_merge with the arbiter -> FIFO connection realized `skid` (§3.4 skid):
// the classes are rr_merge's; only the wiring adds the skid.
class rr_merge_skid #(type T = rr_beat_t, int N = 4, int DEPTH = 2) extends fw_component;
    typedef rr_merge_skid #(T, N, DEPTH) this_t;
    `fw_component_param_utils(this_t)

    fw_rv_sp_in  #(T) in[N];
    fw_rv_sp_out #(T) out;

    rr_arbiter #(T, N)  arb;
    pipe_skid #(T)      skid;
    rr_fifo #(T, DEPTH) fifo;

    function void build();
        foreach (in[i]) in[i] = new(null, $sformatf("in[%0d]", i), this);
        out  = new(null, "out", this);
        arb  = rr_arbiter #(T, N)::type_id::create("arb", this);
        skid = pipe_skid #(T)::type_id::create("skid", this);
        fifo = rr_fifo #(T, DEPTH)::type_id::create("fifo", this);
    endfunction

    function void connect();
        foreach (in[i]) arb.in[i].connect_up(in[i]);
        arb.out.connect(skid.in);
        skid.out.connect(fifo.in);
        fifo.out.connect_up(out);
    endfunction
endclass
