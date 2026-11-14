// A one-channel passthrough: comb() only, every field comb (plan S3.3; the
// comb-port counterpart of fw_rv_slice). out.valid and out.data follow
// in.valid and in.data, and in.ready follows out.ready, in the same time
// step. Reset gating comes from the ports' reset-force: valid and ready read
// 0 while in reset.
class fw_rv_pass #(type T = bit) extends fw_component implements fw_combinational;
    fw_rv_sp_in  #(T) in;
    fw_rv_sp_out #(T) out;

    function new(string name, fw_component parent);
        super.new(name, parent);
        in  = new(null, "in", this);
        out = new(null, "out", this);
        in.sig.set_comb("*");
        out.sig.set_comb("*");
        add_comb(this);
    endfunction

    virtual function void comb();
        out.set_valid(in.get_valid());
        out.set_data(in.get_data());
        in.set_ready(out.get_ready());
    endfunction
endclass
