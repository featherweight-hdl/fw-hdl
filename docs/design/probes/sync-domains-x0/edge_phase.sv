// X0.2 probe: are a clock domain's edges at fixed times, whoever ticks it?
// Two processes tick each domain, the second starting one root cycle (or 3
// time units) later. Edge identification by time needs both to see the same
// edge times. Run: direnv exec . sh docs/design/probes/sync-domains-x0/run_edge_phase.sh
`timescale 1ns/1ns
module edge_phase;
    import fw_hdl_pkg::*;
    logic clk = 0, rst = 0;
    always #5 clk = ~clk;
    fw_clock_xtor_if cif(.clock(clk), .reset(rst));
    fw_clock_period_xtor #(.PERIOD(10ns)) pxt();

    initial begin
        fw_component                top = new("top", null);
        fw_clock_xtor_bridge        rb  = new("rb", top, cif);
        fw_clock_period_xtor_bridge pb  = new("pb", top, pxt.u_if);
        fw_clock_domain             d2  = new("d2", top, 2);
        d2.src.connect(rb);
        fork
            begin repeat (3) begin d2.tick(1); $display("div2   A edge @%0t", $realtime); end end
            begin rb.tick(1);
                  repeat (3) begin d2.tick(1); $display("div2   B edge @%0t", $realtime); end end
            begin repeat (3) begin pb.tick(1); $display("period A edge @%0t", $realtime); end end
            begin #3;
                  repeat (3) begin pb.tick(1); $display("period B edge @%0t", $realtime); end end
        join
        $finish;
    end
endmodule
