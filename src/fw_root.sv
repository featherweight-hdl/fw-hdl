
module fw_root #(
    parameter type Tbind=int
    // Assumptions about clock stability?
) (
    input   clock,
    input   reset
);
    reg in_reset = 0;
    Tbind root = null;

    // Need to pass a virtual-interface handle for working with time

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
                $display("TODO: Create root");
                in_reset <= 1'b0;
                root = new(path);
                fork
                    root.run();
                join_none
            end
            // What's the next timestamp?
            // Need a way to get a callback on next delta
        end
    end


endmodule
