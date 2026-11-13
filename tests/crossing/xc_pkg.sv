// Domain crossing test -- class layer. Each xc_top_* class is one case; the
// testbench builds it, seats its root domains, runs build and connect, and
// calls fw_crossing_check::run() on it (no $fatal), checking what is found.
package xc_pkg;
    import fw_hdl_pkg::*;

    // A one-method data API and its imp.
    interface class xc_if;
        pure virtual function void ping(int v);
    endclass

    class xc_imp implements xc_if;
        int n;
        virtual function void ping(int v); n += v; endfunction
    endclass

    // Domains the cases share, made by the testbench: a second, unrelated
    // root clock (and resets on each clock).
    class xc_env;
        static fw_clock_domain_if clk_b;
        static fw_reset_domain_if rst_a;
        static fw_reset_domain_if rst_b;
    endclass

    class xc_src extends fw_component;
        fw_port #(xc_if) out;
        function new(string name, fw_component parent);
            super.new(name, parent);
            out = new("out", this);
        endfunction
    endclass

    class xc_snk extends fw_component;
        xc_imp           imp;
        fw_export #(xc_if) in_ex;
        function new(string name, fw_component parent);
            super.new(name, parent);
            imp   = new();
            in_ex = new("in_ex", this, imp);
        endfunction
    endclass

    // An export that forwards a clock domain held elsewhere (the testbench's
    // second root), so a parent can hand it to a child.
    class xc_clk_fwd extends fw_export #(fw_clock_domain_if);
        function new(string name, fw_component parent);
            super.new(name, parent, xc_env::clk_b);
            set_ambient();
        endfunction
    endclass

    class xc_rst_fwd extends fw_export #(fw_reset_domain_if);
        function new(string name, fw_component parent, fw_reset_domain_if r);
            super.new(name, parent, r);
            set_ambient();
        endfunction
    endclass

    // --- 1. one domain: nothing -------------------------------------------------
    class xc_top_one extends fw_component;
        xc_src a; xc_snk b;
        function new(string name, fw_component parent); super.new(name, parent); endfunction
        function void build(); a = new("a", this); b = new("b", this); endfunction
        function void connect(); a.out.connect(b.in_ex); endfunction
    endclass

    // --- 2. a /2 child bound to a root-clock sink: clock related, info -------------
    class xc_top_div extends fw_component;
        xc_src a; xc_snk b; fw_clock_domain div2;
        function new(string name, fw_component parent); super.new(name, parent); endfunction
        function void build(); a = new("a", this); b = new("b", this); div2 = new("div2", this, 2); endfunction
        function void connect();
            div2.src.connect(this.clock);
            a.clock.connect(div2);
            a.out.connect(b.in_ex);
        endfunction
    endclass

    // --- 3. a second root clock across a binding: clock unrelated, error --------
    class xc_top_clk2 extends fw_component;
        xc_src a; xc_snk b; xc_clk_fwd ck2;
        function new(string name, fw_component parent); super.new(name, parent); endfunction
        function void build(); a = new("a", this); b = new("b", this); ck2 = new("clk_b2", this); endfunction
        function void connect();
            a.clock.connect(ck2);
            a.out.connect(b.in_ex);
        endfunction
    endclass

    // --- 4. a register-bit reset child bound to its parent: reset related, warn;
    //        waived: info with the reason ----------------------------------------
    class xc_top_soft extends fw_component;
        xc_src a; xc_snk b;
        fw_reg_block #(32) rf; fw_reg #(bit [31:0]) ctrl; fw_reg_reset_domain #(32) ch_rst;
        bit waive;
        function new(string name, fw_component parent, bit waive = 0);
            super.new(name, parent);
            this.waive = waive;
        endfunction
        function void build();
            a = new("a", this); b = new("b", this);
            rf = new("rf", this); ctrl = new("ctrl", rf);
            ch_rst = new("ch_rst", this, ctrl, 3);
        endfunction
        function void connect();
            ch_rst.src.connect(this.reset);
            a.reset.connect(ch_rst);
            a.out.connect(b.in_ex);
            if (waive) a.waive_crossing("out", FW_DOMAIN_RESET, "a drains before ctrl[3] is set");
        endfunction
    endclass

    // --- 5. a crossing element: endpoints on each side, associated explicitly ----
    class xc_elem extends fw_component implements xc_if;
        fw_export #(xc_if) in_ex;    // writer side
        fw_port   #(xc_if) out;      // reader side
        fw_clock_port      wclock, rclock;
        fw_reset_port      wreset, rreset;
        function new(string name, fw_component parent);
            super.new(name, parent);
            wclock = new("wclock", this);
            rclock = new("rclock", this);
            wreset = new("wreset", this);
            rreset = new("rreset", this);
            in_ex  = new("in_ex", this, this);
            out    = new("out", this);
            in_ex.set_domain(wclock); in_ex.set_domain(wreset);
            out.set_domain(rclock);   out.set_domain(rreset);
        endfunction
        virtual function void ping(int v); endfunction
        virtual function bit is_crossing(fw_domain_kind_e k);
            return 1;
        endfunction
    endclass

    // The same element without is_crossing(): its own endpoints cross.
    class xc_elem_bad extends xc_elem;
        function new(string name, fw_component parent); super.new(name, parent); endfunction
        virtual function bit is_crossing(fw_domain_kind_e k); return 0; endfunction
    endclass

    class xc_top_elem extends fw_component;
        xc_src w; xc_snk r; xc_elem e; xc_clk_fwd ck2; xc_rst_fwd rb;
        bit bad;
        function new(string name, fw_component parent, bit bad = 0);
            super.new(name, parent);
            this.bad = bad;
        endfunction
        function void build();
            xc_elem_bad eb;
            w = new("w", this); r = new("r", this); ck2 = new("clk_b2", this);
            rb = new("rst_b2", this, xc_env::rst_b);
            if (bad) begin eb = new("e", this); e = eb; end
            else     e = new("e", this);
        endfunction
        function void connect();
            r.clock.connect(ck2);
            r.reset.connect(rb);
            e.wclock.connect(this.clock);
            e.rclock.connect(ck2);
            e.wreset.connect(this.reset);
            e.rreset.connect(rb);
            w.out.connect(e.in_ex);
            e.out.connect(r.in_ex);
        endfunction
    endclass

    // --- 6. a socket across clocks: both directions -------------------------------
    class xc_sock_side extends fw_component;
        xc_imp imp;
        fw_socket #(xc_if, xc_if) s;
        function new(string name, fw_component parent);
            super.new(name, parent);
            imp = new();
            s   = new("s", this, imp);
        endfunction
    endclass

    class xc_mirror_side extends fw_component;
        xc_imp imp;
        fw_mirror #(xc_if, xc_if) m;
        function new(string name, fw_component parent);
            super.new(name, parent);
            imp = new();
            m   = new("m", this, imp);
        endfunction
    endclass

    class xc_top_sock extends fw_component;
        xc_sock_side a; xc_mirror_side b; xc_clk_fwd ck2;
        function new(string name, fw_component parent); super.new(name, parent); endfunction
        function void build(); a = new("a", this); b = new("b", this); ck2 = new("clk_b2", this); endfunction
        function void connect();
            a.clock.connect(ck2);
            a.s.connect(b.m);
        endfunction
    endclass

    // --- 7. a structural parent forwarding to an overridden child -----------------
    class xc_wrap extends fw_component;
        fw_port #(xc_if) out;
        xc_src s; fw_clock_domain div2;
        function new(string name, fw_component parent);
            super.new(name, parent);
            out = new("out", this);
        endfunction
        function void build(); s = new("s", this); div2 = new("div2", this, 2); endfunction
        function void connect();
            div2.src.connect(this.clock);
            s.clock.connect(div2);
            s.out.connect(out);           // port -> outer port: `out` forwards
        endfunction
    endclass

    class xc_top_fwd extends fw_component;
        xc_wrap w; xc_snk b;
        function new(string name, fw_component parent); super.new(name, parent); endfunction
        function void build(); w = new("w", this); b = new("b", this); endfunction
        function void connect(); w.out.connect(b.in_ex); endfunction
    endclass

    // --- 8. a combine of resets on unrelated clocks: reset-sync error ------------
    class xc_top_comb extends fw_component;
        xc_src a; fw_reset_combine any; xc_rst_fwd ra, rb;
        function new(string name, fw_component parent); super.new(name, parent); endfunction
        function void build();
            a = new("a", this); any = new("any", this, 2);
            ra = new("rst_a", this, xc_env::rst_a); rb = new("rst_b", this, xc_env::rst_b);
        endfunction
        function void connect();
            any.src[0].connect(ra);
            any.src[1].connect(rb);
            a.reset.connect(any);
        endfunction
    endclass
endpackage
