// D-2: structural instrumentation and the bind map.
//
// Three claims:
//
//   1. **`dbg` is an ambient property, like `clock`.** Every component has one,
//      it is inherited from the parent by default, and it is live EARLY ENOUGH
//      that a component's own `build()` can emit into it. That last part is why
//      the context is threaded in `do_build` rather than `do_connect`.
//   2. **A component can carve its own context** and hand it to a subtree, which
//      is the §4.2 promise ("one context per DMA channel"). It needs a typed
//      handle to the inherited domain, hence `dbg_domain()`.
//   3. **The bind map answers "why do I see nothing".** Every endpoint, what it
//      resolved to, and — the payload — everything that is unconnected.
module dbg_struct_tb;
    import fw_hdl_pkg::*;
    `include "dbg/fw_dbg_macros.svh"

    int errors = 0;

    function automatic void chk(bit cond, string msg);
        if (!cond) begin $display("FAIL: %s", msg); errors++; end
    endfunction

    function automatic bit has(string h, string n);
        if (n.len() == 0 || n.len() > h.len()) return 1'b0;
        for (int i = 0; i + n.len() <= h.len(); i++) begin
            if (h.substr(i, i + n.len() - 1) == n) return 1'b1;
        end
        return 1'b0;
    endfunction

    // A trivial API so the toy tree has a real port/export pair to bind.
    interface class toy_if;
        pure virtual function void poke(int v);
    endclass

    // A minimal clock domain, so the toy tree's `clock` ports resolve. (An
    // unconnected root clock is itself a fatal at connect -- which the bind map
    // now diagnoses, but it is not what this test is about.)
    class fake_clock extends fw_export #(fw_clock_domain_if)
            implements fw_clock_domain_if;
        function new(string name, fw_component parent);
            super.new(name, parent);
            set_imp(this);
        endfunction
        virtual task tick(int n = 1); #(n); endtask
        virtual function longint root_ticks(int n = 1); return n; endfunction
    endclass

`ifdef FW_TRACE_OFF
    // Compiled out: the structure is unchanged and still elaborates, but no
    // structural event is emitted. The bind map is NOT part of the debug
    // *stream* -- it is a static artifact — so it must still work.
    class leaf extends fw_component;
        fw_port #(toy_if) out;
        function new(string name, fw_component parent);
            super.new(name, parent);
            out = new("out", this);
        endfunction
    endclass
    class top extends fw_component;
        leaf a;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        virtual function void build(); a = new("a", this); endfunction
    endclass

    fw_component_root #(top) root = new("top");

    initial begin
        automatic fake_clock ck = new("clk", root);
        root.clock.connect(ck);
        root.start();
        chk(has(root.bind_map_json(), "\"path\":\"top.a\""), "OFF: bind map still built");
        chk(fw_dbg_catalog::num_sites() == 0,               "OFF: no sites registered");
        if (errors == 0) $display("[dbg_struct] PASS (FW_TRACE_OFF)");
        else begin $display("[dbg_struct] FAIL (%0d errors)", errors); $fatal(1, "FAIL"); end
        $finish;
    end
