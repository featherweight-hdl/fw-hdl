// The connection check over a component tree (design-sync-rtl §3.1,
// "Rules"): every net of every listed struct-port end has one driver per
// field, and no undriven input that is not optional. Run it after connect().
class fw_sync_conn;
    // The nets reached from the ends of `top` and its descendants, each once.
    static function void nets(fw_component top, ref fw_sync_net ns[$]);
        fw_sync_port ps[$];
        fw_component kids[$];
        top.get_sync_ports(ps);
        foreach (ps[i]) begin
            bit seen = 0;
            foreach (ns[j]) if (ns[j] == ps[i].net) seen = 1;
            if (!seen) ns.push_back(ps[i].net);
        end
        top.get_children(kids);
        foreach (kids[i]) nets(kids[i], ns);
    endfunction

    // Returns 1 and the first error in err.
    static function bit check_tree(fw_component top, output string err);
        fw_sync_net ns[$];
        err = "";
        nets(top, ns);
        foreach (ns[i]) if (ns[i].check(err)) return 1;
        return 0;
    endfunction

    static function void check(fw_component top);
        string err;
        if (check_tree(top, err)) begin
            $fatal(1, "fw-hdl: %s: %s", top.get_full_name(), err);
        end
    endfunction
endclass
