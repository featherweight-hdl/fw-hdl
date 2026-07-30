
typedef class fw_dbg_domain;

// ----------------------------------------------------------------------------
// Thread identity.
//
// SystemVerilog has no thread-local storage, but `std::process` handles are
// stable per process and usable as associative-array keys (verified on Verilator
// 5.049), which is enough to hand out small dense ids. The lookup is on the
// ENABLED path only -- a disabled site never gets this far -- and D-4's op stack
// will cache the id per activation.
// ----------------------------------------------------------------------------
class fw_dbg_thread;
    protected static int m_ids[std::process];
    protected static int m_next = 1;

    static function int id();
        std::process p = std::process::self();
        if (p == null) begin
            return 0;
        end
        if (!m_ids.exists(p)) begin
            m_ids[p] = m_next++;
        end
        return m_ids[p];
    endfunction
endclass

// ----------------------------------------------------------------------------
// The context base: the four identity coordinates of design §4, plus the
// positional payload.
//
// LIFETIME: a context is **borrowed**. It is valid only for the duration of the
// callback that received it. The emitter owns it (via fw_dbg_pool) and reuses
// it, so a steady-state event allocates nothing. A listener that wants to retain
// one calls `snapshot()`, which produces the flat `fw_dbg_rec` -- and that is
// exactly where the record type still belongs: at the boundary to anything that
// stores, serializes, or crosses a substrate.
//
// Under `FW_DBG_DEBUG` the pool poisons a context on release and every accessor
// checks, so retaining a handle fails loudly at the first read instead of
// silently reporting some later event's data.
// ----------------------------------------------------------------------------
virtual class fw_dbg_ctx;
    protected int unsigned m_site_id = FW_DBG_NO_SITE;
    // Resolved once at reset() rather than looked up per access. Every payload
    // push needs it, and a catalog index per field adds up at per-beat rates.
    protected fw_dbg_site  m_site;
    protected fw_dbg_domain m_dom;
    protected int          m_thread_id;
    protected longint      m_stamp;
    protected longint      m_fields[$];
    // The endpoint this event is about, or FW_DBG_NO_SUBJECT. Set by the emitter
    // via `fw_subject; read by the subject filter and carried into the record so
    // the same question can be asked again offline.
    protected int          m_subject = FW_DBG_NO_SUBJECT;
