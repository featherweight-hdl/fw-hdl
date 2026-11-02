# Engine results as part of Zuspec IR: anchors, facts and overlays

*Design note for review, 2026-11-01.*

This note refines Phase 0 and Phase 3 of [adoption-path-plan.md](adoption-path-plan.md).

**The question.** Where should data that comes back from a synthesis engine live? This
covers schedule, timing, area, register names, interface timing and, later, simulation
results. Ideally it is part of Zuspec IR, or bound tightly to it, so that one data model
serves three needs:
- guiding the generation of new Zuspec models
- reporting and visualization
- front-end tooling that maps any result back to user source

## 1. Short answer

Make engine results a **first-class, versioned part of Zuspec IR**, without being part of
the *model tree*. That takes three pieces, all in `zuspec-ir-core`:

1. **Anchors.** Every IR node that can carry a result gets a **stable identity**. The
   front end assigns it, and it survives serialization and reruns. Today the IR has `Loc`
   but no identity, and that is the gap everything else depends on.
2. **Facts.** These are typed, namespaced records attached to anchors:
   - `sched.stage = 2`
   - `timing.path_delay_ps = 840`
   - `rtl.signal = "p2_prev_count"`

   Each records which engine, run and constraints produced it.
3. **Overlays (result sets).** An overlay is the set of facts from one run against one
   version of the model. It is held beside the model, never inside it, and serialized as
   part of the IR bundle. Several overlays can coexist: XLS and native, run A and run B,
   a simulation run.

Every consumer reads through the same API: `facts(node, overlay)`, plus `anchor → Loc`
and the source name.
- **Report renderers, the schedule overlay on source, LSP hints and PR diffs** need only
  that API. So they are written once and work for any input language that supplies `Loc`
  and source names.
- **Refinement passes** consume *model + overlay* and produce a new, lower-layer Zuspec
  model, whose nodes carry `Provenance` back to the anchors they came from. Examples are
  the timing shell, the staged TLM and native V4.
- **Engines** write overlays, so XLS and the native scheduler become interchangeable
  producers of the same data.

## 2. Three kinds of data, three places

Keeping these apart is what makes the binding tight without making the model unstable:

| Kind | Example | Who writes it | Where it lives | Changes the model? |
|---|---|---|---|---|
| **Intent** | target II, clock, "≤3 stages", "this op in stage 2", I/O constraints | user (source annotations) or a tool promoting a result | **model**: `Base.annotations` / a constraints model | yes: it is input |
| **Facts** | stage of each op, node and path delay, RTL register name, latency/II, area estimate, FIFO occupancy, coverage hits | engines, simulators, analyzers | **overlay**, keyed by anchor | no |
| **Refinements** | timing shell, staged TLM (V3.5), V4 cycle class | refinement passes | a **new model** at a lower `IRLayer`, nodes with `Provenance` → anchors, header naming the overlay used | n/a: it's a new model |

There are two transitions between kinds:
- **Promotion (facts → intent):** "freeze this schedule" or "keep op X in stage 2". This
  is how a result becomes guidance for the next build, and it is the hook for Zuspec's
  tweak-and-continue.
- **Refinement (model + facts → new model):** how results become a lower model.

Both are explicit, recorded operations, so we can always tell what the user asked for from
what an engine decided.

## 3. Anchors: stable identity for IR nodes

### 3.1 Requirements
- **Assigned by the front end** (or by a canonical numbering pass right after it), so that
  every input language produces them the same way.
- **Stable across reruns** of the same source, and as stable as practical across unrelated
  edits. An edit to one function should not re-key facts in another.
- **Serializable and inert.** A string or compact ID, never a live object reference. The
  same lesson as `Provenance.source_names`.
- **Granularity:**
  - declarations (component, process, function, field, channel, port, state)
  - statements
  - expressions with a value: the units engines schedule and time

### 3.2 Scheme (recommended)
Use a hierarchical, name-first path, with ordinals only where there is no name:

```
RunLengthEncoder                          component
RunLengthEncoder.prev_count               field / state
RunLengthEncoder.run                      process
RunLengthEncoder.run#s4                   4th statement in run's body
RunLengthEncoder.run#s4.e2                2nd value-producing expr in that statement
```

- Named levels absorb most edits. Ordinals are local to the nearest named scope, so an
  edit re-keys only its own scope.
- Add a **content hash per named scope**, stored in the overlay. On rebuild, a scope whose
  hash is unchanged keeps its facts as "valid". A changed scope's facts become "stale",
  which is still useful in an IDE: show the last build's schedule, greyed out.

### 3.3 Derived anchors
Engines create things with no source counterpart:
- pipeline registers
- flow-control logic
- FIFOs
- state interlocks

Key them as an **anchor plus a qualifier**, for example:
- `(RunLengthEncoder.prev_count, reg@stage2)`
- `(RunLengthEncoder.out_c, fifo)`
- `(RunLengthEncoder.run, flow@stage1)`

That gives them a stable name, and lets a report roll them up under the source construct
they belong to.

