// The value holder shared by the two ends of a struct-port connection
// (design-sync-rtl §3.2, "Connection"). A sync field keeps a current and a
// next value: the driver writes `nxt`, everyone reads `cur`, and commit() at
// the edge copies `nxt` to `cur` (`nxt` keeps its value, so an unwritten
// field holds like a register). A comb field keeps one value, written and
// read at once. Subclasses hold the typed values; this base keeps the field
// table and the reset domain that reset-force reads.
typedef class fw_sync_kernel;
typedef class fw_sync_dom;
virtual class fw_sig_holder;
    string             name;
    fw_sync_field      fields[$];
    fw_reset_domain_if rst;    // null: never in reset
    bit                frozen; // set by freeze(); set_comb is then fatal
    realtime           edge_t = -1; // time of the last commit()
    realtime           wr_t = -1;   // time of an early run() write, below
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
        // A run-phase sync write at a time whose edge has not been committed
        // yet (a process that woke on the edge before the kernel) belongs
        // after that edge, like a nonblocking assignment: keep the next
        // values as they were, for commit() at this time.
        if (phase == FW_SYNC_PH_RUN && !f.comb && edge_t != $realtime
                && wr_t != $realtime) begin
            wr_t = $realtime;
            m_keep();
        end
    endfunction

    static function void m_rule(string msg);
        rule_errs++;
        rule_err = msg;
        if (fatal_on_rule) $fatal(1, "fw-hdl: %s", msg);
    endfunction

    // At the edge: make the sync writes of the last step visible (those
    // kept by m_keep() if an early run() write came at this time).
    function void commit();
        m_commit(wr_t == $realtime);
        edge_t = $realtime;
    endfunction

    // Copy each sync field's next value (or kept value, if kept) to current.
    pure virtual protected function void m_commit(bit kept);
    // Keep each sync field's next value aside, for m_commit(1).
    pure virtual protected function void m_keep();
endclass
