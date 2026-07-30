
// Observable-events vocabulary: kinds, levels, and the small enums that ride in
// event payloads. See docs/fw_hdl_observable_events.md §3 (the taxonomy) and §5
// (control). This file is pure declarations -- no behavior, no dependencies --
// so it is the first thing the package includes.

// --- K1..K7: the kinds ---------------------------------------------------
// The kind is a field in every record AND a bit in the control mask, so a
// consumer can subscribe to (or a context can enable) exactly one class of
// thing. COUNT is an aggregate rather than a stream: a COUNT site maintains a
// counter and emits on demand, so it never appears in a per-event callback.
typedef enum bit [2:0] {
    FW_DBG_OP       = 3'd0,   // operation span:   begin/end + params/results/outcome
    FW_DBG_STATE    = 3'd1,   // state change:     old -> new, by whom, what was dropped
    FW_DBG_DECISION = 3'd2,   // a choice:         winner + why each loser lost
    FW_DBG_SCHED    = 3'd3,   // process lifecycle: fork/retire/block/wake
    FW_DBG_NOTICE   = 3'd4,   // note/info/warn/error, and tripped assertions
    FW_DBG_LINK     = 3'd5,   // causal edge across threads/components
    FW_DBG_COUNT    = 3'd6    // aggregate (counter/histogram), not a stream
} fw_dbg_kind_e;

// Subscription / enable mask: one bit per kind, bit index == the enum value.
typedef bit [7:0] fw_dbg_kinds_t;

localparam fw_dbg_kinds_t FW_K_NONE     = 8'h00;
localparam fw_dbg_kinds_t FW_K_OP       = 8'h01;
localparam fw_dbg_kinds_t FW_K_STATE    = 8'h02;
localparam fw_dbg_kinds_t FW_K_DECISION = 8'h04;
localparam fw_dbg_kinds_t FW_K_SCHED    = 8'h08;
localparam fw_dbg_kinds_t FW_K_NOTICE   = 8'h10;
localparam fw_dbg_kinds_t FW_K_LINK     = 8'h20;
localparam fw_dbg_kinds_t FW_K_COUNT    = 8'h40;
localparam fw_dbg_kinds_t FW_K_ALL      = 8'h7F;

function automatic fw_dbg_kinds_t fw_dbg_kind_bit(fw_dbg_kind_e k);
    return fw_dbg_kinds_t'(1) << int'(k);
endfunction

// --- Levels --------------------------------------------------------------
// A SITE declares the level it belongs to; a CONTEXT enables everything up to
// (and including) a level. Choosing a site's level is the single most important
// instrumentation decision -- see docs debug/instrumenting.md.
typedef enum int {
    FW_L_OFF    = 0,   // nothing
    FW_L_VITAL  = 1,   // structural bind/resolve, errors, tripped asserts   [always on]
    FW_L_TXN    = 2,   // boundary transactions, transfer start/done, irq moves [default]
    FW_L_OP     = 3,   // chunks, arbitration decisions, block/wake
    FW_L_DETAIL = 4,   // per-beat, per-bus-access, register changes
    FW_L_TRACE  = 5    // loop iterations, clock ticks, everything
} fw_dbg_level_e;

// --- Per-kind payload enums ---------------------------------------------

// An operation carries three timestamps in the general case (UVM's
// accept_tr/begin_tr/end_tr): ACCEPTED = the work became eligible, BEGUN = an
// actor started serving it, ENDED = it finished. `begun - accepted` is
// arbitration/queueing latency, MEASURED rather than inferred. When no distinct
// accepting actor exists, ACCEPTED is simply not emitted and equals BEGUN.
typedef enum bit [1:0] {
    FW_OP_ACCEPTED = 2'd0,
    FW_OP_BEGUN    = 2'd1,
    FW_OP_ENDED    = 2'd2
} fw_op_phase_e;

typedef enum bit [2:0] {
    FW_OUT_OK      = 3'd0,
    FW_OUT_ABORTED = 3'd1,
    FW_OUT_ERROR   = 3'd2,
    FW_OUT_TIMEOUT = 3'd3,
    FW_OUT_STALL   = 3'd4
} fw_op_outcome_e;

// Who moved a value. The distinction is what makes "I wrote it and it didn't
// take" debuggable: a SW write followed by a HW update looks identical in a
// value trace and completely different here.
typedef enum bit [1:0] {
    FW_ACTOR_SW    = 2'd0,
    FW_ACTOR_HW    = 2'd1,
    FW_ACTOR_RESET = 2'd2
} fw_dbg_actor_e;

typedef enum bit [2:0] {
    FW_SEV_NOTE  = 3'd0,
    FW_SEV_INFO  = 3'd1,
    FW_SEV_WARN  = 3'd2,
    FW_SEV_ERROR = 3'd3,
    FW_SEV_FATAL = 3'd4
} fw_dbg_severity_e;

// SCHED sub-kind. FORK/RETIRE bracket a process; BLOCK/WAKE bracket a wait.
typedef enum bit [1:0] {
    FW_SCHED_FORK   = 2'd0,
    FW_SCHED_RETIRE = 2'd1,
    FW_SCHED_BLOCK  = 2'd2,
    FW_SCHED_WAKE   = 2'd3
} fw_sched_kind_e;

