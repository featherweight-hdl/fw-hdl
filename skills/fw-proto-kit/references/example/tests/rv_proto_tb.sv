// Demonstrator for the ready/valid protocol kit (rv_proto_pkg). This is an
// example APPLICATION that USES the kit -- it is not part of the kit itself.
//
//   * driver   -- a component with a port over the initiator API (rv_initiator_if);
//                 it send()s N beats.
//   * sink     -- a component that PROVIDES the target API (rv_target_if) via the
//                 `FW_RV_TARGET_IMP macro; put() records each received beat.
//   * observer -- a component that PROVIDES the monitor API (rv_monitor_if) via
//                 `FW_RV_MONITOR_IMP; observe() (non-blocking) records each beat
//                 the passive monitor sees on the bus.
//   * rv_top   -- builds the three bridges over the transactor-interfaces and
//                 connects each to its peer (driver.out -> initiator export;
//                 target port -> sink.in; monitor port -> observer.mon).
//
// The three transactor modules (rv_initiator_xtor / rv_target_xtor /
// rv_monitor_xtor) sit on one shared ready/valid bus; the monitor passively taps
// it (drives nothing) while every beat crosses the real signal-level handshake.
module rv_proto_tb;
    import fw_hdl_pkg::*;
    import rv_proto_pkg::*;

    typedef logic [31:0] data_t;

    localparam int unsigned N = 8;

    // --------------------------------------------------------------
    // Driver: consumes the initiator API through a port.
    // --------------------------------------------------------------
    class driver extends fw_component;
        fw_port #(rv_initiator_if #(data_t)) out;

        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction

        function void build();
            out = new("out", this);
        endfunction

        virtual task run();
            rv_initiator_if #(data_t) api = out.get_if();
            for (int unsigned i = 0; i < N; i++) begin
                automatic data_t v = 32'hcafe_0000 + i;
                api.send(v);
                $display("[driver]  sent 0x%08h @ %0t", v, $time);
            end
        endtask
    endclass

    // --------------------------------------------------------------
    // Sink: PROVIDES the rv_target_if implementation (via the API macro).
    // --------------------------------------------------------------
    class sink extends fw_component;
        data_t received[$];

        `FW_RV_TARGET_IMP(data_t, sink, in);

        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction

        function void build();
            in = new(this);
        endfunction

        virtual task in_put(input data_t t);
            received.push_back(t);
            $display("[sink]    put  0x%08h @ %0t", t, $time);
        endtask
    endclass

    // --------------------------------------------------------------
    // Observer: PROVIDES the rv_monitor_if implementation (via the API macro).
    // A passive subscriber -- records every beat the monitor publishes.
    // --------------------------------------------------------------
    class observer extends fw_component;
        data_t seen[$];

        `FW_RV_MONITOR_IMP(data_t, observer, mon);

        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction

        function void build();
            mon = new(this);
        endfunction

        virtual function void mon_observe(input data_t t);
            seen.push_back(t);
            $display("[monitor] observed 0x%08h @ %0t", t, $time);
        endfunction
    endclass

    // --------------------------------------------------------------
    // Top: instances driver + sink + observer, builds the bridges over the three
    // transactor interfaces, and connects each to its peer.
    // --------------------------------------------------------------
    class rv_top extends fw_component;
        driver   drv;
        sink     chk;
        observer obs;
        rv_target_bridge  #(data_t) tbr;
        rv_monitor_bridge #(data_t) mbr;
        virtual rv_initiator_xtor_if vif_init;
        virtual rv_target_xtor_if    vif_targ;
        virtual rv_monitor_xtor_if   vif_mon;

        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction

        function void build();
            drv = new("drv", this);
            chk = new("chk", this);
            obs = new("obs", this);
            drv.build();
            chk.build();
            obs.build();
        endfunction

        function void connect();
            // Initiator transactor: the driver's port connects to its export.
            rv_initiator_bridge #(data_t) ibr =
                new("init_bridge", this, vif_init);
            drv.out.connect(ibr.exp);

            // Target transactor: a port that calls into the sink's export.
            tbr = new("targ_bridge", this, vif_targ);
            tbr.connect(chk.in);

            // Monitor transactor: a port that publishes to the observer's export.
            mbr = new("mon_bridge", this, vif_mon);
            mbr.connect(obs.mon);
        endfunction
    endclass

    // --------------------------------------------------------------
    // Signal-level setup: the two transactor modules on a shared ready/valid bus.
    // --------------------------------------------------------------
    logic clock = 1'b0;
    logic reset = 1'b1;

    bit        bus_valid;
    bit        bus_ready;
    bit [31:0] bus_data;

    always #5ns clock = ~clock;

    rv_initiator_xtor init_xtor (
        .clock(clock), .reset(reset),
        .data(bus_data), .valid(bus_valid), .ready(bus_ready)
    );
    rv_target_xtor targ_xtor (
        .clock(clock), .reset(reset),
        .valid(bus_valid), .ready(bus_ready), .data(bus_data)
    );
    // Monitor transactor: passively taps the same bus (drives nothing).
    rv_monitor_xtor mon_xtor (
        .clock(clock), .reset(reset),
        .valid(bus_valid), .ready(bus_ready), .data(bus_data)
    );

    initial begin
        automatic rv_top top;
        automatic int errors = 0;

        // Reset, then release.
        reset = 1'b1;
        repeat (4) @(posedge clock);
        reset = 1'b0;

        top = new("top", null);
        top.vif_init = init_xtor.u_if;   // reach into the transactor module
        top.vif_targ = targ_xtor.u_if;
        top.vif_mon  = mon_xtor.u_if;
        top.build();
        top.connect();

        // Start the target + monitor sampling loops, then push N beats.
        fork
            top.tbr.run();
            top.mbr.run();
        join_none
        top.drv.run();

        // Drain: wait until every beat has reached BOTH the sink and the monitor.
        while (top.chk.received.size() < N || top.obs.seen.size() < N)
            @(posedge clock);

        // Check: every beat arrived at the sink, in order, unchanged.
        if (top.chk.received.size() != N) begin
            $display("FAIL: expected %0d beats, got %0d", N, top.chk.received.size());
            errors++;
        end else begin
            for (int unsigned i = 0; i < N; i++) begin
                automatic data_t exp = 32'hcafe_0000 + i;
                if (top.chk.received[i] !== exp) begin
                    $display("FAIL: beat %0d expected 0x%08h got 0x%08h",
                             i, exp, top.chk.received[i]);
                    errors++;
                end
            end
        end

        // Check: the monitor observed the same N beats, in order.
        if (top.obs.seen.size() != N) begin
            $display("FAIL: monitor expected %0d beats, got %0d", N, top.obs.seen.size());
            errors++;
        end else begin
            for (int unsigned i = 0; i < N; i++) begin
                automatic data_t exp = 32'hcafe_0000 + i;
                if (top.obs.seen[i] !== exp) begin
                    $display("FAIL: monitor beat %0d expected 0x%08h got 0x%08h",
                             i, exp, top.obs.seen[i]);
                    errors++;
                end
            end
        end

        if (errors == 0)
            $display("[rv_proto] PASS");
        else
            $display("[rv_proto] FAIL (%0d errors)", errors);
        $finish;
    end

    // Watchdog so a broken handshake fails fast instead of hanging.
    initial begin
        #100us;
        $fatal(1, "[rv_proto] TIMEOUT");
    end
endmodule
