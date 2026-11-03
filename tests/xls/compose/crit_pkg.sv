// A block whose critical path is the multiply chain on the CRIT line.
package crit_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;

    class crit_blk extends fw_component implements fw_runnable;
        fw_port #(fw_get_if #(bit [15:0])) in;
        fw_port #(fw_put_if #(bit [15:0])) out;
        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);
        endfunction
        function void build();
            in = new("in", this);
            out = new("out", this);
        endfunction
        virtual task run();
            forever begin
                bit [15:0] x, y, z;
                in.t.get(x);
                y = x + 16'd1;
                z = ((y * y) * (y ^ 16'h5a5a)) * (y | 16'h0f0f);   // CRIT
                out.t.put(z);
            end
        endtask
    endclass

    class crit_top extends fw_component;
        fw_port #(fw_get_if #(bit [15:0])) in;
        fw_port #(fw_put_if #(bit [15:0])) out;
        crit_blk c;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            in = new("in", this);
            out = new("out", this);
            c = new("c", this);
        endfunction
        function void connect();
            c.in.connect(in);
            c.out.connect(out);
        endfunction
    endclass
endpackage
