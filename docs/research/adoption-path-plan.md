# Making the SV→XLS adoption path real: a phased, Zuspec-first plan

*Plan for review, 2026-11-01.*

This plan implements the roadmap in the "fw-hdl: the SV→XLS adoption path" deck
(`fw-hdl-adoption-path.pptx`). Sources:
- [sv-value-over-xls.md](sv-value-over-xls.md)
- [shell-generation.md](shell-generation.md)
- [timing-shell.md](timing-shell.md)
- [rtl-transaction-backannotation.md](rtl-transaction-backannotation.md)
- [staged-tlm-from-xls.md](staged-tlm-from-xls.md)
- [designer-ramp-to-xls.md](designer-ramp-to-xls.md)

**The constraint that shapes it:** as much as possible goes into **Zuspec**, so that two
later extensions are plug-ins, not rewrites:
- a second input language (Python via zuspec-dataclasses)
- a second synthesis engine (native lowering; later, others)

The product stays narrow: **SV in, XLS as the engine**. The architecture underneath is
built language- and engine-neutral from the first phase.

---

## 1. The placement rule

Ask two questions of every piece of the roadmap:
1. **Would a Python-authored block need it?**
2. **Would a non-XLS engine need it?**

If either answer is yes, the piece goes into Zuspec. Only three kinds of thing stay in
fw-hdl:
- **SV input:** the slang front end, and the discovery of SV class structure (ports,
  exports, bind maps).
- **The SV runtime:** `fw_component`, `fw_channel`, `fw_std_pkg`, and the SV bodies of the
  protocol kits.
- **SV-authoring UX:** coding guide, `fw-hdl check` messages phrased in SV terms, and
  examples.

A corollary follows from the parked multi-language direction (designer-ramp §8).
**Verification's SV projection is needed for a Python-authored block too.** So the
*emitters* of the generated SV collateral are not fw-hdl-specific:
- shells, timing shells, staged TLM, monitors, bind modules and SVUnit API wrappers

They take neutral models in, and belong in Zuspec. They target the fw-hdl runtime the way
a C back end targets libc.

## 2. Target architecture

```
  SV source ──(fw-hdl fe/)──┐                         ┌─ XLS adapter (zuspec-be-xls) ── XLS tools (dv-flow-libsynth)
                            ├─► zuspec IR ─► Engine ──┤
  Python (zdc) ─(DataModel  │  (ir-core)     interface├─ native adapter (zuspec-synth: archsched / V4→V5)
     Factory) ──────────────┘                         └─ (future engines)
                                                  │
     every engine returns RTL + one RESULTS OVERLAY on the same IR (ir-results-overlay.md):
          ┌───────────────────────────────────────────────────────────────────────────┐
          │ anchors (stable IR node ids → Loc, source name)  ◄── assigned by the FE   │
          │ facts keyed by anchor, by namespace:                                      │
          │   iface (BlockSignature = shell.json) · sched · timing · rtl · area · sim │
          │ header: engine+version, constraints used, scope hashes, mapping coverage  │
          └───────────────────────────────────┬───────────────────────────────────────┘
               refinement (model + overlay ─► new lower model) │ readers (reports, checks)
                 ▼               ▼              ▼               ▼              ▼
     Projections (zuspec-be-sv, targeting the fw-hdl SV runtime; Python projections later):
     module shell · RTL wrapper · timing shell · staged TLM (V3.5) · lockstep harness ·
     T1/T2/T3 monitors · SVUnit call-API wrappers · schedule overlay · SDC/handoff
                 ▲
     Neutral checks and tools (zuspec-synth): pin parity · link checks · divergence
     finder · replay · QoR diff · protocol-kit registry · constraints model
```

**Three seams make the extensions cheap:**

| Seam | Interface | First implementation | What it buys later |
|---|---|---|---|
| **Front end → IR** | zuspec IR + source locations + source names + lowerability diagnostics | fw-hdl `fe/` | Python via `DataModelFactory` reuses everything downstream |
| **IR → Engine** | `accepts(block) → verdict + explanation`; `build(block, constraints) → {RTL, results overlay}` (the overlay carries interface, schedule, timing, RTL names and area as facts on IR anchors) | XLS adapter | Native lowering (Track B) and portfolio dispatch are a second and third adapter |
| **Artifacts → Projection** | neutral models in, host-language collateral out | SV over the fw-hdl runtime | A Python/cocotb projection, or another simulator runtime |

