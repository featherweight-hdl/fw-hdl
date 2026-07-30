
`ifndef INCLUDED_FW_DBG_MACROS_SVH
`define INCLUDED_FW_DBG_MACROS_SVH

// ----------------------------------------------------------------------
// Observable-events macros: the compile-time gate and the site declaration.
//
// See docs/fw_hdl_observable_events.md §5 (control) and the companion
// docs/wb_dma_spl_debug_domain_design.md §6 (the efficiency contract).
//
// THE LOAD-BEARING RULE, restated because every macro added here must obey it:
//
//     Argument expressions live INSIDE the enable test.
//
// Payloads call `regs.csr.read()` and build ready-vectors -- not free. The
// begin/param/end shape exists so that the whole block, argument evaluation
// included, sits inside the `if`. A macro that evaluates an argument in order to
// decide whether to emit has broken the facility.
//
// --- Two switches, and why ---------------------------------------------------
//
//   `FW_TRACE_OFF            hard compile-out. Every site vanishes: no port, no
//                            branch, no field, no static variable. This is
//                            invariant G1 and the silicon/production default.
//
//   `FW_TRACE_LEVEL  (0..5)  static ceiling WITHIN a compiled-in build. A site
//                            declared above the ceiling folds to `if (0)` and is
//                            dead-code-eliminated; its site descriptor remains
//                            (and is still catalogued, which is correct -- the
//                            catalog describes the image).
//
// The design doc writes the compile-out condition as "FW_TRACE_LEVEL == 0". It
// is realized as a separate `FW_TRACE_OFF` because the SystemVerilog
// preprocessor cannot compare numbers: `ifdef` is the only static test
// available, so the all-or-nothing switch has to be a distinct symbol from the
// numeric ceiling. Builds that want zero residue define FW_TRACE_OFF.
// ----------------------------------------------------------------------

`ifndef FW_TRACE_LEVEL
  // Compiled in by default. The runtime default is still "every context
  // disabled", so an unconfigured build pays only the disabled-site cost that
  // the T4 gate bounds.
  `define FW_TRACE_LEVEL 5
