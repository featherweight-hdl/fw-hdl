
// ----------------------------------------------------------------------------
// The one-line way to turn the facility on for a run.
//
// Everything else in `dbg/` is mechanism: sites, contexts, domains, listeners.
// This is the policy that makes the mechanism reachable from a command line —
// because a facility that requires a bench edit to see anything is a facility
// nobody uses under time pressure, which is the only time it matters.
//
//     fw_dbg_root dbg = fw_dbg_console::attach(root, "dut");
//     root.start();
//
// Two properties worth stating:
//
//   * It returns `null` and wires NOTHING unless the run asked. A regression
//     that does not pass `+fw_dbg` is byte-for-byte the run it was before —
//     which is what lets this be wired into every top unconditionally.
//   * It must be called BEFORE `start()`, so elaboration events are captured
//     and the gate is resolved by the `apply()` that `start()` already runs.
//
// --- The plusargs ------------------------------------------------------------
//
//   +fw_dbg                 attach a text sink to the component's context
//   +fw_dbg_level=<0..5>    how deep to listen (default 3 = FW_L_OP)
//   +fw_dbg_kinds=<mask>    which kinds (default all; see the FW_K_* bits)
//   +fw_dbg_clamp=<pat>:<n> narrow ONE context path to level n, e.g.
//                           +fw_dbg_clamp=dut.de:5 — deep on the engine, and
//                           whatever `+fw_dbg_level` said everywhere else
//   +fw_dbg_mute=<globs>    silence matching SITES by name, comma-separated —
//                           +fw_dbg_mute=de.arb,int_level_stable
//   +fw_dbg_only=<glob>     the inverse: silence every site EXCEPT matching ones
//   +fw_dbg_subj=[<glob>:]<list>
//                           keep only events about these endpoints —
//                           +fw_dbg_subj=de.arb:1,2,3  (or 0-2,7). Sites that
//                           name no endpoint are unaffected.
//
// The level is *demand*: it is what the sink subscribes to, and a site nothing
// subscribes to never evaluates its arguments. The clamp is the other half of
// §5's demand-then-clamp, exposed because "everything at TRACE" is unreadable
// and "one subsystem at TRACE" is exactly what you want at 2am.
//
// --- Why three axes and not one ----------------------------------------------
//
// The level/context pair handles "this subsystem, this deep". It does not handle
// what arbitration traffic actually looks like: ONE site, in ONE context, firing
// every round, about a DIFFERENT endpoint each time. `mute`/`only` cut on the
// site name; `subj` cuts on the endpoint. All three resolve to per-site state at
// apply() — no string is compared while the model runs, and nothing here is a
// substitute for filtering the recorded stream offline, which stays the primary
// tool because it is the one you can change your mind about.
//
// Directive order is: clamp, then mute/only, then subj — so a mute wins over a
// clamp, and `only` (which silences everything first) dominates both.
// ----------------------------------------------------------------------------
class fw_dbg_console;

    // Split "pattern:level" at the LAST colon, so a pattern may contain one.
    protected static function bit split_clamp(string s, ref string pat, ref int lvl);
        int c = -1;
        foreach (s[i]) if (s[i] == ":") c = i;
        if (c <= 0 || c == s.len() - 1) return 0;
        pat = s.substr(0, c - 1);
        lvl = s.substr(c + 1, s.len() - 1).atoi();
        return 1;
    endfunction

    // Split "glob:list" at the FIRST colon. Unlike a clamp (whose level is the
    // trailing token) the subject list is the tail, and a site glob never
    // contains a colon -- so first-colon is the correct split here and
    // last-colon is the correct split there.
    protected static function bit split_subj(string s, ref string sites, ref string list);
        foreach (s[i]) begin
            if (s[i] == ":") begin
                sites = s.substr(0, i - 1);
                list  = s.substr(i + 1, s.len() - 1);
                return (list.len() > 0);
            end
        end
        sites = "*";
        list  = s;
        return (s.len() > 0);
    endfunction

    // Apply one `cfg` per comma-separated glob. Splitting here rather than
    // teaching the glob matcher about alternation keeps the matcher a matcher.
    protected static function void cfg_each(fw_dbg_root dbg, string globs, int level);
        int start = 0;
        for (int i = 0; i <= globs.len(); i++) begin
            if (i == globs.len() || globs[i] == ",") begin
                if (i > start) begin
                    dbg.cfg("*", .sites(globs.substr(start, i - 1)), .level(level));
                end
                start = i + 1;
            end
        end
    endfunction

    // Build a context for `c`, attach a text sink, and resolve the gate.
    // Returns the domain so a caller can add its own listeners, or null when the
    // run did not ask for one.
    static function fw_dbg_root attach(fw_component c, string name = "dbg");
        fw_dbg_root      dbg;
        fw_dbg_sink_text sink;
        int              lvl   = int'(FW_L_OP);
        int              kinds = int'(FW_K_ALL);
        string           clamp;
        string           mute, only, subj;

        if (c == null || !$test$plusargs("fw_dbg")) return null;

        void'($value$plusargs("fw_dbg_level=%d", lvl));
        void'($value$plusargs("fw_dbg_kinds=%d", kinds));
        if (lvl < 0) lvl = 0;
        if (lvl > int'(FW_L_TRACE)) lvl = int'(FW_L_TRACE);

        dbg  = new(name);
        sink = new("fw-dbg| ");
        dbg.add_listener(sink, fw_dbg_kinds_t'(kinds), fw_dbg_level_e'(lvl));

        // An empty value is "no clamp", not a malformed one -- a build system
        // passing `+fw_dbg_clamp=${var}` with the variable unset should be
        // silent, not scold the user about syntax they did not write.
        if ($value$plusargs("fw_dbg_clamp=%s", clamp) && clamp.len() > 0) begin
            string pat;
            int    clvl;
            if (split_clamp(clamp, pat, clvl)) begin
                // Everything else drops to VITAL; the named path keeps its level.
                // Stated in this order because directives are last-match-wins.
                dbg.cfg("*",  .level(int'(FW_L_VITAL)));
                dbg.cfg(pat,  .level(clvl));
            end else begin
                $display("fw-hdl: +fw_dbg_clamp=%s is not <pattern>:<level> -- ignored", clamp);
            end
        end

        // Site-name filters. Both are last-match-wins directives over the same
        // table the clamp writes, so ordering here IS the documented precedence.
        if ($value$plusargs("fw_dbg_mute=%s", mute) && mute.len() > 0) begin
            cfg_each(dbg, mute, int'(FW_L_OFF));
        end
        if ($value$plusargs("fw_dbg_only=%s", only) && only.len() > 0) begin
            dbg.cfg("*", .sites("*"), .level(int'(FW_L_OFF)));
            cfg_each(dbg, only, lvl);
        end

        // Endpoint filter. An empty allow-list would silence every subject-
        // carrying event, which is never what someone typing this wants -- far
        // more likely a typo -- so it is reported rather than obeyed.
        if ($value$plusargs("fw_dbg_subj=%s", subj) && subj.len() > 0) begin
            string  sites, list;
            longint mask;
            if (split_subj(subj, sites, list)) begin
                mask = fw_dbg_subj_mask(list);
                if (mask == 0) begin
                    $display("fw-hdl: +fw_dbg_subj=%s selects no endpoints -- ignored", subj);
                end else begin
                    dbg.cfg_subjects("*", sites, mask);
                end
            end else begin
                $display("fw-hdl: +fw_dbg_subj=%s is not [<site-glob>:]<list> -- ignored", subj);
            end
        end

        c.set_dbg_domain(dbg);
        dbg.apply();          // start() re-applies for sites born during elaboration
        return dbg;
    endfunction

    // The site catalog, on request. This is the join table -- every symbolic
    // fact about the instrumentation, including each field's declared width and
    // signedness, which is the half a consumer of the record stream cannot
    // guess. Printed after elaboration so instance sites (registers, wait sets)
    // are present; it describes the IMAGE, so sites never executed appear too.
    // Call from a `final` block, not from elaboration.
    //
    // A site's IDENTITY (name, kind, level, file/line) exists before time 0 --
    // the static-initializer idiom guarantees it, and that is what makes the
    // catalog describe the image rather than the run. Its FIELD SCHEMA does not:
    // names and types are recorded on a field's first activation, so at time 0
    // every site has zero fields.
    //
    // So the useful dump is at the END, where the schema reflects everything
    // that actually ran. The honest limitation, stated because a consumer will
    // hit it: a site that never executed appears with its identity and no
    // fields. Declaring the schema at registration would fix that and is the
    // obvious candidate when D-8's catalog artifact needs to be complete for
    // unexercised sites.
    static function void dump_catalog();
        if (!$test$plusargs("fw_dbg_catalog")) return;
        fw_dbg_catalog::dump();
    endfunction

    // Anything that has sites but no context to emit them into. Called by
    // fw_component_root::start() once elaboration has settled: this is the one
    // moment the answer is both complete and still useful.
    //
    // Printed only when a context exists -- in a run with no debug wired at all,
    // "nothing is observable" is the request, not a finding.
    static function void report_uncontexted();
        int n = fw_dbg_catalog::num_uncontexted();
        if (n == 0 || !$test$plusargs("fw_dbg")) return;
        $display("fw-hdl: %0d register block(s) have NO debug context and will emit nothing:", n);
        for (int i = 0; i < n; i++) begin
            $display("          %s", fw_dbg_catalog::uncontexted(i));
        end
        $display("        Build them during elaboration (they adopt the owning component),");
        $display("        or pass the component explicitly: new(\"%s\", <component>)",
                 fw_dbg_catalog::uncontexted(0));
    endfunction

endclass
