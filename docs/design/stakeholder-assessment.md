# Stakeholders: needs, attraction, adoption, and who leads

Assessment, 2026-11-26. It responds to `design-abstraction-collective-win.md`
(the "collective win" draft). It reviews that draft, sets out each
stakeholder's pain points and needs from public research and from what this
repo already records, and recommends a lead stakeholder.

Inputs:
- the repo's earlier work: `pitch.md`, `wedge-assessment.md`,
  `featherweight-ip-strategy.md`, `ip-library-focus.md`, `automated-lifting.md`,
  `lean-positioning.md`, `picorv32-reach-plan.md` and `research/`;
- new web research (sources in §7). Items marked **[unverified]** could not
  be traced to a primary source and should not be quoted as fact.

**Revised 2026-11-26 (§8).** This assumes a lifting path that works, RTL →
fw-hdl sync → fw-hdl process with proven equivalence plus a fast-C emitter.
Under that assumption, adoption should run as parallel streams. They share
one lift engine and one flagship design, and each stream adds only its own
last-mile outlet. The lead is no longer a designer writing fw-hdl. It is
whoever *operates the lift*: the platform/modeling team, together with DV.
Designers are the last to adopt, not the first. The original recommendation
follows. It still holds if the lift stops at the sync level.

**Revised again (§9).** Designers come in through *integration*: top-level
wiring and instancing configured variants. That transform has no "magic" in
it, and the same integration description is the platform frame every other
stream needs.

**Goal recorded (§10).** fw-hdl is meant to cover chip-level concerns: UPF and
IP-XACT interop, and ideally DFT. Chip-level intent goes into the Zuspec IR,
and each standard format is an importer or exporter.

