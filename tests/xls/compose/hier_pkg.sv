// RQ-F1: structural components whose build()/connect() are elaborated, not
// read: a loop of children and channels, a child under an `if` on a class
// parameter, and children configured by a parameter object.
package hier_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;

    // out = in + K
    class add_k #(int K = 1) extends fw_component implements fw_runnable;
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
                out.t.put(x + 8'(K));
            end
        endtask
    endclass

    // loop_n: in -> stage[0] -> ch[0] -> ... -> stage[N-1] -> out
    class loop_top #(int N = 4) extends fw_component;
        fw_port #(fw_get_if #(bit [7:0])) in;
        fw_port #(fw_put_if #(bit [7:0])) out;
        add_k #(1)                stage[N];
        fw_channel #(bit [7:0], 1) ch[N-1];
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            in = new("in", this);
            out = new("out", this);
            foreach (stage[i]) stage[i] = new($sformatf("stage[%0d]", i), this);
            for (int i = 0; i < N - 1; i++) ch[i] = new($sformatf("ch[%0d]", i), this);
        endfunction
        function void connect();
            stage[0].in.connect(in);
            for (int i = 0; i < N - 1; i++) begin
                stage[i].out.connect(ch[i].put_ex);
                stage[i + 1].in.connect(ch[i].get_ex);
            end
            stage[N - 1].out.connect(out);
        endfunction
    endclass
    typedef loop_top #(4) loop4_t;

    // cond_child: a second stage only when TWO is set.
    class cond_top #(bit TWO = 1) extends fw_component;
        fw_port #(fw_get_if #(bit [7:0])) in;
        fw_port #(fw_put_if #(bit [7:0])) out;
        add_k #(1)                a;
        add_k #(2)                b;
        fw_channel #(bit [7:0], 2) c;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            in = new("in", this);
            out = new("out", this);
            a = new("a", this);
            if (TWO) begin
                b = new("b", this);
                c = new("c", this);
            end
        endfunction
        function void connect();
            a.in.connect(in);
            if (TWO) begin
                a.out.connect(c.put_ex);
                b.in.connect(c.get_ex);
                b.out.connect(out);
            end else begin
                a.out.connect(out);
            end
        endfunction
    endclass
    typedef cond_top #(1) cond1_t;
    typedef cond_top #(0) cond0_t;

    // param_obj: out = in * mul + add, from a parameter object.
    class scale_param_t;
        int unsigned mul;
        int unsigned add;
        function new(int unsigned mul = 1, int unsigned add = 0);
            this.mul = mul;
            this.add = add;
        endfunction
    endclass

    class scale extends fw_component_param #(scale_param_t) implements fw_runnable;
        typedef scale_param_t param_t;
        fw_port #(fw_get_if #(bit [7:0])) in;
        fw_port #(fw_put_if #(bit [7:0])) out;
        function new(string name, fw_component parent, param_t params = null);
            super.new(name, parent, params);
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
                out.t.put(8'(x * m_params.mul + m_params.add));
            end
        endtask
    endclass

    // in -> s0 (x*3+1) -> c -> s1 (x*2+5) -> out
    class param_top extends fw_component;
        fw_port #(fw_get_if #(bit [7:0])) in;
        fw_port #(fw_put_if #(bit [7:0])) out;
        scale                      s0, s1;
        fw_channel #(bit [7:0], 1) c;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            scale_param_t p0 = new(3, 1);
            scale_param_t p1 = new(2, 5);
            in = new("in", this);
            out = new("out", this);
            s0 = new("s0", this, p0);
            s1 = new("s1", this, p1);
            c = new("c", this);
        endfunction
        function void connect();
            s0.in.connect(in);
            s0.out.connect(c.put_ex);
            s1.in.connect(c.get_ex);
            s1.out.connect(out);
        endfunction
    endclass
endpackage