`endif

// Statically true iff a site at level LVL survives the compile-time ceiling.
// A constant expression, so the elaborator folds it away.
`define fw_dbg_static_on(LVL) ((LVL) <= `FW_TRACE_LEVEL)

`ifdef FW_TRACE_OFF

  // Compiled out: nothing at all is left behind.
  `define fw_dbg_site_decl(VAR, NAME, KIND, LVL)
  `define fw_dbg_site_inst(VAR, NAME, KIND, LVL)

`else

  // Declare THE static descriptor for one instrumentation site and bind its id
  // to VAR. Place it at the point of use, immediately above the emit:
  //
  //     task service_chunk(int ch, int n);
  //         `fw_dbg_site_decl(SID_CHUNK, "chunk", FW_DBG_OP, FW_L_OP)
  //         `fw_op_begin(m_dbg, SID_CHUNK)
  //             ...
  //
  // The initializer runs ONCE, before time 0, in declaration order -- see the
  // header of fw_dbg_catalog.svh for why that idiom was chosen over a sentinel.
  // VAR is therefore a plain load at the site, with no registration test in
  // front of the enable gate.
  //
  // In a `begin`/`end` block or an automatic task/function, `static` is what
  // makes this one descriptor per SITE rather than one per activation. Do not
  // drop the keyword.
  `define fw_dbg_site_decl(VAR, NAME, KIND, LVL) \
      static int unsigned VAR = fw_dbg_catalog::register_site( \
          NAME, KIND, LVL, `__FILE__, `__LINE__);

  // An INSTANCE site: an assignment, not a declaration, made from a
  // constructor. Widens "site" from "one source location" to "one static,
  // elaboration-time entity with a stable name" -- which a named model object
  // like a register also is.
  //
  // The gain is concrete: a register's change event says `csr` rather than
  // `fw_reg.change(off=8)`, so no second artifact is needed to read the stream,
  // and per-site gating can address one register. The cost is a catalog entry
  // per register, which is elaboration-time and bounded.
  //
  // Instance sites register DURING elaboration, after any pre-start apply().
  // fw_component_root::start() re-applies once connect is done so they are not
  // born disabled.
  `define fw_dbg_site_inst(VAR, NAME, KIND, LVL) \
      VAR = fw_dbg_catalog::register_site(NAME, KIND, LVL, `__FILE__, `__LINE__);

`endif /* FW_TRACE_OFF */

// ----------------------------------------------------------------------
// Borrowed-context check.
//
// Defined in BOTH build modes: the listener API and the context classes exist
// whether or not any site does, so consumer code that names them still
// compiles under FW_TRACE_OFF.
//
// Under `FW_DBG_DEBUG` the pool poisons a context when the callback returns and
// every accessor checks, so a listener that squirrels away the handle fails at
// its first read instead of silently reporting some later event's data. Off by
// default: this is a per-accessor branch, and the rule it enforces is a
// development-time mistake, not a production one.
// ----------------------------------------------------------------------
`ifdef FW_DBG_DEBUG
  `define fw_dbg_live \
      if (m_poisoned) begin \
          fw_dbg_ctx::note_use_after_release(); \
      end
`else
  `define fw_dbg_live
`endif

`ifdef FW_TRACE_OFF

// ======================================================================
// Compiled out. Every site vanishes: no gate, no context, no argument
// evaluation, no static descriptor. `fw_assert` does not even test its
// condition -- an assertion that costs something in a production build is a
// production feature, not an assertion.
// ======================================================================
`define fw_ev_op(DOM, LVL, NM, PHASE)
`define fw_ev_state(DOM, LVL, NM)
`define fw_ev_decision(DOM, LVL, NM)
`define fw_ev_sched(DOM, LVL, NM)
`define fw_ev_notice(DOM, SEV, LVL, NM)
`define fw_ev_link(DOM, LVL, NM)
`define fw_ev_state_at(DOM, SID)
`define fw_ev_decision_at(DOM, SID)
`define fw_ev_notice_at(DOM, SEV, SID)
`define fw_ev_sched_at(DOM, SID)
`define fw_ev_end

`define fw_op_span(H)
`define fw_op_begin(DOM, LVL, NM, H)
`define fw_op_opened
`define fw_op_close(DOM, H)
`define fw_op_end(H)
`define fw_op_accept(DOM, LVL, NM)
`define fw_op_flow(V)
`define fw_op_retag(H, V)
`define fw_op_subject(H, V)

`define fw_track_enter(SID)
`define fw_track_exit

`define fw_subject(V)
`define fw_field(V)
`define fw_field_as(NM, V)
`define fw_field_hex(NM, V)
`define fw_field_t(T, NM, V)
`define fw_field_b(V)
`define fw_field_b_as(NM, V)
`define fw_field_u8(V)
`define fw_field_u8_as(NM, V)
`define fw_field_u16(V)
`define fw_field_u16_as(NM, V)
`define fw_field_u32(V)
`define fw_field_u32_as(NM, V)
`define fw_field_u64(V)
`define fw_field_u64_as(NM, V)
`define fw_field_i8(V)
`define fw_field_i8_as(NM, V)
`define fw_field_i16(V)
`define fw_field_i16_as(NM, V)
`define fw_field_i32(V)
`define fw_field_i32_as(NM, V)
`define fw_field_i64(V)
`define fw_field_i64_as(NM, V)
`define fw_field_h8(V)
`define fw_field_h8_as(NM, V)
`define fw_field_h16(V)
`define fw_field_h16_as(NM, V)
`define fw_field_h32(V)
`define fw_field_h32_as(NM, V)
`define fw_field_h64(V)
`define fw_field_h64_as(NM, V)
`define fw_op_outcome(O)
`define fw_op_tag(V)
`define fw_state_change(O, N, ACTOR, DROPPED)
`define fw_dec_winner(W)
`define fw_dec_cand(C, R)
`define fw_sched_set(K, DT, WAKER)
`define fw_sched_src(SID)
`define fw_link_set(F, T, REL)

`define fw_note_begin(DOM, NM)
`define fw_info_begin(DOM, NM)
`define fw_warn_begin(DOM, NM)
`define fw_error_begin(DOM, NM)
`define fw_assert_begin(DOM, COND, NM)
`define fw_assert_end

`define fw_note(DOM, NM)
`define fw_info(DOM, NM)
`define fw_warn(DOM, NM)
`define fw_error(DOM, NM)
`define fw_assert(DOM, COND, NM)

`else

// ======================================================================
// The emit sites.
//
// Every one has the same three-part shape, and the shape is the contract:
//
//     `fw_ev_<kind>(dom, level, "name")   -- declare the site, take the gate
//         `fw_field(x)  `fw_field(n)      -- payload: INSIDE the gate
//     `fw_ev_end                          -- deliver, release the context
//
// Because the payload statements sit inside the `if`, a disabled site evaluates
// NONE of them -- and the payloads in this codebase call `.read()` on registers
// and build ready-vectors, so that is the difference between "debug is free when
// off" and "debug is a tax you always pay".
//
// DOM is a listener handle (typically a component's `dbg` port `.t`). It is
// loaded once into a local; a null domain is simply not emitted into, which is
// what makes an unwired model cost one predicted branch rather than a crash.
//
// --- Why the locals are declared and then ASSIGNED, never initialized --------
//
// `fw_dbg_listener_if __fw_l = (DOM);` reads better and is a latent bug. A
// declaration WITH AN INITIALIZER inside a `begin`/`end` block has **static**
// lifetime unless the enclosing scope is automatic -- so in a module `initial`
// or `always` block it is evaluated ONCE, before time 0, and every later pass
// silently reuses that first value. An emit site written directly in an
// `initial` block would acquire one context at time 0 and hand out the same
// stale handle for the rest of the run: no error, no crash, just records
// carrying the wrong timestamp and the wrong payload.
//
// Class methods and tasks/functions are automatic by default, which is where
// essentially all real instrumentation lives -- which is exactly what makes the
// failure rare enough to be nasty. Splitting declaration from assignment costs
// nothing and removes the trap entirely, so the macros do that and callers do
// not have to know any of this.
//
// `fw_ev_end` is kind-agnostic: the context dispatches itself through
// `deliver()`, and the pool releases by kind. So adding a kind touches the
// classes and nothing here.
// ======================================================================

// Close a site: apply the subject filter, deliver, release.
//
// The subject test is written so that a site which named no endpoint pays ONE
// signed compare against a local -- no virtual call, no array load. That matters
// because the overwhelming majority of sites have no endpoint axis, and the
// filter must not tax them for a feature they do not use.
`define fw_ev_end \
            if (__fw_c.subject() < 0 || __fw_l.enabled_subj(__fw_sid, __fw_c.subject())) begin \
                __fw_c.deliver(__fw_l); \
            end \
            fw_dbg_pool::release_ctx(__fw_c); \
        end \
    end

`define fw_ev_op(DOM, LVL, NM, PHASE) \
    begin \
        `fw_dbg_site_decl(__fw_sid, NM, FW_DBG_OP, LVL) \
        fw_dbg_listener_if __fw_l; \
        fw_op_ctx          __fw_c; \
        __fw_l = (DOM); \
        if (`fw_dbg_static_on(LVL) && __fw_l != null && __fw_l.enabled(__fw_sid)) begin \
            __fw_c = fw_dbg_pool::acquire_op(__fw_sid); \
            __fw_c.set_phase(PHASE);

