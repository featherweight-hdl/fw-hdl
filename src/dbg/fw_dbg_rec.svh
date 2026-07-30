
// The flat transport record.
//
// This is NOT the in-process API. Components emit by CALLING a listener with a
// borrowed context object (§8.2); the record is what a listener produces when it
// needs to *keep* something -- store it, serialize it, push it into a ring, send
// it across a substrate. `fw_dbg_ctx::snapshot()` is the only place records are
// born on the sim path.
//
// Everything symbolic lives in the site (`fw_dbg_catalog::site(site_id)`), so a
// record is values only: ids, a stamp, the derived flow key, and a positional
// payload. `fields[i]` is named by `site.field_name(i)`.
//
// The kind-discriminated columns (op_phase, outcome, actor, ...) are broken out
// as named members rather than folded into the payload because every decoder,
// filter, and sink needs them and none of them should have to consult a schema
// to find "was this an error". Only site-specific values are positional.
class fw_dbg_rec;
    int unsigned      domain_id = 0;
    int unsigned      site_id   = FW_DBG_NO_SITE;
    fw_dbg_kind_e     kind      = FW_DBG_NOTICE;
    longint           stamp     = 0;     // domain-relative (§7); root_ticks folds
    int               thread_id = 0;

    // The endpoint (channel/port/lane) this event is about, or FW_DBG_NO_SUBJECT.
    // A first-class column rather than a payload field precisely so an offline
    // filter can select on it without consulting a per-site schema -- which is
    // the whole point of pushing filtering downstream.
    int               subject   = FW_DBG_NO_SUBJECT;

    // Derived flow key (§4.1) -- composed of values the hardware itself holds,
    // never an allocation counter, so an RTL stream can compute the same key.
    longint           flow[$];

    // Positional payload; names come from the site's schema.
    longint           fields[$];

    // Span timestamps (OP, close records). `stamp` is when THIS record was
    // produced; these are the operation's own begin and end, carried on the
    // close so a `CLOSE_ONLY` context is still self-sufficient -- otherwise
    // trimming the open records would silently destroy every duration.
    //
    // `accepted` is deliberately NOT here: it is stamped by a DIFFERENT actor
    // (whoever made the work eligible), emitted as its own FW_OP_ACCEPTED
    // record carrying the same derived flow key, and joined downstream. A model
    // that passed a handle between the two actors could not be reconstructed
    // from RTL, which is the whole reason flow keys are derived.
    longint           t_begun    = 0;                // OP (ENDED)
    longint           t_ended    = 0;                // OP (ENDED)

    // Kind-discriminated columns. Meaningful per `kind`; ignored otherwise.
    fw_op_phase_e     op_phase   = FW_OP_BEGUN;      // OP
    fw_op_outcome_e   outcome    = FW_OUT_OK;        // OP (ENDED)
    fw_dbg_actor_e    actor      = FW_ACTOR_HW;      // STATE
    fw_dbg_severity_e severity   = FW_SEV_INFO;      // NOTICE
    fw_sched_kind_e   sched_kind = FW_SCHED_BLOCK;   // SCHED
    fw_dbg_relation_e relation   = FW_REL_CAUSED_BY; // LINK

    function void push_field(longint v);
        fields.push_back(v);
    endfunction

    function void push_flow(longint v);
        flow.push_back(v);
    endfunction

    function fw_dbg_rec copy();
        fw_dbg_rec r = new();
        r.domain_id  = domain_id;
        r.site_id    = site_id;
        r.kind       = kind;
        r.stamp      = stamp;
        r.thread_id  = thread_id;
        r.subject    = subject;
        r.t_begun    = t_begun;
        r.t_ended    = t_ended;
        r.flow       = flow;
        r.fields     = fields;
        r.op_phase   = op_phase;
        r.outcome    = outcome;
        r.actor      = actor;
        r.severity   = severity;
        r.sched_kind = sched_kind;
        r.relation   = relation;
        return r;
    endfunction

    // Human-readable rendering. Joins against the catalog for names -- so this
    // is a *sink-side* operation, never something an emitter does.
    function string to_str();
        fw_dbg_site s = fw_dbg_catalog::site(site_id);
        string      body = "";
        foreach (fields[i]) begin
            body = {body, i == 0 ? "" : " ",
                    $sformatf("%s=%0d", (s != null) ? s.field_name(i) : "?", fields[i])};
        end
        return $sformatf("@%0d [%s] %s(%s)", stamp, kind.name(),
                         (s != null) ? s.name() : "<unknown site>", body);
    endfunction
endclass
