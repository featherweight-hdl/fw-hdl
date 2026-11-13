// The DOMAIN CROSSING check (docs/reference/clocking.md, "Crossings"): one walk
// over the bound endpoints after connect, in simulation.
//
// For each domain kind:
//   * binding    -- a caller-end port and the export it resolves to are in
//                   domains that are not SAME;
//   * component  -- a component that is not a crossing element for the kind
//                   (is_crossing()) has a data endpoint associated with a
//                   domain other than its own;
//   * reset-sync -- a component's reset domain deasserts on no clock, or on one
//                   UNRELATED to the component's clock.
// Not crossings: ambient endpoints (clock, reset, dbg, domain plumbing), an
// unbound component reset (never in reset), and anything inside a declared
// crossing element.
//
// Severity (overridable with +fw_crossings_sev=<kind>:<rel>:<sev>[,...]):
//   clock related info, clock unrelated error, reset related warn, reset
//   unrelated error, reset-sync error, anything waived info.
class fw_crossing_check;

    // Severity overrides, "<kind>:<rel>" -> sev, from the plusarg.
    static fw_crossing_sev_e m_sev_ovr[string];
    static bit               m_sev_read;

    // Find every crossing under root into `found`; return the error count.
    static function int run(fw_component root, ref fw_crossing found[$]);
        fw_component comps[$];
        fw_endpoint  eps[$];
        bit          fwd[string];
        int          nerr = 0;

        read_sev_overrides();
        collect(root, comps);

        // 1. every non-ambient endpoint, and 2. the forwarders: endpoints some
        //    port's ep_next() is (a structural parent's outer port is not a
        //    caller end).
        foreach (comps[i]) begin
            for (int j = 0; j < comps[i].num_endpoints(); j++) begin
                fw_endpoint e = comps[i].get_endpoint(j);
                if (e.m_ambient) continue;
                eps.push_back(e);
            end
        end
        foreach (eps[i]) begin
            fw_endpoint n;
            if (!eps[i].ep_is_port()) continue;
            n = eps[i].ep_next();
            if (n != null) fwd[n.ep_full_name()] = 1'b1;
        end

        // 3. bindings
        foreach (eps[i]) begin
            fw_endpoint p = eps[i];
            fw_endpoint t;
            if (!p.ep_is_port() || fwd.exists(p.ep_full_name())) continue;
            t = terminal(p);
            if (t == null) continue;                  // unresolved: the bind map says so
            for (int k = 0; k < 2; k++) begin
                fw_domain_kind_e kk = fw_domain_kind_e'(k);
                if (inside_same_element(p.ep_owner(), t.ep_owner(), kk)) continue;
                check_pair(found, "binding", kk, p, p.ep_full_name(), p.ep_domain(kk),
                           t.ep_full_name(), t.ep_domain(kk), p.ep_owner(),
                           p.m_dom.exists(kk), t.m_dom.exists(kk));
            end
        end

        // 4. components: an endpoint associated with another domain
        foreach (comps[i]) begin
            fw_component c = comps[i];
            for (int k = 0; k < 2; k++) begin
                fw_domain_kind_e kk = fw_domain_kind_e'(k);
                if (c.is_crossing(kk)) continue;
                for (int j = 0; j < c.num_endpoints(); j++) begin
                    fw_endpoint e = c.get_endpoint(j);
                    if (e.m_ambient || !e.m_dom.exists(kk)) continue;
                    check_pair(found, "component", kk, e, e.ep_full_name(), e.ep_domain(kk),
                               c.get_full_name(), c.domain(kk), c, 1'b1, 1'b0);
                end
            end
        end

        // 5. reset-sync: where a (clock, reset) pair first appears
        foreach (comps[i]) begin
            check_reset_sync(found, comps[i]);
        end

        foreach (found[i]) begin
            if (found[i].sev == FW_XSEV_ERROR) nerr++;
        end
        return nerr;
    endfunction

    // The whole tree, parents first.
    static function void collect(fw_component c, ref fw_component out[$]);
        fw_component kids[$];
        out.push_back(c);
        c.get_children(kids);
        foreach (kids[i]) collect(kids[i], out);
    endfunction

    // Follow a port to the export holding the imp; null when unresolved.
    static function fw_endpoint terminal(fw_endpoint p);
        fw_endpoint e = p;
        int         guard = 0;
        while (e != null && guard < 10000) begin
            if (!e.ep_is_port() && e.ep_is_terminal()) return e;
            e = e.ep_next();
            guard++;
        end
        return null;
    endfunction

    // The nearest crossing element for k at or above c, or null.
    static function fw_component element_of(fw_component c, fw_domain_kind_e k);
        while (c != null) begin
            if (c.is_crossing(k)) return c;
            c = c.get_parent();
        end
        return null;
    endfunction

    // Both ends inside one crossing element: its business, not a crossing.
    static function bit inside_same_element(fw_component a, fw_component b, fw_domain_kind_e k);
        fw_component ea = element_of(a, k);
        return ea != null && ea == element_of(b, k);
    endfunction

    static function void check_pair(ref fw_crossing found[$], input string via,
                                    fw_domain_kind_e k, fw_endpoint from_ep,
                                    string from, fw_domain_ref fd,
                                    string to, fw_domain_ref td, fw_component owner,
                                    bit from_explicit, bit to_explicit);
        fw_domain_if    a, b;
        fw_domain_rel_e rel;
        fw_crossing     x;
        string          w;
        a = (fd != null) ? fd.ref_domain() : null;
        b = (td != null) ? td.ref_domain() : null;
        // An endpoint explicitly associated with an unbound domain port.
        if ((from_explicit && a == null) || (to_explicit && b == null)) begin
            x = new();
            x.kind = k; x.rel = FW_DOMAIN_UNRELATED; x.sev = FW_XSEV_ERROR; x.via = via;
            x.from = from; x.to = to; x.owner = owner;
            x.from_dom = (a != null) ? a.domain_name() : {"<unbound ", (fd != null) ? fd.ref_name() : "?", ">"};
            x.to_dom   = (b != null) ? b.domain_name() : {"<unbound ", (td != null) ? td.ref_name() : "?", ">"};
            x.note = "an endpoint is associated with an unbound domain port";
            found.push_back(x);
            return;
        end
        // An unbound component reset is "never in reset" (and an unbound
        // clock is a connect-time error of its own): not a crossing.
        if (a == null || b == null) return;
        rel = fw_domains::relate(a, b);
        if (rel == FW_DOMAIN_SAME) return;
        x = new();
        x.kind = k; x.rel = rel; x.via = via;
        x.from = from; x.from_dom = a.domain_name();
        x.to = to;     x.to_dom   = b.domain_name();
        x.owner = owner;
        w = (owner != null) ? owner.crossing_waiver(from_ep.ep_name(), k) : "";
        x.waiver = w;
        x.sev    = (w != "") ? FW_XSEV_INFO : severity(k, rel);
        if (k == FW_DOMAIN_RESET)
            x.note = "a reset on one side kills run() processes, and the calls they have in flight, across it";
        else if (rel == FW_DOMAIN_UNRELATED)
            x.note = "needs a synchronizer or an async FIFO (a crossing element)";
        found.push_back(x);
    endfunction

    static function void check_reset_sync(ref fw_crossing found[$], input fw_component c);
        fw_component        p;
        fw_domain_if        rd, cd, sc_d;
        fw_reset_domain_if  r;
        fw_clock_domain_if  sc;
        fw_domain_rel_e     rel;
        fw_crossing         x;
        if (!c.reset.is_connected() || !c.clock.is_connected()) return;
        rd = c.reset.ref_domain();
        cd = c.clock.ref_domain();
        p  = c.get_parent();
        // Report where the pair first appears, not again for every descendant.
        if (p != null && p.reset.is_connected() && p.clock.is_connected()
                && p.reset.ref_domain() == rd && p.clock.ref_domain() == cd) return;
        r  = c.reset.get_if();
        sc = r.sync_clock();
        if (sc == null) begin
            rel = FW_DOMAIN_UNRELATED;
        end else begin
            sc_d = sc;
            rel  = fw_domains::relate(sc_d, cd);
        end
        if (rel != FW_DOMAIN_UNRELATED) return;
        x = new();
        x.kind = FW_DOMAIN_RESET; x.rel = rel; x.via = "reset-sync";
        x.from = c.get_full_name(); x.from_dom = rd.domain_name();
        x.to   = c.get_full_name(); x.to_dom   = cd.domain_name();
        x.owner = c;
        x.waiver = c.crossing_waiver("reset", FW_DOMAIN_RESET);
        x.sev    = (x.waiver != "") ? FW_XSEV_INFO : sev_lookup("reset-sync", FW_XSEV_ERROR);
        x.note   = (sc == null)
            ? "the reset deasserts on no clock (its sources' clocks differ); put a synchronized reset domain after it"
            : "the reset deasserts on a clock unrelated to the component's";
        found.push_back(x);
    endfunction

    static function fw_crossing_sev_e severity(fw_domain_kind_e k, fw_domain_rel_e r);
        fw_crossing_sev_e d;
        if (k == FW_DOMAIN_CLOCK) d = (r == FW_DOMAIN_RELATED) ? FW_XSEV_INFO : FW_XSEV_ERROR;
        else                      d = (r == FW_DOMAIN_RELATED) ? FW_XSEV_WARN : FW_XSEV_ERROR;
        return sev_lookup({fw_domains::kind_name(k), ":", fw_domains::rel_name(r)}, d);
    endfunction

    static function fw_crossing_sev_e sev_lookup(string key, fw_crossing_sev_e d);
        if (m_sev_ovr.exists(key)) return m_sev_ovr[key];
        return d;
    endfunction

    // +fw_crossings_sev=reset:related:error[,clock:related:warn ...]
    static function void read_sev_overrides();
        string s, item;
        if (m_sev_read) return;
        m_sev_read = 1'b1;
        if (!$value$plusargs("fw_crossings_sev=%s", s)) return;
        s = {s, ","};
        item = "";
        for (int i = 0; i < s.len(); i++) begin
            if (s[i] == ",") begin
                add_override(item);
                item = "";
            end else begin
                item = {item, string'(s[i])};
            end
        end
    endfunction

    static function void add_override(string item);
        int    last = -1;
        string key, sv;
        for (int i = 0; i < item.len(); i++) if (item[i] == ":") last = i;
        if (last <= 0) return;
        key = item.substr(0, last - 1);
        sv  = item.substr(last + 1, item.len() - 1);
        if (key == "reset:sync") key = "reset-sync";
        case (sv)
            "info":  m_sev_ovr[key] = FW_XSEV_INFO;
            "warn":  m_sev_ovr[key] = FW_XSEV_WARN;
            "error": m_sev_ovr[key] = FW_XSEV_ERROR;
            default: $display("fw-hdl: +fw_crossings_sev: unknown severity '%s' in '%s'", sv, item);
        endcase
    endfunction

    // ----------------------------------------------------------------------
    // The check as run by fw_component_root::start(), after connect. Plusargs:
    //   +fw_crossings_off            skip the check
    //   +fw_crossings_show           also print info rows
    //   +fw_crossings[=<path>]       write JSON (default fw_crossings.json)
    //   +fw_crossings_nofatal        errors do not stop the run
    // Prints every crossing of severity warn and above; $fatal after printing
    // them all if there is an error.
    // ----------------------------------------------------------------------
    static function void check_root(fw_component root);
        fw_crossing found[$];
        int         nerr;
        bit         show;
        string      path;
        if ($test$plusargs("fw_crossings_off")) return;
        nerr = run(root, found);
        show = $test$plusargs("fw_crossings_show");
        foreach (found[i]) begin
            fw_crossing x = found[i];
            fw_dbg_listener_if d = (x.owner != null) ? x.owner.dbg_if() : null;
            if (x.sev == FW_XSEV_ERROR) begin
                `fw_error_begin(d, "fw_crossing.error")
                `fw_ev_end
            end else if (x.sev == FW_XSEV_WARN) begin
                `fw_warn_begin(d, "fw_crossing.warn")
                `fw_ev_end
            end
            if (x.sev != FW_XSEV_INFO || show) $display("%s", x.line());
        end
        if ($value$plusargs("fw_crossings=%s", path)) begin
            // explicit path
        end else if ($test$plusargs("fw_crossings")) begin
            path = "fw_crossings.json";
        end else begin
            path = "";
        end
        if (path != "") write_json(root, found, path);
        if (nerr != 0 && !$test$plusargs("fw_crossings_nofatal")) begin
            $fatal(1, "fw-hdl: %0d domain crossing error(s) under '%s' (+fw_crossings_nofatal to continue)",
                   nerr, root.get_full_name());
        end
    endfunction

    static function string json(fw_component root, ref fw_crossing found[$]);
        string items = "";
        foreach (found[i]) items = {items, (i == 0) ? "\n    " : ",\n    ", found[i].json()};
        return $sformatf("{\"crossings\":{\"root\":\"%s\",\"items\":[%s\n  ]}}",
                         root.get_full_name(), items);
    endfunction

    static function void write_json(fw_component root, ref fw_crossing found[$], string path);
        int fh = $fopen(path, "w");
        if (fh == 0) begin
            $display("fw-hdl: could not open crossings file '%s' for writing", path);
            return;
        end
        $fdisplay(fh, "%s", json(root, found));
        $fclose(fh);
        $display("fw-hdl: crossings written to '%s'", path);
    endfunction
endclass