`define fw_ev_state(DOM, LVL, NM) \
    begin \
        `fw_dbg_site_decl(__fw_sid, NM, FW_DBG_STATE, LVL) \
        fw_dbg_listener_if __fw_l; \
        fw_state_ctx       __fw_c; \
        __fw_l = (DOM); \
        if (`fw_dbg_static_on(LVL) && __fw_l != null && __fw_l.enabled(__fw_sid)) begin \
            __fw_c = fw_dbg_pool::acquire_state(__fw_sid);

`define fw_ev_decision(DOM, LVL, NM) \
    begin \
        `fw_dbg_site_decl(__fw_sid, NM, FW_DBG_DECISION, LVL) \
        fw_dbg_listener_if __fw_l; \
        fw_decision_ctx    __fw_c; \
        __fw_l = (DOM); \
        if (`fw_dbg_static_on(LVL) && __fw_l != null && __fw_l.enabled(__fw_sid)) begin \
            __fw_c = fw_dbg_pool::acquire_decision(__fw_sid);

`define fw_ev_sched(DOM, LVL, NM) \
    begin \
        `fw_dbg_site_decl(__fw_sid, NM, FW_DBG_SCHED, LVL) \
        fw_dbg_listener_if __fw_l; \
        fw_sched_ctx       __fw_c; \
        __fw_l = (DOM); \
        if (`fw_dbg_static_on(LVL) && __fw_l != null && __fw_l.enabled(__fw_sid)) begin \
            __fw_c = fw_dbg_pool::acquire_sched(__fw_sid);

`define fw_ev_notice(DOM, SEV, LVL, NM) \
    begin \
        `fw_dbg_site_decl(__fw_sid, NM, FW_DBG_NOTICE, LVL) \
        fw_dbg_listener_if __fw_l; \
        fw_notice_ctx      __fw_c; \
        __fw_l = (DOM); \
        if (`fw_dbg_static_on(LVL) && __fw_l != null && __fw_l.enabled(__fw_sid)) begin \
            __fw_c = fw_dbg_pool::acquire_notice(__fw_sid); \
            __fw_c.set_severity(SEV);

