// A one-channel register slice: a 2-entry skid buffer, step() only
// (design-sync-rtl §3.4; the class form of axi4_slice). One beat per cycle;
// out.valid, out.data and in.ready are sync outputs, so every output is a
// register. The out.valid register *is* the RTL's out_valid_q; in.ready is
// written alongside skid_valid, and the reset gates of the RTL come from the
// ports' reset-force (valid and ready read 0 while in reset). As in the RTL,
// the data registers are not reset.
class fw_rv_slice #(type T = bit) extends fw_component implements fw_steppable;
    fw_rv_sp_in  #(T) in;
    fw_rv_sp_out #(T) out;

    bit skid_valid;
    T   skid_data;

    function new(string name, fw_component parent);
        super.new(name, parent);
        in  = new(null, "in", this);
        out = new(null, "out", this);
        add_steppable(this);
    endfunction

    virtual function void step();
        if (in_reset()) begin
            out.set_valid(0);
            skid_valid = 0;
            in.set_ready(1);
        end else if (out.get_ready() || !out.get_valid()) begin
            // Output register free (or emptying): refill, skid first.
            if (skid_valid) begin
                out.set_valid(1);
                out.set_data(skid_data);
                skid_valid = 0;
            end else begin
                out.set_valid(in.get_valid());
                if (in.get_valid()) out.set_data(in.get_data());
            end
            in.set_ready(1);
        end else if (in.get_valid() && in.get_ready()) begin
            // Output stalled: park the accepted beat.
            skid_valid = 1;
            skid_data  = in.get_data();
            in.set_ready(0);
        end
    endfunction
endclass
