// rr_merge between pins: four pin-level producers -> fw_rv_pin_in ->
// rr_merge -> fw_rv_pin_out -> a pin-level consumer, under a clocked
// fw_root. Producer i sends packets of 1-4 beats, data {i, seq}, with random
// gaps; the consumer stalls at random. Checks: a packet's beats arrive
// together (no interleave), each source's beats arrive in order with none
// lost, every source is served, full throughput when nobody stalls, and
// ready/valid read 0 in reset.
import fw_hdl_pkg::*;
import rr_merge_pkg::*;

class rr_merge_root extends fw_component_root #(fw_component);
    rr_merge4_t dut;

    function new(string name);
        super.new(name);
    endfunction

    virtual function void build();
        dut = rr_merge4_t::type_id::create("dut", this);
    endfunction

    virtual function void connect();
        foreach (dut.in[i])
            fw_rv_pin #(rr_beat_t)::find($sformatf("in%0d", i)).connect_in(dut.in[i]);
        fw_rv_pin #(rr_beat_t)::find("out").connect_out(dut.out);
    endfunction
endclass

module rr_merge_tb;
    localparam int N = 4;

    logic clk = 0, rst = 1;
    always #5 clk = ~clk;

    sv_weave_init_m u_init();
    fw_root #(.Tbind(rr_merge_root)) u_root (.clock(clk), .reset(rst));

    logic     a_valid[N], a_ready[N];
    rr_beat_t a_data[N];
    logic     b_valid, b_ready;
    rr_beat_t b_data;

    // The pins are register outputs of the module code below, so the fields
    // they drive are wires on the tree's side (COMB).
    fw_rv_pin_in  #(.T(rr_beat_t), .NAME("in0"), .COMB(1)) u_in0 (
        .valid(a_valid[0]), .data(a_data[0]), .ready(a_ready[0]));
    fw_rv_pin_in  #(.T(rr_beat_t), .NAME("in1"), .COMB(1)) u_in1 (
        .valid(a_valid[1]), .data(a_data[1]), .ready(a_ready[1]));
    fw_rv_pin_in  #(.T(rr_beat_t), .NAME("in2"), .COMB(1)) u_in2 (
        .valid(a_valid[2]), .data(a_data[2]), .ready(a_ready[2]));
    fw_rv_pin_in  #(.T(rr_beat_t), .NAME("in3"), .COMB(1)) u_in3 (
        .valid(a_valid[3]), .data(a_data[3]), .ready(a_ready[3]));
    fw_rv_pin_out #(.T(rr_beat_t), .NAME("out"), .COMB(1)) u_out (
        .valid(b_valid), .data(b_data), .ready(b_ready));

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
                    a_valid[i]     <= 1;
                    a_data[i].data <= {i[1:0], seq[i]};
                    a_data[i].last <= (left[i] == 1);
                end
            end
        end
        b_ready <= full || $urandom_range(3) != 0;
    end

    // Consumer and checks.
    bit          in_pkt;
    int unsigned pkt_src;
    bit [5:0]    exp_seq[N];
    int unsigned n_got[N], n_got_all, errors;
    always @(posedge clk) if (run_rtl && b_valid && b_ready) begin
        int unsigned s;
        s = b_data.data[7:6];
        if (in_pkt && s != pkt_src) begin
            $display("ERROR: beat from in%0d inside a packet from in%0d", s, pkt_src);
            errors++;
        end
        if (b_data.data[5:0] != exp_seq[s]) begin
            $display("ERROR: in%0d: got seq %0d, expected %0d", s, b_data.data[5:0], exp_seq[s]);
            errors++;
        end
        exp_seq[s] = b_data.data[5:0] + 1;
        in_pkt  = !b_data.last;
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

    initial begin
        rr_merge_root r;
        int unsigned n0;
        foreach (a_valid[i]) begin
            a_valid[i] = 0;
            a_data[i]  = '0;
        end
        b_ready = 0;

        // Reset: the pins read ready = 0, valid = 0.
        repeat (3) begin
            @(negedge clk);
            foreach (a_ready[i]) check(a_ready[i] === 1'b0, "a_ready in reset");
            check(b_valid === 1'b0, "b_valid in reset");
        end
        rst = 0;
        repeat (5) begin
            @(negedge clk);
            r = u_root.root;
        end
        check(r != null && r.elaborated, "tree elaborated");
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

        if (errors == 0) $display("PASS: rr_merge: %0d beats", n_got_all);
        else $fatal(1, "FAIL: rr_merge: %0d errors", errors);
        fw_sync_kernel::m_live = 0;
        $finish;
    end
endmodule