`define fw_ev_link(DOM, LVL, NM) \
    begin \
        `fw_dbg_site_decl(__fw_sid, NM, FW_DBG_LINK, LVL) \
        fw_dbg_listener_if __fw_l; \
        fw_link_ctx        __fw_c; \
        __fw_l = (DOM); \
        if (`fw_dbg_static_on(LVL) && __fw_l != null && __fw_l.enabled(__fw_sid)) begin \
            __fw_c = fw_dbg_pool::acquire_link(__fw_sid);

// --- emitting at a PRE-REGISTERED site -----------------------------------
// The `_at` forms take an instance site id (see `fw_dbg_site_inst) instead of
// declaring a static one. Same gate, same shape, same rule about payload
// expressions living inside the `if`. The compile-time level ceiling does not
// apply -- the level lives in the site descriptor, which the preprocessor cannot
// see -- so these are trimmed at run time only.

`define fw_ev_state_at(DOM, SID) \
    begin \
        fw_dbg_listener_if __fw_l; \
        int unsigned       __fw_sid; \
        fw_state_ctx __fw_c; \
        __fw_l   = (DOM); \
        __fw_sid = (SID); \
        if (__fw_l != null && __fw_l.enabled(__fw_sid)) begin \
            __fw_c = fw_dbg_pool::acquire_state(__fw_sid);

`define fw_ev_decision_at(DOM, SID) \
    begin \
        fw_dbg_listener_if __fw_l; \
        int unsigned       __fw_sid; \
        fw_decision_ctx __fw_c; \
        __fw_l   = (DOM); \
        __fw_sid = (SID); \
        if (__fw_l != null && __fw_l.enabled(__fw_sid)) begin \
            __fw_c = fw_dbg_pool::acquire_decision(__fw_sid);

`define fw_ev_notice_at(DOM, SEV, SID) \
    begin \
        fw_dbg_listener_if __fw_l; \
        int unsigned       __fw_sid; \
        fw_notice_ctx      __fw_c; \
        __fw_l   = (DOM); \
        __fw_sid = (SID); \
        if (__fw_l != null && __fw_l.enabled(__fw_sid)) begin \
            __fw_c = fw_dbg_pool::acquire_notice(__fw_sid); \
            __fw_c.set_severity(SEV);

`define fw_ev_sched_at(DOM, SID) \
    begin \
        fw_dbg_listener_if __fw_l; \
        int unsigned       __fw_sid; \
        fw_sched_ctx __fw_c; \
        __fw_l   = (DOM); \
        __fw_sid = (SID); \
        if (__fw_l != null && __fw_l.enabled(__fw_sid)) begin \
            __fw_c = fw_dbg_pool::acquire_sched(__fw_sid);

