// The answer key (docs/design/micro-pipelining-feasibility.md §3.4, F3):
// pipe_map_in pipelined by hand, one class per controller and stage count.
// Each is what an engine should produce from pipe_map_in, written in today's
// sync style and lowered by today's flow, unchanged.
//
// Stage registers are named s<k>_v (valid) and s<k>_d (data), with s<k>_sv
// and s<k>_sd for an elastic stage's skid entry, so that generated stages
// can be paired with these by name. For K = 2, f is cut as
//   stage 1: p = a * b (TP carries c along),  stage 2: y = p + c.
//
// One class per K: the stage types differ with K (TM for K = 1; TP, TM for
// K = 2), and the flow has no generate-like way to vary a class's state.

// stall, K = 1: a register after f; out.ready -> in.ready stays comb.
class pipe_map_in_stall1 #(type TI = pipe_in8_t, type TM = pipe_mid8_t, int N = 4)
        extends fw_component implements fw_combinational, fw_steppable;
    typedef pipe_map_in_stall1 #(TI, TM, N) this_t;
    `fw_component_param_utils(this_t)

    (* fw_sp_comb = "ready" *)       fw_rv_sp_in  #(TI) in[N];
    (* fw_sp_comb = "valid, data" *) fw_rv_sp_out #(TM) out[N];

    bit s1_v[N];    // stage 1 holds a beat
    TM  s1_d[N];

    function void build();
        foreach (in[i]) in[i] = new(null, $sformatf("in[%0d]", i), this);
        foreach (out[i]) out[i] = new(null, $sformatf("out[%0d]", i), this);
    endfunction

    function TM f(TI x);
        TM y;
        y.tag  = x.tag;
        y.y    = x.a * x.b + x.c;
        y.last = x.last;
        return y;
    endfunction

    virtual function void comb();
        foreach (out[i]) out[i].set_valid(s1_v[i]);
        foreach (out[i]) out[i].set_data(s1_d[i]);
        foreach (in[i]) in[i].set_ready(!s1_v[i] || out[i].get_ready());
    endfunction

    virtual function void step();
        if (in_reset()) begin
            foreach (s1_v[i]) s1_v[i] = 0;
            return;
        end
        foreach (in[i]) begin
            if (!s1_v[i] || out[i].get_ready()) begin
                s1_v[i] = in[i].get_valid();
                s1_d[i] = f(in[i].get_data());
            end
        end
    endfunction
endclass

// stall, K = 2: one enable per lane (the last stage empty, or taken) moves
// every stage; a bubble in stage 1 is not squeezed out.
class pipe_map_in_stall2 #(type TI = pipe_in8_t, type TP = pipe_prod8_t,
                           type TM = pipe_mid8_t, int N = 4)
        extends fw_component implements fw_combinational, fw_steppable;
    typedef pipe_map_in_stall2 #(TI, TP, TM, N) this_t;
    `fw_component_param_utils(this_t)

    (* fw_sp_comb = "ready" *)       fw_rv_sp_in  #(TI) in[N];
    (* fw_sp_comb = "valid, data" *) fw_rv_sp_out #(TM) out[N];

    bit s1_v[N];
    TP  s1_d[N];
    bit s2_v[N];
    TM  s2_d[N];

    function void build();
        foreach (in[i]) in[i] = new(null, $sformatf("in[%0d]", i), this);
        foreach (out[i]) out[i] = new(null, $sformatf("out[%0d]", i), this);
    endfunction

    function TP f1(TI x);
        TP y;
        y.tag  = x.tag;
        y.p    = x.a * x.b;
        y.c    = x.c;
        y.last = x.last;
        return y;
    endfunction

    function TM f2(TP x);
        TM y;
        y.tag  = x.tag;
        y.y    = x.p + x.c;
        y.last = x.last;
        return y;
    endfunction

    virtual function void comb();
        foreach (out[i]) out[i].set_valid(s2_v[i]);
        foreach (out[i]) out[i].set_data(s2_d[i]);
        foreach (in[i]) in[i].set_ready(!s2_v[i] || out[i].get_ready());
    endfunction

    virtual function void step();
        if (in_reset()) begin
            foreach (s1_v[i]) s1_v[i] = 0;
            foreach (s2_v[i]) s2_v[i] = 0;
            return;
        end
        foreach (in[i]) begin
            if (!s2_v[i] || out[i].get_ready()) begin
                s2_v[i] = s1_v[i];
                s2_d[i] = f2(s1_d[i]);
                s1_v[i] = in[i].get_valid();
                s1_d[i] = f1(in[i].get_data());
            end
        end
    endfunction
