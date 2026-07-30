
class fw_component implements fw_elaboratable;
    protected string            m_name;
    protected fw_component      m_parent;
    // Everything to elaborate (child components AND ports/exports), walked for
    // build/connect.
    protected fw_elaboratable   m_elab[$];
    // Things to run -- forked during do_run(). A runnable is NOT detected
    // automatically: an object that wants a run() process must explicitly
    // register via add_runnable() (typically from its own constructor). Most
    // ports/exports never do this, so they spawn no process.
    protected fw_runnable       m_run[$];
    // Parallel to m_run: the catalog site naming each forked process, pushed onto
    // the live op stack by the forked thread so fw_dbg_dump() can say which
    // component's run() a blocked thread is in.
    protected int unsigned      m_sid_run[$];
    // Ports and exports seen through their unparameterized face. The same
    // objects as the fw_port/fw_export entries in m_elab, kept separately
    // because an fw_port #(T) cannot be recovered from an fw_elaboratable handle
    // (see fw_dbg_bindable). This is what the bind map walks.
    protected fw_dbg_bindable   m_bind[$];
    // Non-component things that still emit and need a context handed to them --
    // register blocks, principally. See fw_dbg_contextual.
    protected fw_dbg_contextual m_ctxt[$];

    // Every component has a `clock` port: its clock DOMAIN, consumed as the
    // fw_clock_domain_if API. Created here (not in build()) so it exists for
    // wiring before any phase runs. Left unconnected by default; do_connect()
    // auto-inherits it from the parent, or the parent/component overrides it in
    // connect(). The root's clock is seated externally by fw_root.
    fw_port #(fw_clock_domain_if) clock;

    // ...and a `dbg` port: its DEBUG CONTEXT, consumed as the listener API.
    // Deliberately the same shape as `clock` -- created in the constructor,
    // inherited from the parent by default, overridable at any level -- because
    // it is the same kind of thing: an ambient property of where a component
    // sits, not a dependency it declares.
    //
    // The consequence worth naming: this is a BUILT-IN OBSERVER PORT. A bench
    // attaches a sink to any component's context, at any depth, and receives its
    // events -- without that component knowing or being modified. Observing is
    // wiring, not instrumentation.
    //
    // Unbound by default, and an unbound context costs the null check that a
    // disabled context would have cost anyway.
    fw_port #(fw_dbg_listener_if) dbg;

    // The typed handle behind `dbg`, when this component chose its own context.
    // Null means "inherited" -- dbg_domain() then walks up to find it.
    protected fw_dbg_domain     m_dbg_dom;

    // ----------------------------------------------------------------------
    // The AMBIENT component: who owns whatever is being constructed right now.
    //
    // `clock` and `dbg` are ambient properties of where a component sits -- it
    // does not declare them, it inherits them. A register block owned by a
    // component is the same kind of thing, and it should inherit the same way.
    // But a plain object has no parent pointer to walk, so the ownership has to
    // be recorded as it happens.
    //
    // The window is ELABORATION, and only elaboration:
    //
    //   * `new()` sets the owner to `this` -- it runs BEFORE any member the
    //     subclass constructor creates, so `regs = new("regs")` inside
    //     `wb_dma_rf::new` sees `rf`, not `rf`'s parent;
    //   * `do_build()` re-seats it around `this.build()`, because the build walk
    //     is a recursion and the last component CONSTRUCTED is not the one
    //     currently BUILDING;
    //   * `fw_component_root::start()` closes the window after connect, so an
    //     object created at run time never adopts a stale owner. Silence is a
    //     recoverable mistake; the wrong context is not.
    //
    // A component constructed at run time re-opens the window, which is correct:
    // a dynamically created subtree owns what it creates.
    protected static fw_component m_ambient;
    protected static bit          m_ambient_live;

    static function fw_component dbg_ambient();
        return m_ambient_live ? m_ambient : null;
    endfunction

    static function void dbg_end_elaboration();
        m_ambient_live = 1'b0;
        m_ambient      = null;
    endfunction

    function new(string name, fw_component parent);
        m_name = name;
        m_parent = parent;
        clock = new("clock", this);
        dbg   = new("dbg", this);

        if (parent != null) begin
            parent.add_elaboratable(this);
        end

        // Anything this component's constructor builds from here on belongs to
        // it. Last statement in the constructor, deliberately.
        m_ambient      = this;
        m_ambient_live = 1'b1;
    endfunction

    function string get_name();
        return m_name;
    endfunction

    function string get_full_name();
        return (m_parent != null) ? {m_parent.get_full_name(), ".", m_name} : m_name;
    endfunction

    function fw_component get_parent();
        return m_parent;
    endfunction

    // This component's debug context, or null when unbound. Reached through `.t`
    // rather than get_if() so that an unwired `dbg` is silence rather than a
    // fatal -- an unobserved model must still run.
    function fw_dbg_listener_if dbg_if();
        return (dbg != null) ? dbg.t : null;
    endfunction

    // The context as a DOMAIN, not merely as a listener.
    //
    // Needed because a component that wants its own context has to wire the new
    // domain's `up` to the inherited one -- and `dbg.t` is an interface-class
    // handle that cannot be downcast back to fw_dbg_domain (Verilator 5.049,
    // parameterized base). So the typed handle is remembered on the way down the
    // component tree instead of being recovered on the way back:
    //
    //     // in build():
    //     m_ch_dbg = new("ch0", this);
    //     m_ch_dbg.connect_up(dbg_domain());   // nearest inherited domain
    //     set_dbg_domain(m_ch_dbg);            // ...and adopt it as mine
    //
    // That is the §4.2 promise made usable: one context per DMA channel, cutting
    // across the instance hierarchy, without any component knowing the root.
    function void set_dbg_domain(fw_dbg_domain d);
        m_dbg_dom = d;
        dbg.connect(d);
        // Re-resolve: this is normally called from build(), which runs AFTER
        // do_build() step 1 already seated the inherited context.
        dbg.do_connect();
    endfunction

    function fw_dbg_domain dbg_domain();
        if (m_dbg_dom != null) return m_dbg_dom;
        return (m_parent != null) ? m_parent.dbg_domain() : null;
    endfunction

    // Advance this component's clock domain by n cycles (run phase only).
    task tick(int n = 1);
        clock.get_if().tick(n);
    endtask

    // How many root-domain clocks span n ticks of this component's domain.
    function longint root_ticks(int n = 1);
        return clock.get_if().root_ticks(n);
    endfunction

    // Register an elaboratable (child component, port, or export) with this
    // component so it is walked for build/connect.
    function void add_elaboratable(fw_elaboratable e);
        m_elab.push_back(e);
    endfunction

    // Register a port/export under its unparameterized face, for the bind map.
    // Called by fw_port/fw_export alongside add_elaboratable().
    function void add_bindable(fw_dbg_bindable b);
        m_bind.push_back(b);
    endfunction

    // Register something that emits but is not a component, so do_build() can
    // hand it this component's resolved context.
    function void add_contextual(fw_dbg_contextual c);
        m_ctxt.push_back(c);
    endfunction

    // Register a runnable so its run() is forked during do_run(). Called
    // explicitly by objects that need a process (e.g. transactor bridges),
    // usually passing `this` from their own constructor. Being elaboratable
    // does NOT imply being runnable -- this is the opt-in.
    function void add_runnable(fw_runnable r);
        // An instance site per runnable, so the live dump can say WHICH
        // component's run() a blocked thread is inside. Registered here rather
        // than in the constructor because only a runnable component needs one --
        // and here the runnable's index is known, which disambiguates the rare
        // component that forks more than one process.
        int unsigned sid = FW_DBG_NO_SITE;
        string       nm  = (m_run.size() == 0)
                             ? {get_full_name(), ".run"}
                             : $sformatf("%s.run%0d", get_full_name(), m_run.size());
        `fw_dbg_site_inst(sid, nm, FW_DBG_SCHED, FW_L_VITAL)
        m_run.push_back(r);
        m_sid_run.push_back(sid);
    endfunction

    virtual function void build();
    endfunction

    virtual function void connect();
    endfunction

    // Build is TOP-DOWN: build self first (which creates and registers this
    // component's children), then recurse into those just-created children.
    //
    // The debug context is threaded HERE rather than in do_connect (where
    // `clock` is inherited) for one reason: a component's build() is itself
    // worth observing, and a context bound after build has already run is a
    // context that missed it. Because build is top-down this works out: a
    // component's own `dbg` is resolved before its build() executes, and its
    // children's are resolved before theirs.
    virtual function void do_build();
        fw_component prev_ambient = m_ambient;
        bit          prev_live    = m_ambient_live;

        // 1. Resolve my own context. The parent bound it before recursing (or,
        //    for the root, the environment bound it before start()).
        dbg.do_connect();

        // 2. Build self -- this is what creates the children. Own the ambient
        //    across it: the build walk is a recursion, so the last component
        //    CONSTRUCTED is not the one currently BUILDING, and a block created
        //    in build() must land on this component rather than on whichever
        //    sibling happened to be constructed most recently.
        m_ambient      = this;
        m_ambient_live = 1'b1;
        this.build();
        m_ambient      = prev_ambient;
        m_ambient_live = prev_live;

        // 2b. Hand my context to the non-component things built above -- a
        //     register file instrumented here needs no per-design wiring at all.
        foreach (m_ctxt[i]) begin
            m_ctxt[i].set_dbg_context(dbg_if());
        end

        // 3. Hand my context down to any child that did not choose its own. A
        //    component that wants a distinct context binds child.dbg in its own
        //    build(), and this pass leaves it alone.
        //
        //    Only when MINE is bound. Unlike `clock`, a debug context is
        //    optional -- an unobserved model must still run -- and chaining a
        //    child to an unbound parent port would make the child's resolution
        //    walk off the end of the chain and $fatal. Leaving the child
        //    unconnected is what makes "nobody is watching" cost silence.
        if (dbg.is_connected()) begin
            foreach (m_elab[i]) begin
                fw_component c;
                if ($cast(c, m_elab[i]) && !c.dbg.is_connected()) begin
                    c.dbg.connect(this.dbg);
                end
            end
        end

        // 4. Recurse -- children build with their context already seated.
        foreach (m_elab[i]) begin
            m_elab[i].do_build();
        end

        `fw_ev_op(dbg_if(), FW_L_VITAL, "fw_component.build", FW_OP_ENDED)
            `fw_field_as("elab", m_elab.size())
            `fw_field_as("runnables", m_run.size())
        `fw_ev_end
    endfunction

    // Connect is TOP-DOWN: this component connects first, then its children.
    // This is what lets clock domains flow downward -- by the time a child's
    // connect() runs, its `clock` port is already bound (the parent either
    // overrode it in connect() below, or the auto-inherit pass defaulted it to
    // this component's domain), so the child can build a derived domain that
    // pulls from its now-resolved parent. Safe because no connect() body
    // resolves a binding (get_if() is only ever called in run()); connect() just
    // wires pointers, so ordering is free.
    virtual function void do_connect();
        // 1. Wire this level: the user may override any child's clock domain
        //    here (child.clock.connect(some_domain)).
        this.connect();
        // 2. Auto-inherit: any child whose clock was not explicitly bound
        //    defaults to this component's domain.
        foreach (m_elab[i]) begin
            fw_component c;
            if ($cast(c, m_elab[i]) && !c.clock.is_connected()) begin
                c.clock.connect(this.clock);
            end
        end
        // 3. Now recurse -- children connect with their clock already seated.
        foreach (m_elab[i]) begin
            m_elab[i].do_connect();
        end

        `fw_ev_op(dbg_if(), FW_L_VITAL, "fw_component.connect", FW_OP_ENDED)
            `fw_field_as("unresolved", num_unresolved())
        `fw_ev_end
    endfunction

    // Launch the run phase across this subtree. Fork the run() of every runnable
    // registered directly here, then recurse into child components so their
    // runnables are launched too. (Ports/exports are leaves -- they never hold
    // child components -- so the recursion only follows fw_component entries.)
    virtual task do_run();
        foreach (m_run[i]) begin
            automatic fw_runnable r   = m_run[i];
            automatic int unsigned sid = m_sid_run[i];
            // "This process was actually forked." The ABSENCE of this event is
            // the signal worth having: a model where nothing happens because
            // someone forgot add_runnable() is indistinguishable from one that
            // is merely idle, and this is what tells the two apart.
            `fw_ev_op(dbg_if(), FW_L_VITAL, "fw_component.run_fork", FW_OP_BEGUN)
                `fw_field_as("index", i)
            `fw_ev_end
            fork
                begin
                    // Inside the forked process, so the frame lands on the right
                    // thread's stack. A `forever` run() never reaches the pop --
                    // which is correct: the dump's job is to show what is open.
                    `fw_track_enter(sid)
                    r.run();
                    `fw_track_exit
                end
            join_none
        end
        foreach (m_elab[i]) begin
            fw_component c;
            if ($cast(c, m_elab[i])) begin
                c.do_run();
            end
        end
    endtask

    // ----------------------------------------------------------------------
    // The bind map (design §9).
    //
    // The resolved port/export graph: every endpoint, what it was wired to,
    // whether it resolved, and how many runnables were registered. Produced
    // once, after connect, and independently useful -- a large share of "I see
    // nothing" is an unconnected port or a run() that was never registered, and
    // both are visible here at a glance.
    //
    // Note what is NOT here: there is no per-bind or per-resolve *event*. The
    // design's §8 table proposed one, but a stream of resolve events carries
    // nothing this artifact does not carry better, and §14.13 ("emit only the
    // irrecoverable") says to drop it. What IS irrecoverable is the failure
    // itself, so an unconnected port emits a notice and prints this map.
    // ----------------------------------------------------------------------

    function int num_unresolved();
        int n = 0;
        foreach (m_bind[i]) begin
            if (!m_bind[i].bind_resolved()) n++;
        end
        foreach (m_elab[i]) begin
            fw_component c;
            if ($cast(c, m_elab[i])) n += c.num_unresolved();
        end
        return n;
    endfunction

    function void collect_unconnected(ref string paths[$]);
        foreach (m_bind[i]) begin
            if (!m_bind[i].bind_connected()) begin
                paths.push_back({get_full_name(), ".", m_bind[i].bind_name(),
                                 " (", m_bind[i].bind_role(), ")"});
            end
        end
        foreach (m_elab[i]) begin
            fw_component c;
            if ($cast(c, m_elab[i])) c.collect_unconnected(paths);
        end
    endfunction

    // `bit ? "true" : "false"` pads the shorter branch to the width of the
    // longer one (SV unifies the operand types), which silently produces
    // `" true"` in the JSON. A plain function does not.
    protected function string jbool(bit v);
        if (v) return "true";
        return "false";
    endfunction

    // One JSON object per component, appended in tree order.
    function void bind_map_rows(ref string rows[$]);
        string eps = "";
        foreach (m_bind[i]) begin
            eps = {eps, (i == 0) ? "" : ",",
                   $sformatf("{\"name\":\"%s\",\"role\":\"%s\",\"connected\":%s,\"provider\":\"%s\",\"resolved\":%s}",
                             m_bind[i].bind_name(), m_bind[i].bind_role(),
                             jbool(m_bind[i].bind_connected()),
                             m_bind[i].bind_provider(),
                             jbool(m_bind[i].bind_resolved()))};
        end
        rows.push_back($sformatf("    {\"path\":\"%s\",\"runnables\":%0d,\"endpoints\":[%s]}",
                                 get_full_name(), m_run.size(), eps));
        foreach (m_elab[i]) begin
            fw_component c;
            if ($cast(c, m_elab[i])) c.bind_map_rows(rows);
        end
    endfunction

    function string bind_map_json();
        string rows[$];
        string unconn[$];
        string body = "";
        string un   = "";
        bind_map_rows(rows);
        collect_unconnected(unconn);
        foreach (rows[i])   body = {body, (i == 0) ? "\n" : ",\n", rows[i]};
        foreach (unconn[i]) un   = {un, (i == 0) ? "" : ",", $sformatf("\"%s\"", unconn[i])};
        return $sformatf("{\n  \"bind_map\":{\n    \"root\":\"%s\",\n    \"components\":[%s\n    ],\n    \"unconnected\":[%s]\n  }\n}",
                         get_full_name(), body, un);
    endfunction

    // Human-readable form, used on the unconnected-endpoint failure path. Walks
    // up to the root first: when something fails to resolve you want the WHOLE
    // map, not the subtree that happens to contain the casualty.
    function void dump_bind_map();
        fw_component r = this;
        string       unconn[$];
        while (r.get_parent() != null) r = r.get_parent();
        r.collect_unconnected(unconn);

        $display("--- fw-hdl bind map (root '%s') ---", r.get_full_name());
        r.dump_bind_map_1(0);
        if (unconn.size() == 0) begin
            $display("  all endpoints connected");
        end else begin
            $display("  UNCONNECTED (%0d):", unconn.size());
            foreach (unconn[i]) $display("    %s", unconn[i]);
        end
        $display("--- end bind map ---");
    endfunction

    protected function void dump_bind_map_1(int depth);
        string pad = "";
        for (int i = 0; i < depth; i++) pad = {pad, "  "};
        $display("  %s%s%s", pad, get_name(),
                 (m_run.size() != 0) ? $sformatf("   [%0d runnable(s)]", m_run.size()) : "");
        foreach (m_bind[i]) begin
            $display("  %s  %-6s %-10s -> %-12s %s", pad,
                     m_bind[i].bind_role(), m_bind[i].bind_name(),
                     (m_bind[i].bind_provider() == "") ? "<none>" : m_bind[i].bind_provider(),
                     m_bind[i].bind_resolved() ? "" : "UNRESOLVED");
        end
        foreach (m_elab[i]) begin
            fw_component c;
            if ($cast(c, m_elab[i])) c.dump_bind_map_1(depth+1);
        end
    endfunction

endclass