// --- OPERATIONS: spans that outlive the callback ------------------------
//
// An event borrows a context for one callback. An OPERATION does not: its body
// consumes time, so its identity and payload have to survive across a yield.
// The span macros therefore CHECK OUT a context (`acquire_op_span`) and hold it
// in a caller-declared handle until the close.
//
//     `fw_op_span(op)                                 // declare the handle
//     ...
//     `fw_op_begin(dbg_if(), FW_L_OP, "de.chunk", op)
//         `fw_op_flow(ch)  `fw_op_flow(arm_cnt)       // the DERIVED join key
//         `fw_field_as("words", n)                    // parameters
//     `fw_op_opened
//         ... body; may consume time, may block ...
//     `fw_op_close(dbg_if(), op)
//         `fw_field_as("moved", done)                 // results
//         `fw_op_outcome(FW_OUT_OK)
//     `fw_op_end(op)
//
// Three properties that are the whole reason for this shape:
//
//   1. **The handle IS the enable state.** `op` is null when the site was
//      disabled at open, so the close is skipped by a null test rather than by
//      re-asking the gate. An `apply()` that lands mid-operation therefore
//      cannot produce a half-closed span -- an operation is opened and closed
//      under one decision.
//   2. **Payloads on both halves stay inside the gate** (G2). `fw_op_begin`
//      opens an `if`, `fw_op_opened` closes it; `fw_op_close` opens another,
//      `fw_op_end` closes it. Neither block's argument expressions run when the
//      site is off.
//   3. **Depth, parent and duration are never emitted** (G5/§14.13). They are
//      inferable: nesting from the thread id and the open/close order, duration
//      from the two timestamps the close carries. `fw_dbg_track` keeps the live
//      version for the hang dump; the stream stays minimal.
//
// `fw_op_end` takes the handle back so it can null it. That looks redundant
// next to `fw_op_close(dom, op)` and is not: without it the handle dangles at a
// context the pool has already recycled, which is the single nastiest bug this
// mechanism can produce.
`define fw_op_span(H) fw_op_ctx H = null;

`define fw_op_begin(DOM, LVL, NM, H) \
    begin \
        `fw_dbg_site_decl(__fw_sid, NM, FW_DBG_OP, LVL) \
        fw_dbg_listener_if __fw_l; \
        fw_op_ctx          __fw_c; \
        __fw_l = (DOM); \
        H = null; \
        if (`fw_dbg_static_on(LVL) && __fw_l != null && __fw_l.enabled(__fw_sid)) begin \
            __fw_c = fw_dbg_pool::acquire_op_span(__fw_sid); \
            H = __fw_c;

// Emit the open record -- unless this context is CLOSE_ONLY, in which case the
// span still runs and still times itself; only the record is trimmed.
`define fw_op_opened \
            if (__fw_l.emit_open() && \
                (__fw_c.subject() < 0 || __fw_l.enabled_subj(__fw_sid, __fw_c.subject()))) begin \
                __fw_c.set_phase(FW_OP_BEGUN); \
                __fw_c.deliver(__fw_l); \
            end \
        end \
    end

`define fw_op_close(DOM, H) \
    begin \
        fw_dbg_listener_if __fw_l; \
        fw_op_ctx          __fw_c; \
        __fw_l = (DOM); \
        if ((H) != null) begin \
            __fw_c = (H); \
            __fw_c.mark_ended(fw_dbg_pool::now()); \
            __fw_c.set_phase(FW_OP_ENDED);

