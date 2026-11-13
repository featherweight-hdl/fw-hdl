typedef class fw_component;

// A DOMAIN PORT: an fw_port #(T) for a domain API, which also answers which
// kind of domain it carries and what it is bound to, without the caller knowing
// T (fw_domain_ref). Every component has two -- `clock` (fw_clock_port) and
// `reset` (fw_reset_port) -- inherited from the parent; a component on a domain
// boundary declares more and associates its endpoints with them
// (fw_endpoint::set_domain).
//
// Being a subclass of fw_port #(T), a domain port is used exactly as a port:
// `clock.connect(dom)`, `clock.t.tick(1)`, `is_connected()`.
//
// Domain ports are ambient (fw_endpoint::m_ambient): the crossing check does
// not treat them as data bindings.
class fw_domain_port #(type T = fw_domain_if, fw_domain_kind_e K = FW_DOMAIN_CLOCK)
        extends fw_port #(T) implements fw_domain_ref;

    // An OPTIONAL domain port may be left unbound (a component `reset`: unbound
    // means "never in reset"). The bind map then does not list it as
    // unconnected.
    protected bit m_optional;

    function new(string name = "", fw_component parent = null);
        super.new(name, parent);
        set_ambient();
    endfunction

    function void set_optional();
        m_optional = 1'b1;
    endfunction

    virtual function fw_domain_kind_e ref_kind();
        return K;
    endfunction

    virtual function fw_domain_if ref_domain();
        T d;
        if (!is_connected()) return null;
        d = (t != null) ? t : get_if();
        return d;
    endfunction

    virtual function string ref_name();
        return full_name();
    endfunction

    virtual function bit bind_connected();
        return m_optional || super.bind_connected();
    endfunction

    virtual function bit bind_resolved();
        return (m_optional && !is_connected()) || super.bind_resolved();
    endfunction
endclass

typedef fw_domain_port #(fw_clock_domain_if, FW_DOMAIN_CLOCK) fw_clock_port;
