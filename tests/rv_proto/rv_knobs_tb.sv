// The rv transactors' run-time knobs, at module level (no class tree):
// initiator -> pins -> target, with a monitor tapping the pins. Each phase
// drives the transactor interfaces directly and checks one knob:
//   1 defaults:          N beats in order; the monitor sees one first-valid and
//                        one transfer event per beat
//   2 initiator max_gap: valid is low between beats on the pins
//   3 target max_gap:    valid is held high while ready is low
//   4 depth:             with the target stalled, exactly the beats the
//                        buffers hold are accepted (initiator depth 1, target
//                        depth 2, plus one in each core)
// Prints "[rv_knobs] PASS" and "X done".
module rv_knobs_tb;
    typedef logic [15:0] T;
    localparam int unsigned N = 24;

    bit clock = 0, reset = 1;
    always #5 clock = ~clock;

    logic valid, ready;
    T     data;

    fw_rv_initiator_xtor #(.T(T)) u_ini (.clock, .reset, .valid, .ready, .data);
    fw_rv_target_xtor    #(.T(T)) u_tgt (.clock, .reset, .valid, .ready, .data);
    fw_rv_monitor_xtor   #(.T(T)) u_mon (.clock, .reset, .valid, .ready, .data);

    // Pin statistics.
    int unsigned n_idle_between, n_valid_wait, n_xfer;
    bit seen_xfer;
    always @(posedge clock) if (!reset) begin
        if (valid && ready) begin n_xfer++; seen_xfer = 1; end
        if (seen_xfer && !valid) n_idle_between++;
        if (valid && !ready) n_valid_wait++;
    end

    int errors = 0;
    task automatic check(bit c, string msg);
        if (!c) begin errors++; $display("FAIL: %s", msg); end
    endtask

    // Monitor events, collected all the time.
    int unsigned n_first, n_mon_xfer, mon_order_err;
    T mon_first_data[$], mon_xfer_data[$];
    initial begin
        T t; bit first, xfer;
        forever begin
            u_mon.u_if.get_ev(t, first, xfer);
            if (first) begin n_first++; mon_first_data.push_back(t); end
            if (xfer) begin
                n_mon_xfer++; mon_xfer_data.push_back(t);
                if (n_mon_xfer > n_first) mon_order_err++;     // a transfer before its first valid
            end
        end
    end

    function automatic T beat(int unsigned phase, int unsigned i);
        return T'(phase * 256 + i);
    endfunction

    // Send N beats and receive them; returns the received beats in order.
    task automatic stream(int unsigned phase, output bit ok);
        T got;
        ok = 1;
        fork
            for (int unsigned i = 0; i < N; i++) u_ini.u_if.send(beat(phase, i));
            for (int unsigned i = 0; i < N; i++) begin
                u_tgt.u_if.recv(got);
                if (got !== beat(phase, i)) ok = 0;
            end
        join
    endtask

    task automatic reset_stats();
        repeat (4) @(posedge clock);
        n_idle_between = 0; n_valid_wait = 0; n_xfer = 0; seen_xfer = 0;
        n_first = 0; n_mon_xfer = 0; mon_order_err = 0;
        mon_first_data.delete(); mon_xfer_data.delete();
    endtask

    initial begin
        bit ok;
        int unsigned sent;
        repeat (3) @(posedge clock);
        reset = 0;

        // 1 defaults
        reset_stats();
        stream(1, ok);
        repeat (4) @(posedge clock);
        check(ok, "defaults: data");
        check(n_xfer == N, $sformatf("defaults: %0d transfers", n_xfer));
        check(n_first == N && n_mon_xfer == N && mon_order_err == 0,
              $sformatf("defaults: monitor first=%0d xfer=%0d order=%0d", n_first, n_mon_xfer,
                        mon_order_err));
        foreach (mon_xfer_data[i])
            check(mon_xfer_data[i] === beat(1, i) && mon_first_data[i] === beat(1, i),
                  $sformatf("defaults: monitor beat %0d", i));

        // 2 initiator max_gap: idle cycles between beats on the pins
        reset_stats();
        u_ini.u_if.max_gap = 4;
        stream(2, ok);
        u_ini.u_if.max_gap = 0;
        repeat (4) @(posedge clock);
        check(ok, "initiator gap: data");
        check(n_idle_between > N, $sformatf("initiator gap: %0d idle cycles", n_idle_between));
        check(n_first == N && n_mon_xfer == N, "initiator gap: monitor counts");
        $display("[rv_knobs] initiator gap: idle=%0d", n_idle_between);

        // 3 target max_gap: valid waits on ready; the monitor reports the
        // first valid cycle separately from the transfer
        reset_stats();
        u_tgt.u_if.max_gap = 4;
        stream(3, ok);
        u_tgt.u_if.max_gap = 0;
        repeat (4) @(posedge clock);
        check(ok, "target gap: data");
        check(n_valid_wait > N / 2, $sformatf("target gap: %0d valid-wait cycles", n_valid_wait));
        check(n_first == N && n_mon_xfer == N && mon_order_err == 0,
              $sformatf("target gap: monitor first=%0d xfer=%0d order=%0d", n_first, n_mon_xfer,
                        mon_order_err));
        foreach (mon_first_data[i])
            check(mon_first_data[i] === beat(3, i), $sformatf("target gap: first data %0d", i));
        $display("[rv_knobs] target gap: valid-wait=%0d first=%0d xfer=%0d", n_valid_wait,
                 n_first, n_mon_xfer);

        // 4 depth: nobody receives; count the sends that complete
        reset_stats();
        u_ini.u_if.depth = 1;
        u_tgt.u_if.depth = 2;
        sent = 0;
        fork begin
            for (int unsigned i = 0; i < N; i++) begin u_ini.u_if.send(beat(4, i)); sent++; end
        end join_none
        repeat (50) @(posedge clock);
        check(sent == 5, $sformatf("depth: %0d sends completed, expected 5", sent));
        disable fork;

        if (errors == 0) $display("[rv_knobs] PASS");
        else $display("[rv_knobs] FAIL (%0d errors)", errors);
        $display("X done");
        $finish;
    end
endmodule
