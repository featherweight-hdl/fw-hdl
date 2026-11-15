# featherweight-ip as the proof point

Draft, 2026-11-15. This note follows *Traction of prior approaches* in
`pitch.md`. That research found that no hardware-design framework spread on
technical merit alone. Each one that gained traction had a flagship: an owner
shipping product with it, or a body of IP people wanted.

This note sets out what featherweight-ip must deliver to be fw-hdl's flagship.
It also covers how the planned fw-hdl-dv verification library and
featherweight-vip complete the verification story, which the research says is
where adoption starts.

It is a statement of vision and requirements, not an audit of the current
repositories. "Today" observations come from a quick look at the GitHub
organizations on 2026-11-15.

## 1. What the evidence asks for

The relevant findings (sources are in `research/`):

| Finding | What it asks of the IP family |
|---|---|
| A flagship that ships product (Chisel and SiFive, Hardcaml and Jane Street) | At least one complete, running design that people recognize |
| IP used *as plain Verilog* spreads the IP, not the framework (VexRiscv and SpinalHDL) | Verilog for reach, but a path that leads users into the framework |
| A library of components and channels is what made HLS work (MatchLib, Google's Taffel) | Protocol and integration IP, not only leaf blocks |
| PSS stalled with "no bottom-up content" | Ship content (kits, models, checkers), not only a methodology |
| Generated RTL lost ASIC teams (15,000+ manual equivalence-check (LEC) name matches in the Chisel SweRV study) | Readable output, *measured*, e.g. LEC against the reference core |
| Verification wins convert people; designers already spend 49% of their time verifying and prefer lightweight tools | Verification value on day one, with no change to the design |
| Tools that run on existing simulators were adopted (UVM, cocotb, SVA, formal apps) | Everything runs on the user's simulator, flow and testbench |
| Single-maintainer projects stall (MyHDL, OSSS) | Focus; don't spread across 60 repos at once |

## 2. The library family and adoption funnel

There are four libraries and three GitHub organizations. Each one serves a
different stage of adoption:

| Stage | User changes | Library | What they get |
|---|---|---|---|
| 0. Verify existing RTL | Nothing in the design | **featherweight-vip** (`fwvip-*`) | Protocol kits for UVM, cocotb and formal: transactors, checkers, coverage. "A kit, not a methodology." |
| 1. Wrap existing RTL | Adds fw-hdl wrappers | **fw-proto-\*** kits + **fw-hdl-dv** | Method-level tests through transactors, properties on method interfaces, better debug |
| 2. Write new blocks | RTL subset (`comb()`/`step()`) | **fw-hdl** + **featherweight-ip** as examples and building blocks | Same tests, now driving fw-hdl blocks, mixed with legacy RTL |
| 3. Climb the ladder | SPL (sequential process level), MLS (mid-level synthesis)/HLS for selected blocks | fw-hdl engines | The right level for each block, in one interoperating design |

featherweight-vip is the reach channel. It meets verification engineers and
designers on their own platform, with no fw-hdl adoption. fw-proto kits and
fw-hdl-dv convert those users. featherweight-ip is the proof that the
destination is worth reaching.

**The seam is the protocol spec.** `fwvip-uart` is already built on
`fw-proto-uart`, so the layering exists in at least one place. Make it a rule:
one hand-written protocol spec per protocol (as in `fw-proto-axi`), from which
these are all derived:
- the synthesizable transactor;
- the class API;
- the protocol rules;
- the checker;
- the VIP agents.

**Decided (2026-11-15):** `fw-proto-<X>` owns the protocol spec and the one
transactor, and `fwvip-<X>` repackages them for UVM, cocotb and formal. The
featherweight-vip profile's description of a per-kit "core transactor" should
be updated to say this.

**Principle: build with fw-hdl, ship plain SystemVerilog.** It applies to both
families:
- featherweight-ip *and* featherweight-vip are developed with fw-hdl and
  fw-hdl-dv, inside the ivpm/dfm/direnv flow;
- each also has an RTL-only or SV-only release package for end users who use
  neither;
- fw-hdl users get more from the same libraries: class models, method-level
  APIs, properties on method interfaces, and access to every abstraction
  level.

The VexRiscv lesson (plain Verilog spreads the IP but not the framework) is
answered by the second audience: the framework's benefits stay visible to
anyone who looks past the release package.

## 3. What featherweight-ip must deliver

### P1. One flagship design, end to end

The flagship should be a complete SoC people recognize, running on an FPGA
board and in simulation, built from fw-hdl IP and wrapped legacy IP.
- **Near-term candidate:** a Wishbone SoC, since the pieces already exist:
  - `fw-picorv32` as the core;
  - `fw-proto-wb` for the bus;
  - `fw-uart16550`, `fw-i2c` and `fw-wb-dma` as peripherals;
  - the memory primitives.
- **Showcase candidate:** fw collateral around **OpenTitan and Ibex**.
  OpenTitan is a well-known open SoC with a large UVM verification effort.
  Featherweight kits, models and checkers working inside *its* flow borrow an
  established owner's credibility. That is the closest substitute for "a
  company shipping product with it".

**Proposed focus for from-scratch IP (2026-11-15).** See
`ip-library-focus.md`. It proposes a software-ready RISC-V platform kit:
interrupt controllers, then virtio, then the IOMMU. One configuration
produces the RTL, QEMU/Renode device models, the device tree and the tests.

### P2. Published side-by-side evidence for every core rewrite

The core-rewrite series (16550 UART, I2C, picorv32, wb-dma), each verified
against a well-known reference core, is the most valuable asset. For each
rewrite, publish a results table, and include the cases where fw-hdl is worse:

| Measure | Why |
|---|---|
| Source lines: fw-hdl vs reference RTL; test lines | The productivity claim |
| Area and Fmax vs the reference, on a named FPGA and with yosys | The quality-of-results answer that every HLS and generator study is judged on |
| **LEC user matches** needed between the fw-hdl output and itself after a change, or against the reference where it is logically equivalent | Directly answers the Chisel/SweRV "15,000+ matches" result |
| Reference-core bugs found (the i2c fork already says "with bug fixes") | Verification value, the thing that converts people |
| Time to first test; number of levels the same test ran on | The "order of magnitude better designer tests" claim |

Collect the tables on one page. This is the demo the pitch lacks (weak point
7).

### P3. An RTL-only release package

Every IP has a **special release package containing only RTL**: readable
Verilog with a parameter table, which an end user can drop into their own flow
with no other tooling. Release notes name the reference core it replaces. This
gives the VexRiscv-style reach, and every download is a potential stage-0
user.

This package is a distribution format only. Development and verification stay
in the ivpm/dfm/direnv flow, which is a core part of the methodology: it is
what makes the whole development and verification flow easy to automate.
Projects that adopt fw-hdl get that flow too. So the RTL package is what makes
the IP easy to *consume*, and the flow is what makes it easy to *build*.

### P4. Mixed abstraction in one design

At least one block in the flagship should exist on two or more rungs: RTL
subset and SPL, plus an MLS/HLS engine version where it fits. The rungs should
be swappable by configuration, run the same tests, and appear in a published
comparison. This shows the interoperability claim and the "right level per
block" framing, rather than only stating them. The sequential, FSM-heavy
peripherals (UART, I2C) are natural SPL candidates. A datapath block (AES)
suits MLS/HLS.

### P5. Interop with legacy RTL, in a real flow

The flagship mixes fw-hdl blocks with wrapped legacy RTL. The oc-* reference
cores are ready-made legacy RTL. The flagship runs:
- on at least one commercial simulator and on Verilator;
- inside a UVM environment built from featherweight-vip agents.

That demonstrates "no language boundary", the main difference from PyMTL3 and
cocotb.

### P6. Simulator coverage

State and test which simulators run the fw-hdl class runtime: Questa,
Xcelium, VCS, Verilator, xsim. Class support differs between simulators, and
this is the most likely objection from an SV shop.

### P7. Formal on real IP

At least one IP is proven with:
- the protocol checkers in formal;
- properties written on its method interface (the fw-hdl-dv mechanism).

This gives "better formal" a concrete instance.

### P8. Presentation and curation

- **One catalog page** listing every IP, with its status, reference core,
  results table and supported simulators.
- **Archive or relabel the 2019–2024 generation** (`fwuart`, `fwip-*`,
  `fwprotocol-defs`, and others) so a visitor can see what is current.
- **Fill the empty READMEs** (`fw-ibex`, `fw-opentitan`, `fw-proto-core`).
- **Plan "Wrap" demos for the older RTL IP.** `fwnoc`, the Wishbone
  interconnect and the SRAM controllers are free material for "Wrap"-rung
  examples, wrapped behind the protocol kits.

## 4. What fw-hdl-dv must deliver (planned)

fw-hdl-dv is the verification library for people already using fw-hdl. The
current design stub lists:
- PSS-style constrained activity graphs;
- method-driven formal analysis;
- declaratively defined checkers.

The evidence adds requirements and warnings:

1. **Method-level tests are the core product.** Tests talk to a component's
   method interface. They run unchanged on every level (model, wrapped RTL,
   generated RTL, gates) and on every simulator. Designers are the likely
   first adopters.
   - **Bar to meet:** a first test is as easy to write as in cocotb, and
     takes less work than in VUnit: one file, a few lines, a stock runner.
   - **Where it must beat both:** scaling. As a design grows, cocotb and
     VUnit tests stay at signal level, and each new block or refinement needs
     new drivers. fw-hdl-dv tests remain at method level and are reused
     across:
     - blocks, through protocol kits;
     - abstraction levels, through refinement;
     - simulation and formal.

     The demo should show both: one block's first test next to its cocotb
     equivalent, then the same tests reused as the design grows.
2. **Checkers are written once and used in simulation and in formal.** Formal
   *apps* are the fastest-growing formal category because they are
   push-button. Aim for "a property on a method interface proves with one
   command", not "learn formal".
3. **Activity graphs: PSS 3.1 semantics in SV syntax (decided 2026-11-15).**
   - **The goal:** align with PSS 3.1 semantics as far as is practical,
     ideally 100%. Only the syntax differs, where SV has no equivalent
     construct. For example, SV has no `schedule` statement, so actions are
     loaded into a `schedule` object, which is then executed.
   - **The hope:** project fw-hdl-dv descriptions to PSS source, so the same
     scenarios can be reused by PSS tools and flows.
   - **How this answers the PSS adoption evidence.** PSS stalled because it
     was a new language with no bottom-up content and weak tooling. fw-hdl-dv
     changes the order:
     - scenarios are written in SV and run on the user's own simulator, with
       no new tool;
     - they are built from content that already exists (fw-proto kits, VIP
       sequences, method-level APIs);
     - they can be projected to PSS once a project wants portability (SoC,
       post-silicon).

     So fw-hdl-dv becomes an on-ramp *to* PSS and a source of the bottom-up
     content PSS lacks, rather than a competitor. It is the same pattern as
     fw-hdl itself: one description, several implementations, with PSS as one
     more target.
   - **What makes it work:**
     - A written mapping (spec) from each fw-hdl-dv construct to its PSS 3.1
       equivalent, keeping the PSS semantic model: actions, activities,
       flow and resource objects, pools and binding, constraints.
     - Statically analyzable structure, as in fw-hdl. The projection needs
       the action and activity structure elaborated, not hidden in
       procedural code.
     - Round-trip tests: project to PSS and check, with a PSS tool, that the
       projected scenario behaves the same.
   - **Hard parts to plan for:**
     - *Action inference.* A PSS tool completes a partial scenario by
       inferring the actions needed to satisfy flow-object and resource
       bindings. Doing this in an SV runtime needs a solver-backed scheduler,
       beyond what SV `randomize()` offers.
     - *`exec` blocks and target-code templates.* These have no direct SV
       equivalent; decide how exec bodies map (e.g. to method calls on
       fw-hdl ports).
     - *What "practical" excludes.* Keep a published list of PSS features that
       are not supported, or are supported with different syntax, so that
       "100% semantics" stays a measurable claim.

   **Messaging by audience:**
   - *Designers:* "scenarios over your components." For them, PSS alignment
     is a reuse guarantee, not a prerequisite.
   - *Verification engineers:* **"Author in SystemVerilog, ship PSS to SoC
     teams."** Block-level scenarios become the bottom-up content SoC teams
     need. This is the vertical reuse PSS promised, without asking block
     teams to adopt a new language.
4. **Coexist with UVM.** fw-hdl-dv sequences and scenarios should be callable
   from UVM, and featherweight-vip UVM agents should attach to fw-hdl ports.
   UVM is used on about 80% of ASIC projects, so fw-hdl-dv has to plug into
   it, not replace it.
5. **Coverage on method interfaces.** Functional coverage defined at the
   transaction or method level, shared across levels like the tests are.
6. **A Python flavor of fw-hdl-dv (decided 2026-11-15).** The same constructs
   (method-level tests, checkers, coverage, activity graphs with PSS 3.1
   semantics) are also available in Python. Both flavors are held to the same
   conformance suite, so a Python scenario and an SV scenario mean the same
   thing and both project to PSS.
   - **Why:**
     - *Turnaround.* Editing a test does not rebuild the design. The gain is
       largest on Verilator, where any SV change means a C++ rebuild. When
       the design under test is still an fw-hdl model, a Python test can run
       against the Python model with no simulator at all.
     - *Audience.* Python is where designers are heading: 27% of ASIC projects
       use it in verification, and cocotb's ASIC share rose from 26% to 42%.
       It is also the architect's language in the architect path (pitch, *Who
       this is for*, item 3), so the architect's tests carry on to the RTL.
     - *PSS without a new language.* Scenarios with PSS semantics can be
       written in Python as well as in SV. The verification pitch becomes
       "author in SystemVerilog or Python, ship PSS to SoC teams."
   - **Relationship to cocotb and featherweight-vip:**
     - The `fwvip-*` cocotb packages stay what they are: transactors for
       existing cocotb users, with no methodology attached.
     - The Python flavor of fw-hdl-dv is the methodology layer on top. It
       should run on cocotb's runner and simulator interface rather than
       replace it, so a cocotb user can add it to an existing testbench. Tools
       that run on what teams already use are the ones that got adopted.
     - It drives the fw-proto transactor. There is no second, Python-side
       transactor (see §2).
   - **Design points:**
     - *Cross the language boundary at the method level.* cocotb's main speed
       cost is per-signal access from Python on every cycle. Python calls
       transactor methods instead (one call per transaction), and the SV side
       handles the pin-level work. That keeps Python out of the per-cycle
       loop. It is also the concrete form of "scales better than cocotb".
     - *The VPI/DPI mismatch (unresolved; needs a spike).* cocotb runs from
       VPI callbacks in the signal domain, while transactors live in the class
       domain and are reached through DPI.
       - The constraint: by the LRM, an exported SV task (one that consumes
         time) can only be called from inside an imported context task. A VPI
         callback is not that context. Calling an exported *function* from a
         VPI callback after `svSetScope` works on some simulators, but it is
         outside the standard.
       - So a cocotb coroutine cannot simply call a blocking transactor
         method. Candidate designs:
         1. *Doorbell plus DPI payload (hybrid).* An SV server thread per
            transactor sits in an imported context task. Python queues a
            request and rings a doorbell signal through VPI (a cocotb write).
            The SV thread wakes, fetches the request through DPI, calls the
            class method (which may consume time) and posts the result back
            through DPI. A completion signal or callback resumes the cocotb
            coroutine. Everything stays within the standard. The costs are
            one delta-cycle handoff each way and care over cocotb's write
            regions (writes are applied in ReadWrite, never in ReadOnly).
         2. *Signal-only mailbox.* The same idea with the payload also in
            VPI-visible variables. No DPI is needed, so it is the most
            portable. But payloads are limited to what can be flattened into
            signals, and Verilator needs them marked public.
         3. *SV as time master (no cocotb).* SV drives time and calls into
            Python through DPI imports, and Python calls exported tasks from
            inside that context. This is clean and standard, but it gives up
            cocotb's runner and its user base.
         4. *Zero-time calls only, through exported functions from VPI.*
            Simplest, but not portable, and blocking methods still need one
            of the patterns above.
       - Whichever design wins, test code should not see it. Write tests
         against one async method API, with interchangeable backends: the
         pure-Python model (no simulator), cocotb-hosted (1 or 2) and
         SV-hosted (3).
       - The spike should cover Verilator plus two commercial simulators. It
         should measure: whether option 4 works; the correctness of the
         doorbell handoff under reset and multiple clocks; and the cost per
         transaction against plain cocotb signal driving.
     - *Static analyzability.* Projection to PSS and to formal needs the
       action, activity and checker structure elaborated, as in the SV flavor.
       Python is dynamic, so define a projectable subset (classes and
       decorators elaborated into the shared semantic model, as Zuspec does).
       Arbitrary Python can surround a scenario but is not projected. Publish
       where that boundary sits.
     - *What "equivalent" means for random behaviour.* The conformance suite
       should require the same set of legal schedules and solutions, not the
       same random choices. Seed-for-seed reproducibility across flavors helps
       debugging (re-run a failure found in Python on the SV flavor), but it
       ties both flavors to one solver and one random-number sequence. Treat
       it as an optional later tier.
     - *One solver.* Action inference needs a solver-backed scheduler in both
       flavors (see item 3). Share one rather than building two.
   - **Risks:**
     - *Speed on long regressions.* Simulation speed is one of the gaps
       Batten names for PyMTL3. The method-level boundary limits the cost, but
       high-volume regressions may still belong in the SV flavor or on a
       compiled model.
     - *Two flavors to maintain* on a small team. The conformance suite is
       what keeps them from drifting. Build it before the second flavor, not
       after.