endclass

// elastic, K = 1: f, then a skid stage. in.ready is a register (no skid
// entry held), so the ready chain is cut here.
class pipe_map_in_elastic1 #(type TI = pipe_in8_t, type TM = pipe_mid8_t, int N = 4)
        extends fw_component implements fw_combinational, fw_steppable;
    typedef pipe_map_in_elastic1 #(TI, TM, N) this_t;
    `fw_component_param_utils(this_t)

    (* fw_sp_comb = "ready" *)       fw_rv_sp_in  #(TI) in[N];
    (* fw_sp_comb = "valid, data" *) fw_rv_sp_out #(TM) out[N];

    bit s1_v[N];    // the stage's output register holds a beat
    TM  s1_d[N];
    bit s1_sv[N];   // the skid entry holds a beat (taken while out stalled)
    TM  s1_sd[N];

    function void build();
        foreach (in[i]) in[i] = new(null, $sformatf("in[%0d]", i), this);
        foreach (out[i]) out[i] = new(null, $sformatf("out[%0d]", i), this);
    endfunction

    function TM f(TI x);
        TM y;
        y.tag  = x.tag;
        y.y    = x.a * x.b + x.c;
        y.last = x.last;
        return y;
    endfunction

    virtual function void comb();
        foreach (out[i]) out[i].set_valid(s1_v[i]);
        foreach (out[i]) out[i].set_data(s1_d[i]);
        foreach (in[i]) in[i].set_ready(!s1_sv[i]);
    endfunction

    virtual function void step();
        if (in_reset()) begin
            foreach (s1_v[i]) s1_v[i] = 0;
            foreach (s1_sv[i]) s1_sv[i] = 0;
            return;
        end
        foreach (in[i]) begin
            if (!s1_v[i] || out[i].get_ready()) begin
                if (s1_sv[i]) begin
                    s1_v[i]  = 1;
                    s1_d[i]  = s1_sd[i];
                    s1_sv[i] = 0;
                end else begin
                    s1_v[i] = in[i].get_valid();
                    s1_d[i] = f(in[i].get_data());
                end
            end else if (in[i].get_valid() && !s1_sv[i]) begin
                s1_sv[i] = 1;
                s1_sd[i] = f(in[i].get_data());
            end
        end
    endfunction
endclass

// elastic, K = 2: two skid stages, f1 before the first and f2 before the
// second. Stage 2 is updated first, from stage 1's values before the edge;
// r1 (stage 2 takes a beat) is taken before either moves.
class pipe_map_in_elastic2 #(type TI = pipe_in8_t, type TP = pipe_prod8_t,
                             type TM = pipe_mid8_t, int N = 4)
        extends fw_component implements fw_combinational, fw_steppable;
    typedef pipe_map_in_elastic2 #(TI, TP, TM, N) this_t;
    `fw_component_param_utils(this_t)

    (* fw_sp_comb = "ready" *)       fw_rv_sp_in  #(TI) in[N];
    (* fw_sp_comb = "valid, data" *) fw_rv_sp_out #(TM) out[N];

    bit s1_v[N];
    TP  s1_d[N];
    bit s1_sv[N];
    TP  s1_sd[N];
    bit s2_v[N];
    TM  s2_d[N];
    bit s2_sv[N];
    TM  s2_sd[N];

    function void build();
        foreach (in[i]) in[i] = new(null, $sformatf("in[%0d]", i), this);
        foreach (out[i]) out[i] = new(null, $sformatf("out[%0d]", i), this);
    endfunction

    function TP f1(TI x);
        TP y;
        y.tag  = x.tag;
        y.p    = x.a * x.b;
        y.c    = x.c;
        y.last = x.last;
        return y;
    endfunction

    function TM f2(TP x);
        TM y;
        y.tag  = x.tag;
        y.y    = x.p + x.c;
        y.last = x.last;
        return y;
    endfunction

    virtual function void comb();
        foreach (out[i]) out[i].set_valid(s2_v[i]);
        foreach (out[i]) out[i].set_data(s2_d[i]);
        foreach (in[i]) in[i].set_ready(!s1_sv[i]);
    endfunction

    virtual function void step();
        if (in_reset()) begin
            foreach (s1_v[i]) s1_v[i] = 0;
            foreach (s1_sv[i]) s1_sv[i] = 0;
            foreach (s2_v[i]) s2_v[i] = 0;
            foreach (s2_sv[i]) s2_sv[i] = 0;
            return;
        end
        foreach (in[i]) begin
            bit r1;
            r1 = !s2_sv[i];
            // Stage 2: its input is stage 1 (valid s1_v, ready r1).
            if (!s2_v[i] || out[i].get_ready()) begin
                if (s2_sv[i]) begin
                    s2_v[i]  = 1;
                    s2_d[i]  = s2_sd[i];
                    s2_sv[i] = 0;
                end else begin
                    s2_v[i] = s1_v[i];
                    s2_d[i] = f2(s1_d[i]);
                end
            end else if (s1_v[i] && !s2_sv[i]) begin
                s2_sv[i] = 1;
                s2_sd[i] = f2(s1_d[i]);
            end
            // Stage 1: its output is taken when r1.
            if (!s1_v[i] || r1) begin
                if (s1_sv[i]) begin
                    s1_v[i]  = 1;
                    s1_d[i]  = s1_sd[i];
                    s1_sv[i] = 0;
                end else begin
                    s1_v[i] = in[i].get_valid();
                    s1_d[i] = f1(in[i].get_data());
                end
            end else if (in[i].get_valid() && !s1_sv[i]) begin
                s1_sv[i] = 1;
                s1_sd[i] = f1(in[i].get_data());
            end
        end
    endfunction