**Original recommendation, in one paragraph.** The lead has to be someone who *writes*
the method-level description, because every other team's benefit flows from
that source. Of the people who could write it, only the **block designer**
makes the win collective. When verification engineers write fw-hdl, the result
is a better testbench or reference model; that is the single-constituent
pattern the draft criticizes. When architects write it, the result is a model
that ESL history says gets abandoned. So the lead is the designer. But the
designer must be sold on what they get *for their own work*, not on
productivity and not on what others get:
- their verification half (49% of a designer's time): complete method-level
  proofs of their own block, and a fast model to test against;
- their timing-closure loop with physical design: re-pipeline without
  rewriting.

Two ways in, used together:
- *lift* existing RTL, which gives the other teams their benefits with no
  change to the design source;
- *author* new, control- and protocol-heavy blocks, where HLS has never won.

The verification engineer is the **champion**, because they gain most and
earliest. CAD/methodology and management are **gatekeepers** with known, meetable
conditions (§4). The earlier wedge work (verification engineers and VIP) stays
valid as the *vehicle* that builds trust. It is not the lead for this thesis.

---

## 1. Review of the draft

The thesis is right, and stronger than the draft makes it. The research shows
that the costly problems in silicon development sit *between* teams: spec
changes, models drifting from RTL, hardware/software interface bugs, timing
round-trips. Within any one team's work they are smaller. A single-team tool
can't address a boundary.

**Corrections and gaps**

1. **Unfinished bullet.** "It connects" has no object. The natural completion
   is the thesis itself: *it connects the teams through one executable
   description, from which each team gets the artifact it needs: model,
   RTL, proof obligations, transactors, spec.*
2. **The history paragraph has counterexamples worth using, not hiding.**
   - **HLS's best wins were cross-team.** NVIDIA's Catapult results were
     mostly verification: 1000x fewer CPUs for regression and 1000x more
     tests. They were not designer productivity alone (§7, [H1]).
   - **Arm's ASL served architects, verification and documentation at once**,
     because one executable artifact became *the* reference [A3].
   - **Sail did the same for RISC-V** [A4].

   These precedents show collective wins are possible. They also show the
   condition: the shared artifact must be the authoritative source, not a
   side model. The draft should say so; it is the mechanism of the argument.
3. **Missing stakeholders.** The draft lists design, integration, DV, firmware
   and architects. It leaves out:
   - **formal engineers**, whose needs differ from simulation DV;
   - **physical design**, which the draft folds into "integration";
   - **CAD/methodology**;
   - **management**, who approve adoption;
   - **IP vendors**.
4. **Every claim needs its evidence and its gap stated.** Today:

   | Claim in the draft | Evidence we have | Gap |
   |---|---|---|
   | Raises abstraction and productivity for designers | Process-level picorv32 runs at CPI 3.13 against 6.58 | No productivity measurement; area 3.5x (register file in flops); productivity is the weakest pitch (§2.2) |
   | Aids timing closure | Delay model and scheduler exist | **Current data cuts the other way:** Fmax 55.9 against 94.7 MHz, and the delay scheduler made ns/instruction worse (`picorv32-reach-plan.md` §1). Not claimable until B1/B2 land |
   | Faster simulation and better formal for DV | About 75x faster simulation (17M against 0.22M instructions/s); dv-solve-formal 7.2x faster than yosys-smtbmc | Method-level formal not yet run (V0–V4 not started) |
   | Fast software models for firmware | The SV class model runs at 17M instructions/s under Verilator | No C emitter; no QEMU or Renode packaging; firmware needs it *in their* platform |
   | Executable and Lean on-ramps for architects | `lean-positioning.md` | ISA-level precedent only (ASL, Sail); nothing at block level |

   "Broad value is the north star, and we need to be able to back it up" is
   the right standard. Today, only the simulation-speed claim is backed.
5. **Typos:** consituent, "the bring" (they bring), archtecture, diferent.
6. **The last sentence names the open question** ("Ideally, it would be
   design, but this might be challenging"). §5 answers it.

---

## 2. Stakeholders

Each stakeholder has a **role** in adoption:
- **Author:** writes fw-hdl.
- **Consumer:** benefits from what others wrote.
- **Gatekeeper:** can block adoption.

Only an author can lead.

### 2.1 Industry backdrop (applies to everyone)

**From the Siemens/Wilson Research Group 2024 IC/ASIC study [S1, S2]**
- First-silicon success is **14%**, the lowest in 20 years (32% in 2020). The
  2026 study reportedly puts it near **5%** [S3] (secondary reporting).
- **75%** of projects finish behind schedule.
- Designers spend **49%** of their time on verification.
- Debug is the largest single activity for verification engineers, and
  "unpredictable".
- Demand for engineers has flattened (about 2.4–3% a year since 2016), while
  teams take on more tape-outs a year [S2].
- The top cause of respins is logic or functional flaws. Their root causes are
  design errors, then changing, incorrect or incomplete specs.
- "70% of respins are design errors due to changes in the spec." This is a
  Synopsys quote in SemiEngineering [S2], not survey data.

**What this means for the pitch.** The biggest losses come from *spec churn*
and from *keeping models, tests and RTL consistent*. A single description from
which each team's artifact is derived attacks the consistency problem
directly. That is the collective-win argument, and the data supports it better
than any productivity argument.

### 2.2 RTL / block designers: **author**

**Pain points**
- **Verification**, not RTL writing, takes half their time. Rise DA's
  Agarwala: "Most of the schedule is spent on verification and the
  iterations needed to meet PPA" [H5].
- **Late spec changes and ECOs** (§2.1).
- **Timing round-trips with physical design** that force RTL re-pipelining
  (§2.5).
- **Hand-written fast models drift from the RTL**, but that pain belongs to
  another team (`pitch.md` §"Who this is for").

**What they need from fw-hdl**
- Output RTL they would have written: readable, one parameterized module per
  class, names traceable, ECO-patchable.
- QoR within a few percent on the blocks they care about. zpicorv32 is within
  3.1% of picorv32; the process-level version is not yet close.
- Predictable cycle behavior: "one cycle later and it's broken"
  (`pitch.md` §"Overlooked considerations").
- A way to adopt on one block, coexisting with SV RTL.

**What would make it attractive (in order of strength)**
1. **Their verification half gets smaller.** Complete method-level proofs of
   their own block, a fast model to test against, and generated transactors
   for block tests. Each of these is something the designer gets back
   immediately.
2. **Re-pipelining without rewriting** when physical design reports a failing
   path, with an equivalence proof generated along with it.
3. **Their block's model and register map come for free**, so the firmware
   and modeling teams stop chasing them.
4. Less code. True, but the weakest argument; designers don't experience
   writing RTL as the bottleneck.

**What would cause them to consider adopting**
- **Proof on a real block**, with QoR, debug and LEC evidence published
  side by side (`featherweight-ip-strategy.md` P2).
- **SV, not a new language.** The repo's traction research found teams adopt
  tools in their own host language and veto new ones
  (`research/traction-design-frameworks.md`).
- **A first block that is new and control- or protocol-heavy.** HLS owns
  datapaths [H1–H4], and its weak spot, control and protocol logic, is fw-hdl's
  strength.
- A peer who did it (the flagship-owner pattern: every framework with traction
  had one).

**Killers**
- Unreadable or undebuggable output: the Chisel and HLS experience [H6, D5].
- Bluespec-style fragility, where a local edit changes behavior elsewhere [H7].
- QoR loss on the critical path.
- No LEC or SLEC path (the Chisel SweRV study needed 15,000+ manual LEC
  matches).
- "Most designers don't write OO SV" (`pitch.md`, unverified).

### 2.3 Verification (DV) engineers: **author of testbenches, consumer of the design source; champion**

**Pain points**
- Debug is their largest activity [S1].
- Reference models are costly to build and keep in step. No hard number
  exists **[unverified]**, but practitioners agree.
- They wait on RTL to bring up the testbench.
- Simulation is the largest compute consumer. Parallel RTL simulation gains
  only 2–4x over Verilator [D3].
- UVM is used on about 80% of ASIC projects, so incumbency is heavy. cocotb
  is on about 5% of ASIC and about 20% of FPGA projects [D1, D2].
- Encrypted VIP can't run on Verilator, and simulation, formal and emulation
  VIP are separate products (`research/vip-market.md`).

**What they need from fw-hdl**
- The model on day 1, before RTL.
- Transactors and VIP between method and signal level, generated rather than
  hand-written (the bridges already exist for fw-hdl, plain-SV/UVM and
  cocotb).
- Coexistence with UVM.
- Traceable generated code.

**What would make it attractive**
- **The design itself is the reference model.** No second model to keep in
  sync, and testbenches can start on the fast model.
- Regression throughput: the 75x class model is roughly two orders of
  magnitude beyond what parallel RTL simulation achieves.
- Method-level transactions in debug.

**What would cause them to consider adopting**
- It drops into an existing UVM or cocotb bench.
- It helps on wrapped legacy RTL with no design change. This is the low-risk
  entry the earlier wedge work identified.

**Killers**
- Rewriting the bench.
- Maturity doubts: 31% of cocotb users were unsure of cocotb's future [D2].

**Why they are the champion and not the lead.** They gain the most from the
designer adopting, and they can ask for it. But when DV writes fw-hdl by
themselves, the result is a better testbench, not a collective win.

### 2.4 Formal engineers: **consumer; strong ally**

**Pain points**
- **Scarce expertise and costly property writing** [F3].
- **State-space explosion** on deep pipelines, worked around by
  decomposition and bounded proofs [F4].
- **Bounded proofs leave doubt.** riscv-formal is bounded at about 20–30
  cycles, and in one comparison it found only 2 of 7 real bugs [F5].
- **Formal adoption is growing, mostly through apps** that non-experts can
  use (32–35% of designs; apps grew 8.7% a year) [S1, F1].

**What they need from fw-hdl**
- Proof obligations *derived* from the method specs.
- Shallow proofs: one step per method.
- Refinement to RTL with the map supplied (M7).
- Results that standard engines can reproduce (SBY, Jasper, VC Formal).

**What would make it attractive**
- **Complete rather than bounded results.**
- **Proofs no longer have to be hand-decomposed.** The method structure is the
  decomposition.
- **Control logic gets the transaction-level-to-RTL equivalence that
  datapaths already have.** C-to-RTL equivalence tools (VC Formal DPV, Jasper
  C2RTL) prove a C/C++ model equivalent to pipelined RTL. Buyers already pay
  for this, mostly on datapaths [F7, F8]. A refinement map known from the
  lowering could extend it to control logic.
- **Precedent** in Arm ISA-Formal (ASL to properties; found bugs in all eight
  processors) [A3] and Sail on CHERIoT-Ibex [A4].

**What would cause them to consider adopting**
- The picorv32 V-track numbers against riscv-formal on the same core.
- Results reproducible in their own tool.

**Killers**
- Trust in the refinement map.
- How far the proof reaches into hand-written parts.
- A new property language.

### 2.5 Physical design, timing closure, SoC integration: **consumer; gatekeeper on output quality**

**Pain points**
- **Closure loops of days to weeks.** Some fixes require RTL re-pipelining,
  which goes back to the designer [P1, P2].
- **"Interconnect IP changes faster than the timing can be closed"** [P2].
- **Integration may take up to 65% of SoC design time** [P3] (old source,
  close to a vendor).
- **95% of ASICs have two or more asynchronous clock domains** [S1].

**What they need from fw-hdl**
- RTL whose names survive into netlists.
- No surprise in the CDC, RDC, lint and UPF flows.
- ECO-friendly structure.

**What would make it attractive**
- A pipelining change that goes from "file a request with the designer and
  wait for new RTL" to "re-run the schedule with a new delay budget, and get
  an equivalence proof along with it".

**What would cause them to consider adopting**
- They don't adopt; they *accept*. They need first-pass QoR comparable to
  hand-written RTL, and fewer RTL round-trips on a real project.

**Killers**
- Generated RTL that breaks their scripts.
- Unstable names across regenerations.
- An Fmax loss. Today's picorv32 data shows one; this must change before
  claiming timing as a benefit.

### 2.6 Firmware and pre-silicon software: **consumer**

**Pain points**
- **Embedded software is about 40% of complex-SoC cost** [W1].
- **Missing models are the main barrier to virtual prototypes.** "Model
  availability is definitely one of the areas that makes it hard to adopt"
  [W3].
- **Models are late and lag the RTL.** OpenTitan's QEMU fork is pinned to RTL
  1.0.0 with "dummy" devices; LiteX's Renode generator special-cases lagging
  models (`research/ip-market.md`).
- **Device-protocol violations are 38% of Linux driver defects** [W2] (post-silicon
  data).
- **They share unstable RTL drops on emulators** [W4].

**What they need from fw-hdl**
- Models *in their platform* (QEMU, Renode, Virtualizer, SystemC TLM).
- Fast enough to boot an OS.
- Register maps and headers from the same source.
- Models at RTL drop 1, not months later.

**What would make it attractive**
- **Models that are generated and therefore never lag the RTL.**
- **One register-map source** for the hardware, the driver header and the
  model.
- **Less dependence on emulator queues.**

**What would cause them to consider adopting**
- They don't adopt; they *ask*. They need a model plugged into Renode or
  QEMU for a real peripheral set. The "Cheshire, lifted" target in
  `ip-library-focus.md` is the right demo.
- There is no C emitter today, so this benefit is unproven.

**Killers**
- Models outside their platform.
- Fidelity gaps when the OS boots.

### 2.7 Architects and performance modelers: **potential author; low leverage now**

**Pain points**
- **Correlating models with RTL is a standing program.** Ampere runs daily
  correlation regressions, targets 90% of tests within ±10%, and refined the
  process over four CPU generations [A1].
- **Models cost real money; SystemC/ESL stalled** on business model,
  standards and verification gaps [A2].
- **gem5 is not cycle-accurate.** Published error is about 13% on Arm SPEC
  CPU2006, and up to 272% on GPU memory latency [A5].

**What they need from fw-hdl**
- Trustworthy timing, not just function.
- A model that stays correlated *by construction*.
- Interoperability with their C++ and gem5 code base.

**What would make it attractive**
- **The model and the RTL come from one source.** At block level, model-to-RTL
  correlation work goes away.
- **The Lean path** gives a spec that can be proved, as ASL and Sail did for
  ISAs [A3, A4].

**What would cause them to consider adopting**
- A block-level precedent. None exists publicly; executable specs have
  succeeded only at the ISA level, and only after becoming the official
  reference.

**Killers**
- The ESL history makes them wary of "model-first, refine later" pitches.
- The process change involved.
- Little tool budget of their own **[unverified]**.

**Role:** they write fw-hdl at the edges (exploration, ISA-level Lean specs).
They are not the lead.

### 2.8 CAD/methodology teams: **gatekeeper**

**Concerns**
- Open source is seen as buggier, offers no contractual protection, and raises
  security concerns [M1, M2].
- Flow integration.
- Tool qualification. Under ISO 26262, a downstream check (LEC or SLEC) can
  bring a generator down to TCL1 [M3, M4]. This is our inference from those
  sources.

**What they need from fw-hdl**
- Plain SV into the existing signoff flow, with no tool in signoff that isn't
  already there.
- Reproducible builds.
- Equivalence evidence that their commercial tools produce.
- A support story.

**What makes them say yes**
- Nothing in signoff changes.
- The pilot uses their own SEC/LEC tool (`automated-lifting.md` already plans
  for this).

**Killers**
- A new simulator or signoff dependency.
- A single maintainer.

### 2.9 Engineering management and program leads: **gatekeeper and sponsor**

**Pain points**
- Schedule: 75% of projects are late [S1].
- Respins, with some large companies planning for up to four [S2].
- Flat headcount against rising tape-out counts [S2].

**What they need from fw-hdl**
- A bounded-risk pilot on a non-critical block, with metrics they recognize:
  - engineer-hours;
  - weeks until the testbench and the model exist;
  - bugs found before RTL freeze;
  - closure iterations.

  The NVIDIA pattern was a video team's pilot, then adoption across the
  company [H1].

**What makes them say yes**
- Several teams on the same project report gains from the same pilot. This
  is where the collective-win thesis pays off politically. A single-team tool
  needs one manager's sponsorship; a cross-team result *creates* sponsors.

**Killers**
- Risk to a tape-out.
- Any dependency that their team can't support.

### 2.10 IP vendors and the open-source ecosystem: **author (later), multiplier**

- **IP vendors** need proof that their IP works for each customer
  configuration, plus models and VIP shipped with it. One description yields
  all of these, which suits them.
- **Their adoption spreads the framework only if the framework ships with the
  IP.** VexRiscv spread the IP, not SpinalHDL (`featherweight-ip-strategy.md`).
- **Open source and academia** are a channel (CHIPS Alliance; courses), not a
  lead. PyMTL3 and OSSS stalled without an industrial owner
  (`research/pymtl3.md`, `research/traction-design-frameworks.md`).

---

## 3. Who gets what, at a glance

| Stakeholder | Role | Top pain | What fw-hdl gives | Proof we have today | Proof needed |
|---|---|---|---|---|---|
| Block designer | **Author** | Half their time on verification; ECOs; timing round-trips | Complete per-method proofs; a fast model; re-pipelining with proofs; readable RTL | zpicorv32 within 3.1% on LUTs; CPI 3.13 against 6.58 | Area and Fmax at parity (B1/B2); V2/V3; ECO/LEC demo |
| DV engineer | Author (benches); consumer; **champion** | Debug; reference-model upkeep; waiting on RTL | The design is the reference; 75x model; generated transactors and bridges | 75x; wb_xtor bridges for fw-hdl, UVM and cocotb | A bench on a lifted design within a real UVM flow |
| Formal engineer | Consumer; ally | Expertise; state explosion; bounded results | Derived, shallow, complete obligations; refinement map | dv-solve-formal 7.2x faster than yosys-smtbmc | V0–V4 on picorv32 |
| Physical design / integration | Consumer; gatekeeper | Closure loops in weeks; RTL re-pipelining requests | Re-schedule against a delay budget; stable names | None (Fmax is worse today) | Equal or better Fmax; a re-pipelining round-trip demo |
| Firmware | Consumer | Late, lagging models; register-map churn | Generated models; one register source | Fast SV model only | A C/Renode emitter; a lifted SoC demo |
| Architect | Potential author | Model/RTL correlation | Correlation by construction; Lean specs | Lean positioning only | Block-level example |
| CAD/methodology | Gatekeeper | Flow risk; support | Plain SV; their own LEC/SEC; nothing new in signoff | Plain-SV output exists | Pilot inside a commercial flow |
| Management | Gatekeeper/sponsor | Schedule; respins; headcount | Cross-team pilot metrics | None | A pilot with metrics |
| IP vendor | Later author | Per-configuration proof; models and VIP | All from one source | featherweight-ip plans | Flagship IP |

---

## 4. Adoption conditions (all stakeholders)

These are conditions that every pitch has to meet, whoever it is aimed at:
1. **Plain, readable SV out, through unchanged signoff.** This satisfies
   physical design, CAD and the designer at once.
2. **Equivalence evidence produced by the user's own tools.** This lowers
   tool-qualification risk and addresses designers' distrust of generated RTL.
3. **Incremental adoption: one block, alongside SV RTL.** Lifting covers the
   blocks that already exist.
4. **Each team's artifact must reach that team's existing platform:** UVM and
   cocotb for DV, SBY, Jasper and VC Formal for formal, QEMU and Renode for
   firmware.
5. **One flagship, owned and shipped,** with side-by-side published numbers.

---

## 5. Who should lead

**The block designer, sold on their own verification and closure loop, entering
through lifting and new control/protocol blocks.**

### Why not each alternative

- **Verification engineers.** The earlier wedge work chose them because they
  meet the fewest adoption objections, and that still holds for the *vehicle*
  (VIP, observability, testbed). But when DV writes fw-hdl, the design source
  stays hand-written SV. The model, proofs and transactors then sit beside the
  design, not derived from it, and model drift comes back. That is the
  single-constituent outcome the draft warns against. DV can carry the
  message in; it cannot deliver the thesis.
- **Architects.** ESL failed on exactly this path (model first, refine
  later). They also have little budget, and executable specs have no
  block-level precedent.
- **Firmware, physical design and formal.** They are consumers: they don't
  write the description. Their demand is the *pull*, not the lead.
- **Management and CAD.** They are gatekeepers. Their conditions are in §4.

### Why the designer, despite the risk

- **Only a design-level source makes every downstream artifact derived and
  therefore consistent.** Consistency attacks the spec-churn and
  model-drift costs that dominate §2.1.
- **The designer's own pain can be addressed directly.** Pitched on
  productivity, the designer is the hardest sale (A was rated poorly in
  `wedge-assessment.md`). Pitched on verification, they are an easier sale:
  the designer spends half their time verifying, and method-level formal plus
  a fast model is a direct return on that time. NVIDIA's HLS adoption followed
  this pattern [H1].
- **There is a niche where the incumbents lose.** HLS wins datapaths. Control
  and protocol blocks are where HLS is weak, and where method-level transactions,
  transactors and refinement maps are strongest.

### How to make the designer lead workable

| Step | What | Who benefits | Removes which objection |
|---|---|---|---|
| 1 | **Lift existing RTL** (zpicorv32-style, proven equivalent) | DV (model), formal (obligations), firmware (models) | "Don't touch my RTL": the signoff source is unchanged |
| 2 | **Designer's own verification on the lifted or new block**: V2/V3-style proofs, a fast model, generated transactors | Designer | "What's in it for me": half their job |
| 3 | **New control or protocol block authored at method level**, lowered with published QoR, LEC and readability | Designer, physical design | Distrust of generated RTL; QoR |
| 4 | **Re-pipelining round-trip** with an equivalence proof | Physical design, designer | "Timing closure" becomes a claim we can back |
| 5 | **Cross-team pilot metrics** | Management | Sponsorship |

The picorv32 reach plan is already shaped this way. Its A/B/V tracks are
steps 2–4 on one core. The DV-led wedge vehicles (VIP, observability) run in
parallel as trust-builders and as the channel to the champion.

### Checkpoints that would change the recommendation

- **If B1/B2 can't bring area and Fmax within reach of hand-written RTL on
  picorv32**, the designer pitch rests on verification alone. Then make the
  DV engineer the lead, with lifting as the main vehicle, and keep design as
  the destination.
- **If V2/V3 don't beat riscv-formal clearly** (size, run time, completeness),
  step 2 loses its strongest argument. Check this before investing in
  outreach to designers.
- **If interviews with designers (8–10, alongside the DV interviews already
  planned in `wedge-assessment.md` §6) show they won't own a method-level
  source even for new blocks**, fall back to DV-led lifting.

---

## 6. Open questions

1. Who owns the method-level source after hand-off, when an architect or DV
   engineer started it? This is undocumented in the industry
   (`research/architecture-handoff.md`).
2. Do designers accept SV classes as a design language? It is unverified that
   most don't write object-oriented SV; this needs interviews.
3. Is a C/Renode emitter in scope soon? Without it, firmware stays a promise.
4. The register-map churn rate and model build time have no public data.
   Collect them in interviews, because they size the firmware and architect
   value.
5. The respin-cause percentages from the 2024 report are only in a chart.
   Read the values before quoting a split.

---

## 7. Sources

**Surveys**
- [S1] Siemens/Wilson Research Group, 2024 IC/ASIC functional verification trend report: https://static.sw.cdn.siemens.com/siemens-disw-assets/public/1NyfMZJ3nuPhMGQCGFDITG/en-US/ic-asic-functional-verification-trend-report-wp-86424-d3.pdf
- [S2] SemiEngineering, "First-Time Silicon Success Plummets": https://semiengineering.com/first-time-silicon-success-plummets/
- [S3] SemiEngineering, "Hope Is Not a Strategy" (2026; secondary reporting): https://semiengineering.com/hope-is-not-a-strategy-what-first-silicon-success-really-takes/

**HLS and design frameworks**
- [H1] Siemens, "NVIDIA closes design complexity gap with HLS" (vendor): https://resources.sw.siemens.com/en-US/white-paper-working-smarter-not-harder-nvidia-closes-design-complexity-gap-with-hls/
- [H2] Khailany et al., MatchLib, DAC 2018: https://ctorng.com/pdfs/khailany-nvidia-matchlib-dac2018.pdf
- [H3] Siemens, Google WebM HLS (vendor): https://resources.sw.siemens.com/en-US/white-paper-google-develops-webm-video-decompression-hardware-ip-using-high-level/
- [H4] Google XLS: https://github.com/google/xls
- [H5] SemiEngineering, "AI vs. High-Level Synthesis": https://semiengineering.com/ai-vs-high-level-synthesis/
- [H6] Chisel readability (anecdotal): https://news.ycombinator.com/item?id=21340009
- [H7] Bluespec experience (anecdotal): https://news.ycombinator.com/item?id=30776778, https://arxiv.org/pdf/1905.03746

**Verification**
- [D1] Sigasi summary of WRG 2024 methodology data: https://www.sigasi.com/news/verification/
- [D2] cocotb user survey 2023: https://www.cocotb.org/2023/06/17/user-survey-2023
- [D3] Parendi (parallel RTL simulation): https://arxiv.org/html/2403.04714v1
- [D5] Source-level debug for HLS (Stanford dissertation): https://www-vlsi.stanford.edu/people/alum/pdf/2212_Zhang_SourceLevelDebugging.pdf

**Formal**
- [F1] WRG 2022, Part 10: https://blogs.sw.siemens.com/verificationhorizons/2022/12/26/part-10-the-2022-wilson-research-group-functional-verification-study/
- [F3] Gleirscher and Marmsoler, formal methods practitioner study: https://arxiv.org/pdf/2002.07279
- [F4] ChipVerify, formal verification: https://chipverify.com/verification/formal-verification
- [F5] riscv-formal bounds and bug-finding comparison: https://arxiv.org/pdf/2106.10392
- [F7] Cadence Jasper C2RTL: https://www.cadence.com/en_US/home/tools/system-design-and-verification/formal-and-static-verification/jasper-c-formal-verification.html
- [F8] Synopsys DPV: https://www.synopsys.com/blogs/chip-design/datapath-validation-artificial-intelligence-mathematical-cores.html

**Architecture and ISA specs**
- [A1] Ampere model/RTL correlation: https://arxiv.org/html/2608.19300
- [A2] SemiEngineering, "Is SystemC Broken?": https://semiengineering.com/is-systemc-broken/
- [A3] Reid et al., ISA-Formal, CAV 2016: https://alastairreid.github.io/papers/cav2016_isa_formal.pdf
- [A4] sail-riscv: https://github.com/riscv/sail-riscv; CHERIoT-Ibex: https://arxiv.org/pdf/2502.04738
- [A5] gem5 accuracy: https://arxiv.org/pdf/2007.03152, https://research.cs.wisc.edu/hal/papers/vramadas-yarch24-GAP.pdf

**Physical design and integration**
- [P1] Timing closure techniques: https://chipverify.com/rtl-synthesis/timing-closure-techniques
- [P2] Design-Reuse, "Do SoC Architects Have to Get Physical?": https://www.design-reuse.com/article/60909-do-soc-architects-have-to-get-physical-/
- [P3] Design-Reuse, "Minimal Effort Chip Design Using IP" (old): https://design-reuse.com/articles/26124/minimal-effort-chip-design-using-ip.html

**Firmware and software**
- [W1] EE Times / IBS, SoC cost breakdown: https://www.eetimes.com/the-golden-age-of-custom-silicon-draws-near-part-3/
- [W2] Ryzhyk et al., Dingo, EuroSys 2009: http://ryzhyk.net/publications/Ryzhyk_CKH_09.pdf
- [W3] SemiEngineering, "The Drive Toward Virtual Prototypes": https://semiengineering.com/the-drive-toward-virtual-prototypes/
- [W4] DVCon, "Is it a software bug? It is a hardware bug": https://dvcon-proceedings.org/wp-content/uploads/Is-it-a-software-bug-It-is-a-hardware-bug-1.pdf

**CAD/methodology**
- [M1] SemiEngineering, open-source EDA security: https://semiengineering.com/security-concerns-weigh-down-open-source-eda/
- [M2] Kahng, "Looking Into the Mirror of Open Source": https://vlsicad.ucsd.edu/Publications/Conferences/374/c374.pdf
- [M3] Siemens, ISO 26262 tool qualification: https://blogs.sw.siemens.com/verificationhorizons/2022/04/13/clearing-the-fog-of-iso-26262-tool-qualification/
- [M4] SemiEngineering, TCL1: https://semiengineering.com/for-soc-iso-26262-compliance-should-all-eda-tools-be-tcl1/

---

## 8. Revision: lifting first, parallel streams (2026-11-26)

**The premise.** A lifting path works end to end:
- Verilog RTL → fw-hdl sync, at L1, cycle-equivalent and checked by SEC;
- fw-hdl sync → fw-hdl process, at L2 or model level, checked by
  operation-level equivalence;
- a planned fast-C emitter turns the process-level description into
  Renode/QEMU devices.

`automated-lifting.md` covers the pipeline and its checks.

### 8.1 What changes

§5 argued that the lead must be an *author*, because every team's benefit
flows from the source. Lifting breaks that dependency.
- The hand-written RTL stays the source. fw-hdl becomes the
  *derivation engine* that produces each team's artifact from it, with an
  equivalence record.
- The collective win becomes deliverable on existing IP, with no designer
  buy-in.
- The objections that made designer-first risky mostly don't apply: nobody
  is asked to change their RTL, QoR is untouched, and signoff is unchanged.

So yes: **adoption should be parallel.** There is one condition. Run it as
*one engine, one flagship, several outlets*, not as several go-to-market
efforts.

| Shared by every stream | Per-stream (the thin last mile) |
|---|---|
| Lift engine (sync and process); Zuspec IR; equivalence record re-run on every RTL release; one flagship SoC or IP set | The outlet emitter or packaging, and the metric that stream's team trusts |

| Stream | Outlet | Metric they trust | Incumbent gap |
|---|---|---|---|
| Platform / firmware | C model as a Renode peripheral, then a QEMU device; register headers | Linux boots at least 100x faster than Verilator; the model ships with RTL drop N, not months later | Models are hand-written, late, and drift |
| DV | Lifted model as scoreboard predictor; in-situ harness (`automated-lifting.md` §5.5); transactors | Existing tests become equivalence tests unchanged; regression run time | Reference models are costly; RTL is slow |
| Formal | Method-level obligations on the process-level lift, carried to the RTL through the equivalence record | Complete proofs, size and run time against riscv-formal or deep BMC | Bounded results; scarce expertise |
| Architecture | Process model with a timing annotation, correlated by construction | Correlation work removed | Daily correlation regressions |
| Management | The composite: one pilot, several teams' numbers | Weeks earlier, engineer-hours saved | Single-team tools need single sponsors |

Physical design and designers sit outside the first wave. Their stream
starts when re-lowering (retiming, configuration changes) reaches QoR parity.

### 8.2 Who leads now

**The lift operator.** The natural operators are:
- **the platform/modeling team**, which writes the drifting models by hand
  today. They have the most to gain and own the most visible metric (Linux
  boots on a model that is never stale);
- **DV**, because the lift is grounded in DV's predictor and regression
  (`automated-lifting.md` §2), and DV runs the in-situ checks.

They are a better lead than designers in four ways:
1. They don't have to change how they write anything they sign off.
2. Their win is measurable without a QoR comparison.
3. Their budget lines exist: virtual prototypes and emulation.
4. Their success creates the cross-team evidence management responds to.

Designers move from *first author* to *last adopter*:
- **First, passively:** their RTL is lifted, and they see their own block at
  process level, proven equivalent.
- **Then actively:** they edit at process level where that is easier than
  RTL, namely ECOs, re-pipelining and new configurations.

This is the two-ladder plan with the up-ladder running first.

### 8.3 What the premise has to deliver (the gates)

1. **Speed needs the process-level lift.** A sync-level (L1) lift emitted as
   C is a cycle-based model, roughly Verilator speed. The 75x on picorv32 came
   from a *hand-written* process-level description. Sync → process means
   recovering intent from the RTL: FSMs, handshakes, pipelines. That step is
   the research bet, and per-block automation rates will vary
   (`automated-lifting.md` risk 1). **Measure it first:**
   - automation rate per block;
   - model speed against Verilator.

   Without it, the platform and DV-speed streams have nothing to offer.
2. **The lift has to be unattended per release.** Drift doesn't disappear;
   it moves into the lift. If every RTL release needs human help to re-lift,
   consumers get a model that lags, which is the pain we set out to remove.
   **Metric:** re-lift and re-check time per RTL release (hours, no human),
   and the share of releases that re-lift cleanly.
3. **Formal results carry over only as far as the relation reaches.** A
   proof on the process-level lift says something about the RTL only through
   the equivalence relation. At L2 or model level, that covers only the
   observables the relation names. State this in every formal claim.
4. **Readable lifts.** A lift that passes every check but that no one can
   read will be rejected by the designers who are supposed to adopt last
   (`automated-lifting.md` risk 5).

### 8.4 Risks particular to going parallel

- **Spread.** Each outlet has its own platform (Renode/QEMU, UVM/cocotb,
  SBY/Jasper) with real integration cost. Keep each outlet thin, and show all
  of them on the *same* flagship.
- **Message dilution.** Use one message, with the streams as its proof
  points: *keep your RTL; get models, proofs and VIP that stay correct by
  construction.*
- **Lifting could entrench RTL.** If teams get every benefit without
  changing anything, designers may never move up. The pull to move up has to
  be shown: an ECO, a re-pipelining change or a new configuration that is
  easier at process level and re-lowers at QoR parity. Without that demo, the
  abstraction north star is postponed, not reached.

### 8.5 Updated checkpoints

| Checkpoint | If it fails |
|---|---|
| Sync → process lift automated on a set of control/protocol blocks; C model at least 100x faster than Verilator | Platform and speed streams pause; DV-in-situ and formal at sync level continue; fall back to the §5 designer-led path |
| Unattended re-lift per RTL release on the flagship | Present lifting as one-off model creation (weaker), not continuous |
| Method-level formal on the lift beats riscv-formal (picorv32 V-track) | The formal stream falls back to sync-level BMC |
| One pilot with metrics from at least two streams | Revisit whether parallel streams are earning their cost |
| A process-level edit that re-lowers at QoR parity | Designer adoption stays aspirational |

---

## 9. Integration as the designer's way in (2026-11-26)

**The proposal.** Designers start with fw-hdl as the integration layer:
- top-level wiring;
- instancing several variants of a block with different configurations;
- connecting through typed interfaces.

The leaves stay RTL, wrapped. Lifted versions are validated by the existing
simulation DV. This is `roadmap.md` phase 1 ("Wrap and integrate existing
RTL"), now used as the adoption entry.

### 9.1 Why it works for designers

- **No magic.** Instancing, wiring and parameterization lower almost 1:1 to
  `generate` blocks and instances. Distrust of generated RTL, the main reason
  designers reject HLS, Chisel and Bluespec, is weakest here. The output is
  what they would have written.
- **The bar is lower than for design.** Top levels are *already* generated
  at most companies:
  - in-house Perl, Python or Tcl scripts;
  - Verilog-mode AUTOs;
  - IP-XACT flows (Magillem, coreAssembler);
  - OpenTitan's topgen, LiteX, and Chipyard.

  fw-hdl has to beat the incumbent generator, not hand-written RTL.
- **Precedent.** Chisel's most durable success is SoC configuration and
  integration (Chipyard and rocket-chip, with Diplomacy's parameter
  negotiation), more than leaf-block design.
- **The pain is real, though weakly quantified.** One old, vendor-adjacent
  source says integration takes up to 65% of SoC design time [P3]. Variants
  multiply the cost. Connection mistakes are cheap to make and costly to find
  in simulation.
- **The changes are slow.** Leaves change rarely, so wrappers and lifts are
  refreshed seldom. That eases gate 2 of §8.3: re-lifting is rare, and so
  can be supervised at first.
- **The integrators are the right people.** Integration is usually owned by
  the chip-level design lead, who has influence over methodology and is close
  to management.

### 9.2 Why it does more than help designers

The integration description is the **platform frame** in `ip-library-focus.md`
(the platform generator: "configuration to RTL top, QEMU/Renode machine, device
tree, headers"). One description of instances, configurations, address map,
interrupts and clocks feeds every stream:

| Stream | What it gets from the integration description |
|---|---|
| Designer / integrator | Readable SV top; variants from configuration objects; connection errors (protocol, width, direction, unconnected) caught at elaboration |
| Firmware / platform | Memory map, interrupt map, device tree, headers; with lifted leaves, the Renode/QEMU machine |
| DV | SoC-level testbench skeleton; transactors at every typed boundary; per-variant configuration of the bench |
| Formal | Connectivity checks generated from the declared connections (a standard formal app today, usually fed by spreadsheets) |
| Physical design / integration | Stable instance and net names; a structural top with no surprises |

So integration is both the low-risk entry for designers and the backbone of
the parallel streams in §8. The leaves come in through lifting, the top
through integration.

### 9.3 Validating lifts with simulation DV

This fits `automated-lifting.md` checks B and C (the existing regression with
coverage parity; operation-level equivalence in situ). Points to settle:

- **Integration needs no lifting.** Wrapping is enough for the integration
  entry, so that path doesn't depend on lift validation at all. Lifting, and
  validating it, matters only for the model, DV-speed and formal streams.
  Keep the two decoupled so a hard lift never blocks integration.
- **Use SEC where it is cheap.** A sync-level (L1) lift is close to
  structural, and SEC usually closes on it. Simulation DV then carries the
  process-level (L2/model) step, where SEC doesn't apply.
- **Simulation evidence is bounded by coverage.** Validation is only as
  good as the regression and its coverage. Report coverage parity with every
  lift, and say plainly that a lift validated this way is "equivalent under
  the regression", not proven. The formal stream can close specific gaps.
- **Variants multiply validation.** Either the lift preserves
  parameterization (one lift validated across the configurations actually
  instanced), or each configuration is lifted and validated separately. The
  first scales; it requires the lifter to recover parameters, not just
  elaborate one configuration. Validate the configurations the integration
  instantiates, not the full space.
- **Run the in-situ harness on the integrated SoC.** Placing the lifted
  model beside the wrapped RTL inside the integrated top (`automated-lifting.md`
  §5.5) turns SoC-level tests into lift-validation tests too.

### 9.4 Risks

- **Incumbent generators are "good enough" and owned by CAD.** Replacing an
  in-house script needs a reason beyond tidier code. The reason is §9.2:
  the same description produces the platform, the bench and the connectivity
  checks. Without those outlets, fw-hdl is just another netlister.
- **Seen as a netlister.** Integration alone doesn't show the abstraction
  being raised. The bridge to the north star is method-level interfaces at
  the top (typed bundles and protocol kits). With those, the integrated
  design has a method-level view: it can run with lifted or process-level
  leaves, and a leaf can later be authored at process level behind the same
  interface.
- **Chip-level concerns arrive with integration:**
  - several clock and reset domains, and CDC/RDC;
  - power intent (UPF);
  - DFT insertion and pads;
  - IP-XACT exchange with third-party IP.

  *Superseded by §10:* the goal is to encompass these, with UPF and IP-XACT
  interop and, ideally, DFT. At minimum, fw-hdl must not break them (stable
  names, clean hand-off points).
- **Parameter-preserving lifts are harder** than lifting one elaborated
  configuration (§9.3).

### 9.5 What the demo must show

On one flagship SoC (for example, the platform kit's PLIC + UART + core, or
Cheshire):
1. The top level in fw-hdl: two or more variants of a block, configured
   procedurally; leaves wrapped RTL; readable SV out, diffed against the
   original top (or topgen's output).
2. A seeded connection error caught at elaboration, which the original flow
   would have caught only in simulation.
3. From the same description: device tree, headers, a Renode machine, a
   SoC-bench skeleton with transactors, and connectivity checks.
4. Adding a variant or a peripheral: one configuration change, everything
   regenerated with no hand edits (`ip-library-focus.md` milestone 3).
5. One leaf lifted, validated by the existing DV with coverage parity, and
   swapped in as the fast model.

**Metrics:**
- integration source size against the hand-written top or generator input;
- time to add a variant;
- errors caught at elaboration;
- name stability across regenerations;
- for the lifted leaf: coverage parity, plus speed against Verilator.

### 9.6 Updated lead structure

| Role | Who | Writes | Risk to them |
|---|---|---|---|
| Lead author (structure) | Integrator / chip-level design lead | Integration description | Low: no magic, leaves untouched |
| Lead operator (leaves) | Platform/modeling team, with DV | Lifts, validated by DV | Low: nothing they sign off changes |
| Champion | DV | Benches on generated transactors | — |
| Consumers | Firmware, formal, physical design | Nothing | — |
| Gatekeepers | CAD/methodology, management | — | Replacing an in-house generator; pilot risk |
| Later authors | Block designers | Process-level leaves behind the same interfaces | Addressed by the time they arrive |

---

## 10. Chip-level concerns: UPF, IP-XACT, DFT (2026-11-26)

**The goal.** fw-hdl covers chip-level concerns, not just leaf logic and
wiring:
- interop with UPF and IP-XACT;
- DFT, ideally;
- by extension SDC and CDC/RDC collateral, which fall out of the same domain
  model.

### 10.1 Why this strengthens the thesis

Chip-level intent today is a set of **side files**:
- UPF;
- SDC;
- IP-XACT;
- CDC waivers;
- DFT configuration and ICL;
- connectivity spreadsheets.

Different teams write and maintain them, keyed by RTL hierarchy paths, and
keep them consistent by hand. It is the same drift problem as models drifting
from RTL, one level up. Re-partitioning a block or adding a variant breaks the
paths in all of them.

Once fw-hdl owns the integration (§9), it is the one place that knows the
hierarchy, the names, the domains, the crossings and the memories. If
chip-level intent is held there, every side file becomes a **projection**:
regenerated, consistent by construction, and checkable against the others.
For example, a power domain boundary that a clock domain crossing straddles
needs both isolation and a synchronizer. It is the collective-win argument
applied to the PD, low-power and DFT teams.

**Principle (the same rule as for engines):**
- Intent is first-class in the **Zuspec IR**, as domain kinds, crossings,
  memories and test access.
- Each standard is an **importer and exporter, peers behind one interface**.
  No format becomes the core.
- The RTL stays plain SV with no intent embedded in it. The side files carry
  the intent, as the signoff tools expect.

### 10.2 What already points this way

- **`core-domains.md`:**
  - Domain kinds are open, and power and macro membership are planned later
    kinds.
  - The crossing analysis finds every inter-domain connection, which for
    power is the set of isolation sites.
  - UPF and floorplan constraints are named as later consumers (§6; plan
    §510: "a real power kind, UPF and SDC output").
- **`hw-sw-interface.md`:**
  - §7.5 sets out power and clock sequencing rules for each kind.
  - Decision 8: a `power` kind in `fw_domain`, "UPF becomes a projection
    (export) and an import, not the source".
  - Register import from IP-XACT, SystemRDL and hjson; IP-XACT exports often
    mis-mark W1C fields as RW.
- **fw-proto kits** correspond to IP-XACT bus and abstraction definitions.

### 10.3 Each format: what fw-hdl owns, and what stays with commercial tools

| Concern | fw-hdl owns (IR and checks) | Import | Export | Stays with commercial tools | Local verification | Effort |
|---|---|---|---|---|---|---|
| **IP-XACT** (IEEE 1685-2014/2022) | Component, bus interface and parameter model; kit ↔ busDefinition/abstractionDefinition map | Component XML → wrapped fw-hdl component (ports, bus interfaces → kits, parameters, memory maps → registers) | Component and design XML for the integrated top | Commercial integration and DFT tools consume it | Schema validation; round-trip through Kactus2 (open source) | Low–medium |
| **SDC** | Clocks from clock domains, generated clocks, constraints for crossings (clock groups, synchronizer max-delay) | Existing SDC for wrapped IP (constraint merge) | Chip-level SDC consistent with the hierarchy | Static timing signoff | OpenSTA | Low–medium |
| **CDC/RDC collateral** | Crossings are explicit typed objects, with waivers and reasons (core-domains §6) | Tool waiver files (vendor formats) | Constraints and waivers for the CDC tool; check whether Accellera's CDC collateral standard is far enough along to target **[status unverified]** | Structural CDC/RDC signoff | Our own static check; Verilator for function | Medium |
| **UPF** (IEEE 1801) | `power` domain kind: supply sets, power states, isolation, retention and level-shift strategies at crossing sites; sequencing rules (hw-sw §7.5) | IP-level constraint UPF from IP providers (successive refinement) | The integrator's configuration UPF; implementation UPF stays with physical design | Power-aware simulation (Questa PA, VCS NLP); static low-power checks (VC LP, Conformal LP); implementation | **None open source; no Questa here.** Our own power-state semantics in the fast model; external check needs a partner | Medium–high |
| **DFT** | DFT rules as domain-kind rules (clock-gate and async-reset test overrides, test-mode domain); memory inventory per instance and configuration; structural test access: IEEE 1149.1 TAP, IEEE 1687 IJTAG networks (SIBs, TDRs), IEEE 1500 wrappers | Tool-generated MBIST/EDT/OCC blocks, wrapped; existing ICL | ICL for the generated access network; PDL as method-level test procedures (iWrite/iRead are method calls); memory list and DFT configuration for the insertion tool | Scan insertion and stitching, compression, ATPG, MBIST controller generation, test pattern signoff | TAP/IJTAG transactor simulation under Verilator; no open ICL/PDL tooling of note | Medium–high; needs a DFT partner |

**The DFT boundary.** fw-hdl should not insert scan or run ATPG. Those
transforms act on netlists, and commercial tools own them. fw-hdl's part is
the *architecture and intent* at RTL level, which today is set up by hand
around the insertion tool:
- which memories exist, and how each is configured;
- how test mode reaches each clock gate and reset;
- what the access network looks like.

The structural generation (TAP, IJTAG, 1500 wrappers) is "no magic", in the
same sense as integration (§9.1).

**The fast model gains power semantics.** Neither Verilator nor any open tool
reads UPF. The class model can execute the power kind's semantics directly:
- an access to an off domain is an error, or hangs, as the hardware would;
- isolation clamps;
- retention save and restore;
- sequencing rules.

That gives power-aware simulation in the fast model and the open flow, and the
firmware stream gets power-management bring-up (hw-sw §7.5). It is a
differentiator *if* the semantics are cross-checked against a commercial
power-aware simulator at least once.

### 10.4 Order

The order favours what can be verified locally and what builds on work that
exists:
1. **IP-XACT import.** This lowers the cost of wrapping vendor IP and serves
   the integration entry directly (§9).
2. **Clock and reset → SDC and CDC collateral.** The domains and crossing
   analysis already exist; OpenSTA can check the result.
3. **IP-XACT export.** This lets fw-hdl coexist with incumbent integration
   flows rather than replace them, and answers the CAD objection in §9.4.
4. **Power kind → UPF export** (configuration UPF), with power semantics in
   the fast model. Constraint-UPF import comes after that.
5. **DFT rules and the memory inventory.** These are elaboration-time checks
   and a list; they are cheap and useful to DFT engineers at once.
6. **Structural test access (TAP, IJTAG, 1500) with ICL and PDL.** This
   needs a DFT partner to validate.

### 10.5 New stakeholders

These are not covered in §2. The pain points below are practitioner knowledge,
not sourced; research them before quoting.

| Stakeholder | Role | Likely pain points **[unverified]** | What fw-hdl gives |
|---|---|---|---|
| Low-power / power-intent engineers | Consumer; possible author of power intent | UPF hand-written against hierarchy paths, broken by re-partitioning; inconsistent with RTL; power bugs found late in power-aware simulation | UPF as a projection; isolation sites found by the crossing analysis; power-state semantics in the fast model |
| DFT engineers | Consumer; gatekeeper on testability | DFT added late, on the netlist; RTL changes ripple into DFT; the memory list and test-access network maintained by hand | DFT rule checks at elaboration; the memory inventory; generated access network, ICL and PDL |
| Physical design (again) | Consumer of SDC and UPF | Constraint files out of step with the RTL | Consistent SDC and UPF regenerated with the hierarchy |
| CAD/methodology (again) | Gatekeeper | IP-XACT from vendors is incomplete; flows glue many formats | Import and export through standard formats; fw-hdl sits *in* the flow |

### 10.6 Risks

- **Scope.** Each format is a deep field with entrenched tools (Tessent,
  DFTMAX and Modus; VC LP and Conformal LP; Magillem/Arteris). Position
  fw-hdl as the *source of intent* that feeds them, never as a replacement
  for an implementation or signoff tool.
- **We can't verify locally.** UPF and DFT outputs can't be checked with the
  tools here (no Questa; no open UPF or ICL tooling of note). These steps
  need a partner or an internal pilot with commercial tools
  (`automated-lifting.md` §9). Until then, claim structure, not signoff.
- **Standards' versions and vendor dialects.** IP-XACT 2009, 2014 and 2022,
  plus vendor extensions; UPF 2.x against 3.x/4.0 support across tools;
  CDC waiver formats with no standard. Pick the subset the target tools
  accept and test against them.
- **Hierarchy ownership is the premise.** The consistency argument holds
  only if fw-hdl owns the integration. For wrapped blocks with their own UPF,
  SDC and DFT, importing and merging is unavoidable, and it is where errors
  will concentrate.

### 10.7 Next

This is a goal, not yet a plan. When it is scheduled, it deserves its own plan
doc, with a "User benefit" section and a §0 Status, sequenced on §10.4. It
also deserves a short research pass on the §10.5 pain points (low-power, DFT,
SDC/UPF maintenance), like the one done for §2.
