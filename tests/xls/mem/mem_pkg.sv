// Designs for tests/xls/test_sp_mem.py: step classes over an fw_sp_mem.
package mem_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;

    // A command per cycle: {wr, a, d}. A write stores d at a; a read returns
    // the word on rsp (valid-only) the next cycle.
    class mm_rw extends fw_atomic_step #(bit);       // s: a read is in flight
        fw_port #(fw_get_nb_if #(bit [20:0]))   cmd;
        fw_port #(fw_valid_put_if #(bit [15:0])) rsp;
        fw_sp_mem #(bit [15:0], 16)            mem;

        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction

        function void build();
            cmd = new("cmd", this);
            rsp = new("rsp", this);
            mem = new();
        endfunction

        virtual function void step();
            bit [20:0] c;
            bit [15:0] d;
            bit        p;
            p = 1'b0;
            if (s) begin
                d = mem.rd();
                rsp.t.put(d);
            end
            if (cmd.t.try_get(c)) begin
                if (c[20])
                    mem.write(c[19:16], c[15:0]);
                else begin
                    mem.read(c[19:16]);
                    p = 1'b1;
                end
            end
            s = p;
        endfunction
    endclass

    // mm_rw with a response that may stall: an error (a step with a memory
    // cannot stall).
    class mm_bad_stall extends fw_atomic_step #(bit);
        fw_port #(fw_get_nb_if #(bit [3:0]))    cmd;
        fw_port #(fw_put_step_if #(bit [15:0])) rsp;
        fw_sp_mem #(bit [15:0], 16)             mem;

        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction

        function void build();
            cmd = new("cmd", this);
            rsp = new("rsp", this);
            mem = new();
        endfunction

        virtual function void step();
            bit [3:0]  a;
            bit [15:0] d;
            if (s) begin
                d = mem.rd();
                rsp.t.put_or_stall(d);
            end
            s = cmd.t.try_get(a);
            if (s)
                mem.read(a);
        endfunction
    endclass

    class mm_top extends fw_component;
        fw_port #(fw_get_nb_if #(bit [20:0]))   cmd;
        fw_port #(fw_valid_put_if #(bit [15:0])) rsp;
        mm_rw u;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            cmd = new("cmd", this);
            rsp = new("rsp", this);
            u = new("u", this);
        endfunction
        function void connect();
            u.cmd.connect(cmd);
            u.rsp.connect(rsp);
        endfunction
    endclass
endpackage
