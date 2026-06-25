
// Hand-wired parameterized-root example. This is deliberately written WITHOUT
// macros to expose the shape a future `fw_root_param_begin/end would generate.
//
// The crux: fw_root calls `root = new(path)` -- it only ever passes a name. So
// the bridge from module parameters to a typed param object is a bind class
// declared HERE in module scope. Being in module scope, it can read the
// module's parameters; being an fw_component_root_param #(cfg_comp), it IS the
// root component. Its new(string) is where the two worlds meet: it builds the
// typed param_t from the module parameters and forwards it to super.new. That
// keeps fw_root completely unchanged.
//
// What a macro would generate is exactly the cfg_comp_bind class below; the
// only per-instance input the user must supply is the params expression
// (cfg_comp::params(P_COUNT, P_WIDTH)).

module root_param_tb;
    import fw_hdl_pkg::*;
    import root_param_pkg::*;

    // Stand in for "module parameters" the design is configured with.
    localparam int P_COUNT = 4;
    localparam int P_WIDTH = 16;

    logic clock = 1'b0;
    logic reset = 1'b1;
    always #5ns clock = ~clock;

    // ---- begin: what `fw_root_param_begin(cfg_comp, u_root, clock, reset,
    //             cfg_comp::params(P_COUNT, P_WIDTH)) would expand to ----
    class cfg_comp_bind extends fw_component_root_param #(cfg_comp);
        function new(string name);
            // The one bespoke line: turn module parameters into a typed config.
            super.new(name, cfg_comp::params(P_COUNT, P_WIDTH));
        endfunction
    endclass

    fw_root #(.Tbind(cfg_comp_bind)) u_root (
        .clock(clock),
        .reset(reset)
    );
    // ---- end ----

    initial begin
        automatic int errors = 0;

        reset = 1'b1;
        repeat (4) @(posedge clock);
        reset = 1'b0;

        // fw_root news the root one clock after reset release, then forks
        // start() (which runs do_build()). Wait for the root, then for build.
        while (u_root.root == null) @(posedge clock);
        repeat (2) @(posedge clock);

        if (u_root.root.total_bits != P_COUNT * P_WIDTH) begin
            $display("FAIL: total_bits expected %0d got %0d",
                     P_COUNT * P_WIDTH, u_root.root.total_bits);
            errors++;
        end else begin
            $display("  ok: total_bits == %0d", u_root.root.total_bits);
        end

        if (errors == 0)
            $display("[root_param] PASS");
        else
            $display("[root_param] FAIL (%0d errors)", errors);
        $finish;
    end

    initial begin
        #100us;
        $fatal(1, "[root_param] TIMEOUT");
    end
endmodule
