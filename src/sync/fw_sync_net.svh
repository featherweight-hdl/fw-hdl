typedef class fw_sync_port;

// One connection of struct-port ends (design-sync-rtl §3.2, "Connection"):
// the value holder they all share and the ends themselves. connect() merges
// two nets into one; check() applies the driver rules to it.
class fw_sync_net;
    fw_sig_holder holder;
    fw_sync_port  ends[$];

    function new(fw_sig_holder holder);
        this.holder = holder;
    endfunction

    // Take over the ends of net `o`, which then share this net's holder. The
    // per-field semantics (set_comb, in build()) and the reset domain set on
    // either holder carry over.
    function void merge(fw_sync_net o);
        if (o == this) return;
        foreach (holder.fields[i]) begin
            if (o.holder.fields[i].comb) holder.fields[i].comb = 1;
        end
        if (holder.rst == null) holder.rst = o.holder.rst;
        foreach (o.ends[i]) begin
            o.ends[i].m_rebind(this);
            ends.push_back(o.ends[i]);
        end
        o.ends.delete();
    endfunction

    // Take holder h in place of this net's own; every end rebinds to it
    // (fw_sync_bridge: h is a channel of a port that is not a view). The comb
    // declarations and reset domain of the old holder carry over, as in
    // merge(). Fatal if h has other fields.
    function void adopt(fw_sig_holder h);
        if (h == holder) return;
        if (h.fields.size() != holder.fields.size())
            $fatal(1, "fw-hdl: holder \"%s\" cannot take the ends of \"%s\": other fields",
                   h.name, holder.name);
        foreach (holder.fields[i]) begin
            if (h.fields[i].name != holder.fields[i].name)
                $fatal(1, "fw-hdl: holder \"%s\" cannot take the ends of \"%s\": field \"%s\" is \"%s\"",
                       h.name, holder.name, holder.fields[i].name, h.fields[i].name);
            if (holder.fields[i].comb) h.fields[i].comb = 1;
        end
        if (h.rst == null) h.rst = holder.rst;
        holder = h;
        foreach (ends[i]) ends[i].m_rebind(this);
    endfunction

    // The driver rules, after connect (design-sync-rtl §3.1, "Rules"): each
    // field has at most one driving end, and an input field read by an end
    // that is not optional has one. Returns 1 and sets err on an error.
    function bit check(output string err);
        err = "";
        foreach (holder.fields[k]) begin
            fw_sync_field f   = holder.fields[k];
            fw_sync_port  drv = null;
            foreach (ends[i]) begin
                if (!ends[i].drives(f)) continue;
                if (drv != null) begin
                    err = $sformatf("field \"%s\" of \"%s\" has two drivers: %s and %s",
                                    f.name, holder.name, drv.full_name(),
                                    ends[i].full_name());
                    return 1;
                end
                drv = ends[i];
            end
            if (drv != null) continue;
            foreach (ends[i]) begin
                if (ends[i].reads(f) && !ends[i].optional) begin
                    err = $sformatf("%s: input field \"%s\" is not driven (connect it, or set_optional())",
                                    ends[i].full_name(), f.name);
                    return 1;
                end
            end
        end
        return 0;
    endfunction
endclass
