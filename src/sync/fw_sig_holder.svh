// The value holder shared by the two ends of a struct-port connection
// (design-sync-rtl §3.2, "Connection"). A sync field keeps a current and a
// next value: the driver writes `nxt`, everyone reads `cur`, and commit() at
// the edge copies `nxt` to `cur` (`nxt` keeps its value, so an unwritten
// field holds like a register). A comb field keeps one value, written and
// read at once. Subclasses hold the typed values; this base keeps the field
// table and the reset domain that reset-force reads.
//
// Task code (phase RUN) touches a field as a crossing port (fw-hdl-spec
// semantics/processes.md, "Crossings"; sync-task-domains.md §6.6). At an
// edge of the holder's domain (m_at_edge), a read returns the value from
// before the edge (`pre`, saved by commit()); between edges, `cur`. A write
// takes effect at once, in `cur` and `nxt`, and the domain settles: at an
// edge that is after the update, so it overrides a step()'s write there
// (the default) and the step()s read it from the next edge. A second task
// write sampled by the same edge is FW-E-XING-DRIVE-TWICE, and is ignored,
// unless the same thread makes it in the same time step and it restores the
// value from before the first: then it undoes that write (the call's writes
// settle, as comb logic would, to no change).
typedef class fw_sync_kernel;
typedef class fw_sync_dom;
virtual class fw_sig_holder;
    string             name;
    fw_sync_field      fields[$];
    fw_reset_domain_if rst;    // null: never in reset
    bit                frozen; // set by freeze(); set_comb is then fatal
    fw_sync_kernel     kernel;      // set by the kernel's elaborate()
    fw_sync_dom        dom;         // ...with the domain this holder is in

    // Kernel bookkeeping, shared by every holder. The kernel sets `phase`;
    // comb_changes counts comb writes that changed a value (settle stops
    // after a pass that adds none). A broken write rule is fatal, or, with
    // fatal_on_rule = 0 (tests), counted in rule_errs with the last message
    // in rule_err.
    static fw_sync_phase_e phase = FW_SYNC_PH_NONE;
    static int unsigned    comb_changes;
    static bit             fatal_on_rule = 1;
    static int unsigned    rule_errs;
    static string          rule_err;
    // Bumped by every write, settle and edge: a pin bridge waits on it to
    // redrive its pins (fw_rv_pin_in/fw_rv_pin_out).
    static int unsigned    gen;

    function new(string name);
        this.name = name;
    endfunction

    function fw_sync_field add_field(string fname, int width,
                                     fw_sync_dir_e dir = FW_SYNC_FWD);
        fw_sync_field f = new(fname, width, dir);
        fields.push_back(f);
        return f;
    endfunction

    function fw_sync_field field(string fname);
        foreach (fields[i]) if (fields[i].name == fname) return fields[i];
        return null;
    endfunction

    // Make fields comb (design-sync-rtl §3.2, "Per-field semantics"). spec is
    // a comma list; each item is `f`, `*` (every field), or the same prefixed
    // with this holder's name (`ch.f`, `ch.*`). A port that owns several
    // channels resolves the prefix to the channel's holder (S2.6). Call it in
    // build(); after freeze() it is a fatal error, as is an unknown field.
    function void set_comb(string spec);
        string err;
        if (check_comb(spec, err)) begin
            $fatal(1, "fw-hdl: %s: set_comb(\"%s\"): %s", name, spec, err);
        end
        foreach (fields[i]) begin
            if (m_spec_has(spec, fields[i].name)) fields[i].comb = 1;
        end
    endfunction

    // The checks of set_comb, without the fatal: returns 1 and sets err
    // on an error. set_comb calls it; tests call it directly.
    function bit check_comb(string spec, output string err);
        string items[$];
        err = "";
        if (frozen) begin
            err = "the field semantics are frozen (set_comb belongs in build())";
            return 1;
        end
        m_split(spec, items);
        if (items.size() == 0) begin
            err = "empty field list";
            return 1;
        end
        foreach (items[i]) begin
            string f = m_unprefix(items[i]);
            if (f == "") begin
                err = $sformatf("\"%s\" names another channel, not \"%s\"",
                                items[i], name);
                return 1;
            end
            if (f != "*" && field(f) == null) begin
                err = $sformatf("no field \"%s\" in holder \"%s\"", f, name);
                return 1;
            end
        end
        return 0;
    endfunction

    // End of build(): the field semantics may not change after this.
    function void freeze();
        frozen = 1;
    endfunction

    // Split a comma list into trimmed, non-empty items.
    protected function void m_split(string spec, ref string items[$]);
        string cur = "";
        for (int i = 0; i <= spec.len(); i++) begin
            if (i == spec.len() || spec[i] == ",") begin
                if (cur != "") items.push_back(cur);
                cur = "";
            end else if (spec[i] != " " && spec[i] != "\t") begin
                cur = {cur, string'(spec[i])};
            end
        end
    endfunction

    // Strip a `<name>.` prefix; "" if the prefix names another holder.
    protected function string m_unprefix(string item);
        for (int i = 0; i < item.len(); i++) begin
            if (item[i] == ".") begin
                if (item.substr(0, i-1) != name) return "";
                return item.substr(i+1, item.len()-1);
            end
        end
        return item;
    endfunction

    // Does spec (already checked) name field fname?
    protected function bit m_spec_has(string spec, string fname);
        string items[$];
        m_split(spec, items);
        foreach (items[i]) begin
            string f = m_unprefix(items[i]);
            if (f == "*" || f == fname) return 1;
        end
        return 0;
    endfunction

    function void set_reset(fw_reset_domain_if rst);
        this.rst = rst;
    endfunction

    // A peer read of field f sees its reset-force value.
    function bit forced(fw_sync_field f);
        return f.has_force && rst != null && rst.in_reset();
    endfunction

    // Every set_*() calls this before it writes field f; `changed` is whether
    // the write changes the field's current value. Checks the write rules
    // (design-sync-rtl §3.2): comb() writes comb fields only, step() and
    // run() sync fields only.
    protected function void m_wr(fw_sync_field f, bit changed);
`ifndef FW_SYNC_NO_CHECKS
        if (phase == FW_SYNC_PH_COMB && !f.comb)
            m_rule($sformatf("sync field \"%s\" of \"%s\" written from comb()",
                             f.name, name));
        else if (f.comb && (phase == FW_SYNC_PH_STEP || phase == FW_SYNC_PH_RUN))
            m_rule($sformatf("comb field \"%s\" of \"%s\" written from %s",
                             f.name, name,
                             (phase == FW_SYNC_PH_STEP) ? "step()" : "run()"));
`endif
        if (f.comb && changed) comb_changes++;
        gen++;
    endfunction

    // Is task code at an edge of this holder's domain: the domain ran an
    // edge in this time step? (Task code resumes after the edge's group.)
    function bit m_at_edge();
        return phase == FW_SYNC_PH_RUN && dom != null && dom.edge_n != 0
            && dom.edge_t == $realtime;
    endfunction

    // A task write of field f (phase RUN), before m_wr: counts it against
    // the edge that samples it, the domain's next. Returns 1 if it is the
    // second for that edge (C5): an error, and the caller ignores it. One
    // by the thread of the last, in its time step, that restores the value
    // from before it (restores) undoes it instead. first: this is the first
    // for the edge, so the caller records the value it replaces.
    protected function bit m_task_wr(fw_sync_field f, bit restores, output bit first);
        longint unsigned e;
        process          p = process::self();
        first = 0;
        if (phase != FW_SYNC_PH_RUN || dom == null) return 0;
        e = dom.edge_n + 1;
        if (f.xing_n == e && restores && f.xing_p == p && f.xing_t == $realtime) begin
            f.xing_n = 0;   // undone: no task write for the edge
            return 0;
        end
        if (f.xing_n == e) begin
            m_rule($sformatf("FW-E-XING-DRIVE-TWICE: field \"%s\" of \"%s\" written twice by task code for one edge",
                             f.name, name));
            return 1;
        end
        f.xing_n = e;
        f.xing_p = p;
        f.xing_t = $realtime;
        first    = 1;
        return 0;
    endfunction

    // After a task write that changed a value: the domain's comb logic
    // settles on it now.
    protected function void m_task_settle();
        if (kernel != null) kernel.settle_now(this);
    endfunction

    static function void m_rule(string msg);
        rule_errs++;
        rule_err = msg;
        if (fatal_on_rule) $fatal(1, "fw-hdl: %s", msg);
    endfunction

    // The update at the edge: make the sync writes of the edge's step()s
    // visible, keeping the values from before the edge for task reads.
    function void commit();
        m_commit();
    endfunction

    // Save each field's current value as `pre`, then copy each sync field's
    // next value to current.
    pure virtual protected function void m_commit();
endclass