`define fw_op_end(H) \
            if (__fw_l != null && \
                (__fw_c.subject() < 0 || \
                 __fw_l.enabled_subj(__fw_c.site_id(), __fw_c.subject()))) begin \
                __fw_c.deliver(__fw_l); \
            end \
            fw_dbg_pool::release_op_span(__fw_c); \
            H = null; \
        end \
    end

// A DERIVED flow key component (§4.1): composed of values the hardware itself
// holds -- {channel, arm_count, chunk_idx} -- never an allocation counter,
// because an RTL stream has no such counter and the two could then never be
// joined. Push them in a fixed order; the tuple is the join key.
`define fw_op_flow(V) __fw_c.tag(longint'(V));

// Retro-tagging (§4): an operation may begin before its dynamic identity is
// known. A tag applied after `fw_op_opened` lands on the CLOSE record only --
// the open one has already gone out, which is the honest behavior and the
// reason the open record carries whatever was known at entry.
`define fw_op_retag(H, V) if ((H) != null) (H).tag(longint'(V));

// Name a span's endpoint after the fact, for the same reason as `fw_op_retag`:
// an arbitration round does not know which channel it is about until it has
// decided. Goes through a macro rather than `op.set_subject(x)` so it leaves no
// residue under FW_TRACE_OFF -- where the handle does not exist at all.
`define fw_op_subject(H, V) if ((H) != null) (H).set_subject(int'(V));

// The ACCEPTED phase: a point event emitted by whoever makes the work ELIGIBLE,
// which is a different actor from whoever serves it (§14.10). It carries the
// same derived flow key, and `begun - accepted` -- queueing/arbitration latency,
// MEASURED rather than inferred -- falls out of the join downstream. No handle
// passes between the two actors, deliberately: a handoff would be
// unreconstructible from RTL.
`define fw_op_accept(DOM, LVL, NM) `fw_ev_op(DOM, LVL, NM, FW_OP_ACCEPTED)

// --- the live view (fw_dbg_track) --------------------------------------
// NOT an event. These maintain the state that answers "what is everyone
// waiting for right now", which no stream can answer because the answer is the
// absence of records. Separate from the emit macros on purpose: the gate is a
// different one (fw_dbg_track::on(), a single static bit) and the cost model is
// different (per operation, not per listener).
//
// Deliberately not named `fw_op_begin/end`: those belong to D-5's real
// operations, which emit. These only push and pop.
`define fw_track_enter(SID) fw_dbg_track::push_op(SID);
`define fw_track_exit       fw_dbg_track::pop_op();

// --- payload -----------------------------------------------------------
//
// Every field macro routes through ONE core, `fw_field_t(TYPE, NAME, VALUE)`,
// which does two things worth stating:
//
//   1. **The name is passed only while the schema is being written.** A site's
//      field names are recorded once, on the first activation that reaches
//      them, and read from the catalog forever after -- so passing the string on
//      every push would be paying, per event, for information already stored.
//      `de.beat` fires per transferred word with three fields; that is three
//      string copies per word for nothing. The `need_schema()` test costs one
//      predictable branch and is false after the first activation.
//   2. **The type is the decode contract, not decoration.** Values travel as
//      `longint`. A stored -1 is 64 ones, and whether that means -1, 0xff or
//      0xffffffff is a property of the source. An external consumer joining
//      records to the catalog has nothing else to go on, so width and
//      signedness have to be written down -- once, in the schema.
//
// VALUE appears twice in the expansion but is evaluated once (only one branch
// runs). Payload expressions with side effects were already a bug.
// Name the ENDPOINT this event is about -- the channel, port, lane or agent.
// A filtering axis, not a payload: it is a first-class column in the record, so
// `only channel 2` is answerable both at run time (via `cfg_subjects`) and
// offline, without either consumer knowing the site's field schema.
//
// Emit it as WELL AS the value's payload field where a reader wants to see it;
// the subject is a coordinate, and coordinates are cheap.
`define fw_subject(V)       __fw_c.set_subject(int'(V));

`define fw_field_t(T, NM, V) \
    if (__fw_c.need_schema()) __fw_c.push_named(NM, longint'(V), T); \
    else                      __fw_c.push(longint'(V));

// --- the compact forms -------------------------------------------------
//
//     `fw_field_u32(words)              -- name "words", 32-bit unsigned
//     `fw_field_h32_as("addr", w_src)   -- name "addr",  32-bit, hex
//
// The suffix IS the type, and it is the same spelling a catalog dump prints, so
// what you wrote at the site is what a decoder reports. `b` is one bit;
// `u`/`i`/`h` are unsigned decimal, signed decimal, and hex.
//
// The bare-operand forms name the field with the operand's own source text,
// resolved by the preprocessor -- free, and exactly right when the local is
// already called what the field should be called. Use the `_as` form when it is
// not: `c` is a fine name for a loop variable and a poor one for a field.
`define fw_field_b(V)        `fw_field_t(FW_T_b, `"V`", V)
`define fw_field_b_as(NM, V) `fw_field_t(FW_T_b, NM, V)
`define fw_field_u8(V)        `fw_field_t(FW_T_u8, `"V`", V)
`define fw_field_u8_as(NM, V) `fw_field_t(FW_T_u8, NM, V)
`define fw_field_u16(V)        `fw_field_t(FW_T_u16, `"V`", V)
`define fw_field_u16_as(NM, V) `fw_field_t(FW_T_u16, NM, V)
`define fw_field_u32(V)        `fw_field_t(FW_T_u32, `"V`", V)
`define fw_field_u32_as(NM, V) `fw_field_t(FW_T_u32, NM, V)
`define fw_field_u64(V)        `fw_field_t(FW_T_u64, `"V`", V)
`define fw_field_u64_as(NM, V) `fw_field_t(FW_T_u64, NM, V)
`define fw_field_i8(V)        `fw_field_t(FW_T_i8, `"V`", V)
`define fw_field_i8_as(NM, V) `fw_field_t(FW_T_i8, NM, V)
`define fw_field_i16(V)        `fw_field_t(FW_T_i16, `"V`", V)
`define fw_field_i16_as(NM, V) `fw_field_t(FW_T_i16, NM, V)
`define fw_field_i32(V)        `fw_field_t(FW_T_i32, `"V`", V)
`define fw_field_i32_as(NM, V) `fw_field_t(FW_T_i32, NM, V)
`define fw_field_i64(V)        `fw_field_t(FW_T_i64, `"V`", V)
`define fw_field_i64_as(NM, V) `fw_field_t(FW_T_i64, NM, V)
`define fw_field_h8(V)        `fw_field_t(FW_T_h8, `"V`", V)
`define fw_field_h8_as(NM, V) `fw_field_t(FW_T_h8, NM, V)
`define fw_field_h16(V)        `fw_field_t(FW_T_h16, `"V`", V)
`define fw_field_h16_as(NM, V) `fw_field_t(FW_T_h16, NM, V)
`define fw_field_h32(V)        `fw_field_t(FW_T_h32, `"V`", V)
`define fw_field_h32_as(NM, V) `fw_field_t(FW_T_h32, NM, V)
`define fw_field_h64(V)        `fw_field_t(FW_T_h64, `"V`", V)
`define fw_field_h64_as(NM, V) `fw_field_t(FW_T_h64, NM, V)

// --- untyped forms (pre-existing; still valid) -------------------------
// No width or signedness is declared, so a decoder sees `u64`. Prefer a typed
// form when the width is known -- which, in hardware, it always is.
`define fw_field(V)         `fw_field_t(FW_T_none, `"V`", V)
`define fw_field_as(NM, V)  `fw_field_t(FW_T_none, NM, V)
`define fw_field_hex(NM, V) `fw_field_t(FW_T_h64,  NM, V)

// --- per-kind payload --------------------------------------------------
`define fw_op_outcome(O)                      __fw_c.set_outcome(O);
`define fw_op_tag(V)                          __fw_c.tag(V);
`define fw_state_change(O, N, ACTOR, DROPPED) __fw_c.set_change((O), (N), (ACTOR), (DROPPED));
`define fw_dec_winner(W)                      __fw_c.set_winner(W);
`define fw_dec_cand(C, R)                     __fw_c.add_candidate((C), (R));
`define fw_sched_set(K, DT, WAKER)            __fw_c.set_sched((K), (DT), (WAKER));
`define fw_sched_src(SID)                     __fw_c.add_source(SID);
`define fw_link_set(F, T, REL)                __fw_c.set_link((F), (T), (REL));

// --- the K5 family -----------------------------------------------------
// The message IS the site name, so it is a compile-time constant that lives in
// the catalog -- there is no runtime string anywhere on this path. Operands ride
// as fields via `fw_field`, which is why the *_begin forms exist: a diagnostic
// worth emitting is usually worth emitting WITH the values that produced it.
`define fw_note_begin(DOM, NM)  `fw_ev_notice(DOM, FW_SEV_NOTE,  FW_L_TRACE, NM)
`define fw_info_begin(DOM, NM)  `fw_ev_notice(DOM, FW_SEV_INFO,  FW_L_TXN,   NM)
`define fw_warn_begin(DOM, NM)  `fw_ev_notice(DOM, FW_SEV_WARN,  FW_L_VITAL, NM)
`define fw_error_begin(DOM, NM) `fw_ev_notice(DOM, FW_SEV_ERROR, FW_L_VITAL, NM)

`define fw_note(DOM, NM)  `fw_note_begin(DOM, NM)  `fw_ev_end
`define fw_info(DOM, NM)  `fw_info_begin(DOM, NM)  `fw_ev_end
`define fw_warn(DOM, NM)  `fw_warn_begin(DOM, NM)  `fw_ev_end
`define fw_error(DOM, NM) `fw_error_begin(DOM, NM) `fw_ev_end

// An assertion emits ONLY when it trips, and carries operand images rather than
// a pre-formatted string. The condition is evaluated unconditionally (that is
// what an assertion is); everything else is behind the gate.
`define fw_assert_begin(DOM, COND, NM) \
    if (!(COND)) begin \
        `fw_error_begin(DOM, NM)

`define fw_assert_end \
        `fw_ev_end \
    end

`define fw_assert(DOM, COND, NM) `fw_assert_begin(DOM, COND, NM) `fw_assert_end

`endif /* FW_TRACE_OFF */

`endif /* INCLUDED_FW_DBG_MACROS_SVH */
