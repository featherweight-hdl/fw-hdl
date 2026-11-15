# Choosing the wedge

Draft assessment, 2026-11-15. **Current leaning: §4b (an interface observability kit
as the vehicle, the passive half of VIP)**, which refines §4a (VIP as the wedge)
and §4 (traffic generators). This weighs the candidate entry points that came
out of the pitch review and research (`pitch.md`, `featherweight-ip-strategy.md`,
`research/`). It is a recommendation for discussion, not a decision.

**Second vehicle (2026-11-15): fast models through lifting.** This is set out
in `ip-library-focus.md` §0 and `automated-lifting.md` §1a.
- Lifting existing IP, proven equivalent, yields fast platform models. That
  is the lead payoff.
- The lowered and retimed lift is a design proof point and a research
  vehicle.
- Converting the design process is the real goal.

It complements the observability kit. Both need the same operation monitors
and protocol kits.

## 1. The candidates

| # | Path | One-line pitch |
|---|---|---|
| A | Class-based design | Write synthesizable hardware with SV classes; climb the abstraction ladder |
| B | Designer tests | Method-level tests on wrapped RTL: as easy as cocotb, scales better |
| C | PSS in SV | Author scenarios in SV, ship PSS to SoC teams |
| D | Python flavor | fw-hdl-dv in Python, on cocotb, with fast turnaround |
| E | Architects | Explore in Python, hand off as SV, refine behind stable interfaces |
| F | Testbench to testbed | Verification collateral that runs as classes in simulation and as RTL on FPGA or emulator |
| G | featherweight-ip flagship | Readable, verified IP built with fw-hdl, shipped as plain Verilog |

G is not a wedge on its own: the research says a flagship is necessary, but
IP spreads the IP, not the framework (VexRiscv). It is the *proof* for
whichever wedge is chosen.

## 2. Criteria

- **Opportunity:** a documented pain, a gap no one fills well, and timing.
- **Technology fit:** does it rest on what the experiments have shown to work
  (class elaboration, sync lowering to readable parameterized RTL, fw-proto
  transactors), or on things not yet built?
- **Audience fit:** do the users already have the skills, and how big a step
  is adoption for them?
- **Objections:** how many of the known killers (generated-RTL distrust, QoR,
  new language, process change, free incumbents) apply?
- **Provability:** can a small team show it convincingly, cheaply and soon?
- **Pull-through:** does winning here make the other paths easier?

## 3. Assessment

| Path | Opportunity | Technology fit | Audience fit | Objections | Provability | Pull-through |
|---|---|---|---|---|---|---|
| A. Class-based design | Medium: productivity is a perennial want, but no acute pain | Good for the RTL subset; higher rungs unbuilt | Poor: designers don't write OO SV; the ASIC signoff culture | **Many:** generated RTL, LEC, QoR, Chisel/HLS history | Slow: needs P2-style evidence across many blocks | High if it wins |
| B. Designer tests | Medium: designers spend 49% of time verifying, but no metric for method-level testing | Good: wrap + transactors exist | Medium: designers prefer light tools | **Free, good incumbents** (cocotb, VUnit); "scales better" is hard to show in a demo | Medium | Medium |
| C. PSS in SV | Low now: PSS adoption is slow | Hard: solver, action inference, round-trip with commercial tools | Good for verification engineers | Depends on a market that stalled | Slow and needs a commercial PSS tool | Medium (a multiplier later) |
| D. Python flavor | Medium: Python is growing in verification | Hard: the VPI/DPI bridge is unsolved | Good for cocotb users | cocotb is free and good; this is a feature, not a reason to switch | Medium | Low alone |
| E. Architects | Medium: correlation is a known, costly pain | Partly: needs Python/SV conformance | Unverified: organizational fit, Python not the incumbent | ESL's process-change failure; common-mode errors | Slow: needs a customer | Medium |
| **F. Testbench to testbed** | **High:** documented host-boundary pain; effort named as the barrier; Arm ATP calls for hardware generators and none exist; no general on-chip stimulus flow; 87% FPGA bug escapes | **Best:** it uses exactly what has been shown (classes lowered to readable RTL) plus `fw-proto-axi` | **Good:** verification engineers already write classes; kits can be *used* by people who don't | **Fewest:** nobody runs LEC on a testbed, 10% QoR is cheap; plain SV avoids Bluespec's language problem | **Fast and cheap:** a $250 board, measurable curves, a hand-written baseline | **High:** it exercises fw-hdl-dv, the Python host, fw-proto, VIP kits, and builds trust in the lowering for design later |

## 4a. Revised framing: verification IP as the wedge (2026-11-15)

