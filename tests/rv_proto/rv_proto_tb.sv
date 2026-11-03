// Ready/valid kit test (src/std/rv): an initiator and a target transactor on
// one ready/valid bus, with a monitor tapping it. The class tree (driver, sink,
// observer) sends N beats; the sink must receive them in order and unchanged,
// and the monitor must see the same stream. The sink is slower than the bus, so
// ready drops and the handshake is exercised under backpressure.
//
// The payload type comes from rv_proto_pkg (32-bit, 8-bit or a struct).

// fw_root_begin/end (and the bind macros) come from the fw library; the
// rv class layer (APIs, bridges, components) comes from rv_proto_pkg.
`include "fw_hdl_macros.svh"

module rv_proto_tb;
    import fw_hdl_pkg::*;
    import fw_rv_pkg::*;
    import rv_proto_pkg::*;

    // --------------------------------------------------------------
    // Signal-level setup: the two transactor modules on a shared ready/valid bus.
    // --------------------------------------------------------------
    logic clock = 1'b0;
    logic reset = 1'b1;

    bit    bus_valid;
    bit    bus_ready;
    data_t bus_data;

    always #5ns clock = ~clock;

    // Bus monitor: shows the initiator's driven output and the target's ready
    // on the actual wires (no reaching into interfaces).
    int unsigned stalls = 0;
    always @(posedge clock) if (!reset && bus_valid && !bus_ready) stalls++;

    always @(posedge clock) if (!reset)
        $display("[bus]          valid=%b data=0x%0h ready=%b @ %0t",
                 bus_valid, bus_data, bus_ready, $time);

    // The two transactor modules (each bundles its xtor_if + core via an internal
    // ready/valid link) wired together on the shared ready/valid bus. Each
    // xtor_if has an internal pipeline FIFO (depth is a protocol property set in
    // the interface), so the caller can run ahead of the bus round-trip.
    fw_rv_initiator_xtor #(.T(data_t)) init_xtor (
        .clock(clock), .reset(reset),
        .data(bus_data), .valid(bus_valid), .ready(bus_ready)
    );
    fw_rv_target_xtor #(.T(data_t)) targ_xtor (
        .clock(clock), .reset(reset),
        .valid(bus_valid), .ready(bus_ready), .data(bus_data)
    );
    // Monitor transactor: passively taps the same bus (drives nothing).
    fw_rv_monitor_xtor #(.T(data_t)) mon_xtor (
        .clock(clock), .reset(reset),
        .valid(bus_valid), .ready(bus_ready), .data(bus_data)
    );

    // --------------------------------------------------------------
    // Automatic lifecycle, described compactly. `fw_root_begin/bind/end expands
    // to the rv_top_bind class (= fw_component_root #(rv_top) + the bridge
    // construction) and the fw_root instance u_root that runs it: on reset
    // release it news rv_top_bind and forks its run() (build -> connect -> run);
    // on a reset it kills and restarts the tree. u_root.root is the live root.
    //
    // Each bind line constructs one bridge over a live module-scope interface
    // and connects it to a tree endpoint:
    //   initiator -> drv.out (driver's port)   target -> chk.in (sink export)
    //                                           monitor -> obs.mon (observer export)
    // --------------------------------------------------------------
    `fw_root_begin(rv_top, u_root, clock, reset)
        // endpoint, its live vif, the bridge that adapts it. Suffix = endpoint
        // kind: drv.out is a port; chk.in / obs.mon are exports.
        `fw_root_bind_port  (drv.out, init_xtor.u_if, fw_rv_initiator_bridge #(data_t))
        `fw_root_bind_export(chk.in,  targ_xtor.u_if, fw_rv_target_bridge    #(data_t))
        `fw_root_bind_export(obs.mon, mon_xtor.u_if, fw_rv_monitor_bridge   #(data_t))
    `fw_root_end

    initial begin
        automatic int errors = 0;

        // Reset, then release. fw_root elaborates + runs the tree on release.
        reset = 1'b1;
        repeat (4) @(posedge clock);
        reset = 1'b0;

        // Wait for fw_root to new the root (one clock after release), then drain:
        // wait until every beat has reached BOTH the sink and the monitor.
        while (u_root.root == null) @(posedge clock);
        while (u_root.root.chk.received.size() < N || u_root.root.obs.seen.size() < N)
            @(posedge clock);

        // Check: every beat arrived at the sink, in order, unchanged.
        if (u_root.root.chk.received.size() != N) begin
            $display("FAIL: expected %0d beats, got %0d", N, u_root.root.chk.received.size());
            errors++;
        end else begin
            for (int unsigned i = 0; i < N; i++) begin
                automatic data_t exp = beat(i);
                if (u_root.root.chk.received[i] !== exp) begin
                    $display("FAIL: beat %0d expected 0x%0h got 0x%0h",
                             i, exp, u_root.root.chk.received[i]);
                    errors++;
                end
            end
        end

        // Check: the monitor observed the same N beats, in order.
        if (u_root.root.obs.seen.size() != N) begin
            $display("FAIL: monitor expected %0d beats, got %0d", N, u_root.root.obs.seen.size());
            errors++;
        end else begin
            for (int unsigned i = 0; i < N; i++) begin
                automatic data_t exp = beat(i);
                if (u_root.root.obs.seen[i] !== exp) begin
                    $display("FAIL: monitor beat %0d expected 0x%0h got 0x%0h",
                             i, exp, u_root.root.obs.seen[i]);
                    errors++;
                end
            end
        end

        $display("[rv_proto] stalls=%0d", stalls);
        if (stalls == 0) begin
            $display("FAIL: the bus never saw valid && !ready");
            errors++;
        end
        if (errors == 0)
            $display("[rv_proto] PASS");
        else
            $display("[rv_proto] FAIL (%0d errors)", errors);
        $display("X done");
        $finish;
    end

    // Watchdog so a broken handshake fails fast instead of hanging.
    initial begin
        #100us;
        $fatal(1, "[rv_proto] TIMEOUT");
    end
endmodule