`ifdef FW_DBG_DEBUG
    protected bit          m_poisoned;
`endif

    pure virtual function fw_dbg_kind_e kind();

    // Hand this context to a listener through the method that matches its kind.
    // Keeps the emit macros kind-agnostic: one `fw_ev_end` closes every site,
    // and adding a kind does not touch the macro layer.
    pure virtual function void deliver(fw_dbg_listener_if l);

    // --- identity ------------------------------------------------------------
    function fw_dbg_site   site();      `fw_dbg_live return m_site;      endfunction
    function int unsigned  site_id();   `fw_dbg_live return m_site_id;   endfunction
    function fw_dbg_domain ctx();       `fw_dbg_live return m_dom;       endfunction
    function int           thread_id(); `fw_dbg_live return m_thread_id; endfunction
    function longint       stamp();     `fw_dbg_live return m_stamp;     endfunction
    function int           subject();   `fw_dbg_live return m_subject;   endfunction

    function string name();
        fw_dbg_site s = site();
        return (s != null) ? s.name() : "<unknown site>";
    endfunction

    // --- payload: untyped, positional ---------------------------------------
    // The generic consumer (log renderer, JSON sink) walks fields through the
    // site's schema. A consumer that knows the operation projects a typed view
    // over the same values -- the same move fw_reg #(T) makes over fw_reg_base.
    function int     field_count();     `fw_dbg_live return m_fields.size(); endfunction
    function longint field_int(int i);
        `fw_dbg_live
        return (i >= 0 && i < m_fields.size()) ? m_fields[i] : 0;
    endfunction
    function string field_name(int i);
        return (m_site != null) ? m_site.field_name(i) : "?";
    endfunction

    // --- the payload push, in two halves ------------------------------------
    //
    // A site's schema is written ONCE -- on the first activation that reaches a
    // given field -- and read forever after. But the obvious implementation
    // passes the name string on EVERY push and throws it away, and a string
    // argument is not free: `de.beat` fires per word with three fields, so that
    // is three string copies per transferred word, carrying information the
    // catalog already holds.
    //
    // So the macros ask `need_schema()` first and call the string-taking form
    // only while the schema is still being written. After the first activation
    // of a site every push is `push()` -- one queue append, no strings anywhere
    // on the steady-state path.
    function bit need_schema();
        `fw_dbg_live
        return (m_site != null && m_site.field_count() <= m_fields.size());
    endfunction

    function void push(longint v);
        m_fields.push_back(v);
    endfunction

    // Schema-writing push. `nm` is a compile-time string from the macro (the
    // operand's own source text); `t` is the decode contract -- width,
    // signedness, radix -- which is the half a consumer cannot guess.
    function void push_named(string nm, longint v, fw_dbg_ftype_t t = FW_T_none);
        if (m_site != null && m_site.field_count() <= m_fields.size()) begin
            m_site.add_field(nm, t);
        end
        m_fields.push_back(v);
    endfunction

    // --- emitter-side setup (not for listeners) -----------------------------
    // Name the endpoint this event concerns. Out-of-range values are kept as-is
    // rather than clamped: the subject FILTER treats anything it cannot express
    // as "allow", so an unexpected index shows up in the stream instead of being
    // silently dropped. A filter that hides the thing you did not anticipate is
    // worse than no filter.
    function void set_subject(int s);
        m_subject = s;
    endfunction

    virtual function void reset(int unsigned site_id, longint stamp);
        m_site_id  = site_id;
        m_site     = fw_dbg_catalog::site(site_id);
        m_stamp    = stamp;
        m_thread_id = fw_dbg_thread::id();
        m_dom      = null;
        m_subject  = FW_DBG_NO_SUBJECT;
        m_fields.delete();
`ifdef FW_DBG_DEBUG
        m_poisoned = 0;
`endif
    endfunction

    // Called by a domain as the event passes through it: the "tag" transform of
    // the transport design (§5) -- the div-by-1 pass-through that stamps which
    // context an event was emitted into.
    function void set_domain(fw_dbg_domain d);
        m_dom = d;
    endfunction

    function void poison();
`ifdef FW_DBG_DEBUG
        m_poisoned = 1;
`endif
    endfunction

`ifdef FW_DBG_DEBUG
    // Use-after-release detector. Fatal by default -- retaining a borrowed
    // context is a bug that otherwise shows up as one listener reporting another
    // event's data, which is a miserable thing to chase. `m_poison_fatal` exists
    // so the facility's own test can exercise the detector without dying.
    //
    // Honest limitation: the pool REUSES contexts, and acquire() clears the
    // poison. So this catches a read after the callback returned and before the
    // slot is reused -- the common case -- not a read arbitrarily far in the
    // future.
    static int m_use_after_release = 0;
    static bit m_poison_fatal      = 1;

    static function void note_use_after_release();
        m_use_after_release++;
        if (m_poison_fatal) begin
            $fatal(1, "fw_dbg: context used after its callback returned -- contexts are BORROWED; call snapshot() to keep one (see docs debug/listener-api.md)");
        end
    endfunction
`endif

    // --- the retention boundary ---------------------------------------------
    virtual function fw_dbg_rec snapshot();
        fw_dbg_rec r = new();
        `fw_dbg_live
        r.site_id   = m_site_id;
        r.kind      = kind();
        r.stamp     = m_stamp;
        r.thread_id = m_thread_id;
        r.subject   = m_subject;
        r.fields    = m_fields;
        return r;
    endfunction

    function string field_str();
        fw_dbg_site s    = m_site;
        string      body = "";
        foreach (m_fields[i]) begin
            body = {body, i == 0 ? "" : " ",
                    (s != null && s.field_hex(i))
                        ? $sformatf("%s=0x%0h", field_name(i), m_fields[i])
                        : $sformatf("%s=%0d",   field_name(i), m_fields[i])};
        end
        return body;
    endfunction

    virtual function string to_str();
        return $sformatf("%s(%s)", name(), field_str());
    endfunction