## 3. Where things live today, and where they move

Paths:
- fw-hdl paths are relative to `python/fw/hdl/` in this packet.
- Zuspec repos are the dev checkouts. *(Updated 2026-11-02: `packages/zuspec-synth` in
  this packet now has `proc/`.)*

| Piece | Today | SV-specific? | Target |
|---|---|---|---|
| IR data model | `zuspec-ir-core` | neutral | stays; **gains anchors, fact schema, overlays, `ResultStore`** (ir-results-overlay.md) |
| Block signature | ir-core `BlockSignature` / `ChannelSignature` + JSON (`zuspec.block-signature` v1) | neutral | stays; becomes the `iface` facts; add per-channel stage and flop kind |
| Process IR | `zuspec.synth.proc` (dev only) | neutral | stays; **release it** (Phase 0) |
| SV front end | fw-hdl `fe/` | SV | stays in fw-hdl; adopt neutral source-loc and diagnostic formats |
| zuspec IR → XLS IR | `zuspec-be-xls` (`lower_fn`, `lower_proc`) | neutral | stays; becomes the core of the XLS **engine adapter** |
| XLS flow glue | fw-hdl `xls_flow.py` (pyslang + `static_mapper`) | mixed | split: the front-end call stays in fw-hdl; the rest → adapter |
| XLS signature reader | `zuspec-be-xls/signature.py`, `comp_api.xls_binding_sv` | neutral / SV | reader → adapter writes `iface` facts; SV binding → be-sv emitter |
| XLS schedule readers | fw-hdl `stage_tlm.py`, libsynth `xls/lower.py` | neutral input | collapse into the XLS adapter's **overlay writer** (`sched`, `timing`, `rtl`); both tools then read the overlay |
| Native schedule | zuspec-synth `sprtl.Schedule` (int op ids), `SynthIR.schedule_obj` | neutral | key by anchor; native adapter writes the same overlay, so `IRLayer.SCHEDULED` = model + `sched` overlay for either engine |
| StageTLM emitter | fw-hdl `stage_tlm.py` | SV output | → be-sv, as a refinement reading the `sched` overlay (merge with `archsched/emit_v3.py`) |
| ArchSched (V3/V5 emit) | `zuspec-synth/archsched` | neutral model + SV emit | stays; writes the same `sched`/`timing` overlay (Track B side) |
| XLS tool invocation | `dv-flow-libsynth` `synth.xls.Codegen` | neutral | stays; adds block IR and scheduled-IR outputs |
| `synth.xls.Lower` (XLS IR + schedule → V4/V5) | `dv-flow-libsynth` `xls/lower.py` | neutral | stays for now; its stage split is reused by the staged-TLM model |
| Partition / XLS block / Integrate | fw-hdl `spl_flow.py` (SPL→RTL core already in `zuspec.synth.spl`) | Partition: SV; rest: neutral | `xls_block` and `integrate` → zuspec-synth, over contracts |
| Protocol meanings | fw-hdl `fe/bind/protocols.py` `STD_TRANSACTORS` ("KNOWN DEBT") | SV-coded, neutral concept | **kit registry** (descriptor schema + resolver) → zuspec-synth; SV kit bodies stay in fw-hdl `src/std` |
| ready/valid kit | fw-hdl `tests/rv_proto/` (32-bit) | SV | → fw-hdl `src/std/rv/`, parameterized on `type T` |
| Call API (one test at every level) | fw-hdl `fn_api.py`, `comp_api.py` | concept neutral, output SV | API model (derived from the contract) → zuspec; SVUnit emitter → be-sv |
| Cosynthesis contracts | fw-hdl `cosynth/` (text pass on V5 SV + SBY) | RTL-level | record format → zuspec-synth `verify`; the RTL rewrite stays as is until Track B needs it |
| Deadlock / structural verify | `zuspec-synth/verify` | neutral | stays |
| fw runtime SV library | fw-hdl `src/` | SV | stays (it is the SV host runtime) |

