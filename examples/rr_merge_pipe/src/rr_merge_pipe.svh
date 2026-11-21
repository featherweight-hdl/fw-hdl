// The feasibility vehicle (docs/design/micro-pipelining-feasibility.md §3):
// a map on each input, rr_merge unchanged, and a map on the output.
//
//   in[0..N-1] --> min (f_in, N lanes) --> merge (rr_merge) --> mout (f_out) --> out
//
// As written (variant v0) both maps are comb, so the comb paths run from the
// input pins through f_in and the arbiter to the FIFO, and from out.ready
// through f_out's ready, the FIFO and the arbiter back to the input pins.
// Latency in -> out: one edge (the FIFO's output register).
class rr_merge_pipe #(type TI = pipe_in8_t, type TM = pipe_mid8_t, int N = 4, int DEPTH = 2)
        extends fw_component;
    typedef rr_merge_pipe #(TI, TM, N, DEPTH) this_t;
    `fw_component_param_utils(this_t)

    fw_rv_sp_in  #(TI) in[N];
    fw_rv_sp_out #(TM) out;

    pipe_map_in #(TI, TM, N)  min;
    rr_merge #(TM, N, DEPTH)  merge;
    pipe_map_out #(TM)        mout;

    function void build();
        foreach (in[i]) in[i] = new(null, $sformatf("in[%0d]", i), this);
        out   = new(null, "out", this);
        min   = pipe_map_in #(TI, TM, N)::type_id::create("min", this);
        merge = rr_merge #(TM, N, DEPTH)::type_id::create("merge", this);
        mout  = pipe_map_out #(TM)::type_id::create("mout", this);
    endfunction

    function void connect();
        foreach (in[i]) begin
            min.in[i].connect_up(in[i]);
            min.out[i].connect(merge.in[i]);
        end
        merge.out.connect(mout.in);
        mout.out.connect_up(out);
    endfunction
endclass
