
// M4: the DMA worked example, driven through the fw_root lifecycle. dma_top
// wires host.regs_p -> dev.regs; fw_root seats the clock and forks the engine
// and host. The host programs channel 2 and waits for the engine to complete it;
// this module checks the recorded outcome and the engine's serviced count.
`include "fw_hdl_macros.svh"

module reg_dma_tb;
    import fw_hdl_pkg::*;
    import reg_dma_pkg::*;

    logic clock = 1'b0;
    logic reset = 1'b1;

    always #5ns clock = ~clock;

    `fw_root_begin(dma_top, u_root, clock, reset)
    `fw_root_end

    initial begin
        automatic int errors = 0;

        reset = 1'b1;
        repeat (4) @(posedge clock);
        reset = 1'b0;

        while (u_root.root == null) @(posedge clock);
        while (!u_root.root.host.finished) @(posedge clock);

        if (!u_root.root.host.ok) begin
            $display("FAIL: host outcome not ok (done=%0b int_done(1st)=%0b done(2nd)=%0b int_done(2nd)=%0b)",
                     u_root.root.host.first_seen.done,
                     u_root.root.host.first_seen.int_done,
                     u_root.root.host.second_seen.done,
                     u_root.root.host.second_seen.int_done);
            errors++;
        end
        if (u_root.root.dev.m_engine.serviced != 1) begin
            $display("FAIL: engine serviced %0d channels (expected 1)",
                     u_root.root.dev.m_engine.serviced);
            errors++;
        end

        if (errors == 0) $display("[reg_dma] PASS");
        else             $display("[reg_dma] FAIL (%0d errors)", errors);
        $finish;
    end

    initial begin
        #200us;
        $fatal(1, "[reg_dma] TIMEOUT");
    end
endmodule
