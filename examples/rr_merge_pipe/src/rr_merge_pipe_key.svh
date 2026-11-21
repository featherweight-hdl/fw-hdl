// The answer-key composites (§3.4): rr_merge_pipe with one child swapped
// for its pipelined form. Every one has the same parameters (TP is unused
// where f_in is not cut in two) and the same ports, so the RTL bench runs
// each unchanged.

// f_in: stall, K = 1
class rr_merge_pipe_stall1 #(type TI = pipe_in8_t, type TP = pipe_prod8_t, type TM = pipe_mid8_t,
        int N = 4, int DEPTH = 2) extends fw_component;
    typedef rr_merge_pipe_stall1 #(TI, TP, TM, N, DEPTH) this_t;
    `fw_component_param_utils(this_t)

    fw_rv_sp_in  #(TI) in[N];
    fw_rv_sp_out #(TM) out;

    pipe_map_in_stall1 #(TI, TM, N) min;
    rr_merge #(TM, N, DEPTH) merge;
    pipe_map_out #(TM) mout;

    function void build();
        foreach (in[i]) in[i] = new(null, $sformatf("in[%0d]", i), this);
        out   = new(null, "out", this);
        min   = pipe_map_in_stall1 #(TI, TM, N)::type_id::create("min", this);
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

// f_in: stall, K = 2
class rr_merge_pipe_stall2 #(type TI = pipe_in8_t, type TP = pipe_prod8_t, type TM = pipe_mid8_t,
        int N = 4, int DEPTH = 2) extends fw_component;
    typedef rr_merge_pipe_stall2 #(TI, TP, TM, N, DEPTH) this_t;
    `fw_component_param_utils(this_t)

    fw_rv_sp_in  #(TI) in[N];
    fw_rv_sp_out #(TM) out;

    pipe_map_in_stall2 #(TI, TP, TM, N) min;
    rr_merge #(TM, N, DEPTH) merge;
    pipe_map_out #(TM) mout;

    function void build();
        foreach (in[i]) in[i] = new(null, $sformatf("in[%0d]", i), this);
        out   = new(null, "out", this);
        min   = pipe_map_in_stall2 #(TI, TP, TM, N)::type_id::create("min", this);
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

// f_in: elastic, K = 1
class rr_merge_pipe_elastic1 #(type TI = pipe_in8_t, type TP = pipe_prod8_t, type TM = pipe_mid8_t,
        int N = 4, int DEPTH = 2) extends fw_component;
    typedef rr_merge_pipe_elastic1 #(TI, TP, TM, N, DEPTH) this_t;
    `fw_component_param_utils(this_t)

    fw_rv_sp_in  #(TI) in[N];
    fw_rv_sp_out #(TM) out;

    pipe_map_in_elastic1 #(TI, TM, N) min;
    rr_merge #(TM, N, DEPTH) merge;
    pipe_map_out #(TM) mout;

    function void build();
        foreach (in[i]) in[i] = new(null, $sformatf("in[%0d]", i), this);
        out   = new(null, "out", this);
        min   = pipe_map_in_elastic1 #(TI, TM, N)::type_id::create("min", this);
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

// f_in: elastic, K = 2
class rr_merge_pipe_elastic2 #(type TI = pipe_in8_t, type TP = pipe_prod8_t, type TM = pipe_mid8_t,
        int N = 4, int DEPTH = 2) extends fw_component;
    typedef rr_merge_pipe_elastic2 #(TI, TP, TM, N, DEPTH) this_t;
    `fw_component_param_utils(this_t)

    fw_rv_sp_in  #(TI) in[N];
    fw_rv_sp_out #(TM) out;

    pipe_map_in_elastic2 #(TI, TP, TM, N) min;
    rr_merge #(TM, N, DEPTH) merge;
    pipe_map_out #(TM) mout;

    function void build();
        foreach (in[i]) in[i] = new(null, $sformatf("in[%0d]", i), this);
        out   = new(null, "out", this);
        min   = pipe_map_in_elastic2 #(TI, TP, TM, N)::type_id::create("min", this);
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