// Causal relation for a LINK. Emitted ONLY where the edge is irrecoverable
// offline (§14.13): same-thread nesting is inferable and must not be linked.
typedef enum bit [2:0] {
    FW_REL_CAUSED_BY = 3'd0,
    FW_REL_WOKE      = 3'd1,
    FW_REL_ENABLED   = 3'd2,
    FW_REL_SATISFIES = 3'd3,
    FW_REL_RETRIES   = 3'd4
} fw_dbg_relation_e;

// Record mode (per context, §6). Open+close is the DEFAULT because an open
// record is a live hook -- something a close-only stream structurally cannot
// provide. CLOSE_ONLY is a volume optimization for soak runs and the
// post-mortem ring.
typedef enum bit {
    FW_REC_OPEN_CLOSE = 1'b0,
    FW_REC_CLOSE_ONLY = 1'b1
} fw_dbg_recmode_e;

// Reserved site id. Registration starts at 1 so a default-constructed record
// (site_id == 0) is recognizably empty rather than aliasing a real site.
localparam int unsigned FW_DBG_NO_SITE = 0;

// --- Field types ---------------------------------------------------------
// Every payload value is transported as a `longint`, which is the right choice
// for a uniform record and the wrong one for a consumer trying to read it: a
// stored `-1` is 64 ones, and whether that means -1, 0xff, or 0xffffffff is a
// property of the SOURCE, not of the storage.
//
// So the site schema carries the type per field. This is not a render hint --
// it is the decode contract. An external storage package joins records to the
// catalog and has nothing else to go on, so "width and signedness" has to live
// somewhere, and the catalog is the only place it can live once and not per
// record.
//
// Packed so it costs one byte in the descriptor and lands in a JSON catalog as
// three plain numbers.
typedef struct packed {
    bit [6:0] bits;        // declared width, 1..64
    bit       is_signed;   // interpret the stored longint as two's complement
    bit       is_hex;      // render hint ONLY -- never affects the value
} fw_dbg_ftype_t;

localparam fw_dbg_ftype_t FW_T_none = '{7'd64, 1'b0, 1'b0};   // untyped/legacy

localparam fw_dbg_ftype_t FW_T_b    = '{7'd1,  1'b0, 1'b0};

localparam fw_dbg_ftype_t FW_T_u8   = '{7'd8,  1'b0, 1'b0};
localparam fw_dbg_ftype_t FW_T_u16  = '{7'd16, 1'b0, 1'b0};
localparam fw_dbg_ftype_t FW_T_u32  = '{7'd32, 1'b0, 1'b0};
localparam fw_dbg_ftype_t FW_T_u64  = '{7'd64, 1'b0, 1'b0};

localparam fw_dbg_ftype_t FW_T_i8   = '{7'd8,  1'b1, 1'b0};
localparam fw_dbg_ftype_t FW_T_i16  = '{7'd16, 1'b1, 1'b0};
localparam fw_dbg_ftype_t FW_T_i32  = '{7'd32, 1'b1, 1'b0};
localparam fw_dbg_ftype_t FW_T_i64  = '{7'd64, 1'b1, 1'b0};

localparam fw_dbg_ftype_t FW_T_h8   = '{7'd8,  1'b0, 1'b1};
localparam fw_dbg_ftype_t FW_T_h16  = '{7'd16, 1'b0, 1'b1};
localparam fw_dbg_ftype_t FW_T_h32  = '{7'd32, 1'b0, 1'b1};
localparam fw_dbg_ftype_t FW_T_h64  = '{7'd64, 1'b0, 1'b1};

// Compact spelling for a catalog dump / a decoder's type column: `u32`, `i8`,
// `h64`, `b`. Chosen to match the macro suffix exactly, so a reader who sees
// `h32` in a catalog knows what was written at the site.
function automatic string fw_dbg_ftype_str(fw_dbg_ftype_t t);
    if (t.bits == 1 && !t.is_signed && !t.is_hex) return "b";
    return $sformatf("%s%0d", t.is_hex ? "h" : (t.is_signed ? "i" : "u"), t.bits);
endfunction

// --- Subjects (the per-endpoint axis, §5.1) ------------------------------
// A subject is the small dense index of the ENDPOINT an event is about: which
// channel, port, lane, agent. It is a separate axis from the site and from the
// domain, and it has to be, because the events that most need this filter are
// emitted from ONE site in a SHARED context -- `de.arb` decides for all channels
// at one source location inside the engine. Neither a level, a kind, a site glob
// nor a domain path can say "only the rounds that granted channel 2"; only a
// value can.
//
// Deliberately an index, not a general predicate. It costs one shift and one
// mask test, it survives into the record for post-process filtering, and it is
// the axis hardware models actually repeat. A predicate would be more general
// and would put arbitrary code on the emit path, which is the one thing the
// facility promises not to do.
localparam int     FW_DBG_NO_SUBJECT = -1;                    // "this event has no endpoint"
localparam longint FW_DBG_SUBJ_ALL   = 64'hffff_ffff_ffff_ffff;
localparam int     FW_DBG_MAX_SUBJECT = 63;                   // one bit per subject in the mask