Proposed in discussion: make **verification IP** the focus, extending to
traffic generators, rather than leading with traffic generators alone. Every
technique applies to VIP:
- fw-hdl to build transactors and related collateral more efficiently;
- a formal path (protocol checkers as formal assertion IP);
- method-level APIs for UVM, cocotb and fw-hdl-dv;
- extending to synthesizable traffic generation on FPGA and emulators.

**Assessment: this is better than F alone.** It keeps everything that made F
attractive and fixes its weaknesses.

| | F alone (traffic generators) | VIP, extending to traffic generation |
|---|---|---|
| Product category | New and unproven; must educate buyers | **Established:** teams already buy and budget for VIP |
| Day-one usefulness | Needs an at-speed use case | **Every project with a standard bus** uses VIP in simulation |
| Bluespec lesson ("complement UVM") | Must be argued | **Built in:** VIP plugs into UVM by definition |
| Traction pattern 1 (a flagship that ships product) | The demo is the flagship | **We become the flagship owner:** a product line built with fw-hdl |
| PSS lesson ("content, not methodology") | Partly | **Fully:** VIP is content |
| Formal | Not covered | **Covered:** protocol checkers are classic formal assertion IP, and formal apps are the fastest-growing formal category |
| The at-speed story | The whole pitch | **The premium extension** of the same kits |

**The economic argument is the core of it.** Today a protocol is typically
delivered as separate artifacts: simulation VIP, assertion IP for formal, and
accelerated VIP for emulation, often from different products and teams [U:
confirm in the VIP market research]. With one `fw-proto` spec per protocol and
fw-hdl underneath, all of them come from one source:

| Target | Derived artifact |
|---|---|
| UVM simulation | UVM agent around the class transactor |
| cocotb | Python API over the transactor |
| Formal | Protocol checker as properties on the method interface |
| FPGA and emulation | The transactor and traffic generator lowered to RTL |
| fw-hdl users | Direct method-level attachment, no UVM layer |

If fw-hdl makes each protocol several times cheaper to build across all
targets, a small team can cover protocols that would otherwise need a VIP
company. That claim is measurable per kit (lines of code, effort), which is
exactly the P2-style evidence the strategy already asks for.

**Gaps this can fill [U, to verify]:**
- *Open-source simulators.* Commercial VIP is usually encrypted and tied to
  commercial simulators, so Verilator users have little but cocotb Python
  models. Plain-SV VIP that runs on Verilator serves a growing, underserved
  group.
- *Portable acceleration.* Accelerated VIP is tied to one emulator vendor.
- *Open, readable VIP* that users can debug and extend.

**New obstacles this brings:**
- **An established, competitive market.** The big three EDA vendors bundle VIP
  with their simulators, and VIP specialists (SmartDV, Truechip; Avery, now
  Siemens) cover hundreds of protocols [U].
- **Breadth.** Buyers need *their* protocol. Coverage grows one protocol at a
  time, so focus on the AMBA family first: AXI4, AXI4-Lite, AXI4-Stream, APB,
  AHB, then ACE/CHI. `fw-proto-axi` is far along, and Arm's traffic-profile
  spec gives the traffic-generator extension a standard to implement.
- **Trust.** VIP must be right. It needs compliance evidence: checking against
  known-good IP (vendor AXI IP, PULP AXI), cross-checks with other VIP, and
  published protocol-rule coverage.
- **Business model.** Open-source VIP has to answer who pays: support,
  premium kits (accelerated and traffic-generation versions, advanced
  protocols), or services. Decide this early, because it decides whether the
  vendor catalogs are channels or competitors.

**What changes in the plan:**
- *featherweight-vip moves from stage-0 reach channel to the lead product.*
  fw-hdl is presented as the engine behind it, and as the way users extend or
  write their own kits.
- *Sequencing:* `fwvip-axi` (UVM, cocotb, formal) first; the AXI traffic
  generator and the FPGA demo as its at-speed extension; then AXI-Stream,
  APB and AHB.
- *Interviews* add VIP buyers: what they pay for, how they get formal and
  accelerated versions, and whether open-source simulator support matters.
- *Research needed:* the VIP market (players, pricing models, what is bundled,
  open-source options such as PULP's AXI test classes, Xilinx's AXI VIP, and
  cocotbext-axi), and Verilator support for encrypted VIP.

### What the market research changed (`research/vip-market.md`)

**Confirmed:**
- **Simulation, formal and emulation versions are separate products** at the
  big three, and no vendor offers one source across all three as a guarantee
  the buyer can see. SmartDV comes closest, reportedly generating its
  versions from internal tooling.
