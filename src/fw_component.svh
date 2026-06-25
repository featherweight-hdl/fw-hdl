
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

    // Every component has a `clock` port: its clock DOMAIN, consumed as the
    // fw_clock_domain_if API. Created here (not in build()) so it exists for
    // wiring before any phase runs. Left unconnected by default; do_connect()
    // auto-inherits it from the parent, or the parent/component overrides it in
    // connect(). The root's clock is seated externally by fw_root.
    fw_port #(fw_clock_domain_if) clock;

    function new(string name, fw_component parent);
        m_name = name;
        m_parent = parent;
        clock = new("clock", this);

        if (parent != null) begin
            parent.add_elaboratable(this);
        end
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

    // Register a runnable so its run() is forked during do_run(). Called
    // explicitly by objects that need a process (e.g. transactor bridges),
    // usually passing `this` from their own constructor. Being elaboratable
    // does NOT imply being runnable -- this is the opt-in.
    function void add_runnable(fw_runnable r);
        m_run.push_back(r);
    endfunction

    virtual function void build();
    endfunction

    virtual function void connect();
    endfunction

    // Build is TOP-DOWN: build self first (which creates and registers this
    // component's children), then recurse into those just-created children.
    virtual function void do_build();
        this.build();
        foreach (m_elab[i]) begin
            m_elab[i].do_build();
        end
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
    endfunction

    // Launch the run phase across this subtree. Fork the run() of every runnable
    // registered directly here, then recurse into child components so their
    // runnables are launched too. (Ports/exports are leaves -- they never hold
    // child components -- so the recursion only follows fw_component entries.)
    virtual task do_run();
        foreach (m_run[i]) begin
            automatic fw_runnable r = m_run[i];
            fork
                r.run();
            join_none
        end
        foreach (m_elab[i]) begin
            fw_component c;
            if ($cast(c, m_elab[i])) begin
                c.do_run();
            end
        end
    endtask

endclass
