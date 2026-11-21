// The output map, one lane: out.data = f_out(in.data), with
//   f_out: {tag, y, last} -> {tag, y ^ (y >> 3), last}
// a cheaper function than f_in, so the two form a chain of maps around the
// merge. valid passes forward and ready back, in the same time step.
class pipe_map_out #(type TM = pipe_mid8_t) extends fw_component
        implements fw_combinational;
    typedef pipe_map_out #(TM) this_t;
    `fw_component_param_utils(this_t)

    (* fw_sp_comb = "ready" *)       fw_rv_sp_in  #(TM) in;
    (* fw_sp_comb = "valid, data" *) fw_rv_sp_out #(TM) out;

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
        out.set_valid(in.get_valid());
        out.set_data(f(in.get_data()));
        in.set_ready(out.get_ready());
    endfunction
endclass
