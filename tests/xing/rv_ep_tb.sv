// The ready/valid put and get endpoints (sync-task-domains.md X4):
// fw_rv_put_ep and fw_rv_get_ep back to back over one link. Built and run
// by tests/python/system/test_xing_sim.py; prints PASS or FAIL lines. As
// fw-hdl-rt-sv's tests/sv/rv_ep.sv: a source puts 1..N and a sink gets N,
// each after a pseudo-random gap of 0-3 edges; a step-only checker logs
// valid, ready and data at each edge, and the end checks each call:
//   C3  a call's drive is read from the edge after the call
//   C7  the call returns at its handshake edge, and not before
//   C5  after the handshake, the default drops valid (ready) unless a call
//       at that edge raises it again; no beat is repeated or lost
// +mut_put (+mut_get) swaps in an endpoint whose step() keeps the signal up
// (no default): the checks must fail.
`timescale 1ns/1ps
package rv_ep_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;
    typedef bit [7:0] xbyte_t;
    localparam int N = 40;

    // A call: the edge it was made at (0: before the first) and the edge it
    // returned at.
    typedef struct { int c; int r; xbyte_t d; } call_t;

    // Logs the link at each edge (what the step()s read).
    class chk_c extends fw_component implements fw_steppable;
        fw_rv_sp_in #(xbyte_t) ln;
        bit     v[$], rd[$];
        xbyte_t d[$];
        function new(string name, fw_component parent);
            super.new(name, parent);
            add_steppable(this);
        endfunction
        virtual function void step();
            v.push_back(ln.get_valid());
            rd.push_back(ln.get_ready());
            d.push_back(ln.get_data());
        endfunction
        // The edges logged so far: task code at edge k reads k.
        function int n();
            return v.size();
        endfunction
    endclass

    // A gap of 0-3 edges from a 16-bit LFSR.
    class gap_c;
        bit [15:0] s;
        function new(bit [15:0] seed);
            s = seed;
        endfunction
        function int next();
            s = {s[14:0], s[15] ^ s[13] ^ s[12] ^ s[10]};
            return s[1:0];
        endfunction
    endclass

    // The mutants: no default, so the signal stays up after a handshake.
    class mut_put_c extends fw_rv_put_ep #(xbyte_t);
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        virtual function void step();
        endfunction
    endclass

    class mut_get_c extends fw_rv_get_ep #(xbyte_t);
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        virtual function void step();
        endfunction
    endclass

    // Checks one side's calls against the log. Returns the first failure,
    // or "".
    function automatic string check(string side, call_t calls[$], chk_c k, bit is_put);
        foreach (calls[i]) begin
            call_t c = calls[i];
            if (c.d != xbyte_t'(i + 1))
                return $sformatf("%s %0d: data %0d", side, i + 1, c.d);
            if (c.r <= c.c || c.r > k.n())
                return $sformatf("%s %0d: called at %0d, returned at %0d", side, i + 1, c.c, c.r);
            for (int e = c.c + 1; e <= c.r; e++) begin
                bit lv = is_put ? k.v[e - 1] : k.rd[e - 1];
                bit hs = k.v[e - 1] && k.rd[e - 1];
                if (!lv) return $sformatf("%s %0d: not driven at edge %0d (C3)", side, i + 1, e);
                if (is_put && k.d[e - 1] != c.d)
                    return $sformatf("%s %0d: data %0d at edge %0d", side, i + 1, k.d[e - 1], e);
                if (hs != (e == c.r))
                    return $sformatf("%s %0d: handshake %0d at edge %0d, returned at %0d (C7)",
                                     side, i + 1, hs, e, c.r);
            end
            // The edge after the handshake: down, unless the next call was
            // made at the handshake edge.
            if ((i + 1 == calls.size() || calls[i + 1].c > c.r) && c.r < k.n()) begin
                bit lv = is_put ? k.v[c.r] : k.rd[c.r];
                if (lv) return $sformatf("%s %0d: still driven at edge %0d (C5 default)",
                                         side, i + 1, c.r + 1);
            end
        end
        if (calls.size() != N) return $sformatf("%s: %0d calls returned", side, calls.size());
        return "";
    endfunction
endpackage

module rv_ep_tb;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;
    import rv_ep_pkg::*;

    logic clk = 0, rst = 0;
    always #5 clk = ~clk;
    fw_clock_xtor_if cif(.clock(clk), .reset(rst));

    fw_component            top;
    fw_clock_xtor_bridge    rb;
    fw_rv_put_ep #(xbyte_t) xp;
    fw_rv_get_ep #(xbyte_t) xg;
    chk_c                   k;
    fw_sync_kernel          kern;
    call_t                  pc[$], gc[$];

    // Checks the calls that returned against the log, and finishes.
    function automatic void report();
        string e;
        int hs, b2b;
        foreach (k.v[i]) hs += k.v[i] && k.rd[i];
        foreach (pc[i]) if (i > 0 && pc[i].c == pc[i - 1].r) b2b++;
        e = check("put", pc, k, 1);
        if (e == "") e = check("get", gc, k, 0);
        if (e == "" && hs != N) e = $sformatf("%0d handshakes", hs);
        if (e == "" && fw_sig_holder::rule_errs != 0) e = fw_sig_holder::rule_err;
        if (e == "") $display("PASS: rv_ep: %0d beats, %0d back to back", N, b2b);
        else         $display("FAIL: rv_ep: %s", e);
        $finish;
    endfunction

    // A deadlock (a beat that never completes) is checked rather than hangs.
    initial begin
        #5us;
        report();
    end

    initial begin
        mut_put_c mp;
        mut_get_c mg;
        top = new("top", null);
        rb  = new("rb", top, cif);
        if ($test$plusargs("mut_put")) begin mp = new("xp", top); xp = mp; end
        else xp = new("xp", top);
        if ($test$plusargs("mut_get")) begin mg = new("xg", top); xg = mg; end
        else xg = new("xg", top);
        k   = new("k", top);
        xp.clock.connect(rb);
        xg.clock.connect(rb);
        k.clock.connect(rb);
        xp.out.connect(xg.in);
        k.ln = xg.in;
        kern = new("top");
        kern.elaborate(top);
        fw_sig_holder::fatal_on_rule = 0;
        kern.launch();

        fork
            begin   // the source
                gap_c g = new(16'hace1);
                for (int b = 1; b <= N; b++) begin
                    call_t c;
                    repeat (g.next()) rb.tick(1);
                    c.c = k.n();
                    c.d = xbyte_t'(b);
                    xp.put(c.d);
                    c.r = k.n();
                    pc.push_back(c);
                end
            end
            begin   // the sink
                gap_c g = new(16'h5eed);
                for (int b = 1; b <= N; b++) begin
                    call_t c;
                    repeat (g.next()) rb.tick(1);
                    c.c = k.n();
                    xg.get(c.d);
                    c.r = k.n();
                    gc.push_back(c);
                end
            end
        join
        rb.tick(2);
        report();
    end
endmodule