## 4. Correspondence: engine nodes back to anchors

This is the hard part, and it lives in each **engine adapter**. After optimization (CSE,
constant folding, inlining, resource sharing), engine nodes and source anchors are
many-to-many. The adapter's job is to turn every engine node into an anchor set, with a
**mapping-quality** tag:

| Quality | Meaning | Example |
|---|---|---|
| `exact` | one engine node ↔ one anchor | an add that survived optimization |
| `merged` | one engine node ↔ several anchors | CSE'd expression used in two places |
| `derived` | engine-created; anchor + qualifier | pipeline register, flow control |
| `partial` | maps to an enclosing scope only | op produced by inlining or a rewrite |
| `unmapped` | no source counterpart found | report it; never drop it |

**XLS adapter mechanisms**, used together and cross-checked:
1. **The lowering map.** `zuspec-be-xls` knows anchor → emitted XLS node(s) at emission
   time. It records this as it lowers.
2. **`pos` on XLS IR nodes.** It carries source file/line/col, which the front end's `Loc`
   supplies. **To verify:** which XLS optimization passes keep or merge `pos` lists. If
   merging is reliable, `pos` alone recovers `merged` cases after optimization.
3. **Node names.** be-xls names nodes after source names (`prev_count`). That makes RTL
   readable and gives a fallback match, but it is not unique enough on its own.
4. **Block IR** for derived anchors: `p<s>_<name>` registers, `p<s>_valid`, and
   `fifo_<channel>`.

**Native adapter.** It has the IR in hand, so mapping is `exact` or `derived` by
construction. Today the `sprtl` `Schedule` is keyed by integer op IDs with a back-reference
to an FSM op. It needs anchors threaded through, a small change.

**Coverage metric.** Every overlay reports how much of the design maps back to source:
- "97% of ops `exact`/`merged`"
- "91% of critical-path delay attributable to source"

That makes the source mapping itself a measured quantity.

**Lossy engines are acceptable by design (decided 2026-11-01).** An engine that preserves
little source position information still produces a valid overlay. It just limits which
analyses are possible: fewer per-line reports and coarser critical paths. Consumers must
degrade gracefully on `partial`/`unmapped` facts, never fail. The coverage numbers are
informational and tracked for regressions, not a quality bar an engine must pass.

## 5. Facts: the schema

Facts are small typed records: `kind`, `anchor` (+ qualifier), `value`, `quality`. The
**core kinds** are standardized in ir-core, so every engine and every consumer agrees on
them. Engines add **namespaced extras** (`xls.*`, `native.*`) that only specialist tools
read.

| Namespace | Kinds (core) | Anchored at |
|---|---|---|
| `iface` | the existing **`BlockSignature` / `ChannelSignature`** (latency, II, channel ports, flow control), plus per-channel op stage and flop kind | block / channel |
| `sched` | `stage`, `cycle_lo/hi`, `ii` (with a reliability flag: XLS procs report `value_or(1)`), `stage_count` | op, process, state |
| `timing` | `node_delay_ps`, `path_delay_ps`, `critical_path` (ordered anchor list, slack), `clock_period_ps`, `delay_model` (name + version) | op; block |
| `rtl` | `signal` (RTL net name), `register` (derived anchor → reg name, width), `module`, `line` (from the Verilog line map) | op, derived |
| `area` | `estimate` (unit, model), `resource` (shared unit an op is bound to) | op, block |
| `sim` *(later)* | `fifo_occupancy` (histogram), `throughput`, `stall_cycles`, `cover_hits`, `activation_count` | channel, process, cover point |

**Every overlay header records:**
- engine and version, e.g. xlsynth `vX.Y`, codegen 1.5
- delay model
- **constraints (intent) used**, as a hash plus their content
- the IR content hash of each scope
- the producing command
- the timestamp
- **coverage metrics**

**Fold `BlockSignature` in, don't duplicate it.** It already lives in ir-core, is
engine-neutral, and has a JSON form (`zuspec.block-signature` v1). It becomes the
block-level `iface` member of an overlay, and `shell.json` is its file form. This replaces
the separate "block contract model" (step 0.2) in the plan.

## 6. How each use reads the same data

| Use | Reads | Produces |
|---|---|---|
| **Report, single run** | overlay + anchor→`Loc` | per-source-line stage / delay / area; critical path drawn as a source path, with gaps marked `derived`/`unmapped` |
| **Schedule overlay in editor / LSP** | same | hints on SV lines today, Python lines later, with no language-specific code beyond `Loc` |
| **PR QoR diff / XLS-upgrade gate** | two overlays, matched by anchor | "+1 stage in `run#s4`", "critical path moved from X to Y", coverage regressions |
| **XLS vs native cross-check** | two overlays from different engines | where the native schedule differs from XLS's, per anchor: the guide to closing the ~5% gap |
| **Timing shell (refinement)** | model + `iface` + `sched` | new V3 model; header names the overlay |
| **Staged TLM V3.5 (refinement)** | model + `sched` + `rtl.register` (boundary values) | new V3.5 model; stage bodies carry `Provenance` → anchors, so the debugger shows source lines |
| **Monitors T1–T3** | `iface`, `rtl.signal`, `rtl.register` | bind modules; records are labelled by anchor → source name |
| **Divergence finder** | records + anchors | "field `count`, written at `RunLengthEncoder.run#s6` (rle_pkg.sv:61)" |
| **Guidance / tweak-and-continue** | overlay → promoted intent | the next build's constraints; for native, per-op stage directives; for XLS, the subset it accepts (stages, clock, II, I/O constraints) |
| **Architectural exploration** | many overlays (a sweep) | Pareto table keyed by constraint set |

