
package counter_pkg;
    import spl_pkg::*;

    class counter extends spl_component;
        spl_port #(spl_put_if #(bit[31:0]))  out;
        local bit[31:0] count;

        function new(string name, spl_component parent);
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
    import spl_pkg::*;
    import counter_pkg::*;

    spl_put_xtor_if #(bit[31:0]) count_if(.out(count));

    // Maybe this is the bridge: class <-> module
    // Connector?
    class counter_bind extends spl_bind #(counter_pkg::counter);
        function void connect();
            spl_put_xtor_impl #(bit[31:0]) impl = new(count_if);
            root.out.t = impl;
            $display("connect");
        endfunction
    endclass

    spl_root #(
        .Tbind(counter_bind)
    ) u_root (
        .clock(clock),
        .reset(reset)
    );

endmodule

