# Dynamic Functional Coverage in fw-hdl

*Status: design proposal, for review. No implementation yet.*

---

## 1. The thesis

SystemVerilog functional coverage is **static and hand-written**. A covergroup
names a sampling point, enumerates bins, declares crosses, and is sampled by code
someone remembered to write. The cost is paid per design, per register, per
channel, per protocol — and the result measures only what the author thought to
ask about. Everything else is invisible, including the parts of the design the
author did not know existed.

fw-hdl is in an unusual position: **it already holds a machine-readable
description of the model's structure and of everything the model can say about
itself**, built before time 0, with symbolic names and typed field schemas
(`src/dbg/`). That is most of a coverage model. What is missing is not
information — it is the derivation rules and a collector.

The claim this document argues:

> A useful functional coverage model can be **derived**, not declared, from
> fw-hdl's elaboration-time structure; the runtime event stream fills it in at
> zero incremental instrumentation cost; and the resulting metrics sit
> meaningfully **above** code/toggle coverage because they are expressed in the
> model's own vocabulary (registers, transactions, arbitration decisions, wait
> sets, error paths) rather than in lines and nets.

The honest counter-claim, addressed in §9: derived coverage measures **observed
variety**, not **intent**. It is a denominator someone did not have to write, not
a substitute for knowing what matters.

---

## 2. What fw-hdl already knows

Four artifacts exist today. None of them was built for coverage; all four are
coverage inputs.

### 2.1 The component tree and bind map — *structural denominator*

`fw_component` (`src/fw_component.svh`) can already produce
`bind_map_json()`: every component path, its runnable count, and every
port/export endpoint with role, connectedness, provider, and resolution status.
It also knows the clock domain and debug domain each component inherited.

This is the denominator for *reachability*-class metrics: which components,
which endpoints, which providers, which instances of an N-way-replicated bank.

### 2.2 The register model — *access and value denominator*

`fw_reg_base #(W)` (`src/fw_reg_base.svh`) holds, per register: name,
byte offset, reset value, `sw_wmask`, `hw_wmask`, `rclr_mask`. `fw_reg_block`
holds the address map, including nested banks. That is:

- the complete set of legal addresses (so *unvisited registers* is computable);
- per-register, which bits software may write, which hardware owns, which are
  **reserved** (`~sw_wmask & ~hw_wmask`), and which are read-to-clear;
- the reset value, which is the natural "did anything ever move this" reference.

The mask decomposition is the interesting part: it partitions each register into
bit classes that *have different coverage meanings*. A hand-written covergroup
almost never encodes that partition; the register model already does.

### 2.3 The site catalog — *the observable-event schema*

`fw_dbg_catalog` (`src/dbg/fw_dbg_catalog.svh`) holds one `fw_dbg_site`
per instrumentation site in the compiled image, registered before time 0 — **including
sites that never execute**. Each site carries name, kind (OP / STATE / DECISION /
SCHED / NOTICE / LINK / COUNT), level, source file/line, and a positional **field
schema with declared types** (`fw_dbg_ftype_t`: width, signedness, radix).

This is the single most valuable input, and it is worth stating why: the field
schema exists because payload values travel as `longint` and a decoder needs the
width and signedness to interpret them. That same width is exactly what a
coverage engine needs to choose bins. The decode contract and the binning
contract are the same contract.

### 2.4 The runtime event stream — *the sample*

Every enabled event delivers a typed context (`src/dbg/fw_dbg_ctx.svh`) with:

| Column | Available on | Coverage value |
|---|---|---|
| `site_id` | all | which point |
| `ctx()` / domain `path()` | all | per-instance / per-context axis |
| `subject()` | any site that named an endpoint | per-channel/lane/port axis |
| `thread_id`, `stamp` | all | concurrency, ordering, latency |
| `old_val`/`new_val`/`actor`/`dropped` | STATE | value, transition, who moved it |
| `winner`/`candidate(i)`/`reason_of(i)` | DECISION | arbitration, starvation, rejection reasons |
| `phase`/`outcome`/`begun`/`ended`/`flow_key(i)` | OP | transaction outcome, duration, causal join |
| `sched_kind`/`waker`/`source(i)`/`blocked_for` | SCHED | wait-set exercise, block duration |
| `severity` | NOTICE | error-path coverage |
| `relation` | LINK | causal-pair coverage |
| `field_int(i)` + site schema | all | typed payload values |

