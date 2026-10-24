`include "fw_hdl_macros.svh"

module fifo_tb;
    import fw_hdl_pkg::*;
    import fifo_pkg::*;

    logic clock = 1'b0;
    logic reset = 1'b1;
    always #5ns clock = ~clock;

    `fw_root_begin(fifo_top, u_root, clock, reset)
    `fw_root_end

    initial begin
        repeat (4) @(posedge clock);
        reset = 1'b0;
        while (u_root.root == null) @(posedge clock);
        while (!u_root.root.done) @(posedge clock);
        if (u_root.root.errors == 0 && u_root.root.got.size() == 64)
            $display("[fifo] PASS (%0d clocks with push and pop)", u_root.root.same_clock);
        else
            $display("[fifo] FAIL (%0d errors, %0d items)", u_root.root.errors, u_root.root.got.size());
        $finish;
    end

    initial begin
        #100us;
        $fatal(1, "[fifo] TIMEOUT");
    end
endmodule
