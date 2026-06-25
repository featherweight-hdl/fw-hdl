
// Class-level lifecycle harness (seats fw_root so the package elaborates during
// sv2ir). The behavioral proof of the generated RTL is in
// tests/python/system/test_mmio_multi_sim.py.
`include "fw_hdl_macros.svh"

module mmio_multi_tb;
    import fw_hdl_pkg::*;
    import mmio_multi_pkg::*;

    logic clock = 1'b0;
    logic reset = 1'b1;

    always #5ns clock = ~clock;

    `fw_root_begin(multi_top, u_root, clock, reset)
    `fw_root_end

    initial begin
        reset = 1'b1;
        repeat (4) @(posedge clock);
        reset = 1'b0;
        repeat (10) @(posedge clock);
        $display("[mmio_multi] PASS");
        $finish;
    end

    initial begin
        #100us;
        $fatal(1, "[mmio_multi] TIMEOUT");
    end
endmodule