## 5. What featherweight-vip must deliver

Its positioning already matches the evidence: "a kit you import, not a
methodology you adopt", one transactor for cocotb, UVM and formal, checkers
and coverage included. Keep that message. Priorities:

1. **Finish the cocotb path.** cocotb and Python are where designers are going:
   27% of ASIC projects use Python in verification, and the trend is rising.
   That makes cocotb the stage-0 channel to the most likely first adopters.
2. **An AXI kit (`fwvip-axi`).** It does not exist yet, though `fw-proto-axi`
   is far along. Then add AXI-Lite, APB and AHB. AXI is what industry users
   need. Wishbone, UART and I2C prove the pattern but will not draw
   commercial interest.
3. **One source per protocol**, derived from the fw-proto spec (see §2,
   decided).
4. **Build VIP with fw-hdl and fw-hdl-dv (dogfooding).**
   - **The VIP is written with fw-hdl and fw-hdl-dv:**
     - transactors are fw-hdl components;
     - checkers are fw-hdl-dv declarative checkers;
     - sequences and coverage come from method-level APIs.
   - **End users still receive plain SystemVerilog and UVM.** This follows the
     principle in §2.
   - **What this buys us:**
     - VIP gets cheaper to write, so there are more kits per maintainer-hour.
       That directly counters the single-maintainer risk.
     - Every kit doubles as a fw-hdl-dv case study, measured like P2: lines
       of code and effort per kit compared with a hand-written UVM VIP.
     - fw-hdl-dv's requirements come from real VIP rather than speculation.
   - **For fw-hdl users,** the same kit attaches directly to fw-hdl ports at
     the method level, with no UVM layer in between.
