// Round-robin arbiter and mux with packet lock. comb(): pick a winner and
// steer it to `out`, and give `ready` to the winner alone, in the same time
// step (in[i].ready follows out.ready). step(): on an `out` handshake, lock
// onto the winner until its `last` beat, then move the round-robin pointer
// past it.
//
// Every field this class drives is comb: in[i].ready, out.valid, out.data.
// The fields it reads (in[i].valid/data, out.ready) are the peers' choice.
class rr_arbiter #(type T = rr_beat_t, int N = 4) extends fw_component
        implements fw_combinational, fw_steppable;
    typedef rr_arbiter #(T, N) this_t;
    `fw_component_param_utils(this_t)

    (* fw_sp_comb = "ready" *)       fw_rv_sp_in  #(T) in[N];
    (* fw_sp_comb = "valid, data" *) fw_rv_sp_out #(T) out;

    // State, at the width it has as registers.
    typedef bit [$clog2(N)-1:0] idx_t;
    idx_t ptr;    // first input to look at when not locked
    bit   locked; // mid-packet: the grant stays on `owner`
    idx_t owner;

    function void build();
        foreach (in[i]) in[i] = new(null, $sformatf("in[%0d]", i), this);
        out = new(null, "out", this);
    endfunction

    // The input that holds the grant this cycle: the owner while locked,
    // else the first valid input from ptr on (ptr itself when none is valid,
    // which grants nothing since its valid is 0).
    function idx_t grant();
        if (locked) return owner;
        for (int k = 0; k < N; k++) begin
            idx_t i = (ptr + k) % N;
            if (in[i].get_valid()) return i;
        end
        return ptr;
    endfunction

    virtual function void comb();
        idx_t g = grant();
        out.set_valid(in[g].get_valid());
        out.set_data(in[g].get_data());
        foreach (in[i]) in[i].set_ready(i == g && out.get_ready());
    endfunction

    virtual function void step();
        if (in_reset()) begin
            ptr    = 0;
            locked = 0;
            owner  = 0;
        end else if (out.get_valid() && out.get_ready()) begin
            idx_t g = grant();
            T   b = out.get_data();
            locked = !b.last;
            owner  = g;
            if (b.last) ptr = (g + 1) % N;
        end
    endfunction
endclass
