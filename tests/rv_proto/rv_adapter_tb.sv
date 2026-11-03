// The put/get adapters (src/std/rv): a producer written against fw_put_if and a
// consumer written against fw_get_if, joined by ready/valid pins through
// fw_put_to_rv_bridge -> initiator transactor -> target transactor ->
// fw_get_from_rv_bridge. The consumer stalls in bursts, so ready drops; every
// beat must still arrive once, in order.
`include "fw_hdl_macros.svh"

package rv_adapter_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;

    typedef logic [15:0] data_t;
    localparam int unsigned N = 32;

    function automatic data_t beat(int unsigned i);
        return data_t'(16'h1000 + 3 * i);
    endfunction

    class producer extends fw_component implements fw_runnable;
        fw_port #(fw_put_if #(data_t)) out;

        function new(string name, fw_component parent);
            super.new(name, parent);
            parent.add_runnable(this);
        endfunction

        function void build();
            out = new("out", this);
        endfunction

        virtual task run();
            for (int unsigned i = 0; i < N; i++)
                out.t.put(beat(i));
        endtask
    endclass

    class consumer extends fw_component implements fw_runnable;
        fw_port #(fw_get_if #(data_t)) in;
        data_t got[$];

        function new(string name, fw_component parent);
            super.new(name, parent);
            parent.add_runnable(this);
        endfunction

        function void build();
            in = new("in", this);
        endfunction

        virtual task run();
            for (int unsigned i = 0; i < N; i++) begin
                automatic data_t v;
                if (i % 8 == 3) #200ns;     // long enough to fill every FIFO
                in.t.get(v);
                got.push_back(v);
            end
        endtask
    endclass

    class adapter_top extends fw_component;
        producer src;
        consumer dst;

        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction

        function void build();
            src = new("src", this);
            dst = new("dst", this);
        endfunction
    endclass
endpackage

module rv_adapter_tb;
    import fw_hdl_pkg::*;
    import fw_rv_pkg::*;
    import rv_adapter_pkg::*;

    logic clock = 1'b0;
    logic reset = 1'b1;
    bit    bus_valid, bus_ready;
    data_t bus_data;
    int unsigned stalls = 0, beats = 0;

    always #5ns clock = ~clock;
    always @(posedge clock) if (!reset) begin
        if (bus_valid && !bus_ready) stalls++;
        if (bus_valid && bus_ready) beats++;
    end

    fw_rv_initiator_xtor #(.T(data_t)) ix (
        .clock(clock), .reset(reset), .data(bus_data), .valid(bus_valid), .ready(bus_ready));
    fw_rv_target_xtor #(.T(data_t)) tx (
        .clock(clock), .reset(reset), .valid(bus_valid), .ready(bus_ready), .data(bus_data));

    `fw_root_begin(adapter_top, u_root, clock, reset)
        `fw_root_bind_port(src.out, ix.u_if, fw_put_to_rv_bridge #(data_t))
        `fw_root_bind_port(dst.in,  tx.u_if, fw_get_from_rv_bridge #(data_t))
    `fw_root_end

    initial begin
        automatic int errors = 0;
        repeat (4) @(posedge clock);
        reset = 1'b0;
        while (u_root.root == null) @(posedge clock);
        while (u_root.root.dst.got.size() < N) @(posedge clock);
        repeat (20) @(posedge clock);           // a late duplicate would show here
        for (int unsigned i = 0; i < N; i++)
            if (u_root.root.dst.got[i] !== beat(i)) begin
                $display("FAIL: beat %0d expected 0x%0h got 0x%0h", i, beat(i), u_root.root.dst.got[i]);
                errors++;
            end
        if (beats != N) begin
            $display("FAIL: %0d transfers on the pins, expected %0d", beats, N);
            errors++;
        end
        if (stalls == 0) begin
            $display("FAIL: the pins never saw valid && !ready");
            errors++;
        end
        $display("[rv_adapter] stalls=%0d beats=%0d", stalls, beats);
        if (errors == 0) $display("[rv_adapter] PASS");
        else $display("[rv_adapter] FAIL");
        $display("X done");
        $finish;
    end

    initial begin
        #200us;
        $fatal(1, "[rv_adapter] TIMEOUT");
    end
endmodule
