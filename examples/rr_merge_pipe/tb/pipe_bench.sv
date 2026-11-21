// Latency-insensitive bench for rr_merge_pipe and its pipelined variants
// (docs/design/micro-pipelining-feasibility.md F2). It drives the DUT's pins
// and checks streams, not cycles, so every variant runs on it unchanged,
// whatever its latency:
//
//   - drivers: per input, packets of 1-4 beats with random a, b, c and gaps,
//     the same streams for a seed whatever the DUT's timing;
//     `tag` = {source, seq} so each output beat names its source;
//   - sink: `ready` always on (+sink=0), 50% random (+sink=1), or in bursts
//     of 1-16 cycles on and off (+sink=2);
//   - model: per source, a queue of expected output beats f_out(f_in(x)),
//     computed here independently of the classes (64-bit arithmetic);
//   - scoreboard: each output beat is the head of its source's queue (order,
//     content, no loss or duplication), packets arrive whole, and every
//     queue is empty at the end;
//   - protocol monitor at out: valid held until taken, data stable meanwhile;
//   - measures: latency of a lone beat (input to output handshake), beats
//     per cycle with everyone valid and ready, and the source of each of the
//     first 200 packets out (A8: placement changes interleaving).
//
// Plusargs: +sink=<0|1|2> +cycles=<random phase length> +min_tput=<beats in
// 100 full cycles, default 100>. The seed is Verilator's +verilator+seed+<n>.
module pipe_bench #(
    parameter int  N  = 4,
    parameter type TI = pipe_types_pkg::pipe_in8_t,
    parameter type TM = pipe_types_pkg::pipe_mid8_t,
    parameter string NAME = "rr_merge_pipe"
) (
    input  logic             clk,
    output logic             rst,
    output logic [N-1:0]     in_valid,
    input  logic [N-1:0]     in_ready,
    output TI    [N-1:0]     in_data,
    input  logic             out_valid,
    output logic             out_ready,
    input  TM                out_data
);
    // ---- model -------------------------------------------------------------
    function automatic TM model(TI x);
        TM m;
        longint unsigned y;
        y = longint'(x.a) * longint'(x.b) + longint'(x.c);   // f_in
        m.tag  = x.tag;
        m.y    = y;                                          // truncates to 2W
        y      = longint'(m.y);
        m.y    = y ^ (y >> 3);                               // f_out
        m.last = x.last;
        return m;
    endfunction

    // ---- the DUT's outputs, as the edge sees them ---------------------------
    // A clocking block samples them in the Preponed region (#1step), before
    // anything at the edge runs. Read directly at posedge, a class model's
    // comb outputs would race with the kernel, which commits and settles the
    // tree in the edge's active region.
    clocking cb @(posedge clk);
        default input #1step;
        input in_ready, out_valid, out_data;
    endclocking

    // ---- drivers -----------------------------------------------------------
    // A beat offered stays until taken. Each source draws from its own
    // generator, once per beat (its content, the packet length at a packet's
    // first beat, and the idle cycles after it), so a seed gives every
    // variant the same streams whatever the DUT's timing; only when beats
    // are taken differs. `left`: beats of the current packet still to send.
    bit          run, full, stop, probe;
    int unsigned left[N], gap[N];
    bit [5:0]    seq[N];
    int unsigned n_sent[N];
    TM           exp_q[N][$];
    bit [31:0]   rng[N];
    function automatic bit [31:0] draw(int i);
        bit [31:0] x = rng[i];
        x ^= x << 13;
        x ^= x >> 17;
        x ^= x << 5;
        rng[i] = x;
        return x;
    endfunction
    initial begin
        bit [31:0] s0 = $urandom;
        foreach (rng[i]) rng[i] = s0 ^ (32'h9e3779b9 * (i + 1)) | 1;
    end
    always @(cb) if (run) begin
        for (int i = 0; i < N; i++) begin
            if (in_valid[i] && cb.in_ready[i]) begin
                exp_q[i].push_back(model(in_data[i]));
                n_sent[i]++;
                seq[i]++;
                left[i]--;
                in_valid[i] <= 0;
                gap[i] = draw(i) % 4 == 0 ? draw(i) % 4 : 0;
                if (left[i] == 0) gap[i] += draw(i) % 12;   // between packets
            end
            if (!(in_valid[i] && !cb.in_ready[i]) && !probe) begin
                if (gap[i] != 0 && !full) gap[i]--;
                else begin
                    if (left[i] == 0 && !stop) left[i] = draw(i) % 4 + 1;
                    if (left[i] != 0) begin
                        TI x;
                        x      = TI'(0);
                        x.tag  = {i[1:0], seq[i]};
                        x.a    = {draw(i), draw(i)};
                        x.b    = {draw(i), draw(i)};
                        x.c    = {draw(i), draw(i)};
                        x.last = (left[i] == 1);
                        in_valid[i] <= 1;
                        in_data[i]  <= x;
                    end
                end
            end
        end
    end

    // ---- sink --------------------------------------------------------------
    int unsigned sink, burst;
    bit          sink_on;
    always @(cb) if (run) begin
        if (full || probe || stop) out_ready <= 1;
        else case (sink)
            0: out_ready <= 1;
            1: out_ready <= $urandom_range(1) != 0;
            default: begin
                if (burst == 0) begin
                    sink_on = !sink_on;
                    burst   = $urandom_range(16, 1);
                end
                burst--;
                out_ready <= sink_on;
            end
        endcase
    end

    // ---- lone-beat latency: handshake edges, in and out ---------------------
    int unsigned cyc, t_in, t_out;
    always @(cb) begin
        cyc++;
        if (probe && in_valid[0] && cb.in_ready[0]) t_in = cyc;
        if (probe && cb.out_valid && out_ready && t_out == 0) t_out = cyc;
    end

    // ---- scoreboard --------------------------------------------------------
    bit          in_pkt;
    int unsigned pkt_src, n_got[N], n_got_all, errors;
    bit          done;      // the top finishes the sim (and fails it on errors)
    string       order;     // the source of each of the first 200 packets out
    function automatic void err(string msg);
        errors++;
        if (errors <= 10) $display("ERROR @%0t: %s", $time, msg);
    endfunction
    always @(cb) if (run && cb.out_valid && out_ready) begin
        int unsigned s;
        TM e;
        s = 32'(cb.out_data.tag[7:6]);
        if (s >= N) err($sformatf("beat with source %0d", s));
        else if (exp_q[s].size() == 0)
            err($sformatf("in%0d: unexpected beat tag=%h (nothing outstanding)", s, cb.out_data.tag));
        else begin
            e = exp_q[s].pop_front();
            if (cb.out_data !== e)
                err($sformatf("in%0d: got tag=%h y=%h last=%b, expected tag=%h y=%h last=%b",
                              s, cb.out_data.tag, cb.out_data.y, cb.out_data.last, e.tag, e.y, e.last));
        end
        if (in_pkt && s != pkt_src)
            err($sformatf("beat from in%0d inside a packet from in%0d", s, pkt_src));
        if (!in_pkt && order.len() < 200) order = {order, $sformatf("%0d", s)};
        in_pkt  = !cb.out_data.last;
        pkt_src = s;
        n_got[s]++;
        n_got_all++;
    end

    // ---- protocol monitor at out -------------------------------------------
    bit was_stalled;
    TM  stalled_data;
    always @(cb) if (run) begin
        if (was_stalled) begin
            if (!cb.out_valid) err("out: valid dropped before the beat was taken");
            else if (cb.out_data !== stalled_data) err("out: data changed while stalled");
        end
        was_stalled  = cb.out_valid && !out_ready;
        stalled_data = cb.out_data;
    end

    function automatic void check(bit ok, string msg);
        if (!ok) err(msg);
    endfunction

    initial begin
        int unsigned n0, cycles, min_tput, lat;
        if (!$value$plusargs("sink=%d", sink)) sink = 1;
        if (!$value$plusargs("cycles=%d", cycles)) cycles = 2000;
        if (!$value$plusargs("min_tput=%d", min_tput)) min_tput = 100;
        in_valid  = '0;
        in_data   = '0;
        out_ready = 0;
        rst       = 1;
        repeat (3) @(negedge clk);
        check(out_valid === 1'b0, "out_valid = 0 in reset");
        rst = 0;
        repeat (5) @(negedge clk);     // a class tree is built at reset release

        // Latency of a lone beat, sink ready.
        out_ready = 1;
        probe     = 1;
        run       = 1;
        begin
            TI x;
            x = TI'(0);
            x.tag = 0;
            x.a = 3;
            x.b = 5;
            x.c = 7;
            x.last = 1;
            in_data[0]  = x;
            in_valid[0] = 1;
            left[0]     = 1;      // a one-beat packet
        end
        while (t_out == 0 && cyc < 200) @(posedge clk);
        lat = t_out - t_in;
        check(t_out != 0, "lone beat never came out");
        repeat (5) @(posedge clk);
        probe = 0;

        // Random traffic and stalls.
        repeat (cycles) @(posedge clk);

        // Full: everyone always valid and ready.
        full = 1;
        repeat (40) @(posedge clk);
        n0 = n_got_all;
        repeat (100) @(posedge clk);
        check(n_got_all - n0 >= min_tput,
              $sformatf("throughput: %0d beats in 100 cycles, expected >= %0d", n_got_all - n0, min_tput));
        $display("throughput: %0d/100", n_got_all - n0);

        // Drain.
        full = 0;
        stop = 1;
        repeat (400) @(posedge clk);
        foreach (n_sent[i]) begin
            check(n_got[i] == n_sent[i], $sformatf("in%0d: sent %0d, got %0d", i, n_sent[i], n_got[i]));
            check(exp_q[i].size() == 0, $sformatf("in%0d: %0d beats outstanding", i, exp_q[i].size()));
            check(n_got[i] > 50, $sformatf("in%0d served only %0d beats", i, n_got[i]));
        end
        check(!in_pkt, "a packet still open after drain");

        $display("latency: %0d", lat);
        $display("order: %s", order);
        if (errors == 0) $display("PASS: %s sink=%0d: %0d beats", NAME, sink, n_got_all);
        else $display("FAIL: %s sink=%0d: %0d errors", NAME, sink, errors);
        done = 1;
    end
endmodule
