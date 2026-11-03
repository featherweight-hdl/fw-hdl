// B4d: two puts on one channel in one activation, outside the static subset.
// The dfm tasks must report it as a located marker, not raise.
package twice_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;
    class twice extends fw_component implements fw_runnable;
        fw_port #(fw_get_if #(bit [7:0])) in;
        fw_port #(fw_put_if #(bit [7:0])) out;
        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);
        endfunction
        function void build();
            in = new("in", this);
            out = new("out", this);
        endfunction
        virtual task run();
            forever begin bit [7:0] x; in.t.get(x); out.t.put(x); out.t.put(x); end
        endtask
    endclass
    class twice_top extends fw_component;
        fw_port #(fw_get_if #(bit [7:0])) in;
        fw_port #(fw_put_if #(bit [7:0])) out;
        twice t;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            in = new("in", this);
            out = new("out", this);
            t = new("t", this);
        endfunction
        function void connect();
            t.in.connect(in);
            t.out.connect(out);
        endfunction
    endclass
endpackage
