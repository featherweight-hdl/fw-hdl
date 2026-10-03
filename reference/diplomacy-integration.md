# Integrating Diplomacy into fw-hdl — Design

**Status:** design proposal for review
**Scope:** the concrete design of the `negotiate` phase — what a negotiation node is,
what propagates, how it is resolved, how failure produces a remedy, and how the whole
thing stays inert for designs that declare everything.
**Companions:**
`structural-model-and-lowering.md` §5.5 (sketch), §5.7 (address map), §6.3.1 (adapter
registry), step 20, O18/O22/O24/O25, P12/P13;
`parameterized-protocols.md` §6.4 (deferral), §5.3 (inheritance);
`../../../chisel_diplomacy_concept_model.md` (what Diplomacy is and where its ceiling is).

This document does for §5.5.3 what `parameterized-protocols.md` did for §5.5.1: turns a
paragraph into a design. It **corrects three things** in that sketch — where the transform
functions live (§3.2), how resolution is computed (§4), and when adapters are inserted
(§7.2) — and it identifies one Diplomacy concept the prior documents never mention
(§9, P-D1).

---

## 0. Summary of decisions

1. **The negotiation graph is over *endpoints* and *nodes*, not components.** An edge is a
   resolved connection; a **node** is a set of endpoints on one component that the component
   declares to be *related*. Propagation alternates edge → node → edge. (§3.1)
2. **Transform functions belong to the node, not to the parameter object.** §5.5.3 puts
   `xform_down`/`xform_up` on `fw_proto_params`. That is the wrong owner: a transform is a
   property of the component that relates two endpoints, not of a value. Diplomacy agrees —
   `dFn`/`uFn` live on the node; only `edge()` and `bundle()` live on the protocol. (§3.2)
3. **What propagates is a bag of named attributes, not a protocol-specific record.** Each
   attribute declares a direction, a domain, and a combining rule drawn from a **fixed
   catalog**. This is the single most consequential departure from Diplomacy, and it is what
   answers **O22** affirmatively: the address map, clock domain, security, and interrupt
   routing become *attribute kinds*, not additional passes. (§3.3)
4. **Resolution is a monotone fixpoint over a finite-height lattice, not a two-pass walk.**
   On an acyclic graph with independent directions it degenerates to exactly the two-pass
   walk §5.5.3 proposes, at the same cost. Where it differs is that it makes **cyclic
   topologies and mutual up/down dependency legal** — closing **O18** without the
   "authoritative edge" hack, and removing the limitation that is Diplomacy's own ceiling.
   (§4)
5. **`fw_component::do_connect()` must be split into `do_wire` / `do_negotiate` /
   `do_resolve`.** The current recursion interleaves wiring and resolution. That is
   sufficient for resolution — but negotiation needs the *complete* graph before it starts,
   which the present order does not guarantee globally. (§5)
6. **Four tiers, strictly separated: propagate → validate → remedy → solve.** Only the first
   two ever run by default. Remedy names an adapter; it does not insert one. Solving is
   opt-in and lives outside the simulator. (§6)
7. **Adapter insertion is negotiation-time graph rewriting, not a lowering step.** §6.3.1
   places insertion in the generator, which means the inserted adapter's own parameters are
   never negotiated. Because we have a fixpoint kernel, re-running after a rewrite is
   natural. Insertion remains opt-in per edge (**O24** unchanged). (§7.2)
8. **Two existing hand-written passes collapse into this one.** Clock-domain auto-inherit
   (`do_connect` step 2) and debug-context inheritance (`do_build` step 3) **[both exist]**
   are downward attribute propagation with nearest-ancestor-wins. Re-expressing them as
   attributes both shrinks the kernel and gives the new machinery two regression suites on
   day one. (§10, P-D3)