*Terminology: "contract" below means a block's `iface` facts, i.e. the extended
`BlockSignature`, whose file form is `shell.json`.*

**Net effect:**
- fw-hdl shrinks to front end + runtime + kits + UX.
- zuspec-be-xls becomes "the XLS engine".
- zuspec-ir-core holds anchors, the fact schema and overlays (engine results as IR).
- zuspec-synth holds the engine interface, kits, refinements and checks.
- zuspec-be-sv holds every SV projection.

## 4. Phases

Each phase ends with a **demo** and **exit criteria**. Effort: S ≈ days, M ≈ 1–2 weeks,
L ≈ several weeks. **Bold** deliverables land in Zuspec.

The pillar numbers match the deck:
1. keep the language
2. one test suite
3. it's just a module
4. reports in your terms
5. timed views
6. debug

### Phase 0: The spine (anchors, results-as-IR, and the engine seam)

*No user-visible feature. Everything later depends on it.*

| # | Deliverable | Where | Effort |
|---|---|---|---|
| 0.1 | Release the `zuspec-synth` with `proc/`, and pin fw-hdl to it. Confirm `wpk/lower` is pushed (main and `wpk/lower` are both at `3f96fcf` locally) | zuspec-synth, libsynth | S |
| 0.2 | **Anchors:** stable, name-first IR node identity + per-scope content hash; assigned by a canonical pass after any front end; serialized with the model | ir-core; fw-hdl `fe/` fills `Loc` on expressions | M |
| 0.3 | **Fact schema + overlays + `ResultStore`:** core namespaces `iface`, `sched`, `timing`, `rtl`, `area`; overlay header (engine/version, constraints, scope hashes, mapping coverage); IR-bundle file form. `BlockSignature` becomes the `iface` member (extend with per-channel stage, flop kind); `shell.json` is its file form | ir-core | M |
| 0.4 | **XLS adapter overlay writer:** signature proto → `iface`; schedule proto → `sched`/`timing`; block IR + Verilog line map → `rtl`. Correspondence engine-node → anchors with quality tags (lowering map + `pos` + names); records II reliability (procs: `value_or(1)`) | zuspec-be-xls | M |
| 0.5 | **Naming:** be-xls emits XLS node names from source names (`p2_prev_count`, not `p2_add_1432`) and `pos` from `Loc`. Verify which XLS opt passes keep/merge `pos` | be-xls | S |
| 0.6 | **Engine interface** (`accepts`/`build` → RTL + overlay) with the XLS adapter as sole implementation; `fw.hdl.xls.IR` + `synth.xls.Codegen` re-expressed as one adapter call. StageTLM and `synth.xls.Lower` switch to reading the overlay | zuspec-synth `engine/`, be-xls, libsynth | M |
| 0.7 | **Neutrality canary (CI):** one zuspec-dataclasses block (GCD) → `DataModelFactory` → anchors → XLS adapter → overlay + RTL; the SV-authored GCD gives the same `iface` facts and an anchor-isomorphic `sched` overlay | zuspec-be-xls `testing/` | S |
| 0.8 | **Mapping-coverage gate (CI):** % ops `exact`/`merged`, % critical-path delay attributable to source, on AES, rle, gcd. Informational: lossy engines are acceptable and only limit analysis. The gate catches *regressions* in our own lowering's mapping | be-xls `testing/` | S |

**Exit criteria:**
- Every existing fw-hdl XLS test passes through the engine interface.
- The canary and the mapping-coverage gate are green.
- `shell.json` round-trips from an XLS signature through the `iface` facts.
- The anchor scheme has been measured for re-keying on real edit history (fw-aes) before
  it is frozen.

**Why the canary is in Phase 0.** It is the cheapest proof that "maximize Zuspec" is
actually being honored. It costs days now, and catches SV leaking into the neutral layer
while that is still cheap to fix. It is **not** a Python product (still parked).

### Phase 1: "It's just a module" (pillar 3)

