
typedef class fw_component;

// A *port* is an API-implementation *consumer* (TLM/UVM semantics).
//
// A component holds a port to call an API whose implementation lives
// elsewhere. The port is connected to a provider and resolves, via get_if(),
// to the implementation that provider ultimately reaches.
//
// Connection rules:
//   * port-to-export: connect to a peer export that provides the imp, or
//   * port-to-port:   connect this (inner) port up to an outer port, linking
//                     it up the component hierarchy.
// Both providers are fw_if_base, so resolution is uniform: ask the provider
// for its imp. A port is never a provider to an export (calls flow toward the
// imp), which fw_export::connect enforces by only accepting another export.
class fw_port #(type T) extends fw_if_base #(T);
    local string           m_name;
    local fw_component     m_parent;
    local fw_if_base #(T)  m_provider;  // an export (peer) or a port (outer)

    function new(string name = "", fw_component parent = null);
        m_name   = name;
        m_parent = parent;
    endfunction

    // port-to-export or port-to-port. The provider is anything that can
    // resolve to the implementation (an fw_export or another fw_port).
    function void connect(fw_if_base #(T) provider);
        m_provider = provider;
    endfunction

    // Resolve through the connection graph to the concrete implementation.
    virtual function T get_if();
        if (m_provider != null) begin
            return m_provider.get_if();
        end else begin
            $fatal(1, "fw_port '%s' is unconnected", m_name);
            return null;
        end
    endfunction
endclass
