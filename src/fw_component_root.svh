
typedef class fw_component;


class fw_component_root #(type Tb=fw_component) extends Tb;
    std::process            m_proc;

    function new(string name);
        super.new(name, null);
    endfunction

    virtual task run();
        // Manages the entire lifecycle

        // Captures thread we're running in
        m_proc = std::process::self();

        // Runs build, connect across the whole tree
        do_build();
        do_connect();

        // Launches every runnable in the tree (fork happens inside do_run)
        do_run();
    endtask

    virtual task kill();
        m_proc.kill();
    endtask

endclass
