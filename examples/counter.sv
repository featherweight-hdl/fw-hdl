
package counter_pkg;
    import fw_pkg::*;

    class counter extends fw_component;
        fw_port #(fw_put_if #(bit[31:0]))  out;
        local bit[31:0] count;

        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction

        function void build();
            out = new("out", this);
        endfunction

        virtual task run();
            forever begin
                out.t.put(count);
                count++;
            end
        endtask

    endclass

endpackage

module counter(
    input           clock,
    input           reset,
    output[31:0]    count);
    import fw_pkg::*;
    import counter_pkg::*;

    fw_put_xtor_if #(bit[31:0]) count_if(.out(count));

    // Maybe this is the bridge: class <-> module
    // Connector?
    class counter_bind extends fw_bind #(counter_pkg::counter);
        function void connect();
            fw_put_xtor_impl #(bit[31:0]) impl = new(count_if);
            root.out.t = impl;
            $display("connect");
        endfunction
    endclass

    fw_root #(
        .Tbind(counter_bind)
    ) u_root (
        .clock(clock),
        .reset(reset)
    );

endmodule

