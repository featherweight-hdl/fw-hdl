// Constructs the elaboration interpreter must run for wrapped IP (extern_map)
// and the component factory: one top per construct, so a gap shows alone.
package probe_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;

    // A recorder an extern's map method fills in.
    class rec;
        string names[$];
        int    vals[string];
        fw_endpoint ends[$];
        function void add(string n, int v);
            names.push_back(n);
            vals[n] = v;
        endfunction
        function void port(fw_endpoint p, string pin);
            ends.push_back(p);
            names.push_back(pin);
        endfunction
    endclass

    interface class mappable;
        pure virtual function void map(rec r);
    endclass

    class leaf extends fw_component implements fw_runnable, mappable;
        fw_port #(fw_get_if #(bit [7:0])) in[2];
        fw_port #(fw_put_if #(bit [7:0])) out;
        int n = 3;
        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);
        endfunction
        function void build();
            foreach (in[i]) in[i] = new($sformatf("in[%0d]", i), this);
            out = new("out", this);
        endfunction
        virtual function void map(rec r);
            r.add("W", n * 2 + (n > 2 ? 1 : 0));
            foreach (in[i]) r.port(in[i], $sformatf("req%0d", i));
            r.port(out, "gnt");
        endfunction
        virtual task run();
            forever begin
                bit [7:0] x;
                in[0].t.get(x);
                out.t.put(x);
            end
        endtask
    endclass

    // (1) interface-class dispatch + port handles + $sformatf + queues + assoc
    class top_iface extends fw_component;
        fw_port #(fw_get_if #(bit [7:0])) a, b;
        fw_port #(fw_put_if #(bit [7:0])) y;
        leaf u;
        static rec r;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            a = new("a", this); b = new("b", this); y = new("y", this);
            u = new("u", this);
        endfunction
        function void connect();
            mappable m;
            u.in[0].connect(a);
            u.in[1].connect(b);
            u.out.connect(y);
            r = new;
            m = u;
            m.map(r);
        endfunction
    endclass

    // (2) static members of a parameterized class, a static method, a
    // registry keyed by string (the factory's shape).
    virtual class proxy_base;
        pure virtual function fw_component create(string name, fw_component parent);
        pure virtual function string type_name();
    endclass

    class factory;
        static proxy_base by_name[string];
        static string     over[string];
        static function void register(proxy_base p);
            by_name[p.type_name()] = p;
        endfunction
        static function fw_component make(string tn, string name, fw_component parent);
            string t = over.exists(tn) ? over[tn] : tn;
            return by_name[t].create(name, parent);
        endfunction
    endclass

    class registry #(type T = fw_component, string TN = "") extends proxy_base;
        static registry #(T, TN) me = get();
        static function registry #(T, TN) get();
            if (me == null) begin
                me = new;
                factory::register(me);
            end
            return me;
        endfunction
        virtual function fw_component create(string name, fw_component parent);
            T o = new(name, parent);
            return o;
        endfunction
        virtual function string type_name();
            return TN;
        endfunction
        static function T make(string name, fw_component parent);
            fw_component c = factory::make(TN, name, parent);
            T o;
            $cast(o, c);
            return o;
        endfunction
    endclass

    class leaf_f extends leaf;
        typedef registry #(leaf_f, "leaf_f") type_id;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
    endclass

    class leaf2 extends leaf_f;
        typedef registry #(leaf2, "leaf2") type_id;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        virtual function void map(rec r);
            r.add("SUB", 1);
        endfunction
    endclass

    class top_factory extends fw_component;
        fw_port #(fw_get_if #(bit [7:0])) a, b;
        fw_port #(fw_put_if #(bit [7:0])) y;
        leaf_f u;
        static rec r;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            void'(leaf2::type_id::get());
            factory::over["leaf_f"] = "leaf2";
            a = new("a", this); b = new("b", this); y = new("y", this);
            u = leaf_f::type_id::make("u", this);
        endfunction
        function void connect();
            u.in[0].connect(a);
            u.in[1].connect(b);
            u.out.connect(y);
            r = new;
            u.map(r);
        endfunction
    endclass
endpackage
