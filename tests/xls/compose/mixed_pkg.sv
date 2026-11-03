// RQ-F2: a top whose children are of different kinds, nested two deep.
//
//   deep_top:  in -> m (mixed_top) -> out
//   mixed_top: in -> inner (inner_top, structural) -> c0 -> e (ext_neg, extern RTL)
//                 -> c1 -> x (add_k #(5), XLS) -> out
//   inner_top: in -> a (add_k #(1)) -> ch -> b (add_k #(2)) -> out
//
// ext_neg's class is its model; its RTL is the hand-written ext_neg_rtl.sv,
// described by ext_neg_rtl.sig.json (knob design.extern).
package mixed_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;
    import hier_pkg::*;

    class ext_neg extends fw_component implements fw_runnable;
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
            forever begin
                bit [7:0] x;
                in.t.get(x);
                out.t.put(~x);
            end
        endtask
    endclass

    class inner_top extends fw_component;
        fw_port #(fw_get_if #(bit [7:0])) in;
        fw_port #(fw_put_if #(bit [7:0])) out;
        add_k #(1)                 a;
        add_k #(2)                 b;
        fw_channel #(bit [7:0], 1) ch;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            in = new("in", this);
            out = new("out", this);
            a = new("a", this);
            b = new("b", this);
            ch = new("ch", this);
        endfunction
        function void connect();
            a.in.connect(in);
            a.out.connect(ch.put_ex);
            b.in.connect(ch.get_ex);
            b.out.connect(out);
        endfunction
    endclass

    class mixed_top extends fw_component;
        fw_port #(fw_get_if #(bit [7:0])) in;
        fw_port #(fw_put_if #(bit [7:0])) out;
        inner_top                  inner;
        ext_neg                    e;
        add_k #(5)                 x;
        fw_channel #(bit [7:0], 2) c0;
        fw_channel #(bit [7:0], 0) c1;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            in = new("in", this);
            out = new("out", this);
            inner = new("inner", this);
            e = new("e", this);
            x = new("x", this);
            c0 = new("c0", this);
            c1 = new("c1", this);
        endfunction
        function void connect();
            inner.in.connect(in);
            inner.out.connect(c0.put_ex);
            e.in.connect(c0.get_ex);
            e.out.connect(c1.put_ex);
            x.in.connect(c1.get_ex);
            x.out.connect(out);
        endfunction
    endclass

    class deep_top extends fw_component;
        fw_port #(fw_get_if #(bit [7:0])) in;
        fw_port #(fw_put_if #(bit [7:0])) out;
        mixed_top                  m;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            in = new("in", this);
            out = new("out", this);
            m = new("m", this);
        endfunction
        function void connect();
            m.in.connect(in);
            m.out.connect(out);
        endfunction
    endclass
endpackage
