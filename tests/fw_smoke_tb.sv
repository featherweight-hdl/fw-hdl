
// Compile/elaboration smoke test for the featherweight (fw) modeling library.
//
// Importing fw_pkg pulls in every class in the library, while instantiating the
// interface modules and specializing the parameterized classes forces Verilator
// to elaborate them. A successful build of this testbench is the pass criterion.
module fw_smoke_tb;
    import fw_pkg::*;

    bit         clock;
    bit         reset;
    bit [31:0]  count;

    // Exercise the standalone interface modules from the core library.
    fw_clock_xtor_if            u_clk_if (.clock(clock), .reset(reset));
    fw_put_xtor_if #(bit[31:0]) u_put_if (.out(count));

    initial begin
        fw_component                        comp;
        fw_port #(fw_put_if #(bit[31:0]))   port;
        fw_put_xtor_impl #(bit[31:0])       impl;

        // Specialize and construct the core class hierarchy.
        comp = new("root", null);
        port = new("port", comp);
        impl = new(u_put_if);

        // Drive a value through the put transactor.
        impl.put(32'hdead_beef);

        $display("[fw-hdl] smoke compile OK");
        $finish;
    end
endmodule
