
typedef class fw_op_ctx;
typedef class fw_state_ctx;
typedef class fw_decision_ctx;
typedef class fw_sched_ctx;
typedef class fw_notice_ctx;
typedef class fw_link_ctx;

// The debug API: ONE interface class for every hop.
//
// Implemented by SINKS, by transform/tag/filter/replicate DOMAINS, and by
// anything else that wants to watch a model -- so component -> domain,
// domain -> domain, and domain -> sink are all the same call. The unification is
// the point: **a domain IS a listener that forwards to other listeners.**
// Tagging, filtering, merging (N->1) and replicating (1->N) are listener bodies,
// not separate mechanisms.
//
// This REPLACES the flat `emit(fw_dbg_rec)` of the companion transport doc §4.1.
// A record is what a *serializing* listener produces (`fw_dbg_ctx::snapshot()`);
// it is not the in-process interface. Collapsing the two costs nothing -- a
// context is one handle, and its fields are the same stores a packed record
// would take -- and buys typed, named access for the consumers that live in the
// same process: scoreboards, checkers, coverage, reference models.
//
// --- The contract -----------------------------------------------------------
//   * NON-BLOCKING. These are `function`s, not `task`s, so the compiler enforces
//     it: a listener cannot consume time and therefore cannot stall a producer.
//     Backpressure is drop-with-lost-count at a merge node, never a stall.
//   * The context is BORROWED -- valid only for the duration of the callback.
//     Call `snapshot()` to keep anything.
//   * Do not mutate the context; do not call back into the model.
//   * The one sanctioned exception: a debug-only sink may halt the simulator at
//     `on_op(BEGUN)` (the pre-operation breakpoint, design §6.1). That stops
//     everything, so it perturbs no model-level ordering.
interface class fw_dbg_listener_if;
    pure virtual function void on_op      (fw_op_ctx       op);   // phase is in the ctx
    pure virtual function void on_state   (fw_state_ctx    st);
    pure virtual function void on_decision(fw_decision_ctx d);
    pure virtual function void on_sched   (fw_sched_ctx    sc);
    pure virtual function void on_notice  (fw_notice_ctx   n);
    pure virtual function void on_link    (fw_link_ctx     l);

    // The gate. Cheap and side-effect free: one bounds check and one array load
    // against a table recomputed at `apply()`, never a string compare or a map
    // lookup. EVERY payload expression at a site sits behind this, which is why
    // it must never be expensive enough to be worth caching at the site.
    pure virtual function bit enabled(int unsigned site_id);

    // The SUBJECT gate: a second, value-based question asked only of events that
    // named an endpoint (`fw_subject), and only after `enabled()` already said
    // yes. Sites that name no subject never reach it -- the emit macro
    // short-circuits on `subject() < 0` -- so this costs nothing for the vast
    // majority of instrumentation.
    //
    // It exists because the site axis and the domain axis both fail for the case
    // that actually hurts: one site, in one context, deciding about N endpoints.
    // Filtering `de.arb` down to "grants to channels 1..3" is expressible only
    // over the winning VALUE.
    pure virtual function bit enabled_subj(int unsigned site_id, int subject);

    // Should an operation emit its OPEN record, or only its close?
    //
    // Open+close is the default because an open record is a LIVE HOOK -- the
    // pre-operation breakpoint, the "what is running right now" view -- which a
    // close-only stream structurally cannot provide. `FW_REC_CLOSE_ONLY` is the
    // volume trim for soak runs and post-mortem rings, where the stream is read
    // after the fact and the open record's only value has already expired.
    //
    // Asked once per operation, not per record.
    pure virtual function bit emit_open();
endclass