Note `subject()` specifically. It exists because *one site, in one context,
decides about N endpoints* — and a coverage model built per site would collapse
exactly the axis that matters. A derived model gets the per-endpoint cross for
free, which is the cross a hand-written covergroup usually has to be instantiated
N times to express.

---

## 3. The derivation

A coverage model is four things. Each has a source.

| Coverage concept | Derived from |
|---|---|
| **Sample point** | a site in the catalog (one point per site, per kind) |
| **Bins** | the site's field schema types + the kind's semantics (§7 rules) |
| **Axes / crosses** | `subject`, domain `path`, `actor`, `outcome` — first-class columns, so they cross without a schema lookup |
| **Denominator** | the catalog (all sites, including never-hit), the bind map (all endpoints), the register map (all addresses/bit classes), the declared subject/endpoint count |

The collector is a `fw_dbg_listener`. Nothing on the emit path changes. The
listener base class comment already names this use case:

> *"A coverage collector that only wants arbitration decisions overrides
> `on_decision` and inherits six empty bodies."*

And because the gate is **demand-driven** — a domain enables a site only if some
listener subscribed to its kind and level — attaching a coverage collector
*turns on exactly the sites it needs* and nothing else. A run with no collector
is byte-for-byte the run it was before.

---

## 4. Opportunity catalog

Ordered by (value ÷ effort). Each entry names what is measured, where the
denominator comes from, and why it is above code coverage.

### M1 — Site reachability ("was this ever said?") — *near-free*

The catalog is complete at time 0. The set of sites that never fired in a run (or
across a merged regression) is a first-class result with no bins at all.

Why it beats code coverage: a site is a *semantically chosen* point — an
arbitration round, a decode miss, a timeout path — not a line. "47 of 310 sites
never fired, and 9 of them are error paths" is a report a verification lead can
act on; "line 412 uncovered" is not. It is also the cheapest possible metric: one
bit per site id.

**Sub-metric worth calling out separately: error-path coverage.** Every NOTICE
site with severity ≥ WARN is, by construction, a path the designer marked as
exceptional. The fraction of those ever exercised is a direct measure of negative
testing, and today nobody computes it because nobody enumerates the paths. The
catalog enumerates them.

### M2 — Register access and value coverage — *high value, medium effort*

From the register map (§2.2) plus the STATE/DECISION sites the register model
already emits (`<block>.<reg>` change sites, `<block>.decode`,
`<block>.decode_miss`, `<block>.<reg>.masked`):

- **Access coverage**: each register read / written / neither. Denominator is the
  address map, so *unvisited registers* falls out — including registers that
  exist only in a configuration nobody ran.
- **Actor coverage**: each register moved by SW / HW / RESET. This is the
  `fw_dbg_actor_e` column, and it is not derivable from a value trace.
- **Bit-class coverage**, from the mask partition:
  - every `sw_wmask` bit written 0 and 1 by software;
  - every `hw_wmask` bit written 0 and 1 by hardware;
  - every `rclr_mask` register actually read-to-cleared while non-zero (the RTC
    path is frequently untested);
  - every **reserved** bit written — which already emits the `.masked` warning,
    so the negative case is instrumented today.
- **Contention coverage**: a HW update and a SW write to the same register within
  the same cycle/quantum — the SystemRDL precedence corner, almost never covered
  deliberately.
- **Readback coverage**: SW write → SW read of the same offset, and whether the
  value matched. Derivable by joining `decode` decisions against `.masked` and
  change events per offset.

Effort note: *bit-class* coverage is available today (masks are runtime state);
*field-level* coverage (`ch_en`, `done`, `burst_len`) is not, because
`fw_reg #(T)` knows only `$bits(T)` at runtime. See §10.1 for the fix.

### M3 — State and transition coverage — *high value, low effort*

Every STATE event carries `old_val`, `new_val`, `actor`. That is a value
coverpoint **and an arc coverpoint** with no declaration: transitions are
`(old, new)` pairs, and the set observed is the set of arcs exercised.

