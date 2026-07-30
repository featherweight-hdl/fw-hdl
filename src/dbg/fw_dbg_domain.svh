
typedef class fw_component;

// Glob match: `*` stands for any run of characters, including `.`. Used ONCE per
// (domain, directive) at apply() time and never at emit -- the whole point of
// resolving control into a per-site bit is that no string is compared while the
// model runs.
function automatic bit fw_dbg_glob(string pattern, string s);
    int pi = 0, si = 0;
    int star = -1, mark = 0;
    while (si < s.len()) begin
        if (pi < pattern.len() && pattern[pi] == "*") begin
            star = pi++;  mark = si;
        end else if (pi < pattern.len() && pattern[pi] == s[si]) begin
            pi++;  si++;
        end else if (star >= 0) begin
            pi = star + 1;  si = ++mark;
        end else begin
            return 1'b0;
        end
    end
    while (pi < pattern.len() && pattern[pi] == "*") pi++;
    return pi == pattern.len();
endfunction

// Parse a subject allow-list -- "1,2,3" or "0-2,7" -- into a 64-bit mask.
// Returns 0 (allow nothing) for an empty list, which is a request nobody makes
// by accident and which a caller can therefore test for.
function automatic longint fw_dbg_subj_mask(string s);
    longint m   = 0;
    int     lo  = -1, cur = -1;
    bit     rng = 0;
    for (int i = 0; i <= s.len(); i++) begin
        byte ch = (i < s.len()) ? s[i] : ",";
        if (ch >= "0" && ch <= "9") begin
            cur = (cur < 0 ? 0 : cur * 10) + (int'(ch) - int'("0"));
        end else if (ch == "-") begin
            lo = cur;  cur = -1;  rng = 1;
        end else if (ch == "," || ch == " ") begin
            if (cur >= 0) begin
                int a = rng ? lo  : cur;
                int b = cur;
                if (a < 0) a = b;
                for (int v = a; v <= b && v <= FW_DBG_MAX_SUBJECT; v++)
                    if (v >= 0) m |= (64'd1 << v);
            end
            cur = -1;  lo = -1;  rng = 0;
        end
    end
    return m;
endfunction

// One configuration directive. Fields left unset (-1) do not clamp.
//
// A directive selects along TWO independent axes and then clamps along three:
//
//   pattern   which CONTEXTS      (glob over the domain path)
//   sites     which SITES         (glob over the site name; "" or "*" = all)
//   ---
//   kinds     clamp: kind mask
//   level     clamp: verbosity ceiling
//   subjects  filter: allowed endpoints, one bit per subject index
//                     (guarded by has_subj, because an all-ones mask and the
//                      "unset" sentinel would otherwise be the same bit pattern)
//
// The site axis exists because a context is often the wrong granularity. The DMA
// engine is one domain and emits arbitration, bus errors, stalls and wakes from
// it; "quieten arbitration" must not mean "quieten the engine". Resolving a site
// glob at apply() costs one glob per (site x directive) ONCE and nothing at all
// at emit -- the answer lands in the same per-site bit that was already there.
typedef struct {
    string  pattern;
    int     kinds;
    int     level;
    int     records;
    string  sites;      // "" == "*"
    bit     has_subj;   // 0 == this directive says nothing about subjects
    longint subjects;   // allow mask, valid when has_subj
} fw_dbg_cfg_t;

// ----------------------------------------------------------------------------
// A debug DOMAIN: the unit of control, and the node type of the debug tree.
//
// It mirrors `fw_clock_domain` exactly -- an API carried over fw_port/fw_export
// deferred binding, with a tree wired INDEPENDENTLY of the component tree. That
// independence is the property worth having: debug topology is not forced to
// follow build topology, so contexts can be carved along the axis that matters
// (one context per DMA channel, cutting across `rf`, `ch[i]` and the engine)
// rather than along the instance hierarchy.
//
// A domain IS a listener (design §8.2): it receives typed calls and forwards
// them to its own listeners and up toward the root. The default body is the
// transport design's div-by-1 "tag" node -- stamp the originating context and
// pass through. Filter, merge and replicate are the same class with a richer
// body.
// ----------------------------------------------------------------------------
class fw_dbg_domain extends fw_export #(fw_dbg_listener_if)
        implements fw_dbg_listener_if;

    // Toward the root sink (up the DEBUG tree). Parentless and resolved here,
    // not by the component walk -- the same idiom as fw_clock_domain::src.
    fw_port #(fw_dbg_listener_if) up;

    protected string             m_dname;
    protected fw_dbg_listener_if m_up;          // resolved provider, or null
    protected fw_dbg_domain      m_up_dom;      // ...when it is itself a domain
    protected fw_dbg_domain      m_children[$];

    // Subscriptions. Interest is (kinds, level) per listener; a domain's enable
    // state is their UNION, clamped by configuration.
    protected fw_dbg_listener_if m_listeners[$];
    protected fw_dbg_kinds_t     m_lkinds[$];
    protected fw_dbg_level_e     m_llevel[$];

    // The clamp (design §5). Permissive by default, so control is demand-driven:
    // with nothing subscribed, nothing is enabled and no site evaluates its
    // arguments.
    protected fw_dbg_kinds_t     m_cfg_kinds = FW_K_ALL;
    protected fw_dbg_level_e     m_cfg_level = FW_L_TRACE;
    protected fw_dbg_recmode_e   m_recmode   = FW_REC_OPEN_CLOSE;

    // The directives that matched THIS domain's path, in declaration order.
    // Retained past resolve() because a site can be born later (see enabled()),
    // and the clamp for that site has to be computed from the same rules as
    // every other -- a late site that quietly skips the configuration would be a
    // hole exactly where someone is looking hardest.
    protected fw_dbg_cfg_t       m_my_cfgs[$];

    // The resolved gate: one bit per site id. Recomputed at apply(), read at
    // every emit.
    protected bit                m_en[];

    // The resolved subject filter: one 64-bit allow mask per site id, all-ones
    // unless a directive narrowed it. Parallel to m_en and resolved the same
    // way, so the emit path is still two array loads and no strings.
    protected longint            m_subj[];

    function new(string name, fw_component parent = null);
        super.new(name, parent);
        set_imp(this);            // see [[verilator-this-in-ctor-segfault]]
        m_dname = name;
        up = new("up", null);
    endfunction

    // Path in the DEBUG tree (not the component tree) -- what config globs match
    // against. Computed lazily by walking up, so it does not depend on the order
    // in which domains connect.
    virtual function string path();
        return (m_up_dom != null) ? {m_up_dom.path(), ".", m_dname} : m_dname;
    endfunction

    function fw_dbg_recmode_e recmode(); return m_recmode; endfunction

    // The record-mode question, asked through the listener interface so an emit
    // site never has to know whether it is talking to a domain or a bare sink.
    // A domain UP the tree cannot veto: an open record suppressed here is gone
    // for everyone, so the permissive answer is the safe one and the trim has
    // to be configured at the context that owns the traffic.
    virtual function bit emit_open();
        return (m_recmode == FW_REC_OPEN_CLOSE);
    endfunction

    // --- subscription --------------------------------------------------------
    function void add_listener(fw_dbg_listener_if l,
                               fw_dbg_kinds_t     kinds = FW_K_ALL,
                               fw_dbg_level_e     level = FW_L_TRACE);
        m_listeners.push_back(l);
        m_lkinds.push_back(kinds);
        m_llevel.push_back(level);
    endfunction

    function int num_listeners(); return m_listeners.size(); endfunction

    // --- the gate ------------------------------------------------------------
    //
    // Sites are born at any time -- a static site before time 0, a register's
    // instance site during elaboration, and an fw_event_set's during run() (a
    // model that builds its wait set where it waits is idiomatic, not unusual).
    // So the table has to cope with an id past its end, and the only correct
    // answer is to resolve that site now: born-disabled-until-someone-remembers-
    // to-re-apply is a silent hole, and a silent hole in a debug facility is
    // exactly the failure that makes people stop trusting it.
    virtual function bit enabled(int unsigned site_id);
        if (site_id >= m_en.size()) begin
            if (site_id == FW_DBG_NO_SITE) return 0;
            extend();
            if (site_id >= m_en.size()) return 0;   // not a real site
        end
        return m_en[site_id];
    endfunction

    // The subject gate. Asked only for events that named an endpoint, and only
    // after enabled() said yes -- so an unfiltered run pays one bounds check and
    // one mask test on the already-enabled path, and nothing anywhere else.
    //
    // "Cannot express" always means ALLOW: no subject, an index past the mask
    // width, an unresolved site. A filter is a way to look at less; it must
    // never become a way to miss something.
    virtual function bit enabled_subj(int unsigned site_id, int subject);
        if (subject < 0 || subject > FW_DBG_MAX_SUBJECT) return 1'b1;
        if (site_id >= m_subj.size()) return 1'b1;
        return ((m_subj[site_id] >> subject) & 64'd1) != 0;
    endfunction

    // Resolve every site the table does not cover yet. Amortized: it runs once
    // per batch of new sites, not once per emit.
    protected function void extend();
        int unsigned n   = fw_dbg_catalog::num_sites();
        int unsigned old = m_en.size();
        if (n + 1 <= old) return;
        m_en   = new [n+1] (m_en);
        m_subj = new [n+1] (m_subj);
        for (int unsigned s = (old == 0) ? 1 : old; s <= n; s++) begin
            longint sj;
            m_en[s]   = resolve_one(s, sj);
            m_subj[s] = sj;
        end
    endfunction

    // The whole control model for ONE site: demand (does anything here or above
    // want it?) then clamp (does this context's configuration allow it?). The
    // single place the rule is written -- resolve() and extend() both call it.
    //
    // The clamp is recomputed per site rather than held as one domain-wide pair,
    // because a directive may carry a site glob. Directives are last-match-wins,
    // as they were before; a directive with no `sites` matches every site, so
    // existing configurations resolve exactly as they used to.
    protected function bit resolve_one(int unsigned s, output longint subj);
        fw_dbg_site    st = fw_dbg_catalog::site(s);
        fw_dbg_kinds_t kb;
        fw_dbg_level_e lvl;
        fw_dbg_kinds_t ck  = FW_K_ALL;
        fw_dbg_level_e clv = FW_L_TRACE;
        bit            want = 0;

        subj = FW_DBG_SUBJ_ALL;
        if (st == null) return 0;
        kb  = fw_dbg_kind_bit(st.kind());
        lvl = st.level();

        foreach (m_listeners[i]) begin
            if (((m_lkinds[i] & kb) != 0) && (lvl <= m_llevel[i])) want = 1;
        end
        // Upward demand: an event emitted here is forwarded up, so if anything
        // above wants it, this domain must be enabled for it. Asking the parent
        // through enabled() rather than a passed-down array is what makes the
        // lazy path give the same answer as the eager one.
        if (!want && m_up_dom != null) want = m_up_dom.enabled(s);

        foreach (m_my_cfgs[i]) begin
            if (m_my_cfgs[i].sites.len() != 0 &&
                !fw_dbg_glob(m_my_cfgs[i].sites, st.name())) continue;
            if (m_my_cfgs[i].kinds    >= 0) ck   = fw_dbg_kinds_t'(m_my_cfgs[i].kinds);
            if (m_my_cfgs[i].level    >= 0) clv  = fw_dbg_level_e'(m_my_cfgs[i].level);
            if (m_my_cfgs[i].has_subj)      subj = m_my_cfgs[i].subjects;
        end

        return want && ((ck & kb) != 0) && (lvl <= clv);
    endfunction

    // --- forwarding ----------------------------------------------------------
    // The FIRST domain an event enters stamps itself as the originating context;
    // domains above pass it through unchanged. That is the div-by-1 tag node.
    protected function void tag(fw_dbg_ctx c);
        if (c.ctx() == null) begin
            c.set_domain(this);
        end
    endfunction

    protected function bit wants(int i, fw_dbg_kind_e k, fw_dbg_level_e lvl);
        return ((m_lkinds[i] & fw_dbg_kind_bit(k)) != 0) && (lvl <= m_llevel[i]);
    endfunction

    virtual function void on_op(fw_op_ctx op);
        fw_dbg_site s = op.site();
        tag(op);
        foreach (m_listeners[i]) begin
            if (wants(i, FW_DBG_OP, s.level())) m_listeners[i].on_op(op);
        end
        if (m_up != null) m_up.on_op(op);
    endfunction

    virtual function void on_state(fw_state_ctx st);
        fw_dbg_site s = st.site();
        tag(st);
        foreach (m_listeners[i]) begin
            if (wants(i, FW_DBG_STATE, s.level())) m_listeners[i].on_state(st);
        end
        if (m_up != null) m_up.on_state(st);
    endfunction

    virtual function void on_decision(fw_decision_ctx d);
        fw_dbg_site s = d.site();
        tag(d);
        foreach (m_listeners[i]) begin
            if (wants(i, FW_DBG_DECISION, s.level())) m_listeners[i].on_decision(d);
        end
        if (m_up != null) m_up.on_decision(d);
    endfunction

    virtual function void on_sched(fw_sched_ctx sc);
        fw_dbg_site s = sc.site();
        tag(sc);
        foreach (m_listeners[i]) begin
            if (wants(i, FW_DBG_SCHED, s.level())) m_listeners[i].on_sched(sc);
        end
        if (m_up != null) m_up.on_sched(sc);
    endfunction

    virtual function void on_notice(fw_notice_ctx n);
        fw_dbg_site s = n.site();
        tag(n);
        foreach (m_listeners[i]) begin
            if (wants(i, FW_DBG_NOTICE, s.level())) m_listeners[i].on_notice(n);
        end
        if (m_up != null) m_up.on_notice(n);
    endfunction

    virtual function void on_link(fw_link_ctx l);
        fw_dbg_site s = l.site();
        tag(l);
        foreach (m_listeners[i]) begin
            if (wants(i, FW_DBG_LINK, s.level())) m_listeners[i].on_link(l);
        end
        if (m_up != null) m_up.on_link(l);
    endfunction

    // --- elaboration ---------------------------------------------------------
    // Wire this domain into the debug tree. Use THIS rather than
    // `up.connect(parent)` directly: it also records the parent as a domain, so
    // path() can nest and apply() can walk down.
    //
    // Why the parent is passed explicitly instead of being recovered from the
    // resolved provider: Verilator 5.049 silently fails to `$cast` a class
    // handle back out of an interface-class handle WHEN THE CLASS EXTENDS A
    // PARAMETERIZED BASE -- which fw_dbg_domain (an fw_export #(...)) does.
    // (The same cast in fw_component::do_connect works, because fw_component is
    // unparameterized.) So the fw-hdl idiom "resolve through the port, then ask
    // what it is" is not available here, and the structural link has to be
    // stated at wiring time.
    function void connect_up(fw_dbg_domain parent);
        up.connect(parent);
        m_up_dom = parent;
        m_up     = parent;      // resolve NOW: do_connect() is too late for a
                                // domain created during build(), whose whole
                                // reason to exist is to carry build events
        parent.add_child(this);
        // Adopt the parent's already-resolved gate immediately. A fresh domain
        // has no listeners and no clamp of its own, so the parent's table IS its
        // table -- and without this a domain created during build() would stay
        // silent until the next apply(), which is precisely when the structural
        // events it exists to carry are being emitted.
        m_en   = parent.m_en;
        m_subj = parent.m_subj;
    endfunction

    // Resolve `up` here (it is parentless, so the component walk never reaches
    // it). A domain may also be pointed at a plain listener via
    // `up.connect(...)`; it then forwards normally but does not nest.
    virtual function void do_connect();
        if (up.is_connected()) begin
            m_up = up.get_if();
        end
    endfunction

    function void add_child(fw_dbg_domain d);
        m_children.push_back(d);
    endfunction

    // --- control resolution --------------------------------------------------
    // Apply matching directives (in order; last match wins), then recompute this
    // domain's per-site enable bit and recurse. TOP-DOWN, because an event
    // emitted here is forwarded upward: if anything above wants it, this domain
    // must be enabled for it.
    virtual function void resolve(fw_dbg_cfg_t cfgs[$]);
        int unsigned n = fw_dbg_catalog::num_sites();
        string       p = path();

        m_cfg_kinds = FW_K_ALL;
        m_cfg_level = FW_L_TRACE;
        m_recmode   = FW_REC_OPEN_CLOSE;
        m_my_cfgs.delete();
        foreach (cfgs[i]) begin
            if (fw_dbg_glob(cfgs[i].pattern, p)) begin
                m_my_cfgs.push_back(cfgs[i]);
                // The domain-wide summary keeps its old meaning: what the
                // directives that address EVERY site in this context say. Used
                // for recmode and for introspection; the per-site answer is
                // resolve_one's.
                if (cfgs[i].records >= 0) m_recmode   = fw_dbg_recmode_e'(cfgs[i].records);
                if (cfgs[i].sites.len() == 0) begin
                    if (cfgs[i].kinds >= 0) m_cfg_kinds = fw_dbg_kinds_t'(cfgs[i].kinds);
                    if (cfgs[i].level >= 0) m_cfg_level = fw_dbg_level_e'(cfgs[i].level);
                end
            end
        end

        m_en   = new [n+1];
        m_subj = new [n+1];
        for (int unsigned s = 1; s <= n; s++) begin
            longint sj;
            m_en[s]   = resolve_one(s, sj);
            m_subj[s] = sj;
        end

        foreach (m_children[i]) begin
            m_children[i].resolve(cfgs);
        end
    endfunction

    // Re-resolve the whole tree. On a non-root domain this walks up to the root,
    // which owns the directives -- so any component can ask for a refresh
    // without knowing where the root is.
    virtual function void apply();
        if (m_up_dom != null) m_up_dom.apply();
    endfunction

    // How many sites are live here -- for tests, and for the "why am I seeing
    // nothing" question asked of the debug facility itself.
    function int num_enabled();
        int n = 0;
        foreach (m_en[i]) if (m_en[i]) n++;
        return n;
    endfunction
endclass

// ----------------------------------------------------------------------------
// The ROOT of a debug tree: a domain with no `up`, which additionally owns the
// configuration directives and the apply() pass.
//
// Directives are matched against domain PATHS once, here, and resolved into one
// bit per (domain, site). Nothing downstream ever compares a string:
//
//     root.cfg("dma.de",      .level(FW_L_OP));
//     root.cfg("dma.ch2.*",   .level(FW_L_TRACE));       // one channel, deep
//     root.cfg("dma.*",       .kinds(FW_K_DECISION|FW_K_SCHED), .level(FW_L_TRACE));
//     root.cfg("dma.de",      .records(FW_REC_CLOSE_ONLY));
//
//     // One noisy SITE quietened without quietening its context -- the engine
//     // still reports bus errors, stalls and wakes; only arbitration goes away.
//     root.cfg("*", .sites("de.arb"), .level(int'(FW_L_OFF)));
//
//     // ...or kept, but only for the endpoints under suspicion.
//     root.cfg("*", .sites("de.arb"), .subjects(fw_dbg_subj_mask("1,2,3")));
//     root.apply();
// ----------------------------------------------------------------------------
class fw_dbg_root extends fw_dbg_domain;
    protected fw_dbg_cfg_t m_cfgs[$];

    function new(string name = "dbg", fw_component parent = null);
        super.new(name, parent);
    endfunction

    // A directive. Unset arguments do not clamp, so `cfg(p, .level(L))` narrows
    // the level and leaves kinds alone.
    // `sites` narrows the directive to matching site NAMES; `subjects` is an
    // allow mask over endpoint indices. Both default to "says nothing", so every
    // existing call site keeps its exact meaning.
    function void cfg(string  pattern,
                      int     kinds    = -1,
                      int     level    = -1,
                      int     records  = -1,
                      string  sites    = "",
                      longint subjects = 0,
                      bit     has_subj = 1'b0);
        fw_dbg_cfg_t c;
        c.pattern  = pattern;
        c.kinds    = kinds;
        c.level    = level;
        c.records  = records;
        c.sites    = sites;
        c.subjects = subjects;
        c.has_subj = has_subj;
        m_cfgs.push_back(c);
    endfunction

    // Subject filtering reads better as its own call than as two correlated
    // arguments to cfg(): passing a mask and forgetting the flag that validates
    // it is the kind of mistake that silently disables the filter.
    function void cfg_subjects(string pattern, string sites, longint mask);
        cfg(pattern, .sites(sites), .subjects(mask), .has_subj(1'b1));
    endfunction

    function void clear_cfg();
        m_cfgs.delete();
    endfunction

    // Recompute every context's per-site enable table. Call after wiring
    // listeners and after any cfg() change; cheap (sites x domains), and never
    // on a hot path.
    virtual function void apply();
        resolve(m_cfgs);
    endfunction
endclass