| # | Deliverable | Where | Effort |
|---|---|---|---|
| 1.1 | rv kit → `src/std/rv/`, parameterized on `type T`; `fw_put_if`→rv adapter | fw-hdl | S |
| 1.2 | **Kit descriptor schema + registry/resolver** (API → transactor map, override layer, resolution order; shell-generation §4) | zuspec-synth `kits/` | S–M |
| 1.3 | Edge discovery for SV class trees: static, then bind-map (`+fw_bindmap`) → contract | fw-hdl | M |
| 1.4 | **Module-shell + RTL-wrapper emitter** from contract + kit resolution; `pin_style: xls` | zuspec-be-sv `shell/` | M |
| 1.5 | **Pin-parity check** (contract vs contract: model shell vs XLS signature) | zuspec-synth | S |
| 1.6 | Accept `logic`; early lowerability check reporting through the neutral diagnostic format | fw-hdl `fe/` | S–M |
| 1.7 | `fw.hdl.lower` switches from `STD_TRANSACTORS` to the registry; delete the table | fw-hdl | S |

**Demo:** replace an `always_ff` FSM in an existing RTL design with a class behind a
generated shell. Simulate, swap in XLS RTL by fileset, and rerun the same TB.

**Exit criteria:**
- `blinky_top.sv` regenerates as a golden test.
- Pin parity passes against XLS for rle, gcd and AES.
- `STD_TRANSACTORS` is gone.

### Phase 2: One test suite, and RTL the back end accepts (pillars 2, 3)

| # | Deliverable | Where | Effort |
|---|---|---|---|
| 2.1 | **Call-API model** derived from the contract (one call per function/port, bound per level) | zuspec-synth `api/` | S–M |
| 2.2 | **SVUnit API emitter** from the model; `fn_api.py`/`comp_api.py` become thin callers | zuspec-be-sv | M |
| 2.3 | **Constraints model** (clock, stages, II, I/O constraints, reset kind/polarity, data-path reset, I/O flop kinds), mapped by the XLS adapter onto `codegen_main` flags | zuspec-synth, be-xls, libsynth | M |
| 2.4 | **Hand-off bundle**: SDC from contract + constraints, filelist, manifest | zuspec-be-sv (or a `be-handoff`) | S–M |
| 2.5 | Lint gate (Verilator/commercial-lint-clean XLS RTL) in CI | fw-hdl CI | S |

**Demo:** the same SVUnit test runs on the class, the XLS RTL and the gates. The RTL goes
into a commercial synthesis run with no hand edits.

**Exit criteria:**
- `fw.hdl.api` produces identical tests through the new emitter.
- Reset and flop-kind knobs are verified on AES and rle.

### Phase 3: Reports in the designer's terms (pillar 4)

| # | Deliverable | Where | Effort |
|---|---|---|---|
| 3.1 | Report **renderers over the overlay** (no separate report model): per-source-line stage/delay/area; critical path as a source path with `derived`/`unmapped` gaps; mapping coverage in every report | zuspec-synth `report/` (reads ir-core overlays only) | S–M |
| 3.2 | **Promotion:** "freeze schedule" / "keep op X in stage s" turns facts into intent annotations; the XLS adapter maps the subset XLS accepts and flags the rest | ir-core (intent), be-xls | S–M |
| 3.3 | **Renderers:** schedule overlay on source (annotated listing / LSP hints) and per-block summary | zuspec-synth (text/HTML); editor hooks in fw-hdl | M |
| 3.4 | **PR QoR diff + XLS-upgrade gate** (diff two overlays by anchor; also XLS-vs-native overlay diff for Track B) | zuspec-synth, CI recipe | S–M |

**Demo:** edit one SV class. The critical path appears on the SV lines, and the PR shows
"+1 stage, −3% area" against main.

**Exit criteria:** every report line resolves to a source location for AES and rle.

### Phase 4: Timed views behind the same pins (pillar 5)

