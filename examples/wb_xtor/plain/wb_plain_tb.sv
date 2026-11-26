// T4c bench (docs/design/xtor-shell-plan.md, D10): the generated initiator
// and target shells back to back on the bus, driven from class code
// through their plain bridges, with no fw-hdl anywhere. The HVL side is
// what a UVM bench does: build each bridge with its shell's interface,
// give the target its implementation (set_p), start each bridge (run),
// then use the initiator's API. +no_set leaves the target's port unset:
// its run() must stop with $fatal.
module wb_plain_tb;
    import wb_plain_tb_pkg::*;

    bit clk;
    always #5 clk = ~clk;

    logic [31:0] adr, dat_w, dat_r;
    logic [3:0]  sel;
    logic        we, cyc, stb, ack, err;

    // HDL side: the two shells on one bus
    wb_initiator_xtor xi(.clk(clk), .pins_adr(adr), .pins_dat_w(dat_w), .pins_sel(sel),
                         .pins_we(we), .pins_cyc(cyc), .pins_stb(stb), .pins_dat_r(dat_r),
                         .pins_ack(ack), .pins_err(err));
    wb_target_xtor    xt(.clk(clk), .pins_adr(adr), .pins_dat_w(dat_w), .pins_sel(sel),
                         .pins_we(we), .pins_cyc(cyc), .pins_stb(stb), .pins_dat_r(dat_r),
                         .pins_ack(ack), .pins_err(err));
    wb_plain_clk_if ck(.clk(clk));

    // HVL side
    initial begin : hvl
        automatic wb_initiator_bridge_pkg::wb_initiator_bridge bi = new(xi.u_if);
        automatic wb_target_bridge_pkg::wb_target_bridge       bt = new(xt.u_if);
        automatic mem_c m = new(ck);
        automatic drv_c d = new(bi, ck);
        if (!$test$plusargs("no_set")) bt.set_p(m);
        fork
            bi.run();
            bt.run();
        join_none
        d.run();
        if (d.err == "") $display("R ok %0d accesses in %0d edges", N, d.edges);
        else             $display("R fail %s", d.err);
        $finish;
    end

    initial begin
        #100us;
        $display("R fail timeout");
        $finish;
    end
endmodule
