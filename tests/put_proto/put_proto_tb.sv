// Signal-level demonstration of the std `put` protocol: a class-layer producer
// drives put() through its port, which the fw_root block binds to an
// fw_put_xtor_bridge over a live fw_put_xtor_if. Each put() registers its value
// onto the bus output with NO handshake -- put is one-way and unbackpressured,
// so the producer simply emits one beat per clock. A clocked sampler captures
// the bus every cycle, and the test passes once the full BASE..BASE+N-1 run has
// appeared contiguously on the wire.
//
// This is the put counterpart to tests/rv_proto (which proves the handshaked
// ready/valid path) and tests/intf_pc (which proves the same put API used purely
// at the TLM layer, with no transactor). Put has no core FSM: with no handshake
// to translate, the transactor interface drives the pin directly.
`include "fw_hdl_macros.svh"

module put_proto_tb;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;
    import put_proto_pkg::*;

    logic  clock = 1'b0;
    logic  reset = 1'b1;
    data_t bus;

    always #5ns clock = ~clock;

    // The put transactor interface: its put() task registers each beat onto the
    // unhandshaked output `bus`.
    fw_put_xtor_if #(data_t) u_put (.clock(clock), .reset(reset), .out(bus));

    // Clocked sampler: capture the unhandshaked bus value every cycle. With no
    // valid line there is nothing to qualify on, so we record every sample and
    // look for the producer's run within the captured stream.
    data_t samples[$];
    always @(posedge clock) if (!reset) samples.push_back(bus);

    // Bus monitor for visibility.
    always @(posedge clock) if (!reset)
        $display("[bus] data=0x%08h @ %0t", bus, $time);

    // Bind the producer's port to the signal-level put bridge over u_put.
    `fw_root_begin(put_top, u_root, clock, reset)
        `fw_root_bind_port(prod.out, u_put, fw_put_xtor_bridge #(data_t))
    `fw_root_end

    // Did the contiguous BASE..BASE+N-1 run appear on the bus?
    function automatic bit saw_stream();
        for (int i = 0; i + N <= samples.size(); i++) begin
            automatic bit ok = 1'b1;
            for (int unsigned j = 0; j < N; j++)
                if (samples[i + j] !== data_t'(BASE + j)) ok = 1'b0;
            if (ok) return 1'b1;
        end
        return 1'b0;
    endfunction

    initial begin
        automatic int errors = 0;

        reset = 1'b1;
        repeat (4) @(posedge clock);
        reset = 1'b0;

        // fw_root news the root one clock after release; then the producer emits
        // its N beats, one per clock. Allow generous slack for the sampler.
        while (u_root.root == null) @(posedge clock);
        repeat (N + 20) @(posedge clock);

        if (!saw_stream()) begin
            errors++;
            $display("[put_proto] FAIL: contiguous %0d-beat run from 0x%08h not seen",
                     N, BASE);
            foreach (samples[i])
                $display("  sample[%0d] = 0x%08h", i, samples[i]);
        end

        if (errors == 0)
            $display("[put_proto] PASS");
        else
            $display("[put_proto] FAIL (%0d errors)", errors);
        $finish;
    end

    // Watchdog so a broken transactor fails fast instead of hanging.
    initial begin
        #100us;
        $fatal(1, "[put_proto] TIMEOUT");
    end
endmodule
