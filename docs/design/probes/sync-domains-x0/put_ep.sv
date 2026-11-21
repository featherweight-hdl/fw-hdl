// X0.4 probe: a minimal put crossing endpoint (sync-task-domains.md §6.2).
//
// A task-side put() drives a ready/valid channel into a sync consumer. The
// endpoint is a sync participant: its step() is the evaluate hook (sample the
// pre-edge valid/ready; apply the pulse default to valid unless the task drove
// it explicitly at this edge). A task-side drive at edge k writes nxt if the
// kernel has not processed k yet (commit at k moves it), or cur and settles
// if it has. A read (the handshake) uses the pre-edge values either way.
//
// The kernel here is the X0 two-phase kernel (evaluate, update, settle), run
// by hand: +kfirst=1 runs it before the task at every edge, +kfirst=0 after.
// The consumer's log must be the same both ways (C4), with no bubble between
// back-to-back puts (C6/C7), including across a zero-time detour.
//
// Run: direnv exec . sh docs/design/probes/sync-domains-x0/run_put_ep.sh
// (needs the X0 kernel: S=<mirror src>).
`timescale 1ns/1ns
import fw_hdl_pkg::*;

typedef bit [7:0] pbyte_t;

class put_ep extends fw_component implements fw_steppable;
    fw_rv_sp_out #(pbyte_t) o;
    realtime s_t = -1;     // time of the last evaluate hook (edge processed)
    bit      s_valid, s_ready;
    realtime x_t = -1;     // time of the last explicit drive
    int unsigned n_twice;

    function new(string name, fw_component parent);
        super.new(name, parent);
        o = new(null, "o", this);
        add_steppable(this);
    endfunction

    // Evaluate hook at edge k.
    virtual function void step();
        s_t     = $realtime;
        s_valid = o.sig.valid_cur;
        s_ready = o.sig.ready_cur;
        if (s_valid && s_ready && x_t != $realtime) o.set_valid(0);   // pulse default
    endfunction

    function bit processed();
        return s_t == $realtime;
    endfunction

    // C2: the handshake at this edge, from the values before it.
    function bit hs();
        if (processed()) return s_valid && s_ready;
        return o.sig.valid_cur && o.sig.ready_cur;
    endfunction

    // C3/C5: an explicit drive at this edge, seen just after it.
    function void drive(bit v, pbyte_t d);
        if (x_t == $realtime) n_twice++;   // FW-E-XING-DRIVE-TWICE
        x_t = $realtime;
`ifdef NAIVE   // negative control: always to nxt, as a run() write is today
        if (0) begin
`else
        if (processed()) begin
`endif
            o.sig.valid_cur = v; o.sig.valid_nxt = v;
            o.sig.data_cur  = d; o.sig.data_nxt  = d;
            fw_sig_holder::gen++;
            o.sig.kernel.settle_now(o.sig);
        end else begin
            o.sig.valid_nxt = v;
            o.sig.data_nxt  = d;
        end
    endfunction
endclass

// A sync consumer: logs each beat with its edge number; ready from a pattern.
class p_cons extends fw_component implements fw_steppable;
    fw_rv_sp_in #(pbyte_t) i;
    int unsigned cyc;
    string       log;
    function new(string name, fw_component parent);
        super.new(name, parent);
        i = new(null, "i", this);
        add_steppable(this);
    endfunction
    virtual function void step();
        cyc++;
        if (i.get_valid() && i.get_ready()) log = {log, $sformatf(" %0d:%0d", cyc, i.get_data())};
        // ready: low after edges 3, 7 and 8
        i.set_ready(!(cyc == 3 || cyc == 7 || cyc == 8));
    endfunction
endclass

module put_ep_probe;
    logic clk = 0;
    always #5 clk = ~clk;

    fw_component   top;
    put_ep         ep;
    p_cons         cons;
    fw_sync_kernel k;
    bit            kfirst;
    int unsigned   n_edges;

    task automatic tick();
        @(posedge clk);
        if (kfirst) begin #0; #0; #0; end
    endtask

    task automatic put(pbyte_t d);
        ep.drive(1, d);
        do tick(); while (!ep.hs());
    endtask

    initial begin
        string err;
        void'($value$plusargs("kfirst=%d", kfirst));
        top  = new("top", null);
        ep   = new("ep", top);
        cons = new("cons", top);
        ep.o.connect(cons.i);
        k = new("top");
        k.elaborate(top);
        fw_sig_holder::phase = FW_SYNC_PH_RUN;
        fork
            forever begin
                @(posedge clk);
                if (!kfirst) begin #0; #0; end
                if (k.do_edge(k.doms[0], err)) $fatal(1, "%s", err);
                n_edges++;
            end
        join_none
        tick();
        // Back-to-back, through stalls.
        for (int n = 1; n <= 6; n++) put(n);
        // A zero-time detour between two puts.
        put(10);
        #0;
        put(11);
        // A gap of two edges, then back-to-back again.
        repeat (2) tick();
        for (int n = 20; n <= 24; n++) put(n);
        repeat (3) tick();
        // C5: a second explicit drive at one edge is an error.
        ep.drive(0, 0);
        ep.drive(0, 0);
        tick();
        $display("X0.4 kfirst=%0d twice=%0d log:%s", kfirst, ep.n_twice, cons.log);
        $finish;
    end
endmodule
