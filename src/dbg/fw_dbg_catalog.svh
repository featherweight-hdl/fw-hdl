
// The static site catalog: every instrumentation site in the compiled image,
// registered exactly once, before time 0.
//
// --- The registration idiom (chosen deliberately; the C lowering needs the same
// --- shape, a `static const` descriptor) ---------------------------------------
//
//     static int unsigned SID = fw_dbg_catalog::register_site(
//                                   "arb", FW_DBG_DECISION, FW_L_OP);
//
// A function/block-scope `static` with an initializer is elaborated ONCE, before
// time 0, in declaration order -- verified on Verilator 5.049 for both function
// and class-method scope, and for a `begin` block inside a task. Three
// consequences, all of them wanted:
//
//   1. **Zero per-hit cost.** The id is a plain load at the site; there is no
//      "have I registered yet?" test in front of the enable gate. A sentinel
//      (`sid < 0 ? register() : sid`) would have cost one extra branch on every
//      evaluation of every disabled site.
//   2. **The catalog is COMPLETE at time 0** -- including sites that are never
//      executed. That is the correct semantics for a *static* catalog and it is
//      what makes §9's elaboration-time artifact meaningful: it describes the
//      image, not the run.
//   3. **Per-specialization ids** in a parameterized class. `fw_reg #(T)` gets
//      one site per T, which is what you want (the field schema differs).
//
// The catalog is static-only (no singleton handle) so a site initializer cannot
// race a lazily-constructed instance during pre-time-0 elaboration.
class fw_dbg_catalog;
    protected static fw_dbg_site m_sites[$];

    // Register one site and return its id. Ids start at 1; 0 is FW_DBG_NO_SITE,
    // so a default-constructed record is recognizably empty.
    static function int unsigned register_site(
            string         name,
            fw_dbg_kind_e  kind,
            fw_dbg_level_e level,
            string         file = "",
            int            line = 0);
        fw_dbg_site s;
        int unsigned id = m_sites.size() + 1;
        s = new(id, name, kind, level, file, line);
        m_sites.push_back(s);
        return id;
    endfunction

    static function int unsigned num_sites();
        return m_sites.size();
    endfunction

    // Resolve an id to its descriptor. Returns null for FW_DBG_NO_SITE or an
    // out-of-range id, so callers can render "<unknown site>" instead of dying.
    static function fw_dbg_site site(int unsigned id);
        if (id == FW_DBG_NO_SITE || id > m_sites.size()) begin
            return null;
        end
        return m_sites[id-1];
    endfunction

    // First site with this name, or null. For tests and interactive use only --
    // never on an emit path (that is what ids are for).
    static function fw_dbg_site find(string name);
        foreach (m_sites[i]) begin
            if (m_sites[i].name() == name) begin
                return m_sites[i];
            end
        end
        return null;
    endfunction

    // The catalog as a consumer sees it: identity, kind, level, and the FIELD
    // SCHEMA WITH TYPES. The schema half is the part that matters -- payload
    // values travel as `longint`, so without a declared width and signedness a
    // decoder cannot tell -1 from 0xff from 0xffffffff. Strings appear here and
    // only here, off every emit path, which is the whole arrangement: names and
    // types are elaboration-time facts, records are numbers.
    static function void dump();
        $display("fw_dbg_catalog: %0d site(s)", m_sites.size());
        foreach (m_sites[i]) begin
            string sch = m_sites[i].schema_str();
            $display("  %s%s", m_sites[i].to_str(),
                     (sch != "") ? {"  {", sch, "}"} : "");
        end
    endfunction

    // ----------------------------------------------------------------------
    // Emitters that will never emit.
    //
    // A register block built outside elaboration, with no owner passed and no
    // ambient component to adopt, has sites in this catalog and no context to
    // send them to. It is not an error -- a model with no debug wired at all is
    // legitimate -- but it IS the difference between "this subsystem is quiet"
    // and "this subsystem cannot speak", and nothing else can tell you which.
    //
    // Recorded here rather than in fw_reg_block because the catalog is
    // unparameterized: one list spans every register width.
    // ----------------------------------------------------------------------
    protected static string m_uncontexted[$];

    static function void note_uncontexted(string name);
        m_uncontexted.push_back(name);
    endfunction

    // Retract a note: the object turned out not to be a root after all (a block
    // constructed standalone and then nested into a map). Reporting it would be
    // a false alarm, and false alarms are how a diagnostic gets ignored.
    static function void clear_uncontexted(string name);
        foreach (m_uncontexted[i]) begin
            if (m_uncontexted[i] == name) begin
                m_uncontexted.delete(i);
                return;
            end
        end
    endfunction

    static function int    num_uncontexted();  return m_uncontexted.size(); endfunction
    static function string uncontexted(int i);
        return (i >= 0 && i < m_uncontexted.size()) ? m_uncontexted[i] : "";
    endfunction
endclass
