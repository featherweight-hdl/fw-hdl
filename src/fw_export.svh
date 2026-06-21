
typedef class fw_component;

// An *export* is an API-implementation *provider* (TLM/UVM semantics).
//
// It resolves to a concrete implementation in one of two ways:
//   * it wraps a terminal implementation handle -- an imp -- directly, or
//   * it forwards to another export connected below it in the hierarchy
//     (export-to-export connection).
//
// Connection rules enforced here:
//   * an export may connect to another export (or, since an imp is just a T,
//     be given an imp directly via the constructor / set_imp), but
//   * an export may NOT connect to a port -- calls flow toward the imp, never
//     away from it. connect() only accepts another fw_export.
class fw_export #(type T) extends fw_if_base #(T);
    local string          m_name;
    local fw_component    m_parent;
    local T               m_imp;   // terminal implementation (imp), or
    local fw_export #(T)  m_fwd;   // forwarded-to provider (export-to-export)

    function new(string name = "", fw_component parent = null, T imp = null);
        m_name   = name;
        m_parent = parent;
        m_imp    = imp;
    endfunction

    // Bind/replace the terminal implementation this export provides.
    function void set_imp(T imp);
        m_imp = imp;
    endfunction

    // export-to-export: forward to a provider lower in the hierarchy.
    function void connect(fw_export #(T) provider);
        m_fwd = provider;
    endfunction

    // Resolve to the concrete implementation handle (the imp).
    virtual function T get_if();
        if (m_imp != null) begin
            return m_imp;
        end else if (m_fwd != null) begin
            return m_fwd.get_if();
        end else begin
            $fatal(1, "fw_export '%s' resolves to no implementation", m_name);
            return null;
        end
    endfunction
endclass
