// The probe package's tops run in the simulator: the same values the
// elaboration interpreter reads (test_elab_probe.py).
module probe_tb;
    import fw_hdl_pkg::*;
    import probe_pkg::*;
    initial begin
        top_iface   ti;
        top_factory tf;
        leaf2       l2;
        ti = new("ti", null);
        // build and connect only: the top's own ports stay unbound, so the
        // binding resolution do_connect ends with is not wanted here.
        ti.build();
        ti.u.build();
        ti.connect();
        $display("iface names=%p W=%0d ends=%0d", top_iface::r.names, top_iface::r.vals["W"],
                 top_iface::r.ends.size());
        foreach (top_iface::r.ends[i]) $display("iface end %0d %s", i, top_iface::r.ends[i].ep_name());
        tf = new("tf", null);
        tf.build();
        tf.u.build();
        tf.connect();
        $display("factory leaf2=%0d names=%p", $cast(l2, tf.u), top_factory::r.names);
        $display("X done");
        $finish;
    end
endmodule
