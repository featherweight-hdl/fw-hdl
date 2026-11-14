// An end (view) of a component bound to a value holder that another object
// owns and may replace until connect is over, such as a channel of an
// fw_proto role port (fw_sp_base::bind_view; link() swaps its holders). The
// subclass says where the holder is now (target()). The bridge is listed on
// the view's owner; fw_sync_kernel::elaborate() resolves the tree's bridges
// after connect, before the connection check: the view's net adopts the
// holder (fw_sync_net::adopt), and views bridged to one holder share a net,
// so the driver check sees all of them. The holder may also be written by
// code that is no view (a role port's owner), so a bridged view is optional.
virtual class fw_sync_bridge;
    fw_sync_port view;

    function new(fw_sync_port view);
        this.view = view;
        if (view.owner == null)
            $fatal(1, "fw-hdl: fw_sync_bridge: end %s has no owner", view.name);
        view.owner.add_sync_bridge(this);
    endfunction

    // The holder the view joins, as it is after connect.
    pure virtual function fw_sig_holder target();

    static function void resolve_tree(fw_component top);
        fw_sig_holder hs[$];
        fw_sync_net   ns[$];
        m_resolve(top, hs, ns);
    endfunction

    protected static function void m_resolve(fw_component c, ref fw_sig_holder hs[$],
                                             ref fw_sync_net ns[$]);
        fw_sync_bridge bs[$];
        fw_component   kids[$];
        c.get_sync_bridges(bs);
        foreach (bs[i]) begin
            fw_sig_holder h = bs[i].target();
            fw_sync_port  v = bs[i].view;
            int k = -1;
            if (h == null)
                $fatal(1, "fw-hdl: %s: the bridged holder is null", v.full_name());
            foreach (hs[j]) if (hs[j] == h) k = j;
            if (k < 0) begin
                v.net.adopt(h);
                hs.push_back(h);
                ns.push_back(v.net);
            end else begin
                ns[k].merge(v.net);
            end
            v.optional = 1;
        end
        c.get_children(kids);
        foreach (kids[i]) m_resolve(kids[i], hs, ns);
    endfunction
endclass
