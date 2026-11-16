// Module testbench for the hand-written reference rr_merge_ref
// (rtl/rr_merge_ref.sv), with the stimulus and checks of tb/rr_merge_tb.sv
// and no fw-hdl classes: the producers and the consumer drive the module's
// ports directly. Producer i sends packets of 1-4 beats, data
// {i, seq}, with random gaps; the consumer stalls at random. Checks: a
// packet's beats arrive together (no interleave), each source's beats arrive
// in order with none lost, every source is served, full throughput when
// nobody stalls, and reset values.
//
// Reset: the class testbench reads ready = 0 at the pins in reset, but that
// is the pin bridge forcing it (fw_rv_pin: "reset-forced"); the class
// comb() has no reset term, so neither does the reference. Here, in reset,
// out_valid must be 0, and with no input valid only in_0 (ptr = 0) sees
// ready (the FIFO is empty).
//
// With +define+RR_MERGE_GEN the DUT is the RTL generated from the classes
// (module rr_merge, rtl/gen/rr_merge.sv). The reference then runs beside it
// on the same inputs, and every output is compared each cycle (lockstep).
module rr_merge_ref_tb;
    localparam int N = 4;
    localparam int W = 9;   // {data[7:0], last}

    logic clk = 0, rst = 1;
    always #5 clk = ~clk;

    logic         a_valid[N], a_ready[N];
    logic [W-1:0] a_data[N];
    logic         b_valid, b_ready;
    logic [W-1:0] b_data;

    // The DUT's ports: the reference and the generated RTL have the same
    // interface (the classes'): port arrays as packed arrays per field.
    logic [N-1:0]          p_valid, p_ready;
    logic [N-1:0][W-1:0]   p_data;
    for (genvar i = 0; i < N; i++) begin : g_in
        assign p_valid[i] = a_valid[i];
        assign p_data[i]  = a_data[i];
        assign a_ready[i] = p_ready[i];
    end

`ifdef RR_MERGE_GEN
    localparam string DUT = "rr_merge (generated)";
    rr_merge #(.N(N), .DEPTH(2)) dut (
`else
    localparam string DUT = "rr_merge_ref";
    rr_merge_ref #(.N(N), .DEPTH(2)) dut (
`endif
        .clock(clk), .reset(rst),
        .in_valid(p_valid), .in_ready(p_ready), .in_data(p_data),
        .out_valid(b_valid), .out_ready(b_ready), .out_data(b_data));

`ifdef RR_MERGE_GEN
    // Lockstep: the reference on the same inputs; outputs compared at each
    // negedge (inputs change at posedge).
    logic [N-1:0] r_ready;
    logic         r_valid;
    logic [W-1:0] r_data;
    int unsigned  n_cmp, n_mismatch;
    rr_merge_ref #(.N(N), .DEPTH(2)) ref_i (
        .clock(clk), .reset(rst),
        .in_valid(p_valid), .in_ready(r_ready), .in_data(p_data),
        .out_valid(r_valid), .out_ready(b_ready), .out_data(r_data));
    always @(negedge clk) begin
        bit ok;
        ok = b_valid === r_valid && p_ready === r_ready
             && (b_data === r_data || $isunknown(r_data));
        n_cmp++;
        if (!ok) begin
            n_mismatch++;
            if (n_mismatch <= 10)
                $display("ERROR: lockstep @%0t: gen valid=%b data=%h ready=%b, ref valid=%b data=%h ready=%b",
                         $time, b_valid, b_data, p_ready, r_valid, r_data, r_ready);
        end
    end