| # | Deliverable | Where | Effort |
|---|---|---|---|
| 4.1 | **Timing-shell refinement** for function pipelines (exact: latency, II, overlap): model + `iface`/`sched` overlay → V3 model whose header names the overlay | zuspec-synth `timed/` | S |
| 4.2 | **Timing-shell emitter**, merging `stage_tlm.py` and `archsched/emit_v3.py` into one emitter over the schedule model | zuspec-be-sv | S–M |
| 4.3 | **Lockstep harness** generated from the contract (shell vs RTL, pin-for-pin) | zuspec-be-sv + zuspec-synth check | S |
| 4.4 | `fw_channel #(T,1)` same-cycle drain/refill check; `fw_state` primitive | fw-hdl runtime | S |
| 4.5 | **Proc timing shell:** stage/flow-control model, state back-edge II, flop kinds; developed against lockstep from day one | zuspec-synth + be-sv | M–L |
| 4.6 | **Staged TLM (V3.5) refinement**, the first full model + overlay → new model pass: `sched` + `rtl.register` (boundary values) → per-stage processes with `Provenance` → anchors; function pipelines first, then procs | zuspec-synth `staged/`; be-xls writes `rtl.register` from block IR | M (fn), L (proc) |
| 4.7 | Generated link checks V1↔V3.5 (streams) and V3.5↔RTL (lockstep) | zuspec-synth | S |

**Demo:** an architect swaps the RTL of a subsystem for timed shells in an SoC sim, gets
the same throughput and FIFO occupancy as RTL, and runs faster.

**Exit criteria:**
- Lockstep passes for function pipelines (AES, gcd) and for one proc (rle).
- The simulation speedup over RTL is measured, not asserted.

**Track B tie-in.** ArchSched fills the same schedule model. Every timed view therefore
works for the native engine without new emitters, and XLS schedule vs ArchSched becomes a
standing cross-check.

### Phase 5: Debug in source terms (pillar 6)

| # | Deliverable | Where | Effort |
|---|---|---|---|
| 5.1 | **Transaction record format** (channel, index, typed fields, activation, anchor → source loc via the anchor table) + `fw_channel` hook on the model side | zuspec-synth `records/`; hook in fw-hdl runtime | S |
| 5.2 | **T1 pin monitors** and **T2 internal-FIFO monitors** emitted from the contract | zuspec-be-sv | S each |
| 5.3 | **Divergence finder** over record streams (any two levels) | zuspec-synth (Python tool) | S |
| 5.4 | **`rtl.register`/stage-valid facts** from block IR (stage registers, valids, load enables) in the XLS adapter → **T3 bind-module emitter**, self-tested against the timing shell | be-xls + be-sv | M |
| 5.5 | **Replay** (captured T1 records drive the model or timing shell standalone) | zuspec-synth + be-sv driver | S–M |
| 5.6 | Perfetto / vendor transaction-stream / waveform-alias adapters | zuspec-synth | S each |

**Demo:** inject a bug into a block in an SoC run. The divergence finder reports "channel
`output_s`, transaction 1,284, field `count`, rle_pkg.sv:61", and the failing transaction
replays in the class under the SV debugger.

**Exit criteria:** records match bit-for-bit between the model, the timing shell and the
XLS RTL on the regression suite.

### Phase 6: Real blocks

| # | Deliverable | Where | Effort |
|---|---|---|---|
| 6.1 | SRAM via XLS RAM channels; RAM-port monitors | be-xls, be-sv, fw-hdl kit | M–L |
| 6.2 | Multi-proc tops via XLS codegen (adapter option), alongside fw-hdl `Integrate` | be-xls, zuspec-synth | M |
| 6.3 | Target-node delay-model characterization flow | libsynth + be-xls | L |
| 6.4 | Generated DV collateral (UVM agents, SVA, struct-field coverage) from contract + kits | zuspec-be-sv | M |

**Demo:** a memory-backed, multi-process block (GCM or a packet parser) on a commercial
node, end to end.

### Continuous: Track B on the same spine

These items aren't gated on the phases above, but they use their seams:
- **Native adapter** in zuspec-synth (ArchSched + V4→V5) implements the Phase 0 engine
  interface. Its first job is to pass the same contract, lockstep and test-everywhere checks
  as XLS. Then it closes the ~5% QoR gap.
- **Block-IR emitter** from V4 → `block_to_verilog_main`, the bridge that keeps XLS as the
  RTL emitter for tweaked models (staged-tlm §5).
- **Portfolio dispatch** comes once two adapters exist. The Partition step calls `accepts()` on
  each engine; `--explain` shows why.

## 5. What this buys for the two extensions

