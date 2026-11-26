// The wb_xtor bench (wb_xtor_tb.sv) with wb_initiator lowered to RTL: the
// module wb_dut that scripts/emit_rtl.py emits. Everything else is the
// class bench's: the driver, the target (or its mutant, +mut_tgt), the
// memory (+rand) and the checker, run on fw-hdl-rt-sv and joined to the
// module through fw_pin_bridge.
//
// The module's crossing ports are driven by the task side of its crossings
// in the class world: xs implements the Wishbone API (access()) by putting
// the request through std's fw_to_sync_ep (ri, on xi_reqs_*) and getting
// the response from std's fw_from_sync_ep (re, on xi_rsps_*), the outsides
// of the lowered crossings. The module's Wishbone pins reach the class
// target through the top's mirror wb.
//
// The checks are the class bench's (check_parts), and so are the results:
// lowering keeps the class model's timing.
`include "fw_hdl_macros.svh"

package wb_xtor_mixed_pkg;
    import fw_hdl_pkg::*;
    import fw_hdl_std_pkg::*;
    import wb_pkg::*;
    import wb_xtor_tb_pkg::*;

    // The task side of the lowered initiator: the Wishbone API over its
    // two crossings.
    class xs_c extends fw_component implements wb_api_t;
        `fw_component_utils(xs_c)
        fw_export #(wb_api_t)     t;
        fw_to_sync_ep #(req_t)  ri;
        fw_from_sync_ep #(rsp_t)         re;
        virtual function void build();
            t = fw_export #(wb_api_t)::create("t", this);
        endfunction
        virtual task access(output rsp_t rsp, input req_t req);
            ri.put(req);
            re.get(rsp);
        endtask
    endclass

    class mixed_top_c extends fw_component;
        `fw_component_utils(mixed_top_c)
        fw_clock_domain                   clk;
        fw_bundle #(fw_rv_if #(req_t))    qr;     // to xi_reqs_*
        fw_mirror #(fw_rv_if #(rsp_t))    qs;     // from xi_rsps_*
        fw_mirror #(wb_bundle_t)          wb;     // the module's pins
        drv_c                             d;
        xs_c                              xs;
        fw_to_sync_ep #(req_t)          ri;
        fw_from_sync_ep #(rsp_t)                 re;
        wb_target_t                       xt;
        mem_c                             m;
        chk_c                             k;
        virtual function void build();
            clk = fw_clock_domain::create("clk", this, fw_clock_kind::root(10ns));
            fw_clock_domain::set(this, clk);
            qr = fw_bundle #(fw_rv_if #(req_t))::create("qr", this);
            qs = fw_mirror #(fw_rv_if #(rsp_t))::create("qs", this);
            wb = fw_mirror #(wb_bundle_t)::create("wb", this);
            d  = drv_c::create("d", this);
            xs = xs_c::create("xs", this);
            ri = fw_to_sync_ep #(req_t)::create("ri", this);
            re = fw_from_sync_ep #(rsp_t)::create("re", this);
            if ($test$plusargs("mut_tgt")) xt = mut_tgt_c::create("xt", this);
            else                           xt = wb_target_t::create("xt", this);
            m  = mem_c::create("m", this);
            k  = chk_c::create("k", this);
            d.k = k;
            xs.ri = ri;
            xs.re = re;
        endfunction
        virtual function void connect();
            d.p.connect(xs.t);
            ri.pins.connect_up(qr);
            re.pins.connect_up(qs);
            xt.pins.connect_up(wb);
            xt.p.connect(m.t);
            k.p.connect(xt.pins);
        endfunction
    endclass
endpackage

module wb_xtor_mixed;
    import fw_hdl_pkg::*;
    import wb_xtor_tb_pkg::*;
    import wb_xtor_mixed_pkg::*;

    bit clk;
    always #5 clk = ~clk;

    // The module's pins
    logic [31:0] adr, dat_w, dat_r;
    logic [3:0]  sel;
    logic        we, cyc, stb, ack, err;
    // Its crossing ports
    logic        rq_valid, rq_ready, rs_valid, rs_ready;
    req_t        rq_data;
    rsp_t        rs_data;

    mixed_top_c t;
    int         cyc_n;

    wb_dut dut(.wb_adr(adr), .wb_dat_w(dat_w), .wb_sel(sel), .wb_we(we), .wb_cyc(cyc),
               .wb_stb(stb), .wb_dat_r(dat_r), .wb_ack(ack), .wb_err(err),
               .xi_reqs_valid(rq_valid), .xi_reqs_ready(rq_ready), .xi_reqs_data(rq_data),
               .xi_rsps_valid(rs_valid), .xi_rsps_ready(rs_ready), .xi_rsps_data(rs_data));

    fw_pin_bridge #(bit, "top.clk")              b_clk(.i(clk), .o());
    // the request crossing: class -> module, ready back
    fw_pin_bridge #(bit, "top.qr.valid")         b_qv(.i(1'b0), .o(rq_valid));
    fw_pin_bridge #(req_t, "top.qr.data")        b_qd(.i('0), .o(rq_data));
    fw_pin_bridge #(bit, "top.qr.ready")         b_qr(.i(rq_ready), .o());
    // the response crossing: module -> class, ready back
    fw_pin_bridge #(bit, "top.qs.valid")         b_sv(.i(rs_valid), .o());
    fw_pin_bridge #(rsp_t, "top.qs.data")        b_sd(.i(rs_data), .o());
    fw_pin_bridge #(bit, "top.qs.ready")         b_sr(.i(1'b0), .o(rs_ready));
    // the Wishbone pins: module -> target, the target's answer back
    fw_pin_bridge #(bit [31:0], "top.wb.adr")    b_adr(.i(adr), .o());
    fw_pin_bridge #(bit [31:0], "top.wb.dat_w")  b_dw(.i(dat_w), .o());
    fw_pin_bridge #(bit [3:0], "top.wb.sel")     b_sel(.i(sel), .o());
    fw_pin_bridge #(bit, "top.wb.we")            b_we(.i(we), .o());
    fw_pin_bridge #(bit, "top.wb.cyc")           b_cyc(.i(cyc), .o());
    fw_pin_bridge #(bit, "top.wb.stb")           b_stb(.i(stb), .o());
    fw_pin_bridge #(bit [31:0], "top.wb.dat_r")  b_dr(.i(32'd0), .o(dat_r));
    fw_pin_bridge #(bit, "top.wb.ack")           b_ack(.i(1'b0), .o(ack));
    fw_pin_bridge #(bit, "top.wb.err")           b_err(.i(1'b0), .o(err));

    initial begin
        t = mixed_top_c::create("top", null);
        void'(__fw_rt::elaborate(t));
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