9. **Negotiation must be inert for fully-declared designs.** Same elaboration result, no new
   failure modes, no measurable cost. This is the acceptance criterion, not a nicety —
   §5.5.6/**O21** already flags that making the ordinary case worse would sink the whole
   parameter-object change. (§8)
10. **`B` is already designed; `D`/`U`/`E` are the gap.** Diplomacy's `bundle(e)` — edge
    parameters to hardware type — is `wb_abstraction::signals(params)` in §5.2. fw-hdl is
    further along than the sketch suggests; what is missing is the graph walk and the
    payload. (§2.2)

---

## 1. What is being borrowed, and what is not

From the concept-model note, Diplomacy is an **attribute grammar over a DAG**: inherited
attributes flow with the edges, synthesized attributes flow against them, an agreement is
computed where they meet, and only then is hardware generated. Its strengths (single-pass,
deterministic, precise errors) and its four limits (no cycles, no mutual dependency, no
search, no objective) both follow from one restriction: downward output depends only on
downward input, upward output only on upward input.

| Diplomacy concept | Borrow? | fw-hdl form |
|---|---|---|
| Two-phase elaboration | **yes — already have it** | build/connect vs. run; view binding vs. lowering |
| Node / edge graph | **yes** | endpoint groups / resolved connections (§3.1) |
| Downward + upward parameters | **yes** | directed attributes (§3.3) |
| `dFn` / `uFn` | **yes, relocated** | on the node object (§3.2) |
| `edge()` agreement function | **yes** | per-attribute combining rule (§3.3) |
| `bundle(e)` | **already have** | signal descriptor (§5.2) **[designed]** |
| `render(e)` | **yes, cheaply** | bind map already renders; add attributes (P-D4) |
| Node taxonomy (source/sink/adapter/nexus/identity) | **partially** | derived from role + node arity, not declared (§3.4) |
| Aligned ID / address allocation inside a nexus | **yes, later** | address map is a client of this pass (§5.7, step 24) |
| Negotiated **cardinality** (`:=*`) | **no — but name it** | inverts fw-hdl's phase order; §9, P-D1 |
| Single-pass restriction | **no — deliberately dropped** | fixpoint instead (§4) |
| Opaque per-protocol `D`/`U` records | **no — deliberately dropped** | attribute bag (§3.3) |

The two "no"s in the last rows are the design's thesis. Everything else is transcription.

## 2. What fw-hdl already has

### 2.1 The seam

`connect()` wires pointers and nothing resolves inside it — the kernel comment on
`do_connect()` says so explicitly, and `fw_port::do_connect()` is where `t` is bound
**[exists]**. That separation is precisely the seam Diplomacy needs, and it is why §5.5.3
could claim the addition is "one new phase." §5 qualifies that claim.

### 2.2 The bundle axis is already covered

Diplomacy's `NodeImp` has four type parameters: `D`, `U`, `E`, `B`. fw-hdl's `B` is
`wb_abstraction::signals(fw_ep_params)` from §5.2 — a signal list computed *as a function of
the parameter object*, which is exactly `bundle(e)`. The interface class is the class-level
half of the same thing.

So the gap is narrower than the sketch implies: **`D`, `U`, `E`, and the walk.** Worth
stating, because it changes the size estimate for step 20.

### 2.3 The introspection surface

`fw_dbg_bindable` / `dump_bind_map()` **[exists]** already enumerates every endpoint with
name, role, connected, provider, resolved. Negotiation adds columns, not a new artifact —
and the same walk is the extraction path to `dv-solve` (§5.5.5) and the diff basis for P17.

## 3. The model

### 3.1 Nodes and edges

Two distinct relations, and conflating them is the easy error:

- **Edge** — a resolved connection between two endpoints on *different* components
  (port→export peer binding). This is where an agreement is computed.
- **Node** — a set of endpoints on the *same* component that the component declares to be
  related. This is where information is transformed.

A port→port or export→export up-hierarchy binding is **not** an edge in the negotiation
sense; it is an identity node, because it is the same logical connection crossing a
hierarchy boundary. Treating hierarchy links as edges would compute an agreement at every
level and produce N copies of the same diagnostic.

```
  [wb_dma]                          [wb_mem]
   mif0 ──────── edge ───────────── s
     │                               │
   (node: "master group")          (node: implicit sink)
     │
   mif1 ──────── edge ───────────── (…)
```

Propagation alternates: an endpoint's outbound claim comes from its node; an endpoint's
inbound claim comes from its edge.

**Default nodes.** A component that declares nothing gets one **implicit singleton node per
endpoint** — the source/sink case, which contributes its declared attributes and transforms
nothing. This is what keeps §8 (inertness) true: the overwhelming majority of components
never mention a node.

### 3.2 Where the transforms live — correcting §5.5.3

§5.5.3 proposes `xform_down`/`xform_up` on `fw_proto_params`. Three problems:

1. **Wrong owner.** "A 64→32 width bridge halves the data width" is a fact about the
   *bridge*, not about `wb_params`. Putting it on the parameter class means `wb_params` must
   anticipate every component that will ever transform a Wishbone parameter.
2. **It cannot express relations across endpoints.** A crossbar's downward output is a
   function of *all* its inward claims. A method on one endpoint's parameter object has no
   access to the others.
3. **Diplomacy does not do this.** `dFn`/`uFn` are on the node; `edge()`/`bundle()` are on
   the `NodeImp` (the protocol). The sketch merged the two.

The corrected split:

| function | owner | fw-hdl home |
|---|---|---|
| `xform_down(in claims) -> out claims` | **node** | `fw_neg_node` subclass on the component |
| `xform_up(out claims) -> in claims` | **node** | same |
| combine two claims into an agreement | **attribute kind** (protocol-declared) | `fw_neg_attr` rule (§3.3) |
| agreement → signals | **protocol/abstraction** | `fw_abstraction::signals()` (§5.2) |

```systemverilog
// A negotiation node: a component's declaration that some of its endpoints are
// related. A component with no declared node gets one implicit singleton node
// per endpoint, which transforms nothing -- so this class is invisible to the
// 90% case (§8).
virtual class fw_neg_node;
    // Endpoints participating, in declaration order. Inward/outward is derived
    // from role, not restated (§3.4).
    pure virtual function void endpoints(ref fw_dbg_bindable eps[$]);

    // Downward: claims arriving on inward endpoints -> claims emitted on
    // outward endpoints. Default is broadcast-unchanged; override to transform.
    virtual function void xform_down(fw_neg_claim in_[$], ref fw_neg_claim out_[$]);
    virtual function void xform_up  (fw_neg_claim out_[$], ref fw_neg_claim in_[$]);

    // Optional: for a rewriting node (§7.2), the adapters this node can become.
    virtual function void remedies(ref fw_adapter_ref r[$]);
endclass
```

**The default really is broadcast-unchanged, per attribute.** A node that understands
`data_width` but has never heard of `security_level` must pass the latter through
untouched rather than dropping it. This is what makes attribute kinds addable without
touching every node — and it is the property Diplomacy's opaque records do not have.

### 3.3 The payload: a bag of directed attributes

**The central design decision.** Diplomacy's `D` and `U` are protocol-specific case classes.
Adding a concern (coherence, security, a new ordering guarantee) means editing the record
and every transform that pattern-matches it. fw-hdl should instead propagate a **set of
named attribute values**, each carrying its own semantics:

```systemverilog
typedef enum {
    FW_NEG_DOWN,      // initiator -> target  (provenance: who is upstream)
    FW_NEG_UP,        // target -> initiator  (availability: what is reachable)
    FW_NEG_BOTH       // must agree in both directions (dimensional)
} fw_neg_dir_e;

typedef enum {
    FW_NEG_EQUAL,     // all claims must be identical; disagreement is a conflict
    FW_NEG_MIN,       // meet on a numeric domain      (the adder tutorial's rule)
    FW_NEG_MAX,       // join on a numeric domain
    FW_NEG_UNION,     // join on a set domain          (address regions, source IDs)
    FW_NEG_INTERSECT, // meet on a set domain          (supported operations)
    FW_NEG_NEAREST,   // nearest declaring ancestor wins  (ambient: clock, dbg -- §10)
    FW_NEG_PASS       // carried, never combined       (opaque tags)
} fw_neg_rule_e;

// An attribute KIND -- declared once per concern, by whichever package owns the
// concern. The kernel knows only the enum values above; it never knows what
// "data_width" means.
virtual class fw_neg_attr;
    pure virtual function string        kind();     // "wb.data_width", "sys.addr_regions"
    pure virtual function fw_neg_dir_e  dir();
    pure virtual function fw_neg_rule_e rule();
    // Ascending-chain bound: how many times this attribute's value may strictly
    // increase before the fixpoint must have converged. Guarantees termination
    // (§4). For EQUAL/MIN/MAX over a fixed domain this is 1.
    pure virtual function int           height();
endclass
```

**A fixed rule catalog, not user-supplied lattices.** Letting kit authors write arbitrary
`join` functions would make termination unprovable and extraction to `dv-solve`
open-ended. The seven rules above cover every case in this repo and every case in TileLink's
parameter set; a concern that does not fit is a signal to reconsider the concern, not to
extend the catalog. This also pre-answers **O19**: the extractable constraint subset is
*exactly* the catalog, so extraction is total by construction rather than a subset with a
rejection list. (**O-D1** revisits whether seven is the right seven.)

**Worked mapping for what this repo actually contains:**

| attribute kind | dir | rule | claimed by | consumed by |
|---|---|---|---|---|
| `wb.data_width`, `wb.addr_width` | BOTH | EQUAL | both endpoints | signal descriptor, RTL params |
| `sys.addr_regions` | UP | UNION | target endpoints (size+alignment) | address map, decode, reg model |
| `sys.reachable` | UP | UNION | targets | P14 reachability checks |
| `sys.base` | DOWN | EQUAL | initiator address space | software header, PSS (P5) |
| `proto.ops` (`supportsGet`, sizes) | UP | INTERSECT | targets | model specialization, PSS (P-D5) |
| `proto.source_ids` | DOWN | UNION | initiators | nexus ID allocation (step 24) |
| `order.fifo_domain` | UP | PASS | targets | fabric ordering |
| `clk.domain` | DOWN | NEAREST | ancestors | replaces `do_connect` step 2 (§10) |
| `dbg.context` | DOWN | NEAREST | ancestors | replaces `do_build` step 3 (§10) |
| `sec.level` | DOWN | MAX | initiators | negative intent (P14, P-D6) |

Nine of the ten rows are things the existing documents already want; only two of them are
"parameters" in the §5.5 sense. That is the argument for **O22**'s generic answer, made
concrete.

### 3.4 Node taxonomy is derived, not declared

Diplomacy makes the designer pick `SourceNode` / `SinkNode` / `AdapterNode` / `NexusNode`.
fw-hdl already has the two facts needed to derive it: **role** (§5.3) and node arity.

| inward | outward | derived kind |
|---|---|---|
| 0 | n | source — contributes downward claims |
| n | 0 | sink — contributes upward claims |
| n | n, paired | adapter |
| n | m | nexus |
| 1 | 1, no transform | identity (hierarchy crossing) |
| — | — | monitor: reads the edge agreement, contributes nothing |

Deriving rather than declaring removes a whole class of "declared Adapter, wired like a
Nexus" errors that Diplomacy leaves to the user. The monitor row matters for this repo:
`wb_monitor_xtor` and the three declared taps in `tests/uvm` need the negotiated widths and
must not perturb them.

## 4. Resolution: fixpoint, not two passes

§5.5.3 proposes "downward pass → upward pass → per-edge derivation → validation," with
**O18** left open for cyclic topologies. Proposal: compute a **least fixpoint** instead.

```
  seed:   every endpoint's declared attributes; every other attribute = ⊥
  repeat:
      for each node:  out_claims ∪= xform_down(in_claims)
                      in_claims  ∪= xform_up  (out_claims)
      for each edge:  both endpoints ∪= combine(claim_a, claim_b)   -- per attribute rule
  until: no value changed
  then:  per-edge agreement; then validation
```

Four reasons this is the better default, and one honest cost:

1. **Cycles become legal, and O18 closes without a hack.** Rings, crossbars, and any fabric
   with a loop are exactly where negotiated parameters are most valuable and exactly what a
   DAG-shaped attribute grammar cannot express. The alternative on the table — declaring one
   edge authoritative — is a manual cycle-break the user must get right.
2. **Mutual up/down dependency becomes legal.** "The source-ID width I advertise downward
   depends on how many outstanding transactions the targets accept" is unwritable in
   Diplomacy and is a real design need. In a fixpoint it is simply another dependency.
3. **It degenerates.** On an acyclic graph with independent directions, the fixpoint
   converges in exactly two sweeps and computes exactly what the two-pass walk computes.
   There is no cost to designs that would have been fine either way.
4. **Termination is provable.** Each attribute declares `height()`; the product lattice's
   height bounds the sweep count. Exceeding it is a kernel bug with a precise message,
   not a hang.

**The cost:** every attribute rule must be monotone, and `height()` must be honest. A rule
that oscillates (`MIN` one sweep, `MAX` the next) diverges. The fixed catalog (§3.3) is what
makes this checkable — each of the seven rules is monotone by construction, so the obligation
falls on the kernel once rather than on every kit author. This is the main thing **O-D4**
asks the reviewer to accept.

**Determinism.** Sweep order must not affect the result — guaranteed by monotone rules and a
least fixpoint — and the *iteration* order must still be fixed, so that diagnostics and the
provenance trace (P-D2) are byte-reproducible per §3.4 of the companion.

## 5. Phase order — a correction to "one new phase"

§5.5.3 says the addition is one phase: `build → connect → NEGOTIATE → resolve → run`. Reading
the kernel, the change is slightly larger, and the discrepancy is worth being precise about.

`fw_component::do_connect()` **[exists]** does three things in one top-down recursion:
`this.connect()` (wire), the clock auto-inherit pass, then recurse into `m_elab` — and
`m_elab` holds both child components *and* this component's ports, so `fw_port::do_connect()`
(which resolves `t`) fires **inside the same walk that is still wiring descendants**.

That ordering is sufficient for *resolution*, because every edge is wired by the nearest
common ancestor of its two endpoints, which runs before either endpoint resolves. It is
**not** sufficient for *negotiation*, which needs the entire graph as data before the first
sweep. So:

```
do_build      (unchanged)
do_wire       ← this.connect() recursively, everywhere; nothing resolves
do_negotiate  ← seed, sweep to fixpoint, derive agreements, validate
do_resolve    ← fw_port::do_connect() -- bind `t`
do_run        (unchanged)
```

`fw_component::do_connect()` survives as a non-virtual wrapper calling the three, so existing
components that override nothing are unaffected. Components that override `connect()` are
unaffected. What changes is the kernel's walk, and the load-bearing property from §1 of the
companion — "the complete connection graph exists as data before anything is resolved" —
becomes *true globally* rather than true per-edge-by-construction. That is worth having
independently of negotiation: it is also what §7.3's `connect()` residualizer assumes.

**Reset/restart interaction (O8, O-D3).** `fw_root` restarts the class tree on reset. If
negotiation re-runs on every restart, its cost is per-reset rather than per-simulation. Since
the graph is unchanged across a restart, the result is cacheable — but the caching is only
safe if `build()`/`connect()` are deterministic, which O1's subset already requires.

## 6. Four tiers, strictly separated

§5.5.4 establishes resolve / validate / explore and rules out solving with `randomize()` for
two good reasons (arbitrary legal values break byte-reproducibility; randomization-failure
diagnostics are useless at SoC scale). Keep all of that; insert a tier.

| tier | when | mechanism | may fail? |
|---|---|---|---|
| **1. propagate** | every elaboration | fixpoint over the attribute bag (§4) | only on non-termination (kernel bug) |
| **2. validate** | every elaboration | per-attribute conflict + `randomize(null)` checker-mode relations | yes — this is the design error |
| **3. remedy** | on a tier-2 failure | adapter registry lookup keyed by the conflict (§7) | no — it either names an adapter or does not |
| **4. solve / explore** | opt-in, offline | extraction → `dv-solve` **[exists, adjacent]** | n/a |

The separation matters because tier 1 and 2 must be **total and fast** — they run on every
elaboration of every design, including designs that need none of this. Tiers 3 and 4 are
where the interesting capability is, and neither is on the critical path.

## 7. Failure, remedy, and adapter insertion

### 7.1 The diagnostic is the deliverable

`parameterized-protocols.md` §5.5 sets the bar: name both endpoints by hierarchical path,
name the disagreeing field, dump the bind map. Negotiation raises the bar, because a
negotiated value has a **derivation**, and a mismatch between two computed values is far
harder to debug than a mismatch between two declared ones. The kernel must record, per
attribute value, the endpoint that originated it and every node that transformed it:

```
NEGOTIATION CONFLICT at edge top.u_dma.mif0 <-> top.u_mem0.s
  attribute  wb.data_width   (rule EQUAL)
    64  from top.u_dma.mif0
          <- top.u_dma        node "master group"    (pass)
          <- top.u_sys        default at ancestor    (declared: wb_subsystem param_t.data_width = 64)
    32  from top.u_mem0.s
          <- declared at endpoint construction (wb_mem::build, wb_params::mk(32,32))
  remedy     wb_width_bridge (64->32)  -- available; insertion not requested for this edge
```

This is strictly better than what Diplomacy produces — a Scala `require` failure at the
point of conflict with a source locator for one side. It is cheap here precisely because the
propagation is our own code rather than lazy-val evaluation. **P-D2.**

### 7.2 Insertion is a graph rewrite, during negotiation

§6.3.1 places adapter insertion in the *generator*, at lowering. That has a defect the
document does not name: **an adapter inserted after negotiation never participates in it.**
Its own parameters — the bridge's internal buffering, the synchronizer's stage count, the
transactor's beat width on the far side — are then either hardcoded or negotiated in a second
ad-hoc step.

With a fixpoint kernel the correct treatment is available for free:

```
1. negotiate to fixpoint
2. validate -> conflicts
3. for each conflict on an edge with insertion REQUESTED (O24: opt-in, per edge):
       look up remedy -> a node
       rewrite: edge(a,b)  ==>  edge(a,adapter.in) + node(adapter) + edge(adapter.out,b)
4. if any rewrite occurred, goto 1
5. no rewrite occurred: report remaining conflicts as errors, remedies named
```

Rewriting is bounded: each rewrite resolves at least one conflict, and an adapter that
introduces a new conflict on the same attribute is a registry bug caught by a cycle counter.
The re-run is cheap because the fixpoint is incremental — only the rewritten neighbourhood
changes (P-D8).

**The SV/RTL asymmetry, stated honestly.** In the simulator, an inserted node can be a real
class object created by a factory, so SPL-side insertion works at elaboration. RTL-side
insertion cannot — SV cannot instantiate a module by runtime string, which is exactly why
§6.3.1 concluded insertion happens in the generator. Under this design the *decision* is made
during negotiation and recorded on the edge; the *realization* is a class object (SPL) or a
placeholder that the Python emitter turns into a module instance (RTL). One decision point,
two realizations — rather than a decision the generator makes with information negotiation
already had.

**Naming (O-D6).** An inserted adapter gets an instance name that appears in the netlist,
the waveform, and the path map. §2.3 of the companion argues that name predictability is *the*
product property. So the naming rule for inserted nodes must be as mechanical as the rest:
proposal is `<edge-consumer-path>__<adapter-kind>`, derived only from things the user wrote.
Anything involving a counter or a hash reopens the imagination gap.

## 8. Inertness — the acceptance criterion

**O21** already warns that the parameter-object change must not make the ordinary
fixed-and-equal case worse to debug. Negotiation raises the same risk one level higher, so
state the obligation as a test:

> For every design in `tests/` with all parameters declared and equal, elaboration with the
> `negotiate` phase enabled must produce byte-identical results to elaboration without it,
> emit no additional diagnostics, and add no measurable elaboration time.

What makes this achievable rather than aspirational:

- a component that declares no node gets implicit singletons that transform nothing (§3.1);
- an attribute claimed identically at both ends converges in one sweep under EQUAL;
- the conflict path is the only new failure mode, and it fires exactly where the equality
  check of step 3 would have fired anyway.

The corresponding lint (§5.5.6): report edges where every attribute is trivially fixed and
equal, so a user who *expected* negotiation to do something learns that it did not.

## 9. What is deliberately not borrowed

**Negotiated cardinality.** Diplomacy negotiates the *number of edges* (`:=*`, `:*=`), not
only their parameters — a bus node can say "however many masters attach, replicate that count
through this adapter chain." No prior fw-hdl document mentions this, and it is genuinely
useful: "size this arbiter to the number of initiators actually wired" is a question every
integrator asks.

fw-hdl cannot do it as the phases stand. Endpoint arrays are sized in `build()`; edge counts
are known after `connect()`. Negotiated cardinality would make `build` depend on `connect`,
inverting the phase order. Diplomacy affords it because `LazyModule` construction is lazy
Scala — nothing is really "built" until the graph is complete.

Not proposed for v1. Named because it is the one Diplomacy capability with no fw-hdl analogue
and no acknowledgement in the existing design, and because a cheap partial answer may exist:
a **deferred array** idiom where `build()` registers an endpoint *generator* and the kernel
instantiates after wiring. Whether that is worth its complexity is **O-D7** / **P-D1**.

**Objective functions.** Diplomacy has none; neither should tier 1–3. Costs belong in tier 4,
where `dv-solve` can optimize. Mixing an objective into propagation would make elaboration
non-reproducible.

## 10. Absorbing the two existing ambient passes

The kernel already contains two hand-written downward-propagation passes:

| pass | where | rule |
|---|---|---|
| clock-domain auto-inherit | `fw_component::do_connect()` step 2 **[exists]** | child inherits parent's `clock` unless explicitly bound |
| debug-context inheritance | `fw_component::do_build()` step 3 **[exists]** | child inherits parent's `dbg` unless it chose its own; only when the parent's is bound |

Both are `FW_NEG_DOWN` + `FW_NEG_NEAREST` in the vocabulary of §3.3. Re-expressing them as
attributes has three payoffs and one caveat:

- **the kernel shrinks** — two bespoke walks become two attribute declarations;
- **the new machinery arrives with regression coverage** — `tests/clock_domain/` (inherit /
  override / divide) already exercises exactly this behaviour, so the fixpoint kernel can be
  validated against a known-good implementation before any parameter negotiation exists;
- **it settles the precedence question** (**O-D9**) with evidence rather than by argument:
  `parameterized-protocols.md` §5.3 fixes precedence as *explicit at endpoint > nearest
  ancestor default > error*, and NEAREST reproduces it exactly. Negotiated evidence then
  slots in as a claim that participates in the same lattice rather than as a fourth,
  differently-ruled source.
- **caveat:** the `dbg` pass runs during *build*, not connect, and deliberately so — a
  component's own `build()` is worth observing, and a context bound afterwards missed it. So
  `dbg.context` cannot move into a post-connect fixpoint without losing that. Either it stays
  a bespoke build-time pass (and only `clk.domain` migrates), or the kernel gains a
  build-time NEAREST sub-pass. The former is the smaller change and is what this document
  proposes; the latter is tidier. **O-D9.**

This is the highest-confidence, lowest-risk starting point for the whole feature, and it is
independent of protocol parameters entirely.

## 11. Worked example: `fw-wb-dma`

Against the actual repo, with `wb_dma_de` holding `mif0`/`mif1` **[exists]**:

**Today.** `fw_port #(wb_proto_if #(32,32)) mif0, mif1;` — widths in the type, restated at
every level, unreachable from `wb_dma`'s `param_t`.

**After step 3 (parameter objects, no negotiation).** `wb_port mif0, mif1;` with a
`set_default_ep_params()` at `wb_subsystem`. Widths flow top-down; a mismatch is a connect
error.

**After this design.** Add one node declaration on `wb_dma`:

```systemverilog
class wb_dma_master_group extends fw_neg_node;
    // mif0, mif1 are outward (role=initiator); the register slave is inward.
    // Downward: nothing to transform -- widths pass through.
    // Upward:   the union of what mif0 and mif1 can reach IS what this DMA can
    //           reach, which is what the address map and the PSS model need.
endclass
```

and the following becomes derivable rather than declared:

- `wb_mem0`/`wb_mem1` claim `sys.addr_regions` upward; `wb_dma` unions them; the initiator
  view of the DMA — *which memories can this engine target, at which addresses* — is
  computed, not written in three places (`tests/uvm`, the PSS model, the software header);
- the OpenCores RTL variant's declared width participates as a claim, so binding the RTL view
  at a different width is a **negotiation conflict naming the view**, not a wiring bug found
  in simulation;
- `wb_proto_checker` **[exists]** and the monitor taps read the edge agreement, so a
  width-parameterized bench needs no per-variant configuration;
- the boundary report (step 12) gains the negotiated attributes, which is what makes it an
  input to testbench generation rather than only a design check.

The proving ground from `parameterized-protocols.md` §8 — *build the DMA at 64-bit data* —
extends naturally: with negotiation, changing `wb_subsystem`'s parameter object either
propagates to every reachable endpoint or names the one endpoint that could not follow, with
its derivation.

## 12. Staging

This does not add a ladder; it refines existing steps in `structural-model-and-lowering.md`
§11.2.

| existing step | change |
|---|---|
| **step 1** (role) | unchanged — role is the input to §3.4's derived taxonomy |
| **step 2** (endpoint attribute bag) | **make it the negotiation payload from the start.** `fw_ep_attr` and `fw_neg_attr` should be one hierarchy, not two |
| **step 3** (parameter objects) | unchanged; `compatible()` becomes a *client* of the EQUAL rule rather than a separate mechanism |
| **new, before step 13** | **phase split** (§5) + fixpoint kernel + `clk.domain` migration (§10). Independent of protocol parameters; validated by `tests/clock_domain/` |
| **step 13** (address map, validation only) | becomes a *client* of the kernel — this is **O22** answered by construction |
| **step 14** (system checks) | reachability is `sys.reachable` UNION; negative intent is `sec.level` MAX (P-D6) |
| **step 16** (adapter registry) | insertion moves from lowering into negotiation (§7.2); **O24**'s opt-in default unchanged |
| **step 20** (`negotiate`) | **shrinks** — by this point the kernel exists and this step only adds protocol-parameter attribute kinds |
| **step 24** (dv-solve, address assignment) | extraction target is the fixed rule catalog (§3.3), so **O19**'s subset question is pre-answered |

The reordering worth noting: **the kernel lands before the address map, and protocol
parameters land last.** That inverts §11.2's implied order, and it is deliberate — the
riskiest part (the fixpoint kernel) gets validated against the two ambient passes that
already have tests, before anything depends on it.

## 13. Open issues

| # | issue | gates | what closes it |
|---|---|---|---|
| **O-D1** | **Is the seven-rule catalog (§3.3) right?** A fixed catalog buys provable termination and total `dv-solve` extraction; an open one buys expressiveness. The bet is that seven covers everything real. | the kernel | Map TileLink's full parameter set and this repo's ten attribute kinds onto the catalog. If anything needs an eighth rule, the bet is wrong and the design needs a monotonicity *obligation* on user rules instead. |
| **O-D2** | **Transforms on the node, not the parameter object (§3.2).** This contradicts §5.5.3 and should be an explicit decision, not a silent correction. | step 20 design | Reviewer decision. The three arguments in §3.2 are the case. |
| **O-D3** | **Phase split cost (§5).** Splitting `do_connect` is a kernel change touching every design, and negotiation re-runs on every `fw_root` reset restart unless cached. Is per-restart cost acceptable, or is caching required in v1? | the kernel | Measure on `tests/perf` once the split exists. Interacts with **O8**. |
| **O-D4** | **Fixpoint vs. two passes (§4).** The fixpoint closes **O18** and removes Diplomacy's mutual-dependency limit, at the cost of a monotonicity obligation and an `height()` declaration per attribute. Is that trade accepted? | the kernel | Decide with O-D1 — a fixed rule catalog discharges the obligation centrally, which is most of the argument. |
| **O-D5** | **Dual-implementation drift.** Negotiation must produce identical results in the SV kernel and the Python static elaborator, or a design negotiates differently lowered than simulated. This is **O-P7** with a much larger surface. | v2 | Extend the differential oracle (§10.1) to diff *negotiated attribute values*, not only structure. Alternatively declare one implementation normative and have the other consume its output — but that breaks the pure-SV flow. Unresolved and the most likely source of a silent divergence in the whole design. |
| **O-D6** | **Naming of inserted adapters (§7.2).** Insertion creates instances the user never wrote, in a system whose central property is name predictability (§2.3). Is a derived-name rule sufficient, or must insertion always be *named* by the user at the point of request? | step 16 | Decide with **O24**. Leaning: insertion is requested per edge and the request carries the name, which makes the rule vacuous. |
| **O-D7** | **Negotiated cardinality (§9).** Out of scope as stated. Is the deferred-array idiom worth prototyping, or is "size arrays from the component parameter object" permanently good enough? | — | Find a real case in this repo. If none exists, close as won't-do rather than leaving it open. |
| **O-D8** | **What does a monitor read?** The edge agreement, or the node's outward claim? They differ when the node transforms. Affects tap declaration (**O10**) and `wb_proto_checker` binding. | v1 | Edge agreement is almost certainly right — a monitor observes a wire, not an intent — but state it. |
| **O-D9** | **Precedence and the `dbg` pass (§10).** Explicit > negotiated > nearest-ancestor > error, or does negotiated evidence outrank an explicit declaration (it must not)? And does `dbg.context` migrate into the kernel at the cost of a build-time sub-pass, or stay bespoke? | the kernel | §10 proposes: explicit wins always; `clk.domain` migrates; `dbg.context` stays. Confirm. |
| **O-D10** | **Map-valued attributes.** §5.7.1's per-initiator address views are *relations*, not scalars — "target T at base B *in initiator I's view*". Does UNION over a set-of-pairs domain express that, or does the address map need a richer attribute value than the catalog admits? | step 13 | Prototype `sys.addr_regions` against the three-master `fw-wb-dma` topology before committing the catalog. This is the most likely place O-D1's bet fails. |
| **O-D11** | **Does validation via `randomize(null)` survive the attribute-bag refactor?** §5.5.4's checker-mode trick assumes constraints on a typed parameter class. Constraints over an untyped bag may not be expressible in SV at all. | step 20 | Experiment. Fallback: validation is procedural per-attribute code, and only tier 4 uses declared relations — which weakens the "author once, serve three tiers" claim in §5.5.4. |

## 14. Overlooked opportunities

**P-D1 — Negotiated cardinality is a real capability nobody here has named.** §9. Even
declined, it belongs in the model's vocabulary: "how many of these do I need" is the question
integrators ask most and no assembly tool answers.

**P-D2 — Attribute provenance beats Diplomacy's diagnostics.** §7.1. A negotiated value has a
derivation; recording it is nearly free because we own the propagation loop, and it converts
the single worst failure mode of negotiated parameterization (*"why is this 64?"*) into a
printed chain. Diplomacy does not do this. Cheap, differentiating, and it demos — which
§3.6.5 argues is worth optimizing for.

**P-D3 — The two ambient passes are the safest possible first customer.** §10. Clock-domain
inheritance already has tests. Validating a new fixpoint kernel against an existing
hand-written pass, before any parameter depends on it, is the difference between a risky
kernel change and a refactor.

**P-D4 — The negotiated graph is a publishable artifact.** Diplomacy's `render()` produces a
GraphML view of the negotiated SoC, and it is one of the most-cited reasons people like it.
fw-hdl's bind map **[exists]** is 80% of the same thing; adding negotiated attributes and an
emitter gives *"here is your system, with every width, address range, and reachable target,
computed"* — for a package that already emits JSON. Pairs with P16/P17 as a minutes-long demo.

**P-D5 — Negotiated edge attributes are a stimulus space, and this repo can prove it.** An
edge agreement states exactly what is legal on that link: operations, size ranges, address
regions, ordering. That is a PSS constraint set. `src/pss` and the full PSS toolchain are in
this repo, P5 already wants one address-map source feeding PSS, and `peakrdl-pss` **[exists,
adjacent]**. *Negotiate → emit PSS address spaces and legal-operation constraints* closes the
loop from integration model to test generation. Nobody does this — Diplomacy computes the
legal space and then discards it into a generator.

**P-D6 — Security and negative intent ride the same rails.** `sec.level` as a DOWN/MAX
attribute makes *"no non-secure initiator reaches this region"* a propagation result rather
than a bespoke check — delivering P14's negative intent, which §3.4 of the companion calls the
cheapest genuinely differentiated feature, at nearly zero marginal cost once the kernel exists.

**P-D7 — The kernel is a dataflow-analysis framework, not a parameter resolver.** Monotone
fixpoint over a declared lattice on a graph is the standard shape of *every* whole-design
static analysis: CDC, reset-domain crossing, power intent (§14's deferred axis), X-propagation
scoping, clock-gating enable reachability. Building step 20 as a general kernel rather than a
width resolver means each of those is later an attribute declaration. This is the strongest
argument for **O22**'s generic answer and it goes further than §5.7.2 does.

**P-D8 — Monotonicity makes incremental re-negotiation exact.** Because the fixpoint is a
least fixpoint over a monotone system, changing one endpoint's claim requires re-converging
only the affected region. That is the mechanism behind P17 (interface diff / integration
impact): *"IP v1.3 widens this port — here are the seventeen edges whose agreement changes and
the three that now conflict."* P17 is listed as cheap given a typed structural model; with an
incremental fixpoint it is cheap *and* exact.

## 15. Explicitly out of scope

- **Negotiated edge cardinality** — §9, **O-D7**.
- **Objective functions in tiers 1–3** — costs and optimization belong in tier 4 (`dv-solve`),
  because an objective in propagation destroys reproducibility.
- **Automatic, unrequested adapter insertion** — **O24** stands: default is error with the
  remedy named. §7.2 changes *when* insertion happens, not *whether* it is opt-in.
- **Protocol-family conversion as a negotiated outcome** — WB↔AXI bridging is an adapter on
  the §6.3.1 registry, selected by an explicit request; negotiation never decides to change
  protocols.
- **Behavioural contracts** — channel dependency order, coherence invariants, deadlock
  freedom. The concept-model note ranks these last for a reason: they need information of a
  different kind than scalar and set-valued attributes, and a partial model would be worse
  than none. Same posture as power intent in §14 of the companion.
- **Solving during elaboration** — a design with all values declared must never require a
  solver to elaborate (§5.7.3's rule, applied to parameters as well as addresses).
