
typedef class fw_component;

// Root wrapper for a PARAMETERIZED component, mirroring fw_component_root but
// for components built on fw_component_param. Tb is the user component type; we
// require it to expose its parameter type as Tb::param_t (the nested typedef
// every parameterized component already declares). The only structural
// difference from fw_component_root is the constructor: a root parameterized
// component is the top of the tree (parent = null) yet still needs its typed
// config object threaded down to fw_component_param::new.
class fw_component_root_param #(type Tb=fw_component_param) extends Tb;
    // Hoist the component's parameter type (the `<comp>::param_t` convention)
    // to a local name. Notes:
    //   - The direct form `Tb::param_t params` in the port list trips Questa's
    //     parser, so a local typedef is required.
    //   - Reusing the name `param_t` makes Verilator flag a self-referential
    //     typedef, so the local name differs (params_t).
    //   - This is also WHY param_t must be an alias to a standalone class, not
    //     a nested class: Verilator's full build rejects this typedef as
    //     use-before-declaration if Tb::param_t resolves to a class declared
    //     later in Tb's body. See fw_component_param.svh.
    typedef Tb::param_t params_t;

    std::process            m_proc;

    function new(string name, params_t params);
        super.new(name, null, params);
    endfunction

    // Identical lifecycle to fw_component_root -- see that file for the
    // rationale on why this is start()/kill() rather than run().
    virtual task start();
        m_proc = std::process::self();
        do_build();
        do_connect();
        do_run();
    endtask

    virtual task kill();
        m_proc.kill();
    endtask

endclass
