// The Wishbone initiator in Pattern 1 (sync-task-domains.md §4, §5.1, X7):
// wb_init (the sync core plus fw_rv_put_ep/fw_rv_get_ep) on a sync target.
// A sequence makes N accesses, a write then a read back of each address,
// and a step-only logger records the links and the bus at each edge. Prints
// PASS or FAIL; built and run by tests/python/system/test_wb_initiator.py.
//
// Default: the target acks in the first bus cycle and the accesses are back
// to back. The run must be §4's table, access after access:
//   k0   access i calls put(A): req.valid is driven from the next edge (C3)
//   k1   req handshake, put returns (C7) and get raises rsp.ready; the core
//        launches the phase (stb)
//   k2   ack, so rsp handshake: get returns, access() returns, and the next
//        access's put drives req.valid at the same edge (C6); the
//        endpoints' defaults drop req.valid and rsp.ready (C5)
// so access i is called at edge 2i and returns at 2i + 2, with no idle
// cycle but the core's own (stb low at odd edges).
// +rand: 0-3 wait states per phase and 0-3 idle edges between accesses;
// checks only the data and that each access is one bus phase.
// +mut_ws: one wait state per phase, without +rand: the table must fail.
`timescale 1ns/1ps
package wb_init_tb_pkg;
    import fw_hdl_pkg::*;
    import wb_types_pkg::*;
    import wb_init_core_pkg::*;

    localparam int N = 12;

    // A 16-bit LFSR, 0-3 per draw.
    class gap_c;
        bit [15:0] s;
        function new(bit [15:0] seed);
            s = seed;
        endfunction
        function int next();
            s = {s[14:0], s[15] ^ s[13] ^ s[12] ^ s[10]};
            return s[1:0];
        endfunction
    endclass

    // A memory target: ack (comb) after `ws` wait states of a phase; writes
    // land at the ack edge. ws is 0, or drawn per phase with +rand.
    class wb_tgt extends fw_component implements fw_steppable, fw_combinational;
        wb_sp_in wb;
        wb_dat_t mem[16];
        int      cnt, ws;
        bit      rnd;
        gap_c    g = new(16'h0b0e);

        function new(string name, fw_component parent);
            super.new(name, parent);
            wb = new(null, "wb", this);
            wb.sig.set_comb("dat_r, ack, err, rty");
            rnd = $test$plusargs("rand");
            if (rnd) ws = g.next();
            if ($test$plusargs("mut_ws")) ws = 1;
            add_steppable(this);
            add_comb(this);
        endfunction

        virtual function void comb();
            wb.set_ack(wb.get_cyc() && wb.get_stb() && cnt == ws);
            wb.set_dat_r(mem[wb.get_adr()[5:2]]);
            wb.set_err(0);
            wb.set_rty(0);
        endfunction

        virtual function void step();
            if (!(wb.get_cyc() && wb.get_stb())) begin
                cnt = 0;
            end else if (wb.get_ack()) begin
                if (wb.get_we()) mem[wb.get_adr()[5:2]] = wb.get_dat_w();
                cnt = 0;
                if (rnd) ws = g.next();
            end else begin
                cnt++;
            end
        endfunction
    endclass

    // What the step()s read at each edge.
    class wb_log extends fw_component implements fw_steppable;
        fw_rv_sp_out #(wb_req_t) req;
        fw_rv_sp_in  #(wb_rsp_t) rsp;
        wb_sp_out                wb;
        bit rqv[$], rqr[$], rsv[$], rsr[$], stb[$], ack[$];
        function new(string name, fw_component parent);
            super.new(name, parent);
            add_steppable(this);
        endfunction
        virtual function void step();
            rqv.push_back(req.get_valid());
            rqr.push_back(req.get_ready());
            rsv.push_back(rsp.get_valid());
            rsr.push_back(rsp.get_ready());
            stb.push_back(wb.get_cyc() && wb.get_stb());
            ack.push_back(wb.get_ack());
        endfunction
        // The edges logged so far: task code at edge k reads k.
        function int n();
            return rqv.size();
        endfunction
    endclass

    // An access: the edge it was called at, the edge it returned at, and the
    // response. (Where put returned shows in the log: the req handshake.)
    typedef struct { int c; int r; wb_rsp_t rsp; bit we; wb_dat_t d; } acc_t;

    function automatic wb_dat_t val(int i);
        return 32'hc0de_0000 + i * 32'h101;
    endfunction
endpackage

module wb_init_tb;
    import fw_hdl_pkg::*;
    import wb_types_pkg::*;
    import wb_init_core_pkg::*;
    import wb_init_pkg::*;
    import wb_init_tb_pkg::*;

    logic clk = 0, rst = 0;
    always #5 clk = ~clk;
    fw_clock_xtor_if cif(.clock(clk), .reset(rst));

    fw_component         top;
    fw_clock_xtor_bridge rb;
    wb_init              ini;
    wb_tgt               tgt;
    wb_log               lg;
    fw_sync_kernel       kern;
    acc_t                accs[$];
    bit                  rnd;

    // The first failure, or "".
    function automatic string check();
        int nrq, nrs, nph;
        foreach (accs[i]) begin
            acc_t a = accs[i];
            if (a.rsp.err || a.rsp.rty) return $sformatf("access %0d: err/rty", i);
            if (!a.we && a.rsp.dat != a.d)
                return $sformatf("access %0d: read %h, expected %h", i, a.rsp.dat, a.d);
            if (a.r < a.c + 2)
                return $sformatf("access %0d: called %0d, returned %0d", i, a.c, a.r);
        end
        foreach (lg.rqv[e]) begin
            nrq += lg.rqv[e] && lg.rqr[e];
            nrs += lg.rsv[e] && lg.rsr[e];
            nph += lg.stb[e] && lg.ack[e] && lg.rsr[e];
        end
        if (nrq != N || nrs != N || nph != N)
            return $sformatf("%0d requests, %0d responses, %0d bus phases", nrq, nrs, nph);
        if (rnd) return "";
        // §4's table: access i at edges 2i .. 2i + 2.
        foreach (accs[i]) begin
            if (accs[i].c != 2 * i || accs[i].r != 2 * i + 2)
                return $sformatf("access %0d: called %0d, returned %0d (expected %0d, %0d)",
                                 i, accs[i].c, accs[i].r, 2 * i, 2 * i + 2);
        end
        for (int e = 1; e <= 2 * N; e++) begin
            bit odd = e % 2;
            if (lg.rqv[e - 1] != odd || lg.rqr[e - 1] != 1 - lg.stb[e - 1] ||
                lg.rsr[e - 1] != !odd || lg.stb[e - 1] != !odd || lg.ack[e - 1] != !odd)
                return $sformatf("edge %0d: req %0d/%0d rsp %0d/%0d stb %0d ack %0d", e,
                                 lg.rqv[e - 1], lg.rqr[e - 1], lg.rsv[e - 1], lg.rsr[e - 1],
                                 lg.stb[e - 1], lg.ack[e - 1]);
        end
        return "";
    endfunction

    function automatic void report();
        string e = check();
        string m = "";
        if (rnd) m = " +rand";
        if (e == "" && fw_sig_holder::rule_errs != 0) e = fw_sig_holder::rule_err;
        if (e == "") $display("PASS: wb_init%s: %0d accesses in %0d edges",
                              m, N, accs.size() ? accs[$].r : 0);
        else         $display("FAIL: wb_init%s: %s", m, e);
        $finish;
    endfunction

    // A hang (an access that never returns) is reported rather than waited on.
    initial begin
        #20us;
        report();
    end

    initial begin
        rnd = $test$plusargs("rand");
        top = new("top", null);
        rb  = new("rb", top, cif);
        ini = new("ini", top);
        tgt = new("tgt", top);
        lg  = new("lg", top);
        ini.clock.connect(rb);
        ini.core.clock.connect(rb);
        ini.ereq.clock.connect(rb);
        ini.ersp.clock.connect(rb);
        tgt.clock.connect(rb);
        lg.clock.connect(rb);
        ini.wb.connect(tgt.wb);
        lg.req = ini.ereq.out;
        lg.rsp = ini.ersp.in;
        lg.wb  = ini.wb;
        kern = new("top");
        kern.elaborate(top);
        fw_sig_holder::fatal_on_rule = 0;
        kern.launch();

        begin   // the sequence
            gap_c g = new(16'h5eed);
            for (int i = 0; i < N; i++) begin
                acc_t a;
                bit [3:0] slot = i / 2;
                if (rnd) repeat (g.next()) rb.tick(1);
                a.we = (i % 2 == 0);
                a.d  = val(slot);
                a.c  = lg.n();
                if (a.we) ini.write({slot, 2'b00}, a.d, a.rsp);
                else      ini.read({slot, 2'b00}, a.rsp);
                a.r = lg.n();
                accs.push_back(a);
            end
        end
        rb.tick(2);
        report();
    end
endmodule
