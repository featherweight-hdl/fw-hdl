
typedef class fw_component;


class fw_component_root #(type Tb=fw_component) extends Tb;
    std::process            m_proc;

    function new(string name);
        super.new(name, null);
    endfunction

    // Drive the whole lifecycle. This is deliberately NOT named run(): a root
    // component may itself be an fw_runnable with its own behavioral run(), and
    // overriding run() here would shadow it. Keeping the orchestrator separate
    // lets do_run() fork the user's run() like any other runnable -- so a
    // runnable component can serve as the root with no loss of behavior.
    virtual task start();
        // Capture the thread we're running in (so kill() can tear it down).
        m_proc = std::process::self();

        // Run build, connect across the whole tree.
        do_build();
        do_connect();

        // Launch every runnable in the tree -- including the root's own run() if
        // the root component is itself a runnable (fork happens inside do_run).
        do_run();
    endtask

    virtual task kill();
        m_proc.kill();
    endtask

endclass
