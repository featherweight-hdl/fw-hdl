// B4b: a polling consumer on a channel's get_nb_ex end.
//
//   in ──► inc ──ch (depth 1)──► poll (try_get) ──ch2 (depth 2)──► inc ──► out
//
// poll takes a value only when one is there and forwards it; the stream is the
// input plus two.
package nb_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;

    class nb_inc extends fw_component implements fw_runnable;
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
            forever begin bit [7:0] x; in.t.get(x); out.t.put(x + 8'd1); end
        endtask
    endclass

    class nb_poll extends fw_component implements fw_runnable;
        fw_port #(fw_get_nb_if #(bit [7:0])) in;
        fw_port #(fw_put_if #(bit [7:0]))    out;
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
                bit [7:0] x;
                bit       got;
                got = in.t.try_get(x);
                if (got)
                    out.t.put(x);
            end
        endtask
    endclass

    class nb_top extends fw_component;
        fw_port #(fw_get_if #(bit [7:0])) in;
        fw_port #(fw_put_if #(bit [7:0])) out;
        nb_inc                    a, b;
        nb_poll                   p;
        fw_channel #(bit [7:0], 1) ch;
        fw_channel #(bit [7:0], 2) ch2;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            in = new("in", this);
            out = new("out", this);
            a = new("a", this);
            b = new("b", this);
            p = new("p", this);
            ch = new("ch", this);
            ch2 = new("ch2", this);
        endfunction
        function void connect();
            a.in.connect(in);
            a.out.connect(ch.put_ex);
            p.in.connect(ch.get_nb_ex);
            p.out.connect(ch2.put_ex);
            b.in.connect(ch2.get_ex);
            b.out.connect(out);
        endfunction
    endclass
endpackage
