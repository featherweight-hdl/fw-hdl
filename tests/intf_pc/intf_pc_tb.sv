
// Producer/consumer demonstration of the std `put` protocol used purely at the
// TLM (class) layer, driven through the fw_root_begin/fw_root_end lifecycle. The
// class layer (producer, consumer, pc_top) lives in intf_pc_pkg; the put API
// itself is built into fw_std_pkg. This module just supplies clock/reset and the
// fw_root instance, then checks what arrived.
//
// The put API is here a pure TLM call (no signal-level transactor), so the
// fw_root block carries no bind lines: pc_top.connect() wires prod.out ->
// cons.in, and do_run() forks the producer, which puts four beats straight to
// the consumer.
`include "fw_hdl_macros.svh"

module intf_pc_tb;
    import fw_hdl_pkg::*;
    import intf_pc_pkg::*;

    logic clock = 1'b0;
    logic reset = 1'b1;

    always #5ns clock = ~clock;

    `fw_root_begin(pc_top, u_root, clock, reset)
    `fw_root_end

    initial begin
        automatic int errors = 0;

        reset = 1'b1;
        repeat (4) @(posedge clock);
        reset = 1'b0;

        // fw_root news the root one clock after release; the producer sends its
        // four beats during the run phase.
        while (u_root.root == null) @(posedge clock);
        while (u_root.root.cons.received.size() < 4) @(posedge clock);

        if (u_root.root.cons.received.size() != 4) begin
            $display("FAIL: expected 4 items, got %0d", u_root.root.cons.received.size());
            errors++;
        end else begin
            for (int i = 0; i < 4; i++) begin
                automatic data_t exp = 32'hdead_0000 + i;
                if (u_root.root.cons.received[i] !== exp) begin
                    $display("FAIL: item %0d expected 0x%08h got 0x%08h",
                             i, exp, u_root.root.cons.received[i]);
                    errors++;
                end
            end
        end

        if (errors == 0)
            $display("[intf_pc] PASS");
        else
            $display("[intf_pc] FAIL (%0d errors)", errors);
        $finish;
    end

    initial begin
        #100us;
        $fatal(1, "[intf_pc] TIMEOUT");
    end
endmodule