// f_in: credit, K = 1
class rr_merge_pipe_credit1 #(type TI = pipe_in8_t, type TP = pipe_prod8_t, type TM = pipe_mid8_t,
        int N = 4, int DEPTH = 2) extends fw_component;
    typedef rr_merge_pipe_credit1 #(TI, TP, TM, N, DEPTH) this_t;
    `fw_component_param_utils(this_t)

    fw_rv_sp_in  #(TI) in[N];
    fw_rv_sp_out #(TM) out;

    pipe_map_in_credit1 #(TI, TM, N) min;
    rr_merge #(TM, N, DEPTH) merge;
    pipe_map_out #(TM) mout;

    function void build();
        foreach (in[i]) in[i] = new(null, $sformatf("in[%0d]", i), this);
        out   = new(null, "out", this);
        min   = pipe_map_in_credit1 #(TI, TM, N)::type_id::create("min", this);
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

// f_in: credit, K = 2
class rr_merge_pipe_credit2 #(type TI = pipe_in8_t, type TP = pipe_prod8_t, type TM = pipe_mid8_t,
        int N = 4, int DEPTH = 2) extends fw_component;
    typedef rr_merge_pipe_credit2 #(TI, TP, TM, N, DEPTH) this_t;
    `fw_component_param_utils(this_t)

    fw_rv_sp_in  #(TI) in[N];
    fw_rv_sp_out #(TM) out;

    pipe_map_in_credit2 #(TI, TP, TM, N) min;
    rr_merge #(TM, N, DEPTH) merge;
    pipe_map_out #(TM) mout;

    function void build();
        foreach (in[i]) in[i] = new(null, $sformatf("in[%0d]", i), this);
        out   = new(null, "out", this);
        min   = pipe_map_in_credit2 #(TI, TP, TM, N)::type_id::create("min", this);
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

// arb.out -> fifo.in realized skid
class rr_merge_pipe_skid #(type TI = pipe_in8_t, type TP = pipe_prod8_t, type TM = pipe_mid8_t,
        int N = 4, int DEPTH = 2) extends fw_component;
    typedef rr_merge_pipe_skid #(TI, TP, TM, N, DEPTH) this_t;
    `fw_component_param_utils(this_t)

    fw_rv_sp_in  #(TI) in[N];
    fw_rv_sp_out #(TM) out;

    pipe_map_in #(TI, TM, N) min;
    rr_merge_skid #(TM, N, DEPTH) merge;
    pipe_map_out #(TM) mout;

    function void build();
        foreach (in[i]) in[i] = new(null, $sformatf("in[%0d]", i), this);
        out   = new(null, "out", this);
        min   = pipe_map_in #(TI, TM, N)::type_id::create("min", this);
        merge = rr_merge_skid #(TM, N, DEPTH)::type_id::create("merge", this);
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

// f_out: stall, K = 1 (after the merge)
class rr_merge_pipe_out1 #(type TI = pipe_in8_t, type TP = pipe_prod8_t, type TM = pipe_mid8_t,
        int N = 4, int DEPTH = 2) extends fw_component;
    typedef rr_merge_pipe_out1 #(TI, TP, TM, N, DEPTH) this_t;
    `fw_component_param_utils(this_t)

    fw_rv_sp_in  #(TI) in[N];
    fw_rv_sp_out #(TM) out;

    pipe_map_in #(TI, TM, N) min;
    rr_merge #(TM, N, DEPTH) merge;
    pipe_map_out_stall1 #(TM) mout;

    function void build();
        foreach (in[i]) in[i] = new(null, $sformatf("in[%0d]", i), this);
        out   = new(null, "out", this);
        min   = pipe_map_in #(TI, TM, N)::type_id::create("min", this);
        merge = rr_merge #(TM, N, DEPTH)::type_id::create("merge", this);
        mout  = pipe_map_out_stall1 #(TM)::type_id::create("mout", this);
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
