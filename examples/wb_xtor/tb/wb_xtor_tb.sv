// wb_initiator and wb_target back to back over one wb_bundle, with a memory
// model behind the target. A driver makes N accesses through the
// initiator's export (a write then a read back of each word; every 7th
// access goes to an address the memory answers with err), each after a
// pseudo-random gap of 0-3 edges. A step-only checker logs the bus at each
// edge, and the end checks each call against the log:
//   - cyc and stb are high, and the request is on the bus, from the edge
//     after the call to the edge it returns (C3)
//   - the call returns at the edge where ack or err is high, not before (C7)
//   - after that edge, stb is low unless the next call was made at it
//   - the response is the memory's, and the target saw each access once
// +rand gives the memory 0-3 wait states per access.
// +mut_init (+mut_tgt) swaps in a transactor whose comb() keeps stb (ack)
// up once raised: the checks must fail.
`include "fw_hdl_macros.svh"

package wb_xtor_tb_pkg;
    import fw_hdl_pkg::*;
    import fw_hdl_std_pkg::*;
    import wb_pkg::*;

    // The bus: 32-bit addresses and data.
    localparam int AW = 32;
    localparam int DW = 32;
    typedef wb_if        #(AW, DW) wb_api_t;
    typedef wb_bundle    #(AW, DW) wb_bundle_t;
    typedef wb_initiator #(AW, DW) wb_initiator_t;
    typedef wb_target    #(AW, DW) wb_target_t;
    typedef wb_api_t::req_t req_t;
    typedef wb_api_t::rsp_t rsp_t;

    localparam int N = 40;
    localparam bit [AW-1:0] ERR_ADR = 32'hF000_0000;

    // A call: the edge it was made at (0: before the first), the edge it
    // returned at, and what went each way.
    typedef struct { int c; int r; req_t q; rsp_t s; } call_t;

    // The bus at one edge.
    typedef struct packed {
        bit [AW-1:0]   adr;
        bit [DW-1:0]   dat_w;
        bit [DW/8-1:0] sel;
        bit            we, cyc, stb;
        bit [DW-1:0]   dat_r;
        bit            ack, err;
    } bus_t;

    class chk_c extends fw_component implements fw_step_if;
        `fw_component_utils(chk_c)
        fw_monitor #(wb_bundle_t) p;
        bus_t log[$];
        virtual function void build();
            p = fw_monitor #(wb_bundle_t)::create("p", this);
        endfunction
        virtual function void step();
            bus_t b;
            b.adr   = p.adr.read();
            b.dat_w = p.dat_w.read();
            b.sel   = p.sel.read();
            b.we    = p.we.read();
            b.cyc   = p.cyc.read();
            b.stb   = p.stb.read();
            b.dat_r = p.dat_r.read();
            b.ack   = p.ack.read();
            b.err   = p.err.read();
            log.push_back(b);
        endfunction
        // The edges logged so far: task code at edge k reads k.
        function int n();
            return log.size();
        endfunction
    endclass

    // A gap of 0-3 from a 16-bit LFSR.
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

    // The memory behind the target: 16 words; an access to ERR_ADR is an
    // error. Plain, access() answers at once. With +rand it has 0-3 wait
    // states per access, counted by its own step(): access() hands the
    // request over through a crossing and waits for the response.
    // (Before the crossings this took a run() of its own and mailboxes:
    // access() runs on the caller's thread, where ticking the memory's
    // domain is FW-E-DOM-OBJ.)
    class mem_c extends fw_component implements wb_api_t, fw_step_if;
        `fw_component_utils(mem_c)
        fw_export #(wb_api_t) t;
        fw_to_sync   #(req_t) reqs;
        fw_from_sync #(rsp_t) rsps;
        bit [DW-1:0] mem[16];
        int   n_acc;
        bit   rnd;
        gap_c g = new(16'h0b0e);
        int      ws;        // this access's wait states
        bit      busy;
        int      left;
        rsp_t cur;
        virtual function void build();
            t    = fw_export #(wb_api_t)::create("t", this);
            reqs = fw_to_sync   #(req_t)::create("reqs", this);
            rsps = fw_from_sync #(rsp_t)::create("rsps", this);
            rnd  = $test$plusargs("rand");
        endfunction
        function rsp_t apply(req_t req);
            int i = req.adr[5:2];
            rsp_t rsp;
            rsp.err = (req.adr == ERR_ADR);
            if (!rsp.err && req.we)
                for (int b = 0; b < DW/8; b++)
                    if (req.sel[b]) mem[i][8*b +: 8] = req.dat[8*b +: 8];
            rsp.dat = rsp.err ? '0 : mem[i];
            return rsp;
        endfunction
        // n wait states: the call returns n edges later. Entering the sync
        // code costs the first (the request is taken at the next edge).
        virtual task access(output rsp_t rsp, input req_t req);
            n_acc++;
            ws = rnd ? g.next() : 0;
            if (ws == 0) begin
                rsp = apply(req);
                return;
            end
            reqs.put(req);
            rsps.get(rsp);
        endtask
        // Takes a request; gives its response after the rest of its wait
        // states (at the same edge for one).
        virtual function void step();
            req_t q;
            if (busy) begin
                if (left > 0) left--;
            end
            else if (reqs.take(q)) begin
                cur  = apply(q);
                left = ws - 1;
                busy = 1;
            end
            if (busy && left == 0 && rsps.give(cur)) busy = 0;
        endfunction
    endclass

    // Makes the N accesses through port p.
    class drv_c extends fw_component implements fw_run_if;
        `fw_component_utils(drv_c)
        fw_port #(wb_api_t) p;
        chk_c  k;
        call_t calls[$];
        virtual function void build();
            p = fw_port #(wb_api_t)::create("p", this);
        endfunction
        virtual task run();
            wb_api_t i = p.get_if();
            gap_c g = new(16'hace1);
            for (int a = 0; a < N; a++) begin
                call_t c;
                repeat (g.next()) fw_clock_domain::tick(this);
                c.q.adr = (a % 7 == 6) ? ERR_ADR : AW'((a / 2) % 16 * 4);
                c.q.we  = !(a % 2);
                c.q.dat = c.q.we ? DW'(32'h1000_0000 * (a % 16) + a) : '0;
                c.q.sel = '1;
                c.c = k.n();
                i.access(c.s, c.q);
                c.r = k.n();
                calls.push_back(c);
            end
        endtask
    endclass

    // The mutants: comb() keeps stb (ack) up once raised, so it stays up
    // after a termination.
    class mut_init_c extends wb_initiator_t;
        `fw_component_utils(mut_init_c)
        bit up;
        virtual function void comb();
            super.comb();
            up |= reqs.valid();
            pins.stb.write(up);
        endfunction
    endclass

    class mut_tgt_c extends wb_target_t;
        `fw_component_utils(mut_tgt_c)
        bit up;
        virtual function void comb();
            rsp_t s = rsps.peek();
            super.comb();
            up |= rsps.valid() && !s.err;
            pins.ack.write(up);
        endfunction
    endclass

    class top_c extends fw_component;
        `fw_component_utils(top_c)
        fw_clock_domain clk;
        drv_c           d;
        wb_initiator_t  xi;
        wb_target_t     xt;
        mem_c           m;
        chk_c           k;
        virtual function void build();
            clk = fw_clock_domain::create("clk", this, fw_clock_kind::root(10ns));
            fw_clock_domain::set(this, clk);
            d = drv_c::create("d", this);
            if ($test$plusargs("mut_init")) xi = mut_init_c::create("xi", this);
            else                            xi = wb_initiator_t::create("xi", this);
            if ($test$plusargs("mut_tgt"))  xt = mut_tgt_c::create("xt", this);
            else                            xt = wb_target_t::create("xt", this);
            m = mem_c::create("m", this);
            k = chk_c::create("k", this);
            d.k = k;
        endfunction
        virtual function void connect();
            d.p.connect(xi.t);
            xi.pins.connect(xt.pins);
            xt.p.connect(m.t);
            k.p.connect(xi.pins);
        endfunction
    endclass

    // Checks the calls against the log and a shadow of the memory. Returns
    // the first failure, or "".
    function automatic string check(top_c t);
        return check_parts(t.d, t.k, t.m);
    endfunction

    // check(), from the driver, checker and memory (a bench with another
    // top: wb_xtor_mixed.sv).
    function automatic string check_parts(drv_c d, chk_c k, mem_c m);
        call_t calls[$] = d.calls;
        bus_t  l[$] = k.log;
        bit [DW-1:0] shadow[16];
        foreach (calls[a]) begin
            call_t c = calls[a];
            int w = c.q.adr[5:2];
            bit eerr = (c.q.adr == ERR_ADR);
            if (c.r <= c.c || c.r > l.size())
                return $sformatf("access %0d: called at %0d, returned at %0d", a, c.c, c.r);
            for (int e = c.c + 1; e <= c.r; e++) begin
                bus_t b = l[e - 1];
                bit term = b.ack || b.err;
                if (!(b.cyc && b.stb))
                    return $sformatf("access %0d: cyc/stb low at edge %0d (C3)", a, e);
                if (b.adr != c.q.adr || b.we != c.q.we || b.sel != c.q.sel
                        || (c.q.we && b.dat_w != c.q.dat))
                    return $sformatf("access %0d: request not on the bus at edge %0d", a, e);
                if (term != (e == c.r))
                    return $sformatf("access %0d: termination %0d at edge %0d, returned at %0d (C7)",
                                     a, term, e, c.r);
            end
            // The edge after the termination: stb low, unless the next
            // access was called at it.
            if ((a + 1 == calls.size() || calls[a + 1].c > c.r) && c.r < l.size()
                    && l[c.r].stb)
                return $sformatf("access %0d: stb still high at edge %0d (drop)", a, c.r + 1);
            if (c.s.err != eerr)
                return $sformatf("access %0d: err %0d", a, c.s.err);
            if (!eerr && c.q.we) shadow[w] = c.q.dat;
            if (!eerr && c.s.dat != shadow[w])
                return $sformatf("access %0d: read %h, expected %h", a, c.s.dat, shadow[w]);
        end
        if (calls.size() != N) return $sformatf("%0d accesses returned", calls.size());
        if (m.n_acc != N) return $sformatf("the target saw %0d accesses", m.n_acc);
        return "";
    endfunction
endpackage
