// extern_map() runs in a plain simulation too: it only records.
module map_tb;
    import fw_hdl_pkg::*;
    import ext_pkg::*;
    initial begin
        ext_q_param_t p = new(3);
        ext_q_rtl     q = new("q", null, p);
        fw_extern_map x = new;
        q.build();
        q.extern_map(x);
        $display("module=%s fileset=%s", q.extern_module(), q.extern_fileset());
        foreach (x.m_param_names[i])
            $display("param %s=%0d", x.m_param_names[i], x.m_param_int[x.m_param_names[i]]);
        $display("clock=%s reset=%s low=%0d", x.m_clock, x.m_reset, x.m_reset_active_low);
        foreach (x.m_binds[i])
            $display("bind %s %s %s style=%s data=%s", x.m_binds[i].kind,
                     x.m_binds[i].ep.ep_name(), x.m_binds[i].name, x.m_binds[i].style,
                     x.m_binds[i].pins["data"]);
        $display("X done");
        $finish;
    end
endmodule
