// T0 bench (docs/design/xtor-shell-plan.md): the class bench
// (wb_xtor_tb.sv) with wb_initiator replaced by its bridge and the shell
// wb_initiator_xtor on the bus. The driver, target (or +mut_tgt), memory
// (+rand) and checker are the class bench's, joined to the shell's pins
// through fw_pin_bridge; the results must be the class bench's.
`include "fw_hdl_macros.svh"

package wb_xtor_shell_init_pkg;
    import fw_hdl_pkg::*;
    import wb_pkg::*;
    import wb_xtor_tb_pkg::*;
    import wb_initiator_bridge_pkg::*;

    class shell_top_c extends fw_component;
        `fw_component_utils(shell_top_c)
        fw_clock_domain          clk;
        fw_mirror #(wb_bundle_t) wb;     // the shell's pins
        drv_c                    d;
        wb_initiator_bridge      xi;
        wb_target_t              xt;
        mem_c                    m;
        chk_c                    k;
        virtual function void build();
            clk = fw_clock_domain::create("clk", this, fw_clock_kind::root(10ns));
            fw_clock_domain::set(this, clk);
            wb = fw_mirror #(wb_bundle_t)::create("wb", this);
            d  = drv_c::create("d", this);
            xi = wb_initiator_bridge::create("xi", this);
            if ($test$plusargs("mut_tgt")) xt = mut_tgt_c::create("xt", this);
            else                           xt = wb_target_t::create("xt", this);
            m  = mem_c::create("m", this);
            k  = chk_c::create("k", this);
            d.k = k;
        endfunction
        virtual function void connect();
            d.p.connect(xi.t);
            xt.pins.connect_up(wb);
            xt.p.connect(m.t);
            k.p.connect(xt.pins);
        endfunction
    endclass
endpackage

module wb_xtor_shell_init;
    import fw_hdl_pkg::*;
    import wb_xtor_tb_pkg::*;
    import wb_xtor_shell_init_pkg::*;

    bit clk;
    always #5 clk = ~clk;

    logic [31:0] adr, dat_w, dat_r;
    logic [3:0]  sel;
    logic        we, cyc, stb, ack, err;

    // HDL side: the shell alone on the bus
`ifdef GEN_SHELL
    // The generated shell (scripts/emit_xtor.py): the core's port names.
    wb_initiator_xtor xi(.clk(clk), .pins_adr(adr), .pins_dat_w(dat_w), .pins_sel(sel), .pins_we(we), .pins_cyc(cyc),
                         .pins_stb(stb), .pins_dat_r(dat_r), .pins_ack(ack), .pins_err(err));
`else
    wb_initiator_xtor xi(.clock(clk), .adr(adr), .dat_w(dat_w), .sel(sel), .we(we),
                         .cyc(cyc), .stb(stb), .dat_r(dat_r), .ack(ack), .err(err));
`endif

    fw_pin_bridge #(bit, "top.clk")              b_clk(.i(clk), .o());
    fw_pin_bridge #(bit [31:0], "top.wb.adr")    b_adr(.i(adr), .o());
    fw_pin_bridge #(bit [31:0], "top.wb.dat_w")  b_dw(.i(dat_w), .o());
    fw_pin_bridge #(bit [3:0], "top.wb.sel")     b_sel(.i(sel), .o());
    fw_pin_bridge #(bit, "top.wb.we")            b_we(.i(we), .o());
    fw_pin_bridge #(bit, "top.wb.cyc")           b_cyc(.i(cyc), .o());
    fw_pin_bridge #(bit, "top.wb.stb")           b_stb(.i(stb), .o());
    fw_pin_bridge #(bit [31:0], "top.wb.dat_r")  b_dr(.i(32'd0), .o(dat_r));
    fw_pin_bridge #(bit, "top.wb.ack")           b_ack(.i(1'b0), .o(ack));
    fw_pin_bridge #(bit, "top.wb.err")           b_err(.i(1'b0), .o(err));

    shell_top_c t;
    int         cyc_n;

    // HVL side: build and elaborate, then hand the bridge its interface.
    initial begin
        t = shell_top_c::create("top", null);
        void'(__fw_rt::elaborate(t));
        t.xi.vif = xi.u_if;
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
