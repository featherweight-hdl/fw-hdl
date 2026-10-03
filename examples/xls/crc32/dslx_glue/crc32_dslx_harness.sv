// HAND-WRITTEN. The bench for the DSLX path's module, crc32_dslx (the XLS
// codegen of crc32.x's main, with input_valid/output_valid). Port names,
// widths, the valid signals and the reset polarity are copied from the
// generated Verilog by hand, and must be kept in step with codegen's options.
//
// One call at a time: present the arguments for one cycle, then wait for the
// output valid. That needs no latency figure, but it does not pipeline calls.
interface crc32_dslx_if (input bit clk, input bit rst);
    bit [7:0]  message;
    bit        input_valid;
    bit [31:0] out;
    bit        output_valid;

    task automatic call(input bit [7:0] m, output bit [31:0] r);
        // Sample reset on a clock edge: at time 0 the port may not hold the
        // harness's value yet (the first version of this glue presented its
        // call during reset, and hung).
        do @(posedge clk); while (rst);
        message     <= m;
        input_valid <= 1'b1;
        @(posedge clk);
        input_valid <= 1'b0;
        do @(posedge clk); while (!output_valid);
        r = out;
    endtask
endinterface

package crc32_dslx_bind_pkg;
    class crc32_dslx_api implements crc32_pkg_api_pkg::crc32_pkg_api;
        virtual crc32_dslx_if vif;
        virtual task main(input bit [7:0] message, output bit [31:0] result);
            vif.call(message, result);
        endtask
    endclass
endpackage

// The test bench instantiates a module of this name (TestRunner's harness).
module crc32_pkg_api_harness;
    bit clk = 1'b0;
    bit rst = 1'b1;
    always #5 clk = ~clk;
    initial begin
        repeat (4) @(posedge clk);
        rst <= 1'b0;
    end

    crc32_dslx_if u_if (.clk(clk), .rst(rst));
    crc32_dslx u_dut (
        .clk(clk), .rst(rst),
        .input_valid(u_if.input_valid), .message(u_if.message),
        .output_valid(u_if.output_valid), .out(u_if.out));

    // A hung call fails the run instead of stalling it.
    initial begin
        repeat (100000) @(posedge clk);
        $fatal(1, "crc32_pkg_api_harness: timeout after 100000 cycles");
    end

    initial begin
        automatic crc32_dslx_bind_pkg::crc32_dslx_api b = new();
        b.vif = u_if;
        crc32_pkg_api_pkg::impl = b;
    end
endmodule
