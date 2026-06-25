
module fw_root #(
    parameter type Tbind=int
    // Assumptions about clock stability?
) (
    input   clock,
    input   reset
);
    import fw_hdl_pkg::*;

    reg in_reset = 0;
    Tbind root = null;

    // The root clock-domain transactor: bridges the clock-domain API to this
    // module's clock/reset. Its bridge becomes the root component's clock
    // domain, which every other component inherits by default.
    fw_clock_xtor_if u_clk(.clock(clock), .reset(reset));

    always @(posedge clock or posedge reset) begin
        if (reset) begin
            in_reset <= 1'b1;
            if (root != null) begin
                root.kill();
                $display("TODO: kill root");
                root = null;
            end
        end else begin
            if (in_reset) begin
                automatic string path = $sformatf("%m");
                automatic fw_clock_xtor_bridge clk_dom;
                $display("TODO: Create root");
                in_reset <= 1'b0;
                root = new(path);
                // Seat the root component's clock domain before start() so the
                // whole tree resolves through it.
                clk_dom = new("clock", root, u_clk);
                root.clock.connect(clk_dom);
                fork
                    root.start();
                join_none
            end
            // What's the next timestamp?
            // Need a way to get a callback on next delta
        end
    end


endmodule
