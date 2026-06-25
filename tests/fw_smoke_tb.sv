
// Compile/elaboration smoke test for the featherweight (fw) modeling library.
//
// Importing fw_hdl_pkg (kernel) and fw_std_pkg (standard protocol library) pulls
// in every class in the library, while instantiating the interface modules and
// specializing the parameterized classes forces Verilator to elaborate them. A
// successful build of this testbench is the pass criterion.
module fw_smoke_tb;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;

    bit         clock = 1'b0;
    bit         reset = 1'b0;
    bit [31:0]  count;

    always #5 clock = ~clock;   // put() advances one clock; keep the sim moving

    // Exercise the standalone interface modules from the core library.
    fw_clock_xtor_if            u_clk_if (.clock(clock), .reset(reset));
    fw_put_xtor_if #(bit[31:0]) u_put_if (.clock(clock), .reset(reset), .out(count));

    initial begin
        fw_component                        comp;
        fw_port #(fw_put_if #(bit[31:0]))   port;
        fw_put_xtor_bridge #(bit[31:0])     bridge;

        // Specialize and construct the core class hierarchy.
        comp   = new("root", null);
        port   = new("port", comp);
        bridge = new("put", comp, u_put_if);

        // Bind the producer's port to the put bridge, then resolve through the
        // graph and drive a value out the put transactor.
        port.connect(bridge);
        port.get_if().put(32'hdead_beef);

        $display("[fw-hdl] smoke compile OK");
        $finish;
    end
endmodule
