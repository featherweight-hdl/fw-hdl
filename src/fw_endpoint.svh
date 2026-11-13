typedef class fw_component;

// The untyped base of every port and export.
//
// fw_if_base #(T) is specialized per interface type, so code that takes "any
// endpoint" (an extern's port map, a facts declaration, the crossing check)
// takes this instead and names the endpoint through ep_name().
virtual class fw_endpoint;
    // The endpoint's local name. Held here rather than privately in each
    // subclass so that one endpoint can NAME another across the T boundary --
    // which is what lets the bind map say "port `out` -> export `in`" instead of
    // "port `out` -> <something>".
    protected string m_ep_name;

    // An AMBIENT endpoint is plumbing rather than a data binding: a component's
    // `clock`, `reset` and `dbg` ports, domain ports, and the exports a domain
    // is provided through. The crossing check skips them.
    bit              m_ambient;

    // Explicit domain associations (set_domain), by kind. An endpoint with no
    // entry for a kind is in its owner component's domain of that kind.
    fw_domain_ref    m_dom[fw_domain_kind_e];

    function string ep_name();
        return m_ep_name;
    endfunction

    // --- the ends, as objects (the crossing walk; no $cast needed) ----------
    // The component that holds this endpoint (null for a parentless one, such
    // as a derived domain's source port).
    virtual function fw_component ep_owner();
        return null;
    endfunction

    // What this endpoint is bound to: a port's provider; an export's
    // forwarded-to export, or null when it holds an imp.
    virtual function fw_endpoint ep_next();
        return null;
    endfunction

    virtual function bit ep_is_port();
        return 0;
    endfunction

    // An export holding the imp: where a binding ends.
    virtual function bit ep_is_terminal();
        return 0;
    endfunction

    // Full path (owner path + name).
    virtual function string ep_full_name();
        return m_ep_name;
    endfunction

    function void set_ambient();
        m_ambient = 1'b1;
    endfunction

    // Associate this endpoint with a domain of d's kind (a component on a
    // domain boundary does this for the endpoints on each side).
    function void set_domain(fw_domain_ref d);
        if (d != null) m_dom[d.ref_kind()] = d;
    endfunction

    // The domain port this endpoint is in, for kind k: an explicit association,
    // else the owner component's port of that kind.
    function fw_domain_ref ep_domain(fw_domain_kind_e k);
        fw_component o;
        if (m_dom.exists(k)) return m_dom[k];
        o = ep_owner();
        return (o != null) ? o.domain(k) : null;
    endfunction
endclass
