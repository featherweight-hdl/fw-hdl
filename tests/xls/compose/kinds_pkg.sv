// RQ-F3: the three channel kinds.
//
//   vtop: in -> a (vinc: out = in + 1, valid-only out) -> v (fw_valid_channel, 2)
//            -> b (vmix: out = in ^ 8'h5a, valid-only out) -> out (valid-only)
//         b returns one credit per value it takes, over cr (fw_channel, 2); a
//         starts with 2 credits (v's depth) and waits for a credit only when it
//         has none, so v never overflows: a credited link from stand-in blocks.
//   ltop: in -> s (lsrc: forwards in; sets lb = bias + 1) -> ch -> k (lsum:
//            out = in + lb + gain) -> out; bias and gain are top-level levels,
//            lb is a level channel between s and k.
package kinds_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;

    class vinc extends fw_component implements fw_runnable;
        fw_port #(fw_get_if #(bit [7:0]))       in;
        fw_port #(fw_valid_put_if #(bit [7:0])) out;
        fw_port #(fw_get_if #(bit))             cr;
        bit [1:0] credits = 2'd2;
        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);
        endfunction
        function void build();
            in = new("in", this);
            out = new("out", this);
            cr = new("cr", this);
        endfunction
        virtual task run();
            forever begin
                bit [7:0] x;
                bit       c;
                in.t.get(x);
                if (credits == 2'd0) begin
                    cr.t.get(c);
                    credits = credits + 2'd1;
                end
                out.t.put(x + 8'd1);
                credits = credits - 2'd1;
            end
        endtask
    endclass

    class vmix extends fw_component implements fw_runnable;
        fw_port #(fw_get_if #(bit [7:0]))       in;
        fw_port #(fw_valid_put_if #(bit [7:0])) out;
        fw_port #(fw_put_if #(bit))             cr;
        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);
        endfunction
        function void build();
            in = new("in", this);
            out = new("out", this);
            cr = new("cr", this);
        endfunction
        virtual task run();
            forever begin
                bit [7:0] x;
                in.t.get(x);
                cr.t.put(1'b1);
                out.t.put(x ^ 8'h5a);
            end
        endtask
    endclass

    class vtop extends fw_component;
        fw_port #(fw_get_if #(bit [7:0]))       in;
        fw_port #(fw_valid_put_if #(bit [7:0])) out;
        vinc                             a;
        vmix                             b;
        fw_valid_channel #(bit [7:0], 2) v;
        fw_channel #(bit, 2)             cr;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            in = new("in", this);
            out = new("out", this);
            a = new("a", this);
            b = new("b", this);
            v = new("v", this);
            cr = new("cr", this);
        endfunction
        function void connect();
            a.in.connect(in);
            a.out.connect(v.put_ex);
            b.in.connect(v.get_ex);
            b.out.connect(out);
            b.cr.connect(cr.put_ex);
            a.cr.connect(cr.get_ex);
        endfunction
    endclass

    class lsrc extends fw_component implements fw_runnable;
        fw_port #(fw_get_if #(bit [7:0]))       in;
        fw_port #(fw_put_if #(bit [7:0]))       out;
        fw_port #(fw_level_if #(bit [7:0]))     bias;
        fw_port #(fw_level_set_if #(bit [7:0])) lb;
        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);
        endfunction
        function void build();
            in = new("in", this);
            out = new("out", this);
            bias = new("bias", this);
            lb = new("lb", this);
        endfunction
        virtual task run();
            forever begin
                bit [7:0] x, b;
                in.t.get(x);
                b = bias.t.get();
                lb.t.set(b + 8'd1);
                out.t.put(x);
            end
        endtask
    endclass

    class lsum extends fw_component implements fw_runnable;
        fw_port #(fw_get_if #(bit [7:0]))   in;
        fw_port #(fw_put_if #(bit [7:0]))   out;
        fw_port #(fw_level_if #(bit [7:0])) lb;
        fw_port #(fw_level_if #(bit [7:0])) gain;
        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);
        endfunction
        function void build();
            in = new("in", this);
            out = new("out", this);
            lb = new("lb", this);
            gain = new("gain", this);
        endfunction
        virtual task run();
            forever begin
                bit [7:0] x, l, g;
                in.t.get(x);
                l = lb.t.get();
                g = gain.t.get();
                out.t.put(x + l + g);
            end
        endtask
    endclass

    class ltop extends fw_component;
        fw_port #(fw_get_if #(bit [7:0]))   in;
        fw_port #(fw_put_if #(bit [7:0]))   out;
        fw_port #(fw_level_if #(bit [7:0])) bias;
        fw_port #(fw_level_if #(bit [7:0])) gain;
        lsrc                        s;
        lsum                        k;
        fw_channel #(bit [7:0], 1)  ch;
        fw_level_channel #(bit [7:0]) lb;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            in = new("in", this);
            out = new("out", this);
            bias = new("bias", this);
            gain = new("gain", this);
            s = new("s", this);
            k = new("k", this);
            ch = new("ch", this);
            lb = new("lb", this);
        endfunction
        function void connect();
            s.in.connect(in);
            s.bias.connect(bias);
            s.lb.connect(lb.put_ex);
            s.out.connect(ch.put_ex);
            k.in.connect(ch.get_ex);
            k.lb.connect(lb.get_ex);
            k.gain.connect(gain);
            k.out.connect(out);
        endfunction
    endclass
endpackage