- **Verilator cannot run encrypted VIP** (stated in the Verilator docs), and
  UVM on Verilator gained institutional backing in 2026 (CHIPS Alliance SV
  Tools, Google, Antmicro). Unencrypted SV VIP is the only kind that can
  follow that shift. **This is the strongest timing argument found in any of
  the research.**
- **Open options each serve one target:** PULP (simulation), ZipCPU
  (formal), cocotbext-axi (Python). Nothing spans them. There is no credible
  open ACE or CHI VIP.
- **AMBA is royalty-free.**

**Sharpened:**
- **Basic AMBA is a commodity,** effectively bundled at big-three accounts,
  and a small vendor's paid formal AXI VIP failed (ZipCPU's properties went
  from commercial to Apache-2.0). So basic AMBA VIP is an *adoption* vehicle,
  not a revenue line. Keep it free.
- **Revenue, if any, comes from what buyers already pay for separately:**
  compliance and coverage suites, support, a qualified release, premium
  protocols (AXI5 extensions, ACE, CHI), the at-speed traffic-generation
  kits, and services. Sponsorship (CHIPS Alliance and its members) is a
  realistic early funder.
- **The independent VIP vendors are acquired** rather than standing alone.
  That is an exit pattern as much as a risk.
- **featherweight-vip has no traction yet** (at most 3 stars, no AXI
  repository). Credibility has to be built from zero.

**Positioning that follows:**

> The open AMBA VIP for every flow: unencrypted SystemVerilog that runs on
> Verilator and every commercial simulator, with UVM, cocotb, formal and
> synthesizable targets from one protocol spec.

- **First audience:** teams moving to open-source simulators (Verilator, and
  DSim), plus FPGA teams. They are underserved, because encrypted VIP
  excludes them. Ride the CHIPS Alliance UVM-on-Verilator work; that
  community is also a natural sponsor.
- **Second audience:** commercial-simulator teams who want debuggable source
  and a single source across simulation, formal and FPGA or emulation.
- **High-value later:** an open ACE-Lite / CHI subset, which is empty
  territory today. `fwvip-chi` already exists as a start.

**Revised sequencing:**
1. `fwvip-axi` (AXI4, AXI4-Lite) on Verilator and one commercial simulator,
   with UVM, cocotb and formal from one spec, plus independent cross-checks
   against PULP AXI and ZipCPU's properties.
2. AXI4-Stream and APB, then the AXI traffic generator and the FPGA demo as
   the at-speed extension.
3. Approach CHIPS Alliance and the SV Tools members about sponsorship or
   adoption once step 1 runs.
4. AHB, AXI5 features, then a CHI subset.

## 4b. VIP as a vehicle, not the destination (2026-11-15)

**Restated objective.** VIP is a vehicle. The goal is something used in
production that opens a path for the complementary technologies:
- a different way to author SVA;
- PSS;
- a new way to do design;
- immediate debug visibility on design interfaces.

So the question is not "which product sells" but "which product gets into
production flows and lends its credibility to those four".

### What a good vehicle needs

1. **Into production with little friction:** additive, displacing nothing,
   needing no approval.
2. **Sticky and visible:** used every day, by the people we eventually want
   to reach.
3. **Showcases the target technologies:** the user experiences them through
   the vehicle, rather than being told about them.
4. **Earns credibility that transfers:** it is judged on the same qualities
   the new technology will be judged on.
5. **Avoids fights we lose:** not head-on with free or bundled incumbents.

### The candidates

| Vehicle | Friction | Stickiness and reach | SVA | PSS | Design | Debug | Competition |
|---|---|---|---|---|---|---|---|
| **Full VIP** (active drivers and passive monitors) | Medium: must be chosen *instead of* existing VIP | Verification engineers, daily | Yes (its checkers) | Yes (its sequences) | Weak (internals unseen) | Yes | **Commodity / bundled** (vip-market.md) |
| **Passive protocol monitors and checkers** (the "observe" half of VIP) | **Lowest:** bind onto existing RTL, alongside any VIP, no testbench change | **Designers and verification engineers, every debug session** | **Yes, directly** | Partly (observed transactions and scenario coverage) | Partly (method-level view of the design) | **Yes, directly** | **Little:** complements commercial VIP rather than replacing it |
| Formal protocol apps | Low: push-button | Formal users; growing | Yes | No | No | Partly (counterexamples) | Jasper/VC Formal assertion IP add-ons; ZipCPU free |
| Design IP (featherweight-ip) | **High:** design IP must pass signoff | Designers | No | No | **Yes, directly** | No | Vendor and open IP |
| Testbed traffic generators | Medium: needs a board or emulator and a use case | Performance and emulation teams | Partly | Yes (scenarios to descriptors) | **Yes:** lowering proven at speed | Partly | Vendor accelerated VIP; shallow vendor generators |
| Debug viewer tool on its own | Low | Everyone who debugs | No | No | No | Yes | Verdi, Visualizer, free waveform viewers |