For anything that is an FSM in practice — a channel CSR's state field, a
request-state enum, a credit counter — this yields FSM state and arc coverage
*without an FSM having been declared*, and it works identically for state that
lives in a class variable rather than in a register.

Bit-level "every bit of this value toggled both ways" is one OR-accumulate of
`old ^ new` per site: toggle coverage at the *transaction* level of abstraction
rather than the net level, and therefore attributable to a named quantity.

### M4 — Decision / arbitration coverage — *high value, low effort, unique*

DECISION events carry a winner, the candidate list, and **a rejection reason per
loser**. That yields, with no declaration:

- **grant coverage**: every requester won at least once (denominator: the
  observed or declared subject set);
- **rejection-reason coverage**: every reason code the site can produce was
  actually produced — i.e., every path through the arbiter's priority logic;
- **contention-degree bins**: rounds with 1, 2, 3, >3 candidates, crossed with
  the winner. "Channel 7 won, but only ever uncontended" is a real hole and is
  invisible to every other coverage class;
- **fairness/starvation metrics**: max and mean inter-grant gap per subject.
  This is a *metric*, not a bin — see §8 on reporting both.

I know of no mainstream coverage flow that captures rejection reasons, because
nothing else records them. This is the strongest differentiator in the list.

### M5 — Wait-set / scheduling coverage — *medium value, low effort, unique*

A SCHED BLOCK record carries **the source site ids of the wait set**; the matching
WAKE carries **which source woke it**. So the denominator for "every source in
this wait set has, at least once, been the one that woke this thread" is carried
in the event stream itself.

That metric answers a question benches ask constantly and never measure: *did we
ever exercise the path where the timeout fired instead of the completion?* It also
gives per-site block-duration histograms (zero-length blocks — the never-actually-waited
case — are their own bin, and are usually a bug or a missed scenario).

Related and nearly free: **liveness coverage** — `fw_component` registers an
instance site per runnable and emits `run_fork`. Every registered runnable that
never forked, or forked and never emitted again, is reportable. The bind map
supplies the denominator.

### M6 — Operation / transaction coverage — *high value, medium effort*

For every OP span:

- **outcome bins**: OK / ABORTED / ERROR / TIMEOUT / STALL — five bins per site,
  free, and the last three are where the bugs are;
- **duration histograms**: log₂ buckets over `ended - begun`, auto-scaled; the
  interesting bins are the extremes (zero-duration and tail);
- **queueing latency**: `begun - accepted`, joined across actors by the derived
  **flow key**, so it is measured rather than inferred;
- **parameter bins**: typed payload fields binned by §7 rules (size, burst
  length, address alignment);
- **concurrency depth**: how many spans were open at this site simultaneously —
  1 vs. N is the difference between a serialized and a pipelined test;
- **ordering**: completion order vs. begin order per site (out-of-order retire
  observed at least once).

Crossed with `subject` and with domain `path`, this is per-channel transaction
coverage that nobody instantiated per channel.

### M7 — Structural / connectivity coverage — *medium value, medium effort*

The bind map enumerates every endpoint and provider. The metric is: **every
resolved binding was actually used at least once, and every method of the role
API was exercised through it.**

This is genuinely above code coverage: an API method covered through *one*
binding and never through a second binding of the same type is a hole code
coverage cannot see (same lines, different topology).

