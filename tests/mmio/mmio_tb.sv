
// Class-level lifecycle harness (mirrors reg_bus_tb): seats the clock domain via
// fw_root and lets the package elaborate. The behavioral proof of the *generated
// RTL* lives in tests/python/system/test_mmio_sim.py (a Verilog TB over the
// emitted fsm/regblock/top); this module only exercises the class model.
`include "fw_hdl_macros.svh"

module mmio_tb;
    import fw_hdl_pkg::*;
    import mmio_pkg::*;

    logic clock = 1'b0;
    logic reset = 1'b1;

    always #5ns clock = ~clock;

    `fw_root_begin(mmio_top, u_root, clock, reset)
    `fw_root_end

    initial begin
        reset = 1'b1;
        repeat (4) @(posedge clock);
        reset = 1'b0;
        repeat (10) @(posedge clock);
        $display("[mmio] PASS");
        $finish;
    end

    initial begin
        #100us;
        $fatal(1, "[mmio] TIMEOUT");
    end
endmodule
