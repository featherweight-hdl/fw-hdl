// One DOMAIN CROSSING found by fw_crossing_check: logic that works with two
// different domains of one kind (docs/reference/clocking.md, "Crossings").
//
//   via "binding"    -- a port and the export it resolves to are in different
//                       domains (from = the port, to = the export);
//   via "component"  -- a component that is not a crossing element has an
//                       endpoint associated with another domain (from = the
//                       endpoint, to = the component);
//   via "reset-sync" -- a component's reset deasserts on no clock, or on one
//                       unrelated to the component's (from = the component's
//                       reset domain, to = its clock domain).
typedef enum { FW_XSEV_INFO, FW_XSEV_WARN, FW_XSEV_ERROR } fw_crossing_sev_e;

class fw_crossing;
    fw_domain_kind_e  kind;
    fw_domain_rel_e   rel;
    fw_crossing_sev_e sev;
    string            via;
    string            from;
    string            from_dom;
    string            to;
    string            to_dom;
    string            waiver;     // the reason, when waived
    string            note;       // what it means (reset crossings)
    fw_component      owner;      // whose dbg context reports it

    static function string sev_name(fw_crossing_sev_e s);
        case (s)
            FW_XSEV_INFO:  return "info";
            FW_XSEV_WARN:  return "warn";
            FW_XSEV_ERROR: return "error";
            default:       return "?";
        endcase
    endfunction

    // The text line:
    //   fw-hdl crossing [error] clock unrelated binding: top.a.out (top.clk_b2) -> top.b.in_ex (top.clock)
    function string line();
        string s;
        string sv = sev_name(sev);
        while (sv.len() < 5) sv = {sv, " "};
        s = $sformatf("fw-hdl crossing [%s] %s %s %s: %s (%s) -> %s (%s)", sv,
                      fw_domains::kind_name(kind), fw_domains::rel_name(rel), via,
                      from, from_dom, to, to_dom);
        if (waiver != "") s = {s, " waived: ", waiver};
        else if (note != "") s = {s, ": ", note};
        return s;
    endfunction

    function string json();
        return $sformatf({"{\"kind\":\"%s\",\"relation\":\"%s\",\"severity\":\"%s\",",
                          "\"via\":\"%s\",\"from\":\"%s\",\"from_domain\":\"%s\",",
                          "\"to\":\"%s\",\"to_domain\":\"%s\",\"waiver\":\"%s\"}"},
                         fw_domains::kind_name(kind), fw_domains::rel_name(rel),
                         sev_name(sev), via, from, from_dom, to, to_dom, waiver);
    endfunction
endclass