### Assessment

**Full VIP is a reasonable vehicle, but its active half is the wrong place
to start.** Drivers and sequences compete with bundled commercial VIP and
free open options, and a team changes VIP rarely. The passive half
(monitors and checkers) has none of that problem and carries more of the
target technologies.

**Recommended vehicle: an interface observability kit.** Bind it onto any
AXI, AXI-Stream or APB interface in an existing design, with no testbench
change. It gives:
- **immediate debug visibility:** transaction-level views of every bound
  interface (logs, waveform annotation, latency and throughput), the "path to
  immediate debug visibility" directly;
- **protocol checking:** properties written the new way, running in
  simulation and in formal from one source, which showcases the SVA authoring
  approach on real designs;
- **observed scenarios:** the transaction stream gives scenario-level
  coverage, and can be captured and replayed as fw-hdl-dv scenarios, the
  first step toward PSS content;
- **on-hardware observation:** the same monitors lowered to RTL on an FPGA or
  emulator, as deep transaction-level trace where ILA only sees a few signals.
  This is the first proof of the lowering, in a role where nobody signs off
  the RTL.
- **a method-level view of the design:** designers see their interfaces as
  transactions and methods every day, which is the mental model the new
  design approach builds on.

**Why it is the best vehicle on the criteria:**
- *Friction:* it is additive and passive. It works next to Synopsys or
  Cadence VIP, next to cocotb, on Verilator (unencrypted), and on legacy RTL.
  Nobody has to give anything up.
- *Stickiness and reach:* debug is the largest share of verification time,
  and designers spend about half their time verifying. A debug aid is used
  daily, by designers as well as verification engineers. Designers are the
  audience the design technology eventually needs.
- *Credibility that transfers:* every protocol violation it catches on a
  real design earns trust in the checker-authoring approach. Every on-board
  trace earns trust in the lowering.
- *Competition:* it complements commercial VIP instead of fighting a
  commodity, bundled market.

**Where credibility does *not* transfer, honestly:**
- *To design.* No verification vehicle proves a design method; credibility
  in design comes from fw-hdl in a production design path. The observability
  kit prepares the ground (the method-level view, and the lowering proven on
  hardware), but the design claim still needs featherweight-ip and P2-style
  evidence. Treat design as the last step of the path, not something the
  vehicle delivers.
- *To PSS.* Observed scenarios are content, but PSS adoption also depends on
  SoC teams and their tools. The vehicle provides bottom-up content; it does
  not create demand.

**Precedent to heed.** Accellera's Open Verification Library (OVL), an open
checker library, saw moderate use and faded as SVA matured [U]. A checker
library on its own is not enough. The debug views and the on-hardware
observation are what make this more than OVL.

### The resulting path

| Step | Vehicle | Technology introduced | Credibility earned |
|---|---|---|---|
| 1 | Observability kit (bind-on monitors and checkers; AXI4, AXI4-Lite, AXI-Stream, APB) | Debug visibility; the new SVA authoring | "It catches real bugs and makes debug faster, on any simulator" |
| 2 | Same monitors on FPGA and emulator | The lowering | "The generated RTL works at speed" |
| 3 | Active VIP and traffic generation (drivers, sequences, testbeds) | fw-hdl-dv scenarios; testbed collateral | "It drives real traffic, from one source" |
| 4 | Scenarios captured and projected to PSS | PSS | "Block content reaches the SoC team" |
| 5 | featherweight-ip and fw-hdl design | The new design approach | "The method we've been using daily also builds the design" |

Each step uses the trust earned by the one before, and none depends on
winning a commodity fight.

### What to check

- **Interviews:** how long it takes to debug an interface problem today,
  whether teams bind protocol checkers onto RTL now (and which), and whether
  a transaction view of every interface, on any simulator, would be adopted
  without a procurement decision.
- **Research:** OVL's adoption history, and existing transaction-level debug
  tools (Verdi transaction views, Visualizer, vendor protocol analyzers) and
  how they are tied to VIP or simulators.

## 4. Recommendation: F, aimed at verification engineers, proven on FPGA

**The wedge:** open, portable, synthesizable traffic generation and checking
for AXI4 and AXI4-Stream. The same components run as classes in simulation
and as RTL on an FPGA or emulator, driven by scenarios on the host.

