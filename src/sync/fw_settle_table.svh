// The settle table of one component class (design-sync-rtl §4.6.1): the
// struct-port fields its comb() and step() read and write, as "<port>.<field>"
// (port: the member name; field: the holder's add_field() name). The settle
// weaver (fw-hdl python/fw/hdl/weave/settle.py) derives the tables from the
// bodies and registers one per class from <pkg>_woven, keyed by the class
// name (the generic name for a parameterized class). Which of the fields are
// comb is known only at run time (set_comb()), so the tables list all port
// fields; the scheduler keeps the comb ones. An instance finds its table by
// the matchers (one per specialization the weaver saw) with find_for().
// deps_known: the comb_dep() pairs (write, read) are each comb write's
// dependences (the fields its statement reads); else every comb write
// depends on every comb read.
class fw_settle_table;
    string cls;
    string comb_reads[$], comb_writes[$];
    string step_reads[$], step_writes[$];
    bit    deps_known;
    string comb_dep_w[$], comb_dep_r[$];
    fw_settle_match matchers[$];

    static fw_settle_table m_tables[string];

    function new(string cls);
        this.cls = cls;
    endfunction

    function void comb_dep(string w, string r);
        comb_dep_w.push_back(w);
        comb_dep_r.push_back(r);
    endfunction

    static function void add(fw_settle_table t);
        m_tables[t.cls] = t;
    endfunction

    static function fw_settle_table find(string cls);
        return m_tables.exists(cls) ? m_tables[cls] : null;
    endfunction

    // The table of comb() object c's class: of the tables with a matcher
    // that takes c, the one matched deepest. null: none (c's class was not
    // woven, or not specialized in the woven sources).
    static function fw_settle_table find_for(fw_combinational c);
        fw_settle_table best = null;
        int unsigned    bd   = 0;
        foreach (m_tables[k]) begin
            fw_settle_table t = m_tables[k];
            foreach (t.matchers[i]) begin
                if ((best == null || t.matchers[i].depth > bd) && t.matchers[i].test(c)) begin
                    best = t;
                    bd   = t.matchers[i].depth;
                end
            end
        end
        return best;
    endfunction
endclass
