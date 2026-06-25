// Ready/valid protocol-kit demonstration with the FULL three-component
// transactor structure (see skills/fw-proto-kit). Per role:
//
//   1. transactor-interface SV interface (rv_*_xtor_if) -- implements the API
//      methods (send/recv) over an internal DEPTH-deep FIFO, and is a ready/valid
//      endpoint on an internal LINK to the core. send()/recv() only touch the
//      FIFO (send blocks only when full, recv only when empty); a clocked always
//      block drains/fills the FIFO across the link. This lets the caller PIPELINE
//      -- run ahead by up to DEPTH beats, decoupled from the link/bus round-trip.
//      The link is ALWAYS a plain ready/valid channel (`up_valid`/`up_data`/
//      `up_ready`); it never adopts the external protocol's language. FIFO DEPTH
//      is a fixed protocol property set inside the interface (a localparam), NOT
//      a port parameter -- see the Verilator note below.
//   2. core transactor module (rv_*_xtor_core) -- a clocked FSM that is a
//      ready/valid endpoint on the internal link and runs the signal-level
//      protocol on the pins (for ready/valid the pins ARE ready/valid). A richer
//      protocol (e.g. wishbone) elaborates a larger pin-level FSM here; the
//      internal ready/valid link contract is unchanged.
//   3. transactor module (rv_*_xtor) -- instances the interface + core and
//      wires the ready/valid link between them with plain nets, exposing
//      clock/reset + pins.
//
// On top of that sit the class-level pieces:
//   * API interface-classes (rv_initiator_if / rv_target_if), each shipping its
//     `FW_RV_*_IMP implementation macro.
//   * Bridge classes holding a virtual transactor-interface and implementing /
//     consuming the API (initiator = provider/export, target = port).
//   * driver (port) pushes beats; sink (export) receives them.
//
// The two transactor modules share one ready/valid bus, so every beat crosses
// the real handshake; the target bridge applies backpressure.
//
// DESIGN NOTES (what makes the clocked-core split correct):
//   * Every interface and module is CLOCKED (has clock/reset). In this flow a
//     module/core output is only reliably observed by another block's clocked
//     sampling when it is REGISTERED -- a combinational drive into an interface
//     input port loses the value to a delta-cycle race. Real protocol cores are
//     clocked FSMs anyway, so this is the natural form.
//   * The interface<->core link is ALWAYS a plain ready/valid channel (never the
//     external protocol's language), and a real clocked handshake -- not a bare
//     registered passthrough. A passthrough merely delays the signals, and the
//     latency lets the consumer re-sample a beat the producer has not yet
//     advanced past (duplicated beats). A proper ready/valid handshake transfers
//     exactly one beat per (valid && ready) cycle on each side.
//   * Parameterize SYMMETRICALLY or not at all. A parameter on the interface
//     mangles its type (e.g. rv_initiator_xtor_if__D4), so EVERY element naming
//     that type must carry the same parameter -- the `virtual` handle, bridge,
//     wrapper. Asymmetry (a #(.DEPTH(4)) instance bound to a plain
//     `virtual rv_initiator_xtor_if`) gives Verilator "expected ... interface but
//     ... is a different interface". Fixed properties like FIFO DEPTH are kept as
//     internal localparams so no parameter is threaded through every element.
//   * Verilator quirks (rev v5.049): a parameterized interface as a MODULE PORT
//     crashes elaboration (V3Param.cpp:523), and a `type`-parameterized interface
//     INSTANCE does not receive externally-driven input values. So the
//     transactor interfaces/cores are concrete (logic [31:0]) while the class
//     layer stays parameterized. Full simulators (Questa/VCS/Xcelium) support
//     the parameterized form; that is the production structure.

// fw_root_begin/end (and the bind macros) come from the fw library; the
// rv class layer (APIs, bridges, components) comes from rv_proto_pkg.
`include "fw_hdl_macros.svh"

module rv_proto_tb;
    import fw_hdl_pkg::*;
    import rv_proto_pkg::*;

    // --------------------------------------------------------------
    // Signal-level setup: the two transactor modules on a shared ready/valid bus.
    // --------------------------------------------------------------
    logic clock = 1'b0;
    logic reset = 1'b1;

    bit        bus_valid;
    bit        bus_ready;
    bit [31:0] bus_data;

    always #5ns clock = ~clock;

    // Bus monitor: shows the initiator's driven output and the target's ready
    // on the actual wires (no reaching into interfaces).
    always @(posedge clock) if (!reset)
        $display("[bus]          valid=%b data=0x%08h ready=%b @ %0t",
                 bus_valid, bus_data, bus_ready, $time);

    // The two transactor modules (each bundles its xtor_if + core via an internal
    // ready/valid link) wired together on the shared ready/valid bus. Each
    // xtor_if has an internal pipeline FIFO (depth is a protocol property set in
    // the interface), so the caller can run ahead of the bus round-trip.
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
        `fw_root_bind_port  (drv.out, init_xtor.u_if, rv_initiator_bridge #(data_t))
        `fw_root_bind_export(chk.in,  targ_xtor.u_if, rv_target_bridge    #(data_t))
        `fw_root_bind_export(obs.mon, mon_xtor.u_if, rv_monitor_bridge   #(data_t))
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
                automatic data_t exp = 32'hcafe_0000 + i;
                if (u_root.root.chk.received[i] !== exp) begin
                    $display("FAIL: beat %0d expected 0x%08h got 0x%08h",
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
                automatic data_t exp = 32'hcafe_0000 + i;
                if (u_root.root.obs.seen[i] !== exp) begin
                    $display("FAIL: monitor beat %0d expected 0x%08h got 0x%08h",
                             i, exp, u_root.root.obs.seen[i]);
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