Caveat, stated plainly: fw-hdl resolves a port into `port.t` and callers invoke
the API directly, so there is no interception point today. Two honest options —
(a) protocols built with **fw-proto-kit** already emit OP spans at the transactor
boundary, so method-level coverage is free *for kit-built protocols*; (b) a
generated counting decorator (`fw_cov_tap #(API)`, emitted by the `` `FW_*_IMP ``
macros) for the general case, opt-in because it costs a virtual call. Recommend
(a) now, (b) only if demand appears.

### M8 — Configuration and topology coverage (cross-run) — *medium value, low effort*

A run's *shape* — parameter values, number of channels, which optional blocks
were built, which clock-domain ratios were configured, which bindings resolved —
is an elaboration-time fact available in the bind map and component params. A
regression's configuration coverage is then "which points in the legal
configuration space did we ever elaborate", which today is tracked in
spreadsheets or not at all.

This one needs no runtime sampling at all: it is produced by elaboration and
merged across runs.

---

## 5. Architecture

```
  elaboration                     run                        post
  ───────────                     ───                        ────
  fw_dbg_catalog ─┐
  bind_map_json  ─┼─► fw_cov_model ──► fw_cov_collector ──► results.json ──► merge
  register map   ─┘    (denominator)    (fw_dbg_listener)     (numerator)      │
  refinement.yaml ─────────┘                   ▲                               ▼
                                               │                          report / UCIS
                                        events from domains
```

Proposed location: `src/cov/`, package `fw_cov_pkg`, depending on `fw_hdl_pkg`.
Nothing in `src/dbg/` changes.

### 5.1 The collector is a listener

```systemverilog
class fw_cov_collector extends fw_dbg_listener;
    protected fw_cov_plan m_plan[];   // indexed by site_id, built at attach()

    virtual function void on_state(fw_state_ctx st);
        fw_cov_plan p = m_plan[st.site_id()];
        if (p == null) return;
        p.sample_value(st.new_val(), st.subject());
        p.sample_arc(st.old_val(), st.new_val());
        p.sample_actor(st.actor());
        p.sample_toggle(st.old_val() ^ st.new_val());
    endfunction
    // ... on_decision / on_op / on_sched / on_notice likewise
endclass
```

Properties this inherits rather than re-invents:

- **Non-blocking by construction** — the listener API is `function`s, so a
  collector cannot perturb model timing. Coverage sampling is a classic source of
  "it only fails with coverage on"; here the compiler forbids it.
- **Zero cost when off** — demand-driven gating; no collector, no enabled sites,
  no argument evaluation.
- **Attachable anywhere, at any depth**, without touching the model — the `dbg`
  port is a built-in observer port on every component. Per-channel coverage
  contexts cost one `connect_up` and no model edits.
- **Subject and domain axes for free**, resolved as integers and paths, no string
  work on the sample path.

### 5.2 Attach, mirroring `fw_dbg_console`

```systemverilog
fw_cov_collector cov = fw_cov::attach(root, "dut");   // null unless +fw_cov
root.start();
...
fw_cov::write("cov.json");
```

Plusargs mirroring the debug console's vocabulary: `+fw_cov`,
`+fw_cov_level=<0..5>`, `+fw_cov_only=<glob>`, `+fw_cov_refine=<file>`,
`+fw_cov_out=<file>`. Same reason: a facility that needs a bench edit is a
facility nobody uses.

Level interacts with cost honestly: register-value coverage lives at
`FW_L_DETAIL`, so asking for M2 asks for detail-level traffic. The collector
subscribes per *kind and level*, so "decisions at OP level only" is expressible
and is the sensible regression default.

### 5.3 The sample path

Per site, a pre-built `fw_cov_plan` holds the bin strategy chosen at attach time
(from the schema — once, not per event). Dense strategies are a bit vector
indexed by value; sparse strategies are an associative array with a cap and an
`others` bin. Crosses are composed as `(bin_idx * n_subjects) + subject`, which
keeps the hot path to an index computation and an increment. No strings, no
`sformatf`, no catalog lookup at sample time — the same discipline the rest of
the facility keeps.

### 5.4 Identity and merging

Bins are keyed **symbolically** — `(domain path, site name, field name, bin
label)` — never by site id, which is a build-order artifact and unstable across
compiles. Merge across runs is then a plain union of counts, done in Python
(`python/fw/cov`), which also renders the report and, optionally, writes UCIS or
a covergroup-shaped view for teams whose signoff tooling demands one.

### 5.5 On `FW_DBG_COUNT`

The kind exists in the taxonomy and has no implementation, no context class, and
no `on_count` in the listener interface. Recommendation: **leave it that way for
now.** Everything in §4 is derivable sink-side from existing kinds; adding an
emit path for aggregates would put counting on the producer's side of the
boundary for no gain. Reserve COUNT for *hand-declared* aggregates later (§10.3).

---

## 6. What this does *not* need

Worth stating, because it is the cost that kills coverage programs:

- no covergroup declarations;
- no per-design sampling code;
- no per-channel/per-bank instantiation (the `subject` and `path` axes replicate
  automatically);
- no changes to any existing model, at all, for M1/M3/M4/M5;
- no simulator coverage licence for the collection itself.

---

## 7. Bin inference rules

Chosen at attach time from the site kind and the field's `fw_dbg_ftype_t`.

| Input | Strategy |
|---|---|
| width 1 | two bins {0, 1}; arcs {0→1, 1→0} |
| width ≤ 6 (≤ 64 values) | one bin per value; arcs recorded up to a cap |
| width > 6, unsigned | {zero, all-ones, reset-value, min-seen, max-seen, powers-of-two boundary, `others`} + per-bit toggle accumulator |
| width > 6, signed | as above plus {negative, positive, sign-flip arc} |
| hex hint | affects rendering only, never binning |
| enum-typed column (`outcome`, `actor`, `severity`, `relation`, `sched_kind`, `op_phase`) | one bin per enumerator — the complete, correct set, known statically |
| `subject` | dense axis, width = max subject seen (or declared; see §10.2) |
| duration / latency | log₂ buckets, plus explicit {0} and {tail} bins |
| candidate/reason lists (DECISION) | reason-code bins per site; winner bins over the subject axis |
| wait-set sources (SCHED) | one bin per source site id present in any BLOCK record |

The `others` bin is mandatory on every sparse strategy, and it is reported: a
point that is 90% `others` is a point whose binning needs refinement, and the
report should say so rather than look green.

**Bin-explosion control** is a first-class rule, not an afterthought: a global
per-site bin cap (default ~256) with the overflow folded into `others`, plus a
total-bin budget that the attach reports if exceeded. Auto-derived models fail by
exploding, so the explosion has to be bounded by construction.

---

## 8. Two kinds of result

The report must separate them, because they answer different questions:

- **Coverage** (bounded, 0–100%): bins hit / bins defined. Meaningful only where
  the denominator is *real* — an enum, a mask partition, an address map, a
  declared endpoint count.
- **Metrics** (unbounded observations): starvation gaps, duration tails,
  concurrency depth, `others` fraction, inter-arrival distributions. These have
  no natural 100%, and forcing them into a percentage is how coverage reports
  become decoration.

A derived model produces a lot of the second kind. Presenting it as the first
kind would be the main way this feature could mislead.

---

## 9. The intent gap (the honest limitation)

Derived coverage tells you **what varied**. It cannot tell you **what should
have varied**. Three specific failure modes and their mitigations:

1. **Vacuous closure.** 100% of derived bins hit can coexist with an unverified
   design, because the bins were chosen by a rule and not by a risk analysis.
   *Mitigation:* report M1-style absences (never-hit sites, never-visited
   registers, never-taken error paths) as the headline; report percentages
   second. The absences are the actionable part.
2. **Noise.** Some sites are uninteresting and their bins dilute the numbers.
   *Mitigation:* a checked-in **refinement file** — the same glob vocabulary as
   `fw_dbg_root::cfg` — carrying exclusions, goals, illegal bins, and explicit
   crosses. Refinement is reviewable, diffable, and accumulates the intent the
   derivation cannot infer.
3. **Drift.** Auto-derived points appear and vanish as instrumentation changes,
   so trends break. *Mitigation:* symbolic keys (§5.4) plus a **promotion path**
   — a derived point that someone has reasoned about gets named in the refinement
   file with a goal, which pins it and makes its disappearance an error.

Stated as a rule: *derivation supplies the denominator nobody wants to write;
refinement supplies the intent only a human has.* The design is worth building
because the first half is the expensive half, and it is the half fw-hdl can
automate.

---

## 10. Dependencies and small additions needed

### 10.1 Register field schemas (needed for M2 field-level coverage)

`fw_reg #(T)` types a register over a packed struct, but SV offers no runtime
introspection of `T`'s members, so field names/offsets are not available to a
collector. Two paths, not exclusive:

- **`` `fw_reg_fields `` macro** — declare `(name, lsb, width)` once at register
  construction, registering them into the register's existing site field schema.
  Cheap, elaboration-time, uses the mechanism already in place.
- **Front-end extraction** — `python/fw/hdl` already parses SV with pyslang and
  recovers packed-struct member layout for synthesis. The same walk can emit the
  field table into the coverage model artifact, with zero SV-side annotation.

Recommend the macro first (works in pure-simulation flows, no toolchain
dependency) and the front-end path as the enrichment.

### 10.2 Declared endpoint counts (improves M4/M6 denominators)

`subject` is an index with no declared cardinality, so "every channel granted"
currently has an *observed* denominator — which silently under-reports when a
channel is never requested at all. A one-line per-site declaration
(`subjects = N`, alongside the existing site registration) turns that into a real
denominator. This is a small addition to `fw_dbg_site` and is the difference
between "all observed channels were granted" and "all 31 channels were granted".

### 10.3 Nothing else

M1, M3, M4, M5, M7(a), M8 need no library changes whatsoever.

---

## 11. The multi-view payoff

`python/fw/hdl` lowers fw-hdl models to synthesizable RTL. If instrumentation
sites lower with the model — and the facility was designed for this, which is why
flow keys are *derived from values the hardware holds* rather than allocated —
then **the TLM view and the RTL view produce streams against the same site
catalog and therefore the same coverage model**.

Two consequences worth the effort on their own:

- **Coverage parity as an equivalence check.** Run the same stimulus against both
  views and diff the coverage models. Bins hit in TLM and not in RTL (or vice
  versa) localize behavioral divergence to a named site — a much sharper signal
  than an output mismatch, and available before any mismatch occurs.
- **Coverage written once.** The refinement file, the goals, and the report apply
  unchanged across views, including a formal view where "unreachable" from the
  prover can retire a derived bin that simulation would chase forever.

This is the part no static covergroup flow can do, because a covergroup is
written against one view's variable names.

---

## 12. Phasing

| Phase | Content | Library changes | Value |
|---|---|---|---|
| **P0** | Catalog + bind-map denominators; hit/never-hit; error-path coverage (M1); JSON out; Python report/merge | none | immediate, days |
| **P1** | Collector + plans; STATE values/arcs/actor/toggle (M3); DECISION winner/reason/contention (M4); SCHED wait-set + liveness (M5); subject & path axes | none | the bulk of the differentiated value |
| **P2** | Register map walk; access/bit-class/RTC/reserved/contention (M2); field schemas (§10.1); refinement file; declared subject counts (§10.2) | `` `fw_reg_fields ``, `fw_dbg_site.subjects` | highest-value domain-specific metrics |
| **P3** | OP spans: outcome/duration/latency/concurrency/ordering (M6); protocol-role coverage via proto-kit spans (M7a); configuration coverage (M8); UCIS/covergroup export; RTL-view parity (§11) | optional `fw_cov_tap` | signoff integration and cross-view |

Each phase is independently shippable, and P0 is worth shipping alone.

---

## 13. Open questions for review

1. **Default level.** M2 needs `FW_L_DETAIL`; M4/M5 need `FW_L_OP`. Should the
   regression default be OP-level (cheap, keeps M3/M4/M5) with detail-level
   register coverage as an opt-in run? I lean yes.
2. **Sampling epoch.** Should the collector ignore events before an explicit
   "test started" mark, so configuration traffic does not colour register
   coverage? Proposal: an epoch API, default = sample everything, because a
   surprising amount of interesting traffic happens during configuration.
3. **Arc coverage cap.** Transition pairs are O(values²). Cap at width ≤ 6 as
   §7 says, or make it a refinement-file opt-in for wider fields?
4. **`others` policy.** Report `others`-dominated points as *warnings* in the
   report, or as failures of the model rather than of the test?
5. **Does M7(b) earn its keep?** A generated per-binding tap costs a virtual call
   on every API call. My instinct is no — proto-kit spans cover the protocols
   that matter — but it is the only route to endpoint-level coverage for
   hand-rolled APIs.
6. **Where does the refinement file live and who owns it?** Per-model, checked in
   next to the model, or per-project? It behaves like a waiver file, and waiver
   files rot when ownership is unclear.
