
typedef class fw_component;

// A *port* is an API-implementation *consumer* (TLM/UVM semantics).
//
// A component holds a port to call an API whose implementation lives
// elsewhere. The port is connected to a provider and, during the connect phase,
// resolves the provider's implementation handle into the public member `t`. Run-
// phase code then calls the API directly as `port.t.method(...)` -- no per-call
// graph walk.
//
// Connection rules:
//   * port-to-export: connect to a peer export that provides the imp, or
//   * port-to-port:   connect this (inner) port up to an outer port, linking
//                     it up the component hierarchy.
// Both providers are fw_if_base, so resolution is uniform: ask the provider
// for its imp. A port is never a provider to an export (calls flow toward the
// imp), which fw_export::connect enforces by only accepting another export.
class fw_port #(type T) extends fw_if_base #(T)
        implements fw_elaboratable, fw_dbg_bindable;
    // The resolved implementation handle (the imp), bound during do_connect().
    // This is the run-phase call target: `port.t.method(args)`. Null until
    // connect resolves it (an unconnected port leaves it null).
    T                      t;

    local fw_component     m_parent;
    local fw_if_base #(T)  m_provider;  // an export (peer) or a port (outer)

    function new(string name = "", fw_component parent = null);
        m_ep_name = name;
        m_parent  = parent;
        // A port is elaboratable: register with the containing component so the
        // lifecycle walk reaches it. An ACTIVE port (a bridge overriding run())
        // is then launched by do_run() alongside child components.
        if (parent != null) begin
            parent.add_elaboratable(this);
            // ...and bindable, so the bind map can enumerate it without having
            // to know T (see fw_dbg_bindable).
            parent.add_bindable(this);
        end
    endfunction

    // --- fw_dbg_bindable ------------------------------------------------------
    virtual function string bind_name();      return m_ep_name;          endfunction
    virtual function string bind_role();      return "port";             endfunction
    virtual function bit    bind_connected(); return m_provider != null; endfunction
    virtual function bit    bind_resolved();  return t != null;          endfunction
    virtual function string bind_provider();
        return (m_provider != null) ? m_provider.ep_name() : "";
    endfunction

    // port-to-export or port-to-port. The provider is anything that can
    // resolve to the implementation (an fw_export or another fw_port).
    function void connect(fw_if_base #(T) provider);
        m_provider = provider;
    endfunction

    // Has a provider been bound? Used by the clock-domain auto-inherit pass to
    // tell an explicitly-bound child port from one that should default to its
    // parent's domain.
    function bit is_connected();
        return m_provider != null;
    endfunction

    // Resolve through the connection graph to the concrete implementation.
    //
    // The unconnected case used to be a bare `$fatal` naming one port, which is
    // the least useful moment to be told the least useful fact: you learn that
    // SOMETHING is unwired, then go read source to find out what else is. Now it
    // emits a VITAL notice and dumps the whole bind map first, so the failure
    // carries its own diagnosis -- every endpoint in the tree, what it resolved
    // to, and everything else that is also unconnected.
    virtual function T get_if();
        if (m_provider != null) begin
            return m_provider.get_if();
        end else begin
            `fw_error_begin(pdbg(), "fw_port.unconnected")
            `fw_ev_end
            report_unconnected();
            $fatal(1, "fw_port '%s' is unconnected", full_name());
            return null;
        end
    endfunction

    // --- diagnostics ----------------------------------------------------------
    // A port's emitting context is its OWNING COMPONENT's context: a port has no
    // context of its own, and giving it one would double the size of the debug
    // tree for no benefit. Reached through `.t` rather than get_if(), so a port
    // that fails to resolve can never recurse into itself while reporting it.
    protected function fw_dbg_listener_if pdbg();
        return (m_parent != null) ? m_parent.dbg_if() : null;
    endfunction

    function string full_name();
        return (m_parent != null) ? {m_parent.get_full_name(), ".", m_ep_name}
                                  : m_ep_name;
    endfunction

    protected function void report_unconnected();
        $display("");
        $display("fw_port '%s' is UNCONNECTED -- resolution has no provider.", full_name());
        if (m_parent != null) begin
            m_parent.dump_bind_map();
        end
    endfunction

    // --- fw_elaboratable lifecycle -------------------------------------------
    // A bare port has nothing to build (its binding is performed by the owning
    // component via connect(provider)). A port does NOT run by default; an
    // ACTIVE port -- a bridge with a sampling loop -- additionally
    // `implements fw_runnable` so add_runnable() queues its run().
    virtual function void do_build();
    endfunction

    // Resolve the implementation handle once, here, so run-phase code can use
    // `t` directly. Resolution walks the connection graph (get_if). Safe because
    // connect is top-down and no connect() body resolves a binding: by the time
    // a port's do_connect runs, its whole provider chain is already wired.
    virtual function void do_connect();
        if (m_provider != null) begin
            t = get_if();
        end
    endfunction
endclass
