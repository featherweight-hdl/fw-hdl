// fw_sp_comb weaver test bench (plan S6.1b): builds a small tree, freezes it
// (which applies the woven declarations) and prints the comb flags as
// RESULT lines. +no_init skips the woven __register() (nothing woven is registered).
module sp_comb_tb;
    import fw_hdl_pkg::*;
    import sp_comb_pkg::*;

    function automatic string flags(fw_sync_port v);
        fw_sig_holder h = v.holder();
        return $sformatf("%0d%0d%0d", h.field("valid").comb, h.field("ready").comb,
                         h.field("data").comb);
    endfunction

    initial begin
        fw_component top;
        c_comb a;
        c_sub s;
        c_gen4_t g;
        if (!$test$plusargs("no_init")) sp_comb_pkg_woven::__register();
        top = new("top", null);
        a = new("a", top);
        s = new("s", top);
        g = new("g", top);
        fw_sync_kernel::freeze_tree(top);
        $display("RESULT a.o %s", flags(a.o));
        $display("RESULT a.i %s", flags(a.i));
        $display("RESULT a.p [%s]", a.p.got);
        $display("RESULT s.o %s", flags(s.o));
        $display("RESULT s.j %s", flags(s.j));
        $display("RESULT s.p [%s]", s.p.got);
        $display("RESULT g.g %s", flags(g.g));
        $finish;
    end
endmodule