endclass

// credit, K = 1: stages that never stall (valid only), into a FIFO of
// D = K + 2 entries per lane; in.ready is a count of beats taken and not
// yet left (a register), so the ready chain is cut. D = K + 2 keeps one beat
// per cycle: a beat is counted from the edge that takes it to the edge it
// leaves the FIFO, K + 1 edges later.
class pipe_map_in_credit1 #(type TI = pipe_in8_t, type TM = pipe_mid8_t, int N = 4)
        extends fw_component implements fw_combinational, fw_steppable;
    typedef pipe_map_in_credit1 #(TI, TM, N) this_t;
    `fw_component_param_utils(this_t)

    localparam int D = 3;

    (* fw_sp_comb = "ready" *)       fw_rv_sp_in  #(TI) in[N];
    (* fw_sp_comb = "valid, data" *) fw_rv_sp_out #(TM) out[N];

    bit                   s1_v[N];
    TM                    s1_d[N];
    TM                    mem[N*D];   // lane i: mem[i*D +: D]
    bit [1:0]             wr[N], rd[N];
    bit [1:0]             fc[N];      // FIFO entries held
    bit [2:0]             cnt[N];     // beats taken and not yet left

    function void build();
        foreach (in[i]) in[i] = new(null, $sformatf("in[%0d]", i), this);
        foreach (out[i]) out[i] = new(null, $sformatf("out[%0d]", i), this);
    endfunction

    function TM f(TI x);
        TM y;
        y.tag  = x.tag;
        y.y    = x.a * x.b + x.c;
        y.last = x.last;
        return y;
    endfunction

    virtual function void comb();
        foreach (out[i]) out[i].set_valid(fc[i] != 0);
        foreach (out[i]) out[i].set_data(mem[i * D + rd[i]]);
        foreach (in[i]) in[i].set_ready(cnt[i] < D);
    endfunction

    virtual function void step();
        if (in_reset()) begin
            foreach (s1_v[i]) s1_v[i] = 0;
            foreach (wr[i]) wr[i] = 0;
            foreach (rd[i]) rd[i] = 0;
            foreach (fc[i]) fc[i] = 0;
            foreach (cnt[i]) cnt[i] = 0;
            return;
        end
        foreach (in[i]) begin
            bit take, pop, arrive;
            take   = in[i].get_valid() && cnt[i] < D;
            pop    = fc[i] != 0 && out[i].get_ready();
            arrive = s1_v[i];
            if (arrive) begin
                mem[i * D + wr[i]] = s1_d[i];
                wr[i] = (wr[i] + 1) % D;
            end
            if (pop) rd[i] = (rd[i] + 1) % D;
            fc[i]   = fc[i] + arrive - pop;
            cnt[i]  = cnt[i] + take - pop;
            s1_v[i] = take;
            s1_d[i] = f(in[i].get_data());
        end
    endfunction
endclass

// credit, K = 2: as credit1, with f cut in two (D = 4).
class pipe_map_in_credit2 #(type TI = pipe_in8_t, type TP = pipe_prod8_t,
                            type TM = pipe_mid8_t, int N = 4)
        extends fw_component implements fw_combinational, fw_steppable;
    typedef pipe_map_in_credit2 #(TI, TP, TM, N) this_t;
    `fw_component_param_utils(this_t)

    localparam int D = 4;

    (* fw_sp_comb = "ready" *)       fw_rv_sp_in  #(TI) in[N];
    (* fw_sp_comb = "valid, data" *) fw_rv_sp_out #(TM) out[N];

    bit                   s1_v[N];
    TP                    s1_d[N];
    bit                   s2_v[N];
    TM                    s2_d[N];
    TM                    mem[N*D];
    bit [1:0]             wr[N], rd[N];
    bit [2:0]             fc[N];
    bit [2:0]             cnt[N];

    function void build();
        foreach (in[i]) in[i] = new(null, $sformatf("in[%0d]", i), this);
        foreach (out[i]) out[i] = new(null, $sformatf("out[%0d]", i), this);
    endfunction

    function TP f1(TI x);
        TP y;
        y.tag  = x.tag;
        y.p    = x.a * x.b;
        y.c    = x.c;
        y.last = x.last;
        return y;
    endfunction

    function TM f2(TP x);
        TM y;
        y.tag  = x.tag;
        y.y    = x.p + x.c;
        y.last = x.last;
        return y;
    endfunction

    virtual function void comb();
        foreach (out[i]) out[i].set_valid(fc[i] != 0);
        foreach (out[i]) out[i].set_data(mem[i * D + rd[i]]);
        foreach (in[i]) in[i].set_ready(cnt[i] < D);
    endfunction

    virtual function void step();
        if (in_reset()) begin
            foreach (s1_v[i]) s1_v[i] = 0;
            foreach (s2_v[i]) s2_v[i] = 0;
            foreach (wr[i]) wr[i] = 0;
            foreach (rd[i]) rd[i] = 0;
            foreach (fc[i]) fc[i] = 0;
            foreach (cnt[i]) cnt[i] = 0;
            return;
        end
        foreach (in[i]) begin
            bit take, pop, arrive;
            take   = in[i].get_valid() && cnt[i] < D;
            pop    = fc[i] != 0 && out[i].get_ready();
            arrive = s2_v[i];
            if (arrive) begin
                mem[i * D + wr[i]] = s2_d[i];
                wr[i] = (wr[i] + 1) % D;
            end
            if (pop) rd[i] = (rd[i] + 1) % D;
            fc[i]   = fc[i] + arrive - pop;
            cnt[i]  = cnt[i] + take - pop;
            s2_v[i] = s1_v[i];
            s2_d[i] = f2(s1_d[i]);
            s1_v[i] = take;
            s1_d[i] = f1(in[i].get_data());
        end
    endfunction
endclass
