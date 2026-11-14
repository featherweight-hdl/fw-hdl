// One end of a struct-port connection, untyped: the views (fw_rv_sp_out,
// fw_rv_sp_in) extend it. An end belongs to a component, which lists it
// (fw_component.add_sync_port) for the connection check and for freeze().
//
// role says which fields this end drives: FWD for the producer (out view),
// BWD for the consumer (in view); it reads the others. An end joined to an
// inner end of the same role by connect_up() is a pass-through: it drives
// and reads nothing itself, the inner end does.
virtual class fw_sync_port;
    string        name;
    fw_component  owner;     // null: not listed anywhere (a bare test view)
    fw_sync_dir_e role;
    fw_sync_net   net;
    bit           through;   // set on the outer end by connect_up()
    bit           optional;  // an undriven input is not an error

    function new(string name, fw_component owner, fw_sync_dir_e role,
                 fw_sig_holder h);
        this.name  = name;
        this.owner = owner;
        this.role  = role;
        net = new(h);
        net.ends.push_back(this);
        if (owner != null) owner.add_sync_port(this);
    endfunction

    function string full_name();
        return (owner != null) ? {owner.get_full_name(), ".", name} : name;
    endfunction

    function fw_sig_holder holder();
        return net.holder;
    endfunction

    // Inputs of this end may stay undriven (fw-hdl ports are mandatory by
    // default).
    function void set_optional();
        optional = 1;
    endfunction

    function bit drives(fw_sync_field f);
        return !through && f.dir == role;
    endfunction

    function bit reads(fw_sync_field f);
        return !through && f.dir != role;
    endfunction

    // Called by fw_sync_net.merge(): this end now shares net n's holder. The
    // view sets its typed handle.
    function void m_rebind(fw_sync_net n);
        net = n;
        m_set_holder(n.holder);
    endfunction

    pure virtual protected function void m_set_holder(fw_sig_holder h);

    // Join a peer end (the typed connect() of the view calls this).
    protected function void m_connect(fw_sync_port peer);
        net.merge(peer.net);
    endfunction

    // Join the end `outer` of the parent component, which becomes a
    // pass-through for this end. Fatal unless outer's owner is this end's
    // owner's parent (both may be null in a bare test).
    protected function void m_connect_up(fw_sync_port outer);
        string err;
        if (check_connect_up(outer, err)) begin
            $fatal(1, "fw-hdl: %s: connect_up(%s): %s", full_name(),
                   outer.full_name(), err);
        end
        outer.through = 1;
        net.merge(outer.net);
    endfunction

    function bit check_connect_up(fw_sync_port outer, output string err);
        err = "";
        if (owner != null && outer.owner != null
                && owner.get_parent() != outer.owner) begin
            err = $sformatf("%s is not a port of %s's parent",
                            outer.full_name(), owner.get_full_name());
            return 1;
        end
        return 0;
    endfunction
endclass