Why F wins on balance:
- **It is the only path where the known killers mostly don't apply.**
  Distrust of generated RTL, QoR and signoff culture defeat A; free
  incumbents blunt B and D; a stalled market limits C; process change and
  unverified organizational fit limit E. For test collateral, the RTL is
  never signed off, 10% overhead is cheap, and the authors already know
  classes.
- **It plays to what is proven.** The experiments show classes lowering to
  readable, parameterized RTL. F needs that and the AXI transactor, not the
  higher rungs or a PSS solver.
- **It has a gap with a name on it.** Vendor generators are shallow; ATP has
  no hardware; emulator vendors' compilers lock you to one box; processor-
  driven tools need transactors for I/O.
- **It is cheap to prove and easy to see.** The host-boundary curve, line
  rate with no bubbles, the same seed giving the same trace in simulation and
  on the board, and the comparison with a hand-written baseline are all
  concrete.
- **It pulls the rest along without depending on them.**
  - fw-hdl-dv (scenarios on the host; checkers in hardware);
  - the Python flavor (only the host side, on the board's Arm cores);
  - fw-proto and featherweight-vip (the kits *are* VIP);
  - design (a team that trusts the lowering for its testbed has seen it
    work).

### Which audience inside F

Three audiences share the same collateral. They differ in value and
reachability:

| Audience | Skills fit | Value | Reachability | Role |
|---|---|---|---|---|
| Emulation and ASIC-prototyping verification engineers | Best: SV classes, UVM, transactors | Highest: emulation time is expensive | Slow: large companies, vendor relationships; we have no emulator to demo on | **Primary target for the message** |
| FPGA design teams | Weaker: MATLAB, C on the core | Medium | Easy: cheap boards, open source, PYNQ, cocotb | **Users of ready-made kits; the demo and community channel** |
| IP vendors validating at speed | Good | Medium–high | Medium | Early adopters to look for |

So: **build and demonstrate on FPGA, aim the message at verification
engineers who need at-speed traffic.** The FPGA board is the proof vehicle
and the open-source on-ramp. Emulation and prototyping teams are the audience
with the skills and the budget. FPGA teams mostly configure kits rather than
write collateral, which is fine: they still pull the kits into their flows.

### How it must differ from Bluespec

- complement UVM; position as the synthesizable layer a UVM or fw-hdl-dv
  bench drives;
- keep the solver, coverage and scoreboards on the host, and only per-cycle
  work in hardware;
- show bit-exact reproducibility across simulation and hardware;
- implement a standard (ATP profiles) rather than a private format;
- hold the wedge for years.

## 5. What to defer

- **A (class-based design as the headline).** Keep it as the roadmap and the
  long-term destination, not the opening message.
- **C (PSS projection).** Keep the semantics aligned so the option stays open;
  don't build the projection or round-trip tests until a customer asks.
- **D (Python flavor).** Build only what the host side of the testbed needs.
  The full cocotb bridge waits.
- **E (architects).** Keep the story; no investment.
- **B (designer tests)** comes nearly free from F: the class model in
  simulation is a method-level test target. Show it, but don't lead with it.
- **featherweight-ip:** narrow to what F needs (AXI and AXI-Stream transport,
  the generator, checkers, the performance monitor) plus the existing
  Wishbone vertical as the design proof.

## 6. Checkpoints and kill criteria

| When | Checkpoint | If it fails |
|---|---|---|
| Before building much | 8–10 interviews with emulation and prototyping verification engineers (questions in `research/emulation-traffic-generators.md` and `research/bluespec-testbenches.md`) | If they say vendor VIP and virtual hosts cover their needs, shift the primary audience to FPGA kits; if neither audience has the pain, fall back to B |
| Demo phases 1–2 | Line rate with no bubbles; within about 10% of the hand-written baseline; same seed, same trace in simulation and on the board | If the lowering can't reach line rate or the overhead is far over 10%, the technology isn't ready for this wedge either |
| Demo phases 3–4 | Multi-stream QoS results; ATP profiles running in hardware; scenarios from the host | — |
| After publishing | At least one outside team using a kit (an IP vendor, an open-source project, a course) | Without an outside user, revisit the audience before adding domains |

## 7. Uncertainties in this assessment

- The size of the host-boundary pain varies by project (PMC found the link
  often isn't the bottleneck), and NVMe-under-emulation data is not public.
  The user's own experience of last week is a data point; interviews are the
  rest.
- The emulator vendors' behavioral compilers were not verified in detail.
  If they are better than assumed, the emulation message narrows to
  portability and openness.
- FPGA teams' willingness to adopt SV-class collateral is unknown, which is
  why they are cast as kit users.