| Extension | Work left after Phase 5 |
|---|---|
| **Python input** | Close the zuspec-dataclasses → IR gaps for the hardware subset (process bodies, channels, source locs), surfaced by growing the canary. Write a Python edge-discovery pass equivalent to 1.3. **Everything else is reused:** contract, engine, reports, every SV projection (verification still gets shells, timing shells and monitors), divergence and replay. Optionally a pytest call-API emitter alongside SVUnit (2.1 already has the model) |
| **Another engine** | Implement `accepts`/`build`, map its nodes to anchors, and write an overlay. Missing namespaces degrade gracefully (e.g. no `sched` or `rtl.register`): no timing shell or T3 monitors for that engine, but shells, T1/T2 monitors, tests and lockstep still work |

## 6. Decisions for review

1. **Where SV projections live.**
   - **Recommend:** `zuspec-be-sv`, as a new `fw` target over the fw-hdl runtime.
   - **Alternative:** keep them in fw-hdl until a second input language exists. That is
     cheaper now, but it defers the split to when it is most expensive.
   - **Note:** `archsched/emit_v3.py` already sets the precedent of emitting fw-hdl
     classes from zuspec-synth.
2. **Where the fw runtime lives.**
   - **Recommend:** it stays in fw-hdl; the be-sv emitters declare a runtime-version
     dependency.
   - **Revisit** if the Python-authored flow needs the runtime without the front end.
3. **Two SV front ends.** fw-hdl `fe/` and `zuspec-fe-sv` are separate pyslang mappers.
   - **Recommend:** no merge now. Do make both emit the Phase 0 source-loc/diagnostic
     format, and decide on consolidation after Phase 1.
4. **New packages vs subpackages.**
   - **Recommend:** anchors, fact schema, overlays and `ResultStore` go in
     **`zuspec-ir-core`**. Front-end tooling (reports, LSP, PR diff) and other input
     languages need them without depending on synthesis.
   - Engine interface, kits, refinements, records and checks go in subpackages of
     `zuspec-synth` (`engine`, `kits`, `report`, `timed`, `staged`, `records`). Split out
     only if dependency weight demands it. Fewer repos means less release coordination.
5. **`synth.xls.Lower` home.** It consumes XLS IR, so it isn't zuspec-IR-neutral.
   - **Recommend:** it stays in libsynth. The native engine is the zuspec-IR-level one in
     zuspec-synth.
6. **Results are IR, not a sidecar format** (see [ir-results-overlay.md](ir-results-overlay.md)).
   - Engine results are typed facts on stable IR anchors, held in overlays beside the
     model, versioned with the IR schema.
   - Reports, guidance (promotion to intent) and refinements (staged TLM, timing shell)
     all read the same overlays.
   - **Review the anchor scheme first.** Everything else depends on it.
7. **Pinning XLS.** Contract, pipeline-map and naming rely on codegen 1.5 behavior.
   - **Recommend:** pin the xlsynth release, and gate upgrades with the Phase 3.4 diff and
     the Phase 5 record self-test.

## 7. Risks

| Risk | Mitigation |
|---|---|
| Multi-repo coordination slows every phase | Few subpackages (decision 4); fw-hdl is the first consumer and CI runs across the pinned set; land the neutral model and its first SV user in the same week |
| The neutral layer is designed for SV and XLS only, and "neutral" in name only | Phase 0 canary from zdc; the native adapter (Track B) as the second engine before the interface is frozen; mark interfaces provisional until both exist |
| Over-abstraction delays the commercial demo | Each Zuspec deliverable ships with its SV user in the same phase; no model without an emitter or check consuming it |
| XLS internals (block-IR names, II for procs) shift | Read from block IR every build; pin the version; self-tests in 4.3/5.4 |
| `zuspec.synth.proc` exists only in a dev checkout | Phase 0.1 release before anything else |

## 8. Status

| Phase | State | Note |
|---|---|---|
| 0 | done (release pending) | [phase0-plan.md](phase0-plan.md), [phase0-status.md](phase0-status.md) |
| 1 | planning | Detailed plan: [phase1-plan.md](phase1-plan.md) (draft for review) |
| 2–6 | not started | — |

*Update this table as steps land, so a fresh session can resume from this file.*
