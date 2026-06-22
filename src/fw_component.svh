
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

    function new(string name, fw_component parent);
        m_name = name;
        m_parent = parent;

        if (parent != null) begin
            parent.add_elaboratable(this);
        end
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

    // Connect is BOTTOM-UP: children connect first, then this component, so a
    // parent can rely on its children being fully connected (and resolve
    // bindings upward) in its own connect().
    virtual function void do_connect();
        foreach (m_elab[i]) begin
            m_elab[i].do_connect();
        end
        this.connect();
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
