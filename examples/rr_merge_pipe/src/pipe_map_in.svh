// The input map, N lanes: out[i].data = f_in(in[i].data), with
//   f_in: {tag, a, b, c, last} -> {tag, y = a * b + c, last}
// (y is twice as wide as a, b and c). valid passes forward and ready back,
// in the same time step: a map with no storage, written as plain comb().
// This is the "before" form a recognizer must find (§3.1).
//
// It is one class for the N lanes because the parameterized lowering does
// not take arrays of child components (`pipe_map_in m[N]`).
class pipe_map_in #(type TI = pipe_in8_t, type TM = pipe_mid8_t, int N = 4)
        extends fw_component implements fw_combinational;
    typedef pipe_map_in #(TI, TM, N) this_t;
    `fw_component_param_utils(this_t)

    (* fw_sp_comb = "ready" *)       fw_rv_sp_in  #(TI) in[N];
    (* fw_sp_comb = "valid, data" *) fw_rv_sp_out #(TM) out[N];

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

    // One statement per field: fw_settle orders comb() by the reads and
    // writes of each top-level statement, so out[i].data must not share a
    // statement with in[i].ready (a false comb loop through the arbiter).
    virtual function void comb();
        foreach (out[i]) out[i].set_valid(in[i].get_valid());
        foreach (out[i]) out[i].set_data(f(in[i].get_data()));
        foreach (in[i]) in[i].set_ready(out[i].get_ready());
    endfunction
endclass
