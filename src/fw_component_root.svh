
typedef class fw_component;
typedef class fw_dbg_console;   // declared later in the package (needs the domain)


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

        // Live tracking, if this run asked for it. Before build, so a frame
        // opened during elaboration would be counted too.
        if ($test$plusargs("fw_dbg_track")) begin
            fw_dbg_track::set_enabled(1);
        end

        // Run build, connect across the whole tree.
        do_build();
        do_connect();

        // Elaboration is over. Close the ambient-ownership window (see
        // fw_component) so nothing created during the run adopts a stale owner:
        // a silent object is a recoverable mistake, an object reporting into the
        // wrong context is not.
        fw_component::dbg_end_elaboration();
        fw_dbg_console::report_uncontexted();

        // Re-resolve the gate. INSTANCE sites (registers, register blocks) are
        // registered during elaboration -- after any apply() the environment did
        // before start() -- so without this pass they would be born disabled.
        if (dbg_domain() != null) begin
            dbg_domain().apply();
        end

        // The bind map is complete exactly here: every port resolved, every
        // export bound, every runnable registered -- and nothing has run yet.
        emit_bind_map();

        // Launch every runnable in the tree -- including the root's own run() if
        // the root component is itself a runnable (fork happens inside do_run).
        do_run();
    endtask

    // Emit the static bind-map artifact (design §9).
    //
    // OPT-IN, because writing a file into every existing run's directory is a
    // behavior change nobody asked for:
    //
    //     +fw_bindmap             -> write ./fw_bindmap.json
    //     +fw_bindmap=<path>      -> write <path>
    //     +fw_bindmap_show        -> print the human-readable form
    //
    // The failure path does not need any of these: an unconnected endpoint
    // prints the map unconditionally, which is the moment you actually want it.
    virtual function void emit_bind_map();
        string path;
        int    fh;

        if ($test$plusargs("fw_bindmap_show")) begin
            dump_bind_map();
        end

        if ($value$plusargs("fw_bindmap=%s", path)) begin
            // explicit path
        end else if ($test$plusargs("fw_bindmap")) begin
            path = "fw_bindmap.json";
        end else begin
            return;
        end

        fh = $fopen(path, "w");
        if (fh == 0) begin
            $display("fw-hdl: could not open bind map '%s' for writing", path);
            return;
        end
        $fdisplay(fh, "%s", bind_map_json());
        $fclose(fh);
        $display("fw-hdl: bind map written to '%s'", path);
    endfunction

    // The answer to "nothing is happening".
    //
    // Every thread's open operations and, for a blocked one, exactly what it is
    // waiting for -- by name. Call it from a watchdog, from a $finish hook, or
    // from an interactive prompt; it is a function, so it is safe anywhere.
    //
    // Requires +fw_dbg_track (see fw_dbg_track.svh for why that is opt-in). When
    // tracking is off this prints how to turn it on rather than an empty dump:
    // the one thing worse than no information is a report that looks like
    // information and is not.
    virtual function void fw_dbg_dump();
        $display("%s", fw_dbg_track::report());
    endfunction

    virtual task kill();
        m_proc.kill();
    endtask

endclass