`else

    class counting_listener extends fw_dbg_listener;
        int    n_build, n_connect, n_fork, n_notice;
        string notice_paths[$];
        string last_notice;

        virtual function void on_op(fw_op_ctx op);
            case (op.name())
                "fw_component.build":    n_build++;
                "fw_component.connect":  n_connect++;
                "fw_component.run_fork": n_fork++;
                default: ;
            endcase
        endfunction
        virtual function void on_notice(fw_notice_ctx n);
            n_notice++;
            last_notice = n.name();
            notice_paths.push_back({n.name(), "@", (n.ctx() != null) ? n.ctx().path() : "-"});
        endfunction
    endclass

    // --- the toy tree ------------------------------------------------------
    //   top
    //     +- p     (producer: a port `out`, and a runnable)
    //     +- c     (consumer: an export `in` over a real imp)
    //     +- s     (carves its OWN debug context)
    //     +- stray (a port nobody connects -- the thing under test)

    class imp_c implements toy_if;
        int seen;
        virtual function void poke(int v); seen = v; endfunction
    endclass

    class producer extends fw_component implements fw_runnable;
        fw_port #(toy_if) out;
        function new(string name, fw_component parent);
            super.new(name, parent);
            out = new("out", this);
            add_runnable(this);
        endfunction
        virtual function void build();
            // Emitted from INSIDE build(). If the context were threaded in
            // do_connect, this would be lost -- which is the whole point.
            `fw_note(dbg_if(), "producer.built")
        endfunction
        virtual task run();
        endtask
    endclass

    class consumer extends fw_component;
        fw_export #(toy_if) in;
        imp_c               imp;
        function new(string name, fw_component parent);
            super.new(name, parent);
            imp = new();
            in  = new("in", this, imp);
        endfunction
    endclass

    // A component that wants its own context, carved along its own axis rather
    // than inherited from the instance hierarchy.
    class subsys extends fw_component;
        fw_dbg_domain own;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        virtual function void build();
            own = new("sub", this);
            own.connect_up(dbg_domain());   // the inherited context, typed
            set_dbg_domain(own);            // ...adopt it as mine
            `fw_note(dbg_if(), "subsys.built")
        endfunction
    endclass

    class top extends fw_component;
        producer          p;
        consumer          c;
        subsys            s;
        fw_port #(toy_if) stray;            // deliberately never connected

        function new(string name, fw_component parent);
            super.new(name, parent);
            stray = new("stray", this);
        endfunction
        virtual function void build();
            p = new("p", this);
            c = new("c", this);
            s = new("s", this);
        endfunction
        virtual function void connect();
            p.out.connect(c.in);
        endfunction
    endclass

    fw_dbg_root              rootdom = new("top");
    fw_component_root #(top) root    = new("top");

    initial begin
        automatic counting_listener log = new();
        automatic string            map;
        automatic string            unconn[$];
        automatic fake_clock        ck = new("clk", root);

        // Subscribe and resolve BEFORE elaboration. This is legal only because
        // the site catalog is complete at time 0 (D-0) -- every site in the
        // image is registered whether or not its code has run yet. Without that
        // property the structural events, which are emitted DURING elaboration,
        // could never be captured.
        root.clock.connect(ck);

        rootdom.add_listener(log, FW_K_ALL, FW_L_TRACE);
        rootdom.apply();
        root.set_dbg_domain(rootdom);

        root.start();
        #1;

        // ===== 1. the context is ambient, inherited, and live during build ===
        chk(root.dbg_if()     != null, "root has a context");
        chk(root.p.dbg_if()   != null, "a child inherits its parent's context");
        chk(root.c.dbg_if()   != null, "...and so does its sibling");

        chk(log.n_notice >= 2, "notices emitted from inside build() were heard");
        begin
            automatic bit saw_p = 0, saw_s = 0;
            foreach (log.notice_paths[i]) begin
                if (log.notice_paths[i] == "producer.built@top") saw_p = 1;
                // ===== 2. a carved context reports its OWN path ==============
                if (log.notice_paths[i] == "subsys.built@top.sub") saw_s = 1;
            end
            chk(saw_p, "an inherited context tags events with the ROOT path");
            chk(saw_s, "a carved context tags its subtree with its OWN path");
        end

        // ===== 3. the phases actually ran, and the runnable was forked =======
        // top + p + c + s == 4 components.
        chk(log.n_build   == 4, $sformatf("one build event per component (got %0d)",   log.n_build));
        chk(log.n_connect == 4, $sformatf("one connect event per component (got %0d)", log.n_connect));
        chk(log.n_fork    == 1, $sformatf("one run_fork per registered runnable (got %0d)", log.n_fork));

        // ===== 4. the bind map ==============================================
        map = root.bind_map_json();
        $display("--- bind map JSON ---");
        $display("%s", map);
        chk(has(map, "\"root\":\"top\""),                        "map names the root");
        chk(has(map, "\"path\":\"top\""),                        "map lists the root component");
        chk(has(map, "\"path\":\"top.p\""),                      "map lists a child");
        chk(has(map, "\"path\":\"top.s\""),                      "map lists every child");
        // every component has the two ambient endpoints...
        chk(has(map, "{\"name\":\"clock\",\"role\":\"port\""),   "map lists the clock port");
        chk(has(map, "{\"name\":\"dbg\",\"role\":\"port\""),     "map lists the dbg port");
        // ...and the user's port resolved through to the consumer's export
        chk(has(map, "\"name\":\"out\",\"role\":\"port\",\"connected\":true,\"provider\":\"in\",\"resolved\":true"),
            "map records port -> provider -> resolved");
        chk(has(map, "\"name\":\"in\",\"role\":\"export\",\"connected\":true,\"provider\":\"<imp>\""),
            "map records an export holding a terminal imp");
        chk(has(map, "\"name\":\"stray\",\"role\":\"port\",\"connected\":false"),
            "map records the unconnected port");
        chk(has(map, "\"runnables\":1"),                         "map records registered runnables");

        // ===== 5. the unconnected list is the diagnosis ======================
        root.collect_unconnected(unconn);
        begin
            automatic bit saw_stray = 0;
            foreach (unconn[i]) if (has(unconn[i], "top.stray")) saw_stray = 1;
            chk(saw_stray, "unconnected list names the port by full path");
            chk(has(map, "\"unconnected\":[") && has(map, "top.stray"),
                "...and the JSON carries it too");
        end
        chk(root.num_unresolved() > 0, "num_unresolved() counts the casualty");

        // What a failing get_if() prints. Shown rather than triggered: the
        // $fatal itself is unchanged SystemVerilog behavior, and a test that
        // dies cannot also report. THIS is the part that is new.
        $display("");
        $display("--- what an unconnected port now reports ---");
        $display("fw_port '%s' is UNCONNECTED -- resolution has no provider.",
                 root.stray.full_name());
        root.dump_bind_map();

        if (errors == 0) $display("[dbg_struct] PASS");
        else begin
            $display("[dbg_struct] FAIL (%0d errors)", errors);
            $fatal(1, "[dbg_struct] FAIL");
        end
        $finish;
    end
`endif /* FW_TRACE_OFF */

endmodule
