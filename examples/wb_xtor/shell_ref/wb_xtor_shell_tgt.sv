// T5 bench (docs/design/xtor-shell-plan.md): the class bench
// (wb_xtor_tb.sv) with wb_target replaced by its bridge and the shell
// wb_target_xtor on the bus. The driver, initiator (or +mut_init), memory
// (+rand) and checker are the class bench's, joined to the shell's pins
// through fw_pin_bridge; the results must be the class bench's.
`include "fw_hdl_macros.svh"

package wb_xtor_shell_tgt_pkg;
    import fw_hdl_pkg::*;
    import wb_pkg::*;
    import wb_xtor_tb_pkg::*;
    import wb_target_bridge_pkg::*;

    class shell_top_c extends fw_component;
        `fw_component_utils(shell_top_c)
        fw_clock_domain          clk;
        fw_bundle #(wb_bundle_t) wb;     // the shell's pins
        drv_c                    d;
        wb_initiator_t           xi;
        wb_target_bridge         xt;
        mem_c                    m;
        chk_c                    k;
        virtual function void build();
            clk = fw_clock_domain::create("clk", this, fw_clock_kind::root(10ns));
            fw_clock_domain::set(this, clk);
            wb = fw_bundle #(wb_bundle_t)::create("wb", this);
            d  = drv_c::create("d", this);
            if ($test$plusargs("mut_init")) xi = mut_init_c::create("xi", this);
            else                            xi = wb_initiator_t::create("xi", this);
            xt = wb_target_bridge::create("xt", this);
            m  = mem_c::create("m", this);
            k  = chk_c::create("k", this);
            d.k = k;
        endfunction
        virtual function void connect();
            d.p.connect(xi.t);
            xi.pins.connect_up(wb);
            xt.p.connect(m.t);
            k.p.connect(xi.pins);
        endfunction
    endclass
endpackage

module wb_xtor_shell_tgt;
    import fw_hdl_pkg::*;
    import wb_xtor_tb_pkg::*;
    import wb_xtor_shell_tgt_pkg::*;

    bit clk;
    always #5 clk = ~clk;

    logic [31:0] adr, dat_w, dat_r;
    logic [3:0]  sel;
    logic        we, cyc, stb, ack, err;

    // HDL side: the shell alone on the bus
`ifdef GEN_SHELL
    // The generated shell (scripts/emit_xtor.py): the core's port names.
    wb_target_xtor xt(.clk(clk), .pins_adr(adr), .pins_dat_w(dat_w), .pins_sel(sel), .pins_we(we), .pins_cyc(cyc),
                      .pins_stb(stb), .pins_dat_r(dat_r), .pins_ack(ack), .pins_err(err));
`else
    wb_target_xtor xt(.clock(clk), .adr(adr), .dat_w(dat_w), .sel(sel), .we(we),
                      .cyc(cyc), .stb(stb), .dat_r(dat_r), .ack(ack), .err(err));
`endif

    fw_pin_bridge #(bit, "top.clk")              b_clk(.i(clk), .o());
    fw_pin_bridge #(bit [31:0], "top.wb.adr")    b_adr(.i(32'd0), .o(adr));
    fw_pin_bridge #(bit [31:0], "top.wb.dat_w")  b_dw(.i(32'd0), .o(dat_w));
    fw_pin_bridge #(bit [3:0], "top.wb.sel")     b_sel(.i(4'd0), .o(sel));
    fw_pin_bridge #(bit, "top.wb.we")            b_we(.i(1'b0), .o(we));
    fw_pin_bridge #(bit, "top.wb.cyc")           b_cyc(.i(1'b0), .o(cyc));
    fw_pin_bridge #(bit, "top.wb.stb")           b_stb(.i(1'b0), .o(stb));
    fw_pin_bridge #(bit [31:0], "top.wb.dat_r")  b_dr(.i(dat_r), .o());
    fw_pin_bridge #(bit, "top.wb.ack")           b_ack(.i(ack), .o());
    fw_pin_bridge #(bit, "top.wb.err")           b_err(.i(err), .o());

    shell_top_c t;
    int         cyc_n;

    // HVL side: build and elaborate, then hand the bridge its interface.
    initial begin
        t = shell_top_c::create("top", null);
        void'(__fw_rt::elaborate(t));
        t.xt.vif = xt.u_if;
    end

    // 400 edges, as the class bench's +fw_edges=400; then its report.
    always @(posedge clk) begin
        cyc_n++;
        if (cyc_n == 401) begin
            string e;
            int b2b;
            foreach (t.d.calls[i]) if (i > 0 && t.d.calls[i].c == t.d.calls[i - 1].r) b2b++;
            e = check_parts(t.d, t.k, t.m);
            if (e == "") $display("R ok %0d accesses in %0d edges, %0d back to back",
                                  N, t.d.calls[N - 1].r, b2b);
            else         $display("R fail %s", e);
            foreach (__fw_rt::diags[i]) $display("D %s %s", __fw_rt::diags[i].id, __fw_rt::diags[i].path);
            $finish;
        end
    end
endmodule
