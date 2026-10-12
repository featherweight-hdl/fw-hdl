typedef class fw_mirror;

// A *socket* is one side of a bidirectional link (design §3).
//
// fw_socket #(I, E) CALLS the I API and PROVIDES the E API. Its peer is an
// fw_mirror #(I, E) -- the same type pair -- which calls E and provides I. Both
// sides name the link by one <I, E>, so there is no "which way round are the
// parameters" question, and connecting a socket to anything but the mirror of
// the same pair is a compile error.
//
// A socket is a typed pairing of an ordinary fw_port #(I) and fw_export #(E);
// it adds no resolution machinery. Outbound calls go through `t`, resolved once
// in do_connect() exactly as fw_port::t is. Inbound calls land on the E imp
// given at construction -- normally the socket subclass itself, stamped by
// `FW_SOCKET_IMP_BEGIN/END (see fw_hdl_macros.svh).
//
// A socket is MANDATORY: an unbound one fails at connect, naming itself and
// dumping the bind map (the fw_port diagnostic). There is no half-bound link.
//
// In the bind map a socket is ONE endpoint (role "socket", provider = the
// peer it was connected to), not the port and export it is made of.
class fw_socket #(type I = int, type E = int) implements fw_elaboratable, fw_dbg_bindable;
    I               t;       // outbound imp, resolved in do_connect()
    fw_port   #(I)  imp_p;   // what this side calls
    fw_export #(E)  exp_x;   // what this side provides

    protected string       m_name;
    protected fw_component m_parent;
    string                 m_peer;   // full path of what this side was connected to (bind map)

    function new(string name, fw_component parent, E imp = null);
        m_name   = name;
        m_parent = parent;
        imp_p  = new({name, ".i"}, parent);
        exp_x  = new({name, ".e"}, parent, imp);
        if (parent != null) begin
            parent.add_elaboratable(this);
            parent.remove_bindable(imp_p);
            parent.remove_bindable(exp_x);
            parent.add_bindable(this);
        end
    endfunction

    // --- fw_dbg_bindable ------------------------------------------------------
    virtual function string bind_name();      return m_name;                endfunction
    virtual function string bind_role();      return "socket";              endfunction
    virtual function bit    bind_connected(); return imp_p.is_connected();  endfunction
    virtual function bit    bind_resolved();  return t != null;             endfunction
    virtual function string bind_provider();  return m_peer;                endfunction

    function string get_name();
        return m_name;
    endfunction

    function string full_name();
        return (m_parent != null) ? {m_parent.get_full_name(), ".", m_name} : m_name;
    endfunction

    // Peer bind: one call wires both directions. Either side may initiate it;
    // fw_mirror::connect(s) is the same edge pair.
    function void connect(fw_mirror #(I, E) m);
        imp_p.connect(m.exp_x);     // I calls go to the mirror's I imp
        m.imp_p.connect(exp_x);     // E calls come back to this socket
        m_peer   = m.full_name();
        m.m_peer = full_name();
    endfunction

    // Hierarchical bind: expose this INNER socket as an OUTER socket of the
    // same type, held by an enclosing component. Port->port goes up; the
    // outer export forwards down to this one.
    function void connect_up(fw_socket #(I, E) outer);
        imp_p.connect(outer.imp_p);
        outer.exp_x.connect(exp_x);
        m_peer = {"^", outer.full_name()};
    endfunction

    // Replace the inbound imp after construction (for a component that builds
    // the socket before the object that implements E exists).
    function void set_imp(E imp);
        exp_x.set_imp(imp);
    endfunction

    // --- fw_elaboratable ------------------------------------------------------
    virtual function void do_build();
    endfunction

    // get_if() rather than reading imp_p.t: an unbound socket must fail here,
    // loudly and by name, not as a null dereference on first use.
    virtual function void do_connect();
        t = imp_p.get_if();
    endfunction
endclass

// A *mirror* is the other side of a socket's link: fw_mirror #(I, E) CALLS E
// and PROVIDES I. See fw_socket.
class fw_mirror #(type I = int, type E = int) implements fw_elaboratable, fw_dbg_bindable;
    E               t;       // outbound imp, resolved in do_connect()
    fw_port   #(E)  imp_p;
    fw_export #(I)  exp_x;

    protected string       m_name;
    protected fw_component m_parent;
    string                 m_peer;

    function new(string name, fw_component parent, I imp = null);
        m_name   = name;
        m_parent = parent;
        imp_p  = new({name, ".e"}, parent);
        exp_x  = new({name, ".i"}, parent, imp);
        if (parent != null) begin
            parent.add_elaboratable(this);
            parent.remove_bindable(imp_p);
            parent.remove_bindable(exp_x);
            parent.add_bindable(this);
        end
    endfunction

    virtual function string bind_name();      return m_name;                endfunction
    virtual function string bind_role();      return "mirror";              endfunction
    virtual function bit    bind_connected(); return imp_p.is_connected();  endfunction
    virtual function bit    bind_resolved();  return t != null;             endfunction
    virtual function string bind_provider();  return m_peer;                endfunction

    function string get_name();
        return m_name;
    endfunction

    function string full_name();
        return (m_parent != null) ? {m_parent.get_full_name(), ".", m_name} : m_name;
    endfunction

    function void connect(fw_socket #(I, E) s);
        s.connect(this);
    endfunction

    function void connect_up(fw_mirror #(I, E) outer);
        imp_p.connect(outer.imp_p);
        outer.exp_x.connect(exp_x);
        m_peer = {"^", outer.full_name()};
    endfunction

    function void set_imp(I imp);
        exp_x.set_imp(imp);
    endfunction

    virtual function void do_build();
    endfunction

    virtual function void do_connect();
        t = imp_p.get_if();
    endfunction
endclass