The pattern: a consumer never parses an engine's file format. Only the adapter does,
once, into facts.

## 7. Physical form

- **In memory:** the model (`ir.Context`) is unchanged. A `ResultStore` holds overlays and
  an anchor index (anchor ↔ node). Lookups go node → anchor → facts.
  - This follows the precedent of `Base.annotations`, which is excluded from `==`: results
    must never change whether two models compare equal.
- **On disk, the IR bundle:**
  - the model, via the existing versioned YAML serializer, with `_layer`
  - one file per overlay (`overlays/<engine>-<run>.json`), carrying the schema version,
    the header from §5, and facts as columnar arrays keyed by anchor (compact for
    100k-node designs)
  - the anchor table (anchor → `Loc`, source name, scope hash)

  Tools that only report (CI diff, viewer, LSP) load the anchor table and overlays without
  loading the model or any engine.
- **Lifecycle:**
  - a full build writes a fresh overlay
  - an incremental build marks facts in changed scopes `stale`
  - overlays are cheap to keep: retain main's overlay for PR diffs

## 8. What exists, and what changes

| Exists | Use as is / change |
|---|---|
| ir-core `Loc` (file, line, pos) | use as is; front ends must fill it on expressions too, not just declarations |
| ir-core `Provenance` (`pass_name`, `source_names`, `site`) | use as is for refinements; add `overlay` (which result set guided the pass) |
| ir-core `Annotation` | carrier for **intent**, including promoted results |
| ir-core `BlockSignature` + JSON | becomes the `iface` facts; extend with per-channel stage and flop kind |
| ir-core serializer with `_layer`; zuspec-synth `IRLayer` (ACTIVITY < SCHEDULED < PIPELINE < STRUCTURAL) | **SCHEDULED = model + `sched` overlay**, so XLS and the native `SchedulePass` both produce it. Today `SynthIR.schedule_obj` is native-only and keyed by int op IDs |
| zuspec-synth `sprtl.Schedule` | adapt: key by anchor (keep int IDs internal) |
| zuspec-synth `StageIR.loc`, `archsched` delay tables | fill `timing` facts (native adapter) |
| fw-hdl `stage_tlm.py`, libsynth `xls/lower.py` schedule readers | collapse into the **XLS adapter's overlay writer**; StageTLM and Lower read the overlay |
| **Missing:** anchors, `ResultStore`/overlay schema, correspondence in be-xls, coverage metric | new; Phase 0 |

## 9. Risks and open points

| Risk | Note |
|---|---|
| Anchor churn makes overlays useless across edits | Name-first paths + scope hashes; measure re-keying on real edit histories (fw-aes git log) before freezing the scheme |
| XLS optimization loses the correspondence | Accepted: lossy engines only limit analysis. Measure coverage on AES, rle and gcd so reports can say what they cannot attribute |
| Schema creep (every engine wants its own kinds) | Small standardized core; everything else namespaced; a kind joins the core only when two producers fill it |
| Two IRs in fw-hdl (ir-core `Context` and `zuspec.synth.proc.Design`) | Anchors are assigned once, on the ir-core form. `proc` nodes carry the anchor of the node they came from. This needs checking in `fe/elab` |
| Overlay size on large designs | Columnar storage; per-scope files if needed |
| Promotion to XLS is lossy (no per-op stage input) | State it in reports: promoted intent that the engine can't honor is flagged, not dropped silently |

## 10. Effect on the plan

These changes apply to [adoption-path-plan.md](adoption-path-plan.md):
- **Phase 0 is reshaped around anchors + overlays in ir-core.** The "contract model" and
  "schedule model" become fact namespaces (`iface`, `sched`), not separate models.
  `BlockSignature` is extended, not replaced.
- **Phase 0 adds a correspondence-coverage gate** next to the zuspec-dataclasses canary.
- **Phase 3 has no separate "report model"** because it *is* the overlay. Phase 3 is
  renderers and diffs only.
- **Phases 4–5:** the timing shell, staged TLM and monitors are refinements or readers of
  overlays. The staged TLM is the first **model + overlay → new model** pass.
- **Package placement:** anchors, facts, overlays and `ResultStore` go in **ir-core**, not
  zuspec-synth. Front-end tooling and other languages need them without depending on
  synthesis.
