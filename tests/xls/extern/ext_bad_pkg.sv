// Wrappers with one mistake each (test_extern.py), plus a module with tied
// and open pins, and a fileset given by name.
`include "fw_hdl_macros.svh"

package ext_bad_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;
    import ext_pkg::*;

    // One child of type Q between in and out.
    class one_top #(type Q = ext_q) extends fw_component;
        fw_port #(fw_get_if #(bit [7:0])) in;
        fw_port #(fw_put_if #(bit [7:0])) out;
        Q u;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            ext_q_param_t p = new(1);
            in = new("in", this);
            out = new("out", this);
            u = new("u", this, p);
        endfunction
        function void connect();
            u.in.connect(in);
            u.out.connect(out);
        endfunction
    endclass

    // Two children of type Q, through a channel.
    class two_top #(type Q = ext_q) extends fw_component;
        fw_port #(fw_get_if #(bit [7:0])) in;
        fw_port #(fw_put_if #(bit [7:0])) out;
        Q u, v;
        fw_channel #(bit [7:0], 1) c;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            ext_q_param_t p = new(1);
            in = new("in", this);
            out = new("out", this);
            u = new("u", this, p);
            v = new("v", this, p);
            c = new("c", this);
        endfunction
        function void connect();
            u.in.connect(in);
            u.out.connect(c.put_ex);
            v.in.connect(c.get_ex);
            v.out.connect(out);
        endfunction
    endclass

    // The map every bad wrapper starts from, less what it gets wrong.
    virtual class q_base extends ext_q implements fw_extern_impl;
        `fw_extern_utils("fw_rv_fifo", "../../../src/rtl/fw_rv_fifo.sv")
        function new(string name, fw_component parent, param_t params = null);
            super.new(name, parent, params);
        endfunction
        pure virtual function void extern_map(fw_extern_map x);
        function void ports(fw_extern_map x);
            x.rv(in, "in", .data("in_data"), .valid("in_vld"), .ready("in_rdy"));
            x.rv(out, "out", "xls", .data("out_data"));
        endfunction
    endclass

    class no_reset extends q_base;
        function new(string name, fw_component parent, param_t params = null);
            super.new(name, parent, params);
        endfunction
        virtual function void extern_map(fw_extern_map x);
            x.clock("clk");
            ports(x);
        endfunction
    endclass
    typedef one_top #(no_reset) bad_no_reset_t;

    class unknown_pin extends q_base;
        function new(string name, fw_component parent, param_t params = null);
            super.new(name, parent, params);
        endfunction
        virtual function void extern_map(fw_extern_map x);
            x.clock("clk");
            x.reset("rst");
            ports(x);
            x.tie("nope", 0);
        endfunction
    endclass
    typedef one_top #(unknown_pin) bad_unknown_pin_t;

    class twice extends q_base;
        function new(string name, fw_component parent, param_t params = null);
            super.new(name, parent, params);
        endfunction
        virtual function void extern_map(fw_extern_map x);
            x.clock("clk");
            x.reset("rst");
            ports(x);
            x.tie("clk", 0);
        endfunction
    endclass
    typedef one_top #(twice) bad_twice_t;

    class width extends q_base;
        function new(string name, fw_component parent, param_t params = null);
            super.new(name, parent, params);
        endfunction
        virtual function void extern_map(fw_extern_map x);
            x.param("WIDTH", 9);
            x.param("DEPTH", 1);
            x.clock("clk");
            x.reset("rst");
            x.rv(in, "in", .data("in_data"), .valid("in_vld"), .ready("in_rdy"));
            x.rv(out, "out", "xls", .data("out_data"));
        endfunction
    endclass
    typedef one_top #(width) bad_width_t;

    class dir extends q_base;
        function new(string name, fw_component parent, param_t params = null);
            super.new(name, parent, params);
        endfunction
        virtual function void extern_map(fw_extern_map x);
            x.clock("clk");
            x.reset("rst");
            x.rv(in, "in", .data("in_data"), .valid("in_vld"), .ready("out_rdy"));
            x.rv(out, "out", "xls", .data("out_data"));
        endfunction
    endclass
    typedef one_top #(dir) bad_dir_t;

    class unmapped extends q_base;
        function new(string name, fw_component parent, param_t params = null);
            super.new(name, parent, params);
        endfunction
        virtual function void extern_map(fw_extern_map x);
            x.clock("clk");
            x.reset("rst");
            x.rv(in, "in", .data("in_data"), .valid("in_vld"), .ready("in_rdy"));
        endfunction
    endclass
    typedef one_top #(unmapped) bad_unmapped_t;

    class bad_param extends q_base;
        function new(string name, fw_component parent, param_t params = null);
            super.new(name, parent, params);
        endfunction
        virtual function void extern_map(fw_extern_map x);
            x.param("NOPE", 1);
            x.clock("clk");
            x.reset("rst");
            ports(x);
        endfunction
    endclass
    typedef one_top #(bad_param) bad_param_t;

    class kind extends q_base;
        function new(string name, fw_component parent, param_t params = null);
            super.new(name, parent, params);
        endfunction
        virtual function void extern_map(fw_extern_map x);
            x.clock("clk");
            x.reset("rst");
            x.level(in, "in_data");
            x.rv(out, "out", "xls", .data("out_data"));
        endfunction
    endclass
    typedef one_top #(kind) bad_kind_t;

    // The map reads the instance name: two instances, two maps.
    class per_instance extends q_base;
        function new(string name, fw_component parent, param_t params = null);
            super.new(name, parent, params);
        endfunction
        virtual function void extern_map(fw_extern_map x);
            x.param("DEPTH", get_name() == "u" ? 1 : 2);
            x.clock("clk");
            x.reset("rst");
            ports(x);
        endfunction
    endclass
    typedef two_top #(per_instance) bad_per_instance_t;

    class named_fs extends ext_q implements fw_extern_impl;
        `fw_extern_utils("fw_rv_fifo", "fifo")
        function new(string name, fw_component parent, param_t params = null);
            super.new(name, parent, params);
        endfunction
        virtual function void extern_map(fw_extern_map x);
            x.clock("clk");
            x.reset("rst");
            x.rv(in, "in", .data("in_data"), .valid("in_vld"), .ready("in_rdy"));
            x.rv(out, "out", "xls", .data("out_data"));
        endfunction
    endclass
    typedef one_top #(named_fs) named_fs_t;

    // A wrapper finding its module through a fileset, an XLS child and a
    // wrapper beside it: in -> u (named_fs) -> c -> x (add_k #(3)) -> c2 -> w -> out.
    class mix_t extends fw_component;
        fw_port #(fw_get_if #(bit [7:0])) in;
        fw_port #(fw_put_if #(bit [7:0])) out;
        named_fs                   u;
        hier_pkg::add_k #(3)       x;
        ext_q_rtl                  w;
        fw_channel #(bit [7:0], 1) c, c2;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            ext_q_param_t p = new(2);
            in = new("in", this);
            out = new("out", this);
            u = new("u", this, p);
            x = new("x", this);
            w = new("w", this, p);
            c = new("c", this);
            c2 = new("c2", this);
        endfunction
        function void connect();
            u.in.connect(in);
            u.out.connect(c.put_ex);
            x.in.connect(c.get_ex);
            x.out.connect(c2.put_ex);
            w.in.connect(c2.get_ex);
            w.out.connect(out);
        endfunction
    endclass

    class tie_open extends ext_q implements fw_extern_impl;
        `fw_extern_utils("q_dbg", "q_dbg.sv ../../../src/rtl/fw_rv_fifo.sv")
        function new(string name, fw_component parent, param_t params = null);
            super.new(name, parent, params);
        endfunction
        virtual function void extern_map(fw_extern_map x);
            x.clock("clk");
            x.reset("rst");
            x.rv(in, "in", .data("in_data"), .valid("in_vld"), .ready("in_rdy"));
            x.rv(out, "out", "xls", .data("out_data"));
            x.tie("dbg_en", 0);
            x.tie("mode", 2);
            x.open("dbg_q");
        endfunction
    endclass
    typedef one_top #(tie_open) tie_open_t;
endpackage
