
class fw_reqrsp_if #(type Treq, type Trsp);
    // outputs (returns) lead: out = call(in).
    pure virtual task call(output Trsp out, input Treq in);
endclass