5. **A visible bridge to fw-hdl.** Each kit's docs end with "next step: wrap
   your RTL and test at the method level" and link to the fw-proto kit. This is
   the step from stage 0 to stage 1 of the funnel.

## 6. Focus and sequencing

The one-maintainer risk is real: three organizations and about 60 repos. A
proposed order:

1. **Prove the funnel on one vertical.** Use Wishbone + UART + I2C +
   picorv32, which already exist end to end. Deliver P2 (results tables), P3
   (Verilog drop-ins), P5 (mixed legacy plus fw-hdl SoC) and P8 for that
   vertical only.
2. **Reach industry users:**
   - `fwvip-axi` with the cocotb path (featherweight-vip priorities 1 and 2),
     built with fw-hdl and fw-hdl-dv as the first full dogfooding case
     (priority 4);
   - the fw-hdl-dv minimum, which is method-level tests plus checkers shared
     between simulation and formal (fw-hdl-dv items 1 and 2);
   - the conformance suite, then the Python flavor of that minimum on top of
     the cocotb path (fw-hdl-dv item 6). Both reach the same first adopters.
3. **Show the ladder:** P4 on one sequential peripheral and one datapath
   block.
4. **Showcase:** OpenTitan and Ibex collateral (P1, showcase candidate) and
   P7 formal.
5. **Then breadth:** CHI, more peripherals, activity graphs in fw-hdl-dv.

## 7. Open decisions

- Should the flagship be a self-built Wishbone SoC, OpenTitan collateral, or
  both in sequence?
- Is there a potential "owner" (a company, a university course, an open
  hardware project) who would build and ship something with the library? The
  research suggests this matters more than any feature.
- Which PSS tool to use for the projection round-trip tests, and which
  features are first in the "not supported" list (action inference is the
  likely candidate).
- Python flavor of fw-hdl-dv: is cross-flavor seed reproducibility a
  requirement or a later tier? And how do cocotb (VPI, signal domain) and
  the transactors (DPI, class domain) meet? See §4 item 6 for the candidate
  designs and the spike to choose between them.