`endif

    // Producers. A beat offered stays until taken. `left` counts the beats
    // of the current packet still to send (0: between packets).
    bit          run_rtl, full, stop;
    int unsigned left[N];
    bit [5:0]    seq[N];
    int unsigned n_sent[N];
    always @(posedge clk) if (run_rtl) begin
        for (int i = 0; i < N; i++) begin
            if (a_valid[i] && a_ready[i]) begin
                n_sent[i]++;
                seq[i]++;
                left[i]--;
                a_valid[i] <= 0;
            end
            if (!(a_valid[i] && !a_ready[i])) begin
                if (left[i] == 0 && !stop && (full || $urandom_range(3) == 0))
                    left[i] = $urandom_range(4, 1);
                if (left[i] != 0 && (full || $urandom_range(3) != 0)) begin
                    a_valid[i] <= 1;
                    a_data[i]  <= {i[1:0], seq[i], left[i] == 1};
                end
            end
        end
        b_ready <= full || $urandom_range(3) != 0;
    end

    // Consumer and checks. b_data = {src[1:0], seq[5:0], last}.
    bit          in_pkt;
    int unsigned pkt_src;
    bit [5:0]    exp_seq[N];
    int unsigned n_got[N], n_got_all, errors;
    always @(posedge clk) if (run_rtl && b_valid && b_ready) begin
        int unsigned s;
        s = 32'(b_data[8:7]);
        if (in_pkt && s != pkt_src) begin
            $display("ERROR: beat from in%0d inside a packet from in%0d", s, pkt_src);
            errors++;
        end
        if (b_data[6:1] != exp_seq[s]) begin
            $display("ERROR: in%0d: got seq %0d, expected %0d", s, b_data[6:1], exp_seq[s]);
            errors++;
        end
        exp_seq[s] = b_data[6:1] + 1;
        in_pkt  = !b_data[0];
        pkt_src = s;
        n_got[s]++;
        n_got_all++;
    end

    task automatic check(bit ok, string msg);
        if (!ok) begin
            $display("ERROR: %s", msg);
            errors++;
        end
    endtask

    task automatic check_reset_values(string when);
        check(b_valid === 1'b0, $sformatf("out_valid = 0 %s", when));
        check(a_ready[0] === 1'b1 && a_ready[1] === 1'b0 && a_ready[2] === 1'b0
              && a_ready[3] === 1'b0,
              $sformatf("ready on in0 only (ptr = 0, FIFO empty) %s", when));
    endtask

    initial begin
        int unsigned n0;
        foreach (a_valid[i]) begin
            a_valid[i] = 0;
            a_data[i]  = '0;
        end
        b_ready = 0;

        // Reset: state and the registered out_valid clear after the first edge.
        repeat (3) begin
            @(negedge clk);
            check_reset_values("in reset");
        end
        rst = 0;
        repeat (5) @(negedge clk);
        check_reset_values("after reset");
        run_rtl = 1;

        // Random traffic and stalls.
        repeat (2000) @(posedge clk);

        // Full: everyone always valid and ready, one beat per cycle out.
        full = 1;
        repeat (20) @(posedge clk);
        n0 = n_got_all;
        repeat (100) @(posedge clk);
        check(n_got_all - n0 == 100, $sformatf("full throughput: %0d beats in 100 cycles", n_got_all - n0));

        // Drain: finish the packets in flight, then compare counts.
        full = 0;
        stop = 1;
        repeat (200) @(posedge clk);
        foreach (n_sent[i]) begin
            check(n_got[i] == n_sent[i], $sformatf("in%0d: sent %0d, got %0d", i, n_sent[i], n_got[i]));
            check(n_got[i] > 100, $sformatf("in%0d served only %0d beats", i, n_got[i]));
        end
        check(!in_pkt, "a packet still open after drain");

        // Reset again after traffic (ptr has moved): the state clears.
        @(negedge clk);
        run_rtl = 0;
        b_ready = 0;
        foreach (a_valid[i]) a_valid[i] = 0;
        rst = 1;
        repeat (2) @(negedge clk);
        check_reset_values("in a second reset");

`ifdef RR_MERGE_GEN
        check(n_mismatch == 0, $sformatf("lockstep: %0d of %0d cycles differ from the reference",
                                         n_mismatch, n_cmp));
        $display("lockstep: %0d cycles compared with rr_merge_ref", n_cmp);
`endif
        if (errors == 0) $display("PASS: %s: %0d beats", DUT, n_got_all);
        else $fatal(1, "FAIL: %s: %0d errors", DUT, errors);
        $finish;
    end
endmodule