endclass

// --- K1: OP -----------------------------------------------------------------
// Three timestamps in the general case (UVM's accept/begin/end): ACCEPTED = the
// work became eligible, stamped by whoever MAKES it eligible; BEGUN = an actor
// started serving it, stamped by whoever SERVES it; ENDED = it finished. The two
// actors are joined by the derived flow key, not by a passed handle -- which is
// what lets the RTL side compute the same join.
class fw_op_ctx extends fw_dbg_ctx;
    protected fw_op_phase_e   m_phase;
    protected fw_op_outcome_e m_outcome;
    protected longint         m_flow[$];
    // A SPAN's own begin/end. Both live on the context for its whole duration,
    // which is why a span checks a context OUT of the pool rather than
    // borrowing one for a callback.
    protected longint         m_begun;
    protected longint         m_ended;

    virtual function fw_dbg_kind_e kind(); return FW_DBG_OP; endfunction
    virtual function void deliver(fw_dbg_listener_if l); l.on_op(this); endfunction

    function fw_op_phase_e   phase();   `fw_dbg_live return m_phase;   endfunction
    function fw_op_outcome_e outcome(); `fw_dbg_live return m_outcome; endfunction

    // The DERIVED flow key (§4.1): composed of values the hardware itself holds
    // -- {channel, arm_count, chunk_idx} -- never a model-local allocation
    // counter, because an RTL stream has no such counter and the two streams
    // could then never be joined.
    function int     flow_count();    `fw_dbg_live return m_flow.size(); endfunction
    function longint flow_key(int i);
        `fw_dbg_live
        return (i >= 0 && i < m_flow.size()) ? m_flow[i] : 0;
    endfunction

    // Retro-tagging (§4): an operation may begin before its dynamic identity is
    // known. Tags applied after entry land on the close record; tags known at
    // entry ride the open record too, so a live listener can filter on them.
    function void tag(longint v);
        m_flow.push_back(v);
    endfunction

    function void set_phase(fw_op_phase_e p);     m_phase   = p; endfunction
    function void set_outcome(fw_op_outcome_e o); m_outcome = o; endfunction

    // --- span timestamps -----------------------------------------------------
    function longint begun();  `fw_dbg_live return m_begun; endfunction
    function longint ended();  `fw_dbg_live return m_ended; endfunction

    // Duration is DERIVED, never a stored field and never emitted separately --
    // §14.13's "emit only the irrecoverable". Offered here so a sink does not
    // have to remember which two columns to subtract.
    function longint duration();
        `fw_dbg_live
        return (m_ended >= m_begun) ? (m_ended - m_begun) : 0;
    endfunction

    function void mark_begun(longint t); m_begun = t; m_ended = t; endfunction

    // Closing also re-stamps the record. `stamp` means "when this record was
    // produced", and a close record is produced at the END of the operation --
    // leaving it at the open time makes a span's two records arrive out of order
    // in any time-sorted view, which is every view.
    function void mark_ended(longint t); m_ended = t; m_stamp = t;  endfunction

    virtual function void reset(int unsigned site_id, longint stamp);
        super.reset(site_id, stamp);
        m_phase   = FW_OP_BEGUN;
        m_outcome = FW_OUT_OK;
        m_begun   = stamp;
        m_ended   = stamp;
        m_flow.delete();
    endfunction

    virtual function fw_dbg_rec snapshot();
        fw_dbg_rec r = super.snapshot();
        r.op_phase = m_phase;
        r.outcome  = m_outcome;
        r.flow     = m_flow;
        r.t_begun  = m_begun;
        r.t_ended  = m_ended;
        return r;
    endfunction

    // The flow key is shown on EVERY phase, not just the open: it is the join
    // column, and a close whose flow you cannot read is a close you cannot pair
    // by eye. Duration rides on the close because that is the one number a
    // reader wants and the one they would otherwise compute by hand.
    virtual function string to_str();
        string f = "";
        foreach (m_flow[i]) f = {f, $sformatf("%s%0d", i == 0 ? "" : ".", m_flow[i])};
        return $sformatf("%s %s%s%s", m_phase.name(), super.to_str(),
                         (f != "") ? {" flow=", f} : "",
                         (m_phase == FW_OP_ENDED)
                             ? $sformatf(" -> %s dur=%0d", m_outcome.name(), duration())
                             : "");
    endfunction
endclass

// --- K2: STATE --------------------------------------------------------------
// A value moved. `actor` and `dropped` are what make "I wrote it and it read
// back different" a one-line diagnosis rather than a bisect.
class fw_state_ctx extends fw_dbg_ctx;
    protected longint        m_old, m_new, m_dropped;
    protected fw_dbg_actor_e m_actor;

    virtual function fw_dbg_kind_e kind(); return FW_DBG_STATE; endfunction
    virtual function void deliver(fw_dbg_listener_if l); l.on_state(this); endfunction

    function longint        old_val();  `fw_dbg_live return m_old;     endfunction
    function longint        new_val();  `fw_dbg_live return m_new;     endfunction
    function longint        dropped();  `fw_dbg_live return m_dropped; endfunction
    function fw_dbg_actor_e actor();    `fw_dbg_live return m_actor;   endfunction

    function void set_change(longint o, longint n, fw_dbg_actor_e a,
                             longint dropped = 0);
        m_old = o;  m_new = n;  m_actor = a;  m_dropped = dropped;
    endfunction

    virtual function void reset(int unsigned site_id, longint stamp);
        super.reset(site_id, stamp);
        m_old = 0;  m_new = 0;  m_dropped = 0;  m_actor = FW_ACTOR_HW;
    endfunction

    virtual function fw_dbg_rec snapshot();
        fw_dbg_rec r = super.snapshot();
        r.actor = m_actor;
        r.push_field(m_old);
        r.push_field(m_new);
        r.push_field(m_dropped);
        return r;
    endfunction

    // The old->new pair is the headline, but a STATE site may also carry
    // payload fields -- the CAUSE of an interrupt, which channel, what cleared
    // it -- and dropping them here made those sites emit values no reader ever
    // saw. Rendered after the change, so the shape of the common (field-less)
    // case is unchanged.
    virtual function string to_str();
        string f = field_str();
        return $sformatf("%s 0x%0h -> 0x%0h by %s%s%s", name(), m_old, m_new,
                         m_actor.name(),
                         m_dropped != 0 ? $sformatf(" (dropped 0x%0h)", m_dropped) : "",
                         (f != "") ? {" ", f} : "");
    endfunction
endclass

// --- K3: DECISION -----------------------------------------------------------
// A selection plus the inputs that produced it and, critically, the REJECTION
// REASON for each non-winner. This is the kind that makes starvation and "my
// request was silently ignored" debuggable, and it is almost never logged.
// Reason codes are site-local small integers; the site's schema names them.
class fw_decision_ctx extends fw_dbg_ctx;
    protected longint m_winner;
    protected bit     m_have_winner;
    protected longint m_cand[$];
    protected int     m_reason[$];   // parallel to m_cand; 0 == "won"

    virtual function fw_dbg_kind_e kind(); return FW_DBG_DECISION; endfunction
    virtual function void deliver(fw_dbg_listener_if l); l.on_decision(this); endfunction

    function bit     have_winner(); `fw_dbg_live return m_have_winner; endfunction
    function longint winner();      `fw_dbg_live return m_winner;      endfunction
    function int     cand_count();  `fw_dbg_live return m_cand.size(); endfunction
    function longint candidate(int i);
        `fw_dbg_live
        return (i >= 0 && i < m_cand.size()) ? m_cand[i] : 0;
    endfunction
    // Why candidate i did not win. 0 means it did.
    function int reason_of(int i);
        `fw_dbg_live
        return (i >= 0 && i < m_reason.size()) ? m_reason[i] : 0;
    endfunction

    function void set_winner(longint w); m_winner = w; m_have_winner = 1; endfunction
    function void add_candidate(longint c, int reason = 0);
        m_cand.push_back(c);
        m_reason.push_back(reason);
    endfunction

    virtual function void reset(int unsigned site_id, longint stamp);
        super.reset(site_id, stamp);
        m_winner = 0;  m_have_winner = 0;
        m_cand.delete();  m_reason.delete();
    endfunction

    virtual function fw_dbg_rec snapshot();
        fw_dbg_rec r = super.snapshot();
        r.push_field(m_have_winner ? m_winner : -1);
        foreach (m_cand[i]) begin
            r.push_field(m_cand[i]);
            r.push_field(longint'(m_reason[i]));
        end
        return r;
    endfunction

    virtual function string to_str();
        string c = "";
        foreach (m_cand[i]) begin
            c = {c, i == 0 ? "" : " ",
                 $sformatf("%0d%s", m_cand[i],
                           m_reason[i] == 0 ? "*" : $sformatf("(r%0d)", m_reason[i]))};
        end
        return $sformatf("%s(%s)%s%s", name(), field_str(),
                         m_have_winner ? $sformatf(" winner=%0d", m_winner) : "",
                         (c != "") ? {" cand=[", c, "]"} : "");
    endfunction
endclass

// --- K4: SCHED --------------------------------------------------------------
// fork / retire / block(on = wait-set) / wake(by = source, blocked_for). The
// kind that answers "why is nothing happening" -- the top integration question,
// and the difference between a five-minute and a five-hour debug.
class fw_sched_ctx extends fw_dbg_ctx;
    protected fw_sched_kind_e m_skind;
    protected longint         m_blocked_for;
    protected int unsigned    m_waker;      // site id of the source that woke us
    protected int unsigned    m_sources[$]; // site ids of the wait set

    virtual function fw_dbg_kind_e kind(); return FW_DBG_SCHED; endfunction
    virtual function void deliver(fw_dbg_listener_if l); l.on_sched(this); endfunction

    function fw_sched_kind_e sched_kind();  `fw_dbg_live return m_skind;       endfunction
    function longint         blocked_for(); `fw_dbg_live return m_blocked_for; endfunction
    function int unsigned    waker();       `fw_dbg_live return m_waker;       endfunction
    function int             source_count(); `fw_dbg_live return m_sources.size(); endfunction
    function int unsigned    source(int i);
        `fw_dbg_live
        return (i >= 0 && i < m_sources.size()) ? m_sources[i] : FW_DBG_NO_SITE;
    endfunction

    function void set_sched(fw_sched_kind_e k, longint blocked_for = 0,
                            int unsigned waker = FW_DBG_NO_SITE);
        m_skind = k;  m_blocked_for = blocked_for;  m_waker = waker;
    endfunction
    function void add_source(int unsigned sid); m_sources.push_back(sid); endfunction

    virtual function void reset(int unsigned site_id, longint stamp);
        super.reset(site_id, stamp);
        m_skind = FW_SCHED_BLOCK;  m_blocked_for = 0;  m_waker = FW_DBG_NO_SITE;
        m_sources.delete();
    endfunction

    virtual function fw_dbg_rec snapshot();
        fw_dbg_rec r = super.snapshot();
        r.sched_kind = m_skind;
        r.push_field(m_blocked_for);
        r.push_field(longint'(m_waker));
        foreach (m_sources[i]) r.push_field(longint'(m_sources[i]));
        return r;
    endfunction

    virtual function string to_str();
        string s = "";
        foreach (m_sources[i]) begin
            fw_dbg_site ss = fw_dbg_catalog::site(m_sources[i]);
            s = {s, i == 0 ? "" : ", ", (ss != null) ? ss.name() : "?"};
        end
        case (m_skind)
            FW_SCHED_BLOCK: return $sformatf("block %s on {%s}", name(), s);
            FW_SCHED_WAKE:  begin
                fw_dbg_site w = fw_dbg_catalog::site(m_waker);
                return $sformatf("wake %s by %s after %0d", name(),
                                 (w != null) ? w.name() : "?", m_blocked_for);
            end
            default: return $sformatf("%s %s", m_skind.name(), name());
        endcase
    endfunction
endclass

// --- K5: NOTICE -------------------------------------------------------------
// note / info / warn / error, and `assert` (which emits ONLY when tripped,
// carrying operand images rather than a pre-formatted string). A kind within the
// same catalog rather than a parallel print facility, so it routes, filters, and
// correlates with everything else.
class fw_notice_ctx extends fw_dbg_ctx;
    protected fw_dbg_severity_e m_sev;

    virtual function fw_dbg_kind_e kind(); return FW_DBG_NOTICE; endfunction
    virtual function void deliver(fw_dbg_listener_if l); l.on_notice(this); endfunction

    function fw_dbg_severity_e severity(); `fw_dbg_live return m_sev; endfunction
    function void set_severity(fw_dbg_severity_e s); m_sev = s; endfunction

    virtual function void reset(int unsigned site_id, longint stamp);
        super.reset(site_id, stamp);
        m_sev = FW_SEV_INFO;
    endfunction

    virtual function fw_dbg_rec snapshot();
        fw_dbg_rec r = super.snapshot();
        r.severity = m_sev;
        return r;
    endfunction

    virtual function string to_str();
        return $sformatf("%s %s", m_sev.name(), super.to_str());
    endfunction
endclass

// --- K6: LINK ---------------------------------------------------------------
// A causal edge, emitted ONLY where it is irrecoverable offline (§14.13).
// Same-thread nesting is inferable from the stream and must NOT be linked; this
// kind exists for the cross-thread and cross-component hop.
class fw_link_ctx extends fw_dbg_ctx;
    protected fw_dbg_relation_e m_rel;
    protected longint           m_from, m_to;

    virtual function fw_dbg_kind_e kind(); return FW_DBG_LINK; endfunction
    virtual function void deliver(fw_dbg_listener_if l); l.on_link(this); endfunction

    function fw_dbg_relation_e relation(); `fw_dbg_live return m_rel;  endfunction
    function longint           from_id();  `fw_dbg_live return m_from; endfunction
    function longint           to_id();    `fw_dbg_live return m_to;   endfunction

    function void set_link(longint f, longint t, fw_dbg_relation_e r);
        m_from = f;  m_to = t;  m_rel = r;
    endfunction

    virtual function void reset(int unsigned site_id, longint stamp);
        super.reset(site_id, stamp);
        m_from = 0;  m_to = 0;  m_rel = FW_REL_CAUSED_BY;
    endfunction

    virtual function fw_dbg_rec snapshot();
        fw_dbg_rec r = super.snapshot();
        r.relation = m_rel;
        r.push_field(m_from);
        r.push_field(m_to);
        return r;
    endfunction

    virtual function string to_str();
        return $sformatf("%s %0d %s %0d", name(), m_from, m_rel.name(), m_to);
    endfunction
endclass

// ----------------------------------------------------------------------------
// TYPED PROJECTION over an operation's payload.
//
// The same move `fw_reg #(T)` makes over `fw_reg_base`: the untyped, positional
// payload is what a generic consumer (log renderer, JSON sink, an external
// storage package) walks through the site schema; a consumer that KNOWS the
// operation projects a typed view over the very same values and reads them by
// name.
//
// It is a view, not a container -- it holds the context, copies nothing, and is
// as borrowed as the context is. `T` is a packed struct whose field order
// matches the order the site pushes; `params()` reinterprets the payload as
// that struct.
//
//     typedef struct packed { bit [7:0] ch; bit [23:0] words; } chunk_p_t;
//
//     virtual function void on_op(fw_op_ctx op);
//         fw_op_view #(chunk_p_t) v = fw_op_view #(chunk_p_t)::over(op);
//         if (v != null) $display("ch=%0d", v.params().ch);
//     endfunction
//
// `over()` returns null when the payload cannot fill T, so a listener watching
// a stream of mixed operations tests once instead of reading garbage. The
// alternative -- a silent partial fill -- produces plausible wrong numbers,
// which is the worst failure mode a debug facility has.
// ----------------------------------------------------------------------------
class fw_op_view #(type T = bit [63:0]);
    protected fw_op_ctx m_op;

    protected function new(fw_op_ctx op);
        m_op = op;
    endfunction

    // How many payload words T needs, rounded up to the 64-bit words the
    // positional payload is stored in.
    static function int words();
        return ($bits(T) + 63) / 64;
    endfunction

    static function fw_op_view #(T) over(fw_op_ctx op);
        fw_op_view #(T) v;
        if (op == null || op.field_count() < words()) return null;
        v = new(op);
        return v;
    endfunction

    function fw_op_ctx raw(); return m_op; endfunction

    // The payload, reinterpreted. Fields are packed LSB-first in push order, so
    // the struct's LAST member corresponds to the FIRST pushed field -- the
    // ordinary SystemVerilog packed-struct convention, stated because getting it
    // backwards is silent.
    function T params();
        bit [64*8-1:0] raw_bits = '0;
        for (int i = 0; i < words() && i < 8; i++) begin
            raw_bits[64*i +: 64] = m_op.field_int(i);
        end
        return T'(raw_bits);
    endfunction
endclass

// ----------------------------------------------------------------------------
// The context pool.
//
// One depth-indexed free list per kind. Emit is a `function`, so it runs to
// completion without yielding: the only way a second context of the same kind
// can be live is an emit *inside* a callback on the same thread, and the depth
// index handles exactly that. No thread-local storage is needed, and steady
// state allocates nothing.
//
// Every acquire MUST be matched by a release -- which is why the macros own both
// ends and hand-written emits should not exist.
// ----------------------------------------------------------------------------
class fw_dbg_pool;
    protected static fw_op_ctx       m_op[$];        protected static int m_op_d;
    protected static fw_state_ctx    m_state[$];     protected static int m_state_d;
    protected static fw_decision_ctx m_decision[$];  protected static int m_decision_d;
    protected static fw_sched_ctx    m_sched[$];     protected static int m_sched_d;
    protected static fw_notice_ctx   m_notice[$];    protected static int m_notice_d;
    protected static fw_link_ctx     m_link[$];      protected static int m_link_d;

    // The stamp. Domain-relative time (design §7, folded through root_ticks) is
    // wired in D-4 with the op stack; until then every context carries raw
    // simulation time, which is correct for a single-domain model and monotonic
    // for all of them.
    static function longint now();
        return longint'($time);
    endfunction

    static function fw_op_ctx acquire_op(int unsigned site_id);
        fw_op_ctx c;
        if (m_op_d == m_op.size()) begin c = new(); m_op.push_back(c); end
        c = m_op[m_op_d++];
        c.reset(site_id, now());
        return c;
    endfunction
    static function void release_op();
        if (m_op_d > 0) begin m_op[--m_op_d].poison(); end
    endfunction

    static function fw_state_ctx acquire_state(int unsigned site_id);
        fw_state_ctx c;
        if (m_state_d == m_state.size()) begin c = new(); m_state.push_back(c); end
        c = m_state[m_state_d++];
        c.reset(site_id, now());
        return c;
    endfunction
    static function void release_state();
        if (m_state_d > 0) begin m_state[--m_state_d].poison(); end
    endfunction

    static function fw_decision_ctx acquire_decision(int unsigned site_id);
        fw_decision_ctx c;
        if (m_decision_d == m_decision.size()) begin c = new(); m_decision.push_back(c); end
        c = m_decision[m_decision_d++];
        c.reset(site_id, now());
        return c;
    endfunction
    static function void release_decision();
        if (m_decision_d > 0) begin m_decision[--m_decision_d].poison(); end
    endfunction

    static function fw_sched_ctx acquire_sched(int unsigned site_id);
        fw_sched_ctx c;
        if (m_sched_d == m_sched.size()) begin c = new(); m_sched.push_back(c); end
        c = m_sched[m_sched_d++];
        c.reset(site_id, now());
        return c;
    endfunction
    static function void release_sched();
        if (m_sched_d > 0) begin m_sched[--m_sched_d].poison(); end
    endfunction

    static function fw_notice_ctx acquire_notice(int unsigned site_id);
        fw_notice_ctx c;
        if (m_notice_d == m_notice.size()) begin c = new(); m_notice.push_back(c); end
        c = m_notice[m_notice_d++];
        c.reset(site_id, now());
        return c;
    endfunction
    static function void release_notice();
        if (m_notice_d > 0) begin m_notice[--m_notice_d].poison(); end
    endfunction

    static function fw_link_ctx acquire_link(int unsigned site_id);
        fw_link_ctx c;
        if (m_link_d == m_link.size()) begin c = new(); m_link.push_back(c); end
        c = m_link[m_link_d++];
        c.reset(site_id, now());
        return c;
    endfunction
    static function void release_link();
        if (m_link_d > 0) begin m_link[--m_link_d].poison(); end
    endfunction

    // ------------------------------------------------------------------------
    // SPAN checkout (D-5).
    //
    // Every acquire above hands out a BORROWED context: valid for one callback,
    // released by DEPTH off a shared stack. That is safe for exactly one
    // reason -- an emit is a `function`, so it never yields, and no other thread
    // can run between acquire and release.
    //
    // A span breaks that invariant: its body consumes time, so two forked
    // processes can hold open operations simultaneously and will finish in an
    // order nobody controls. Release-by-depth would then hand thread A's
    // context back while thread B is still filling it.
    //
    // The fix is not per-thread stacks (the first thing that suggests itself) --
    // it is simply to **release by HANDLE**. A free list has no order to get
    // wrong, so interleaved spans across any number of threads are correct
    // without the pool knowing threads exist. Steady-state allocation is still
    // zero: the list grows to the high-water mark of concurrent open operations
    // and stops.
    // ------------------------------------------------------------------------
    protected static fw_op_ctx m_span_free[$];
    protected static int       m_span_live;
    protected static int       m_span_peak;

    static function fw_op_ctx acquire_op_span(int unsigned site_id);
        fw_op_ctx c;
        if (m_span_free.size() == 0) begin
            c = new();
        end else begin
            c = m_span_free.pop_back();
        end
        c.reset(site_id, now());
        c.mark_begun(now());
        m_span_live++;
        if (m_span_live > m_span_peak) m_span_peak = m_span_live;
        return c;
    endfunction

    static function void release_op_span(fw_op_ctx c);
        if (c == null) return;
        c.poison();
        m_span_free.push_back(c);
        m_span_live--;
    endfunction

    // High-water mark of concurrently open operations. A span leak shows up
    // here as unbounded growth long before it shows up as memory, so this is
    // worth being able to ask about.
    static function int span_peak(); return m_span_peak; endfunction
    static function int span_live(); return m_span_live; endfunction

    // Kind-agnostic release, so one `fw_ev_end` closes every site.
    // (`release` is a SystemVerilog keyword -- hence the suffix.)
    static function void release_ctx(fw_dbg_ctx c);
        case (c.kind())
            FW_DBG_OP:       release_op();
            FW_DBG_STATE:    release_state();
            FW_DBG_DECISION: release_decision();
            FW_DBG_SCHED:    release_sched();
            FW_DBG_NOTICE:   release_notice();
            FW_DBG_LINK:     release_link();
            default: ;
        endcase
    endfunction
endclass
