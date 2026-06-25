
// M3: register-block bus integration over the kernel, driven through the
// fw_root lifecycle on a real clock. reg_bus_top wires cpu.regs_p -> dev.regs in
// its own connect(); fw_root seats the clock domain and forks both runnables.
// This module supplies clock/reset and checks the CPU's recorded outcome.
`include "fw_hdl_macros.svh"

module reg_bus_tb;
    import fw_hdl_pkg::*;
    import reg_bus_pkg::*;

    logic clock = 1'b0;
    logic reset = 1'b1;

    always #5ns clock = ~clock;

    `fw_root_begin(reg_bus_top, u_root, clock, reset)
    `fw_root_end

    initial begin
        automatic int errors = 0;

        reset = 1'b1;
        repeat (4) @(posedge clock);
        reset = 1'b0;

        while (u_root.root == null) @(posedge clock);
        while (!u_root.root.cpu.finished) @(posedge clock);

        if (!u_root.root.cpu.ok) begin
            $display("FAIL: cpu outcome not ok (ctrl_rb.go=%0b status.done=%0b payload=0x%03h)",
                     u_root.root.cpu.ctrl_rb.go,
                     u_root.root.cpu.seen.done,
                     u_root.root.cpu.seen.payload);
            errors++;
        end

        if (errors == 0) $display("[reg_bus] PASS");
        else             $display("[reg_bus] FAIL (%0d errors)", errors);
        $finish;
    end

    initial begin
        #100us;
        $fatal(1, "[reg_bus] TIMEOUT");
    end
endmodule
