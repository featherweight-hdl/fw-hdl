// Relations between domains of one kind.
//
//   SAME      -- a.domain_equiv() == b.domain_equiv();
//   RELATED   -- their root sets (sources followed to domain_nsrc() == 0)
//                intersect: for clocks, both divide one root clock (rational,
//                shared edges); for resets, one is built from the other, or
//                both from a common one;
//   UNRELATED -- otherwise.
//
// A null domain (an unbound domain port) is SAME only as another null, and
// UNRELATED to anything else.
class fw_domains;

    static function fw_domain_rel_e relate(fw_domain_if a, fw_domain_if b);
        fw_domain_if ra[$];
        fw_domain_if rb[$];
        if (a == null || b == null) begin
            return (a == b) ? FW_DOMAIN_SAME : FW_DOMAIN_UNRELATED;
        end
        if (a.domain_equiv() == b.domain_equiv()) return FW_DOMAIN_SAME;
        roots(a, ra);
        roots(b, rb);
        foreach (ra[i]) begin
            foreach (rb[j]) begin
                if (ra[i] == rb[j]) return FW_DOMAIN_RELATED;
            end
        end
        return FW_DOMAIN_UNRELATED;
    endfunction

    // The root domains d is built from (d itself when it is a root). Each root
    // appears once.
    static function void roots(fw_domain_if d, ref fw_domain_if out[$]);
        int n;
        if (d == null) return;
        n = d.domain_nsrc();
        if (n == 0) begin
            foreach (out[i]) begin
                if (out[i] == d) return;
            end
            out.push_back(d);
            return;
        end
        for (int i = 0; i < n; i++) begin
            roots(d.domain_src(i), out);
        end
    endfunction

    static function string kind_name(fw_domain_kind_e k);
        case (k)
            FW_DOMAIN_CLOCK: return "clock";
            FW_DOMAIN_RESET: return "reset";
            default:         return "?";
        endcase
    endfunction

    static function string rel_name(fw_domain_rel_e r);
        case (r)
            FW_DOMAIN_SAME:      return "same";
            FW_DOMAIN_RELATED:   return "related";
            FW_DOMAIN_UNRELATED: return "unrelated";
            default:             return "?";
        endcase
    endfunction

endclass
