// The bench's top module: builds top_c, elaborates and runs it on
// fw-hdl-rt-sv, and prints the result. Simulation only: it calls rt-sv's
// internal entry points (__fw_rt, __fw_rt_kern), as rt-sv's own tests do,
// since the runtime has no public run entry point yet. fe-sv elaborates
// wb_xtor_tb_pkg::top_c without it (flow.yaml).
module wb_xtor_tb;
    import fw_hdl_pkg::*;
    import wb_xtor_tb_pkg::*;

    top_c t;

    initial begin
        string e;
        int nerr, b2b;
        t = top_c::create("top", null);
        nerr = __fw_rt::elaborate(t);
        if (nerr == 0) __fw_rt_kern::run();
        foreach (t.d.calls[i]) if (i > 0 && t.d.calls[i].c == t.d.calls[i - 1].r) b2b++;
        e = (nerr != 0) ? $sformatf("%0d elaboration errors", nerr) : check(t);
        if (e == "") $display("R ok %0d accesses in %0d edges, %0d back to back",
                              N, t.d.calls[N - 1].r, b2b);
        else         $display("R fail %s", e);
        foreach (__fw_rt::diags[i]) $display("D %s %s", __fw_rt::diags[i].id, __fw_rt::diags[i].path);
        $finish;
    end
endmodule
