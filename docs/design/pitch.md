# Designing Hardware with SystemVerilog Classes

> **Review convention (2026-11-14):** Review comments appear as quoted blocks starting
> with **Review:**. The original text is unchanged. The sections after
> "Key requirements" are new. Sources are numbered and listed at the end.

The SystemVerilog language is really several languages together.
There's the structural subset (modules, interfaces, signals) used
for design. There's the temporal assertion subset (SVA). There's
the class-based subset that includes randomization. Functional 
coverage bridges the structural, assertion, and class-based domains.

We typically think about designing synthesizable hardware using the
structural subset, but there are very compelling reasons to explore
the use of the class-based subset for this purpose as well:
- Dynamically-defined structure with procedurally-defined parameters
- Substitute different implementations
- Bridge to higher-level design abstractions, such as mid-level and high-level synthesis
- An incremental path to 
- Better integration with verification. Easier path for designer tests
- Better support for formal verification

> **Review:** This list is the heart of the pitch, but there is no evidence for
> the problem behind it yet. The Wilson/Siemens 2024 study supplies some [1]:
> - Only 14% of IC/ASIC projects reached first-silicon success, the lowest in
>   the 20 years of the study.
> - Design engineers spend about 49% of their time on verification.
> - Debug is the largest single share of verification time.
>
> One sentence with these numbers would anchor "better integration with
> verification" and "easier path for designer tests".

> **Review: "Dynamically-defined structure".** Readers will take "dynamic" to
> mean run-time allocation, and that is exactly what synthesis and formal tools
> reject. The structure is built procedurally at elaboration (time 0) and fixed
> after that. Brad Pierce gives this as the condition under which classes are
> synthesizable [9]. Suggest "procedurally-elaborated structure", and say here
> that it is frozen at time 0.

> **Review: "Substitute different implementations".** The factory swap is
> resolved at elaboration time and never becomes run-time polymorphism in the
> hardware. Vivado [3] and yosys-slang [4] both reject virtual dispatch and
> polymorphism, so this has to be stated plainly. It also explains why fw-hdl
> works where "just synthesize the classes" does not.

> **Review:** The "An incremental path to" bullet is unfinished. It probably
> means "an incremental path to higher abstraction from existing RTL", which
> would merge it with the last key requirement.

> **Review: "Better support for formal verification".** The claim needs a
> mechanism. I found no primary source saying that Jasper, VC Formal or Questa
> Formal accept class-based design input, so a stock formal tool will run on the
> generated RTL. The real advantage could be one of these:
> - Properties are written once against class-level semantics and carried
>   through the lowering.
> - The IR makes the state space explicit (registers and comb functions), so
>   formal can run directly on it.
> - Designer tests and formal share one harness.
>
> Choose one and say it.

Strictly speaking, classes are software constructs with dynamic memory management,
handles, etc. This means that we must enforce some rules in order to project a
class-based description to hardware. Class libraries are a great asset here: 
classes in the library are given well-defined semantics -- both in execution and
other representations. As long as an implementation follows the defined semantics,
it's equivalent.

> **Review:** This paragraph is the strongest idea in the pitch and is
> understated. Mainstream tools support SV classes in synthesis unevenly and
> inconsistently:
> - Design Compiler accepts static methods of parameterized classes only if the
>   class is `virtual` and declared in `$unit` [2].
> - Vivado 2024.1 synthesizes class objects created at declaration, including
>   inheritance and virtual overrides (more than its UG901 table admits [3]),
>   but rejects any base handle holding a derived object (tested locally; see
>   below).
> - sv2v cannot handle some synthesizable parameterized-class uses [5].
> - Genus and Quartus support is reported as limited (unverified).
>
> See *Existing tool support for class-based design* below for the full
> survey. Do **not** claim that "no tool synthesizes SV classes": Vivado's
> documentation contradicts it.
>
> fw-hdl does not depend on any of this. The front end statically elaborates the
> classes to Zuspec IR and emits plain Verilog, so the downstream tools never see
> a class. Say so explicitly: it is the answer to the first objection an
> experienced designer will raise ("my synthesis tool doesn't take classes").

> **Review: "it's equivalent".** Equivalence is asserted here, not checked. With
> three or more implementations (SV runtime, RTL, C), the pitch should say how
> they are kept consistent: a conformance suite, cross-implementation
> co-simulation, or formal equivalence between the IR and the generated RTL.
> See *Overlooked considerations* below.

Now, class libraries for hardware modeling and generation are not a new concept.
- SystemC in C++
- CHISEL in Scala
- ROHD
- ...

> **Review:** Complete the list. Each of these overlaps with part of fw-hdl's
> claims, and a reviewer will ask about them:
> - PyMTL3: FL/CL/RTL modeling levels, Verilog translation and Verilog import [12].
> - Amaranth [13]
> - Bluespec [14]
> - SpinalHDL
> - Hardcaml [15]
> - Clash
> - MyHDL
> - Accellera PSS: not an HDL, but the closest precedent for "one specification
>   with several conforming implementations" [8].

But, fw-hdl approaches this differently. The class libraries above exist for a 
single purpose: either simulate the execution semantics of hardware or generate
synthesizable HDL. In both cases, they are designed to execute. fw-hdl exists
to provide a specification that can be mapped to:
- An executable representation in SystemVerilog
- A synthesizable representation in Verilog RTL
- An executable representation in C
- ...

> **Review: the "single purpose" claim is factually weak, and the cited projects
> contradict it.**
> - **SystemC** has had an Accellera synthesizable subset since 2016 [6]. It
>   feeds HLS tools such as Catapult and Stratus. NVIDIA MatchLib uses one
>   SystemC source for both simulation and HLS [7].
> - **Chisel/FIRRTL/CIRCT** emits Verilog and also has native simulators
>   (ESSENT, and CIRCT's Arcilator) [10] and formal flows [11].
> - **ROHD** has its own event simulator *and* generates "readable, EDA tool
>   compatible SystemVerilog". Its paper also pitches "gradual adoption"
>   alongside SV, which is close to fw-hdl's own message [16].
> - **PyMTL3, Amaranth, Bluespec and Hardcaml** all simulate natively and emit
>   Verilog [12–15].
>
> The claim that does hold up is narrower. In every one of these, *the library
> implementation is the semantics*: what the Scala/Dart/C++/Python code does
> defines what the hardware means. fw-hdl separates a written specification
> (user-facing classes and their minimum-bar semantics) from interchangeable
> implementations, which a simulator vendor can even supply natively (see
> `architecture.md`). Two more things are distinctive:
> - the source language is SystemVerilog itself, which the target users already
>   know and their simulators already run, not a host language they must adopt;
> - the reference executable runs on any stock SV simulator, with no proprietary
>   simulator or extra language runtime.
>
> Suggested rewrite: "Existing class libraries define hardware semantics by
> their own implementation, in a language foreign to the RTL flow. fw-hdl
> defines semantics as a specification in SystemVerilog, and treats the SV
> runtime, the RTL generator, and the C model as peer implementations of that
> specification."

> **Review:** The "In both cases, they are designed to execute" sentence argues
> against fw-hdl too, since the SV runtime executes. The distinction is static
> versus dynamic interpretation (`architecture.md`: "most implementations will
> interpret a fw-hdl description statically"). Use that wording.

Key requirements:
- Seamless interoperability with existing Verilog RTL
- Support for designs using multiple abstraction levels
- Excellent test and verification automation -- both dynamic and formal
- Incremental adoption path that pays at each level

> **Review:** These are good. Two are missing:
> - **Readable, traceable output.** The generated RTL is what goes through CDC,
>   lint, LEC, DFT and timing.
> - **Fixed point in time.** All structure and parameters are resolved at
>   elaboration, and nothing is allocated after time 0.
>
> "Pays at each level" would be stronger if each level were named. The roadmap
> already defines them: wrap and integrate existing RTL, then domains, then glue
> logic, then protocol kits.

## Assessment: where the argument is strong and weak (new)

### Strong

| Point | Why it holds |
|---|---|
| The problem (verification load) | Hard numbers: 14% first-silicon success, ~49% of design time spent verifying [1]. |
| A library with defined semantics, separate from its implementations | No surveyed library does this. Each of SystemC, Chisel, ROHD and PyMTL3 defines meaning by its own implementation. This is fw-hdl's real novelty. |
| SV as the source language | The source is in the language the RTL flow and simulators already use. ROHD has to justify Dart and Chisel has to justify Scala; fw-hdl has no host language to justify. |
| Static elaboration to IR, then plain Verilog | Sidesteps the uneven, vendor-specific class support in synthesis [2][3][4][5]. Downstream signoff tools see ordinary RTL. |
| Method-level designer tests | Tests start before RTL exists, reach the wires through protocol transactors, follow each refinement, and share an interface with formal properties. Signal-level frameworks such as cocotb cannot do this. |
| Interop and incremental adoption | Wrapping existing RTL (roadmap phase 1) delivers value before anyone writes logic in classes. |

### Weak, with a proposed new direction

1. **"Other libraries have a single purpose."** This is factually wrong for every
   cited example [6][7][10][12–16], and a knowledgeable reader will stop there.
   *New direction:* lead with **specification versus implementation**. In other
   libraries the implementation *is* the semantics; fw-hdl writes the semantics
   down and treats the SV runtime, RTL, C and formal as peer implementations,
   which simulator vendors may implement natively. PSS [8] is the precedent to
   cite: a specification with several conforming implementations.

2. **"Dynamic structure" and "substitute implementations".** As worded, these
   promise exactly what synthesis forbids (run-time allocation and dispatch).
   *New direction:* reframe as **"programmable elaboration"**: a fully procedural,
   object-oriented generate phase that ends at time 0 and leaves a fixed
   netlist. Pitch the factory as configuration-time IP selection, which is how
   verification engineers already think of the UVM factory.

3. **"Better support for formal".** There is no mechanism behind it yet, and
   commercial formal tools will see only generated RTL. *New direction:* make the
   claim about **one description serving three purposes**. The same class
   description provides the design, its executable model, and a structure
   (explicit state plus comb/sync functions in the IR) that formal and
   equivalence checking can consume directly. Defer "better formal" until a
   demo exists.

4. **"Easier designer tests".** This is weak only as worded; the substance is
   strong. Cocotb (the obvious comparison [1]) makes tests easier to *write*,
   but the designer still drives the design at the signal level. That assumes
   the design already exists as RTL and that the test speaks the wire protocol.
   fw-hdl changes *what the test talks to*:
   - **Start at the method level.** The designer tests behavior through the
     component's method interface before any RTL exists.
   - **Reuse protocol transactors.** Protocol kits bridge that same method
     interface to the wires once the design is refined. The test does not
     change; the transactor absorbs the protocol detail.
   - **Follow the refinement.** The same test runs against every abstraction
     of the design as it is refined (method-level model, SV runtime, generated
     RTL, C model).
   - **Write formal properties against the same interface.** Properties stated
     on the method interface apply at every level, which also gives point 3
     the mechanism it lacks.

   *New direction:* make this the headline benefit: **designer tests that are
   an order of magnitude better**. Tests begin on day one at the method level,
   are written once, and are carried through refinement down to RTL and formal.
   Cocotb supports only the last step of that path. Back the "order of
   magnitude" with a measurable demo, for example test lines and days-to-first-test
   for one block written method-first in fw-hdl versus signal-level in cocotb.

5. **Unnamed audience.** RTL designers and verification engineers want different
   things. *New direction:* sequence the two groups (see *Who this is for* and
   *The abstraction ladder*).
   - **Verification engineers first.** Wrapping existing RTL gives them better
     debug and an on-ramp to formal, with no change to the design.
   - **Designers next.** Show them the RTL subset (`comb()`, `step()`) as a
     small step from the `always` blocks they write today. Contrast it with
     HLS or XLS, which demand a very different way of thinking. They then climb
     to higher subsets only when each step pays.

6. **Equivalence is assumed, not ensured.** With several implementations, "it's
   equivalent" is the riskiest sentence in the pitch. *New direction:* turn it
   into a feature. **Conformance is part of the spec**: a shared conformance
   suite plus differential and formal equivalence between the IR and the
   generated RTL. This also answers the debug and trust objections.

7. **No proof point.** *New direction:* close the pitch with one concrete demo
   (see *Open questions*). One description, three implementations and one test
   suite carry more conviction than the bullet lists.

### Suggested one-paragraph pitch built on the strong points

> fw-hdl lets you describe hardware with SystemVerilog classes, the language
> your simulators and verification teams already use. Construction is fully
> programmable but ends at elaboration. What remains is a fixed design with
> precisely specified semantics. Because those semantics are written down
> rather than implied by one tool, the same description runs on any SV
> simulator, lowers to readable Verilog for your existing synthesis and signoff
> flow, and becomes a fast C model, with a shared conformance suite keeping
> them equivalent. Designers test at the method level from day one, before any
> RTL exists. The same tests and formal properties follow the design through
> every refinement, with protocol transactors bridging down to the wires.
> Start by wrapping and integrating the RTL you already have. Write new logic
> in an RTL subset that reads like the `always` blocks you know, and climb to
> higher abstractions one step at a time, only where it pays.

## Candidate framing: SystemVerilog testbench to FPGA testbed (new, 2026-11-15)

The same source runs efficiently as classes in any SV simulator *and* lowers
efficiently to synthesizable RTL for an FPGA or emulator. Applied to
verification collateral, that is a pipeline from testbench to testbed:
transactors, traffic generators, checkers and coverage written once, run in
simulation, then placed on hardware at speed.

**Why it may be the strongest entry point:**
- **The hardest objections don't apply.** Generated RTL lost ASIC teams over
  readability, LEC and ECOs (*Traction*, pattern 3), and QoR is the first
  question for any design flow. Test collateral is not signed off: nobody
  runs LEC on a traffic generator, and 10% area is cheap on an FPGA or
  emulator.
- **The right authors.** Verification engineers already write classes. This is
  H2 (verification first) with a deliverable they can't easily get today: the
  research found the effort, not the value, is what stops synthesizable
  testbenches ("as complicated as the RTL itself").
- **A gap no one fills.** Emulator vendors' behavioral synthesis (XRTL,
  IXCOM, ZEMI-3) is tied to one emulator and does not target FPGA. Processor
  tools (Breker, STING) need transactors for I/O. No general on-chip stimulus
  flow exists (`research/emulation-traffic-generators.md`).
- **A wedge into design.** A team that trusts the lowering for its testbed
  has seen the mechanism work. Design blocks are the next step, not the first.

**What makes it more than "synthesize the testbench":**
- **The partition is a method interface, chosen by configuration.** Every
  transaction-based acceleration flow splits the testbench by hand into a
  synthesizable side and a host side (the SCE-MI/TBX split). Here, in
  simulation, both sides are classes. For the testbed, the factory places
  some components in hardware and the method interfaces between the two sides
  become generated channels (doorbells, descriptor rings, streamed
  results). Moving the boundary is a configuration change, not a rewrite.
- **What lowers and what stays on the host:**
  - *Lowers:* transactors, stimulus engines that expand descriptors, LFSR
    randomization, checkers, coverage and statistics counters.
  - *Stays:* constraint solving and scenario selection (fw-hdl-dv, in Python
    or SV), complex reference models, reporting.

  This is the same split the research found works (keep the per-cycle work in
  hardware, batch the host traffic), made systematic.

**What has to be true:**
- **A defined synthesizable testbench subset.** It needs structure fixed at
  elaboration, no allocation after time 0, and bounded queues. Publish it like
  the design subset.
- **Randomization semantics across the boundary.** In classes, `randomize()`;
  in hardware, an LFSR or descriptors solved on the host. Equivalence means the
  same legal set, not the same values (as for the Python flavor of fw-hdl-dv).
- **The generated host channel is the crux.** It is the same problem as the
  Python VPI/DPI bridge, and as FireSim bridges and SCE-MI pipes: batch,
  stream, never stall per transaction. Design it once for both.
- **Throughput, not area,** is the QoR measure that matters for a testbed.

> **Review:** Check whether this should become the headline, ahead of
> class-based design itself. It inverts the original pitch's order (design
> first, verification as a benefit).
>
> **The Bluespec precedent** (`research/bluespec-testbenches.md`). Bluespec made
> this technical case around 2007–09 (synthesizable BSV testbenches, an EVE
> ZeBu partnership, "1,000x–10,000x"), and no named company is documented
> using it for testbenches. The likely causes:
> - *A new language with scheduler semantics.* This does not apply to fw-hdl,
>   which is plain SV.
> - *The synthesized bench was a subset of real verification:* no solver,
>   coverage or rich scoreboards. fw-hdl answers this with the split, not a
>   subset: solver, scenarios and scoreboards stay on the host and only the
>   per-cycle work goes to hardware.
> - *A small proprietary vendor,* and a pitch that changed five times in ten
>   years. Open source helps; focus is up to us.
> - *Emulator vendors absorbed the need* with their own behavioral compilers
>   (unverified), so fw-hdl's emulation value is portability, not capability.
>
> What fw-hdl must do differently:
> - complement UVM rather than replace the testbench;
> - show bit-exact reproducibility (same seed, same trace) across simulation
>   and hardware;
> - keep generated SV readable, with a debug map back to the classes;
> - publish independent case studies, not self-graded benchmarks;
> - pick one wedge and hold it.

## Who this is for (new)

The pitch never names its user. The groups below are listed in adoption order:

1. **Verification engineers: the first beneficiaries.** They already know
   classes and factories. Wrapping existing RTL (roadmap phase 1) changes
   nothing in the design, yet gives them:
   - improved debug at the method and transaction level, through protocol
     transactors attached to the wrapped RTL;
   - an on-ramp to formal, with properties written against the method
     interface rather than raw signals.

   The value comes without anyone writing new logic in classes, so adoption
   carries no design risk.

   **Pitch line: "Author in SystemVerilog, ship PSS to SoC teams."** fw-hdl-dv
   scenarios follow PSS 3.1 semantics in SV syntax and project to PSS source
   (see `featherweight-ip-strategy.md` §4). This targets PSS's documented
   weak point, block-level adoption:
   - *Today:* block teams have little reason to learn a new language, so SoC
     teams lack the "bottom-up content" PSS depends on.
   - *With fw-hdl-dv:* block teams write scenarios in the language and
     simulator they already use. The SoC team receives PSS for vertical reuse
     at no extra authoring cost.

   fw-hdl-dv also has a Python flavor held to the same conformance suite
   (`featherweight-ip-strategy.md` §4, item 6). Scenarios with PSS semantics
   can be written in Python too, and tests change without rebuilding the
   design. For Python-first teams the line reads "author in Python, ship PSS".

   > **Review:** The line holds only if the projection is faithful and the
   > receiving SoC team's PSS tool accepts the output. Back it with round-trip
   > tests against at least one commercial PSS tool, and publish the list of
   > unsupported PSS features.
2. **RTL designers: the real test.** Most do not write object-oriented SV
   (my reading of the field, unverified). The demo that wins them over is a
   side-by-side comparison (see *The abstraction ladder*): first HLS or Google
   XLS, then the fw-hdl RTL subset. The RTL subset is a small step from the
   `always` blocks they write today, whereas HLS is a very different way of
   thinking. To this group, classes must read as a tidier way to write the RTL
   they already know, not as UVM.

   **A second reason for designers to adopt it: the fast platform falls out
   of the design (new, 2026-11-15).** Teams are already under pressure to
   deliver fast software platforms (QEMU or Renode machines, virtual
   prototypes) so firmware and drivers can start before silicon or FPGA.
   Today a separate modelling team writes those models by hand, and they
   drift from the RTL.
   - With fw-hdl, the designer writes the design view at the level where the
     register map and function are settled. The fast platform model is
     derived from that view at once.
   - The designer then refines toward RTL, establishing equivalence (SEC, or
     transaction-level refinement) at each step. The platform stays the same
     source, proven equivalent, rather than a model that was right early on
     and wrong by tapeout.
   - Assembly extends this to the whole SoC. The configuration that connects
     the blocks produces the RTL SoC, a complete emulation platform, the
     device tree and the tests.

   This benefit doesn't depend on the designer believing that classes write
   better RTL. The software team needs the platform anyway; here it is a
   by-product of design work instead of a second project.

   Lifting existing open IP is the same mechanism run upward. RTL people
   already trust is lifted, proven equivalent to the original, and given a
   generated model. The planned case study is Cheshire, a taped-out Linux
   SoC from the PULP project with no upstream QEMU or Renode machine. Lifting
   it is the evidence for this design-side claim. See
   `ip-library-focus.md` §0.

   > **Review:** The evidence for drift is strong, but it comes from open
   > projects. OpenTitan's QEMU fork is pinned to an old RTL release and
   > grades its own devices down to "dummy". LiteX's Renode generator has
   > special cases wherever a model lags the RTL. See
   > `research/ip-market.md` §4.
   >
   > What has *not* been shown:
   > - how much commercial teams spend on platform models;
   > - whether designers, rather than a modelling team, would own them.
   >
   > The claim also depends on two things that don't exist yet: a C view
   > that QEMU or Renode can host, and a separation of each block's function
   > from its timing. Without both, the "fast model" is just compiled RTL,
   > which Verilator already provides.
3. **Architecture and modeling teams: a path into design.** Today an
   architecture model is usually thrown away at hand-off. The design team
   re-reads it as a document, and the RTL is written from scratch. fw-hdl's
   shared multi-language semantic model changes that:
   - **Explore in Python.** The architect builds the model from fw-hdl
     library constructs (components, ports, channels, protocol kits) in
     Python, the language most architects already use.
   - **Hand off as SystemVerilog.** The same model maps to SV, which becomes
     the design team's starting point rather than a specification to
     re-read.
   - **Refine behind stable interfaces.** As long as the interfaces stay
     consistent, the design team implements the internals at whichever rung
     fits (RTL subset, SPL, HLS). The elaboration-time factory swaps their
     implementation in for the architect's model, block by block.

   **What this adds beyond the hand-off:**
   - *The architect's model stays alive.* It becomes the reference model
     that the design's verification compares against.
   - *Tests carry over.* The architect's method-level tests are the first
     tests on the design, as in point 4 of *Weak*.
   - *Performance correlation.* If the architect's model and the design run
     the same scenarios through the same interfaces, latency and throughput
     can be compared block by block as the design is refined. Checking the
     RTL against the performance model is a known, largely manual pain
     point; this would make it routine.
   - *The C model and MLS/HLS stay available* at the top of the ladder for
     the same team.

   **Evidence and precedents:**
   - *PyMTL3 shows that FL-to-RTL refinement with reused tests works.* It
     also shows two traps:
     - the levels lived in one Python-only world;
     - its author concluded that Python cycle-level models are too slow.

     The shared semantic model answers both: Python is a front end, not the
     runtime the design depends on, and the same model can run as SV or as
     a C model.
   - *SystemC TLM succeeded for architecture and virtual platforms, but
     stopped at the hand-off.* Nothing carried the model into design except
     through HLS (MatchLib, Catapult).

   **What the research found** (`research/architecture-handoff.md`):
   - *The problem is real.*
     - Intel reports that TLM models and RTL "are created independently by
       different teams", and that correlating them "is usually a huge effort…
       almost no automation tools."
     - Ampere built dedicated infrastructure over four core generations to
       reach "90% of tests within ±10%" IPC.
     - Models that are not checked against RTL are badly wrong: 51% and 31%
       match in IBM's PowerPC 604 study.
   - *Shared structure makes correlation cheap.*
     - NVIDIA MatchLib, where the model is also the synthesis source, gets
       within about 3% of RTL.
     - Arm and FireSim reached the same conclusion from the other direction,
       by deriving models from RTL.
     - Intel's ROHD paper describes an IP team building a micro-architectural
       performance model designed for reuse in unit verification. That is a
       near-exact precedent, written in Dart.
   - *ESL refinement has been pitched before, and it failed.* It needed
     process change, and models stayed "islands."

   **How the pitch should answer the risks:**
   - **No process change; refine block by block.** The factory swap
     replaces one block at a time. The architect's model keeps running
     everywhere else, so nothing is a top-down switch. This is the opposite
     of the failed ESL story, and it also keeps simulation fast: Intel
     measured 64 transactions/s with RTL in the loop against 50k for TLM
     alone, but here only the block under refinement is RTL.
   - **Share interfaces and scenarios, not internals.** The designer writes
     the internals independently. What is shared is the interface, the
     scenarios and the measurement points. That answers Ampere's
     common-mode-error concern, because the reference model stays an
     independent implementation behind the same interface.
   - **Automate the correlation infrastructure.** Teams such as Intel and
     Ampere build their own: unified event streams, the same traffic into
     the model and the RTL, per-block metrics. fw-hdl provides that by
     construction. Correlation of internal timing remains engineering work,
     but the harness is free.
   - **Don't lead with Python.** Incumbent performance models are written in
     C++ or SystemC, and Python is used mainly for analytical and
     ML-accelerator models. Pitch "explore in the language you work in, on
     one semantic model", with Python as the first front end. Long
     workloads run on the C-model lowering, not in Python (the PyMTL3
     lesson).

   > **Review: conditions for this claim to hold.**
   > - **Interface consistency is the crux.** Architects work at transaction
   >   level, while designs end at pins. The protocol kits (method interface
   >   plus transactors) are what keep the interface "the same" across that
   >   gap, so say this explicitly.
   > - **The Python and SV semantics must match exactly.** This is the
   >   conformance problem (*Weak*, point 6) applied across languages: the
   >   same model must behave the same in Python and in SV.
   > - **Organizational fit is unverified.** Find evidence on how architecture
   >   teams hand off today (Python vs SystemC vs spreadsheets) and who owns
   >   the model afterwards. Interviews, as for designer testing, are the
   >   likely source.
4. **Verification engineers on emulation: synthesizable collateral.**
   Performance verification on an emulator needs traffic generators, for
   example a multi-stream NVMe traffic profile.
   - **The bottleneck.** If the host sends every transaction across the
     host-emulator boundary, emulation slows considerably.
   - **The fix is a design.** A generator that lets the host build transfer
     descriptor chains, then runs them more or less autonomously, performs
     well. But writing it is a real hardware design: descriptor fetch,
     arbitration across streams, rate control and completion tracking. That
     cost is why such generators are rare and expensive.
   - **The fw-hdl angle.** Verification engineers write the generator with
     higher-level constructs (SPL for the descriptor engine, protocol kits for
     the interfaces) and get synthesizable RTL within about 10% of
     hand-written code. The generator becomes something a verification team
     can build in weeks rather than a design project.

   Why this may be the best-fitting audience for the abstraction ladder:
   - *A relaxed QoR budget.* An emulator cares about capacity and emulation
     clock, not silicon area or power, so 10% off hand-written code is easily
     acceptable. HLS succeeded where QoR budgets were relaxed (Google VCU), and
     this budget is more relaxed still.
   - *The right authors.* Verification engineers already think in classes,
     sequences and transactions. This is H2 (verification first) with a
     concrete deliverable.
   - *One source, every platform.* The same generator runs as a class model in
     simulation (fast, debuggable), as RTL on the emulator, and on an FPGA
     prototype, behind the same method interface. This is the
     multi-implementation pitch in its most concrete form.
   - *It connects the family.* The host side builds descriptor chains from
     fw-hdl-dv scenarios (PSS semantics, so they also project to PSS). The
     wire side reuses the synthesizable fw-proto transactors. The traffic
     profiles can come from the architects' performance model (item 3).

   **The same collateral is a testbench for your FPGA design.** FPGA teams
   already test on the board, often instead of simulating. Competing
   approaches to on-board and post-silicon testing mostly mean "write C code
   that runs on the processor core". That only reaches what the processor can
   reach, at the processor's speed, with no cycle-level control. fw-hdl
   collateral is hardware placed next to the design under test:
   - it drives interfaces the processor can't reach (streaming ports, custom
     buses) at line rate;
   - it produces cycle-level patterns such as backpressure and bursts;
   - it checks and collects coverage in hardware, at speed;
   - it comes from the same source as the simulation testbench, so a test
     moves from simulation to the board unchanged ("one test, every level"
     reaches the lab).

   The elaboration-time factory swaps the test collateral in and out, so the
   production build carries none of it.

   The evidence (`research/emulation-traffic-generators.md`, §8):
   - 87% of FPGA projects had non-trivial bug escapes (Wilson 2024), and lab
     validation is often the primary strategy.
   - The processor-driven tools concede the I/O gap. Breker generates a
     "TrekBox" of transactors for external ports, and the common PSS pattern
     is a processor write that triggers a VIP command.
   - No vendor or startup offers a general way to write on-chip stimulus;
     only fixed-function IP and research systems exist.
   - ILA's shallow trace is pushing checkers into hardware (Hassert, FireSim
     assertion synthesis). fw-hdl-dv checkers could synthesize onto the board
     as well.

   The risk is the audience: FPGA teams lean on lab bring-up, MATLAB and C on
   the core, so class-based SV collateral asks more of them than it asks of
   verification engineers.

   > **Review: what the research found** (`research/emulation-traffic-generators.md`).
   > - **The problem is documented.** Host syncs cap the speed-up of
   >   transaction-based acceleration. Analog Devices cut syncs 470x and run
   >   time fell 15x. Practitioners name the *effort* as the barrier: a
   >   synthesizable testbench is "as complicated, if not more, as the RTL
   >   itself" (PMC).
   > - **There is a named gap.** Arm's Adaptive Traffic Profiles spec calls for
   >   "low-gate-count hardware" generators for emulation and FPGA, but Arm
   >   ships only a C++ engine. AMD's AXI Traffic Generator is shallow: 256
   >   register-programmed commands per direction, no descriptor chains. An
   >   fw-hdl generator that runs ATP profiles would fill that gap.
   > - **Vendors confirm demand.** Siemens VirtuaLAB markets "autonomous
   >   traffic generation". FireSim's bridges show the same architecture in
   >   research: models on the FPGA, host traffic batched.
   > - **Risks:**
   >   - Storage performance validation has standardized on a QEMU virtual
   >     host running real drivers and fio. Position the generator as a
   >     complement (line rate, stress, determinism), not a replacement.
   >   - Emulator compilers already accept behavioral SV (Veloce XRTL,
   >     Palladium IXCOM, ZeBu ZEMI-3). fw-hdl's case rests on portability
   >     across emulators and FPGA, the class-model twin in simulation, the
   >     scenario-to-descriptor link, and openness.
   >   - Bluespec pitched high-level synthesizable testbenches around 2009 and
   >     it did not catch on. Find out why before repeating it.
   >   - PMC found the host link often isn't the bottleneck. The size of the
   >     pain varies by project, and NVMe-under-emulation data is not public.
   >   - Throughput matters more than area. The generator must sustain line
   >     rate with no bubbles.

## The abstraction ladder (new)

The strongest designer argument is not "higher abstraction". It is
**incremental abstraction**: every rung is a small step from the one below,
and the designer chooses how far to climb, block by block.

| Rung | What the designer writes | Distance from today's RTL |
|---|---|---|
| Wrap | Existing Verilog, wrapped and integrated through classes | None. The design is unchanged. |
| RTL subset | `comb()` and `step()` methods on component classes | Small. These read as `always_comb` / `always_ff` bodies organized into classes. |
| Sequential process level (SPL) | Sequential processes with inferred FSMs | Moderate. The designer writes the control flow, and the FSM is derived from it. |
| MLS / HLS | Method- and transaction-level behavior; scheduling and pipelining by a synthesis engine (XLS is one such engine) | Large. This is where HLS tools start today. |

The contrast to draw with HLS and XLS: those tools ask the designer to jump
straight to the top rung and trust the scheduler, which is the daunting part.
fw-hdl lets them start on the rung they already stand on. All rungs share one
component model, one test interface and one formal interface, so a block can
move up a rung without disturbing its neighbours or its tests.

> **Review:** The evidence is now in *Traction of prior approaches* below. It
> partly supports this section and partly corrects it:
> - The documented HLS barriers are fit and integration, more than
>   abstraction distance.
> - Teams that commit to HLS report 50–75% less effort.
>
> So emphasize "the right rung for each block, interoperating" more than "HLS
> is daunting". The demo should present one small block written three ways:
> HLS/XLS, the fw-hdl RTL subset, and SPL.

## Evidence for the premise (new)

- Verification dominates effort and first-pass success is falling [1].
- Demand for designer-written tests is real. The Wilson study now tracks Python
  and cocotb testbenches [1], so designers are adopting test frameworks outside
  the SV/UVM stack. Those frameworks still work at the signal level on finished
  RTL, which leaves room for method-level designer tests (see *Weak*, point 4).
- The static subset of SV classes, used as namespaces and parameterized
  utilities, is already accepted by several synthesis front ends [2][3][4]. The
  idea that classes can describe hardware is not new to tool vendors.
- Higher-abstraction HDLs have shipped real silicon: SiFive with Chisel, and
  NVIDIA MatchLib with SystemC HLS [7]. Adoption stays concentrated in a few
  organizations with software-heavy teams.

## Existing tool support for class-based design (new)

**Question.** Does any existing tool synthesize, or formally verify, hardware
described with SystemVerilog classes? (Researched 2026-11-15.)

**Verdict: false for one tool, true for every other tool checked.**
- **Vivado synthesizes class-based RTL, and correctly.** We tested Vivado 2024.1
  locally (`research/sv-class-synth/README.md`). These synthesized and passed
  self-checking post-synthesis simulation:
  - objects as register state;
  - objects with constructor arguments;
  - composition of objects;
  - one object per `generate` iteration and per module instance;
  - inheritance;
  - a virtual method override;
  - an abstract class with a pure virtual method.
- **Vivado does more than UG901 documents.** The guide lists virtual and
  abstract classes as *Not Supported*, yet both worked.
- **Polymorphism fails everywhere in Vivado.** A base-class handle can never
  hold a derived object (assignment, initialization and `base h =
  derived::new()` all fail).
- **Objects must be created at their declaration.** `new` called in an
  `initial` loop is rejected.
- **Implementation selection works only by type.** The one working idiom is
  `parameter type IMPL`; a base handle cannot be used.
- Every other synthesis tool I could check supports classes only as namespaces,
  or not at all.
- I found no formal tool documented to accept class-based design.
- No tool supports polymorphism through base handles, even when it could be
  resolved at elaboration, and none synthesizes objects allocated at run time.

**Support levels used below:**
- **L0:** no class support.
- **L1:** classes as namespaces: static methods, typedefs and parameters of
  (parameterized) classes, but no objects.
- **L2:** objects built with `new` at time 0, whose members act as state and
  whose non-virtual methods are called from `always` blocks.
- **L3:** inheritance and virtual methods, resolved statically at elaboration.
- **L4:** objects allocated at run time.

| Tool | Synthesis | Formal | Evidence | Confidence |
|---|---|---|---|---|
| AMD Vivado 2024.1 | L2, L3 without polymorphism: objects created at declaration, inheritance, virtual overrides and abstract classes all work; a base handle holding a derived object fails; procedural `new` fails | n/a | [3], [24]; local test `research/sv-class-synth/` | **Verified locally**, synthesis plus post-synthesis simulation (14 tests) |
| Synopsys Design Compiler | L1 (static functions in parameterized classes; class must be `virtual` and in `$unit`) | — | [2] | Secondary (2013); no current doc found |
| Synplify Pro (2024) | L0 (classes absent from the SV feature table) | — | [25] | Primary (absence from the table) |
| Intel Quartus Prime | L0 (the "Classes" LRM section is unsupported) | — | [26] | Secondary (search snippet of a page that now returns 404) |
| Cadence Genus | L0 reported | — | — | Unverified |
| Siemens Precision, Lattice Radiant, Gowin | ? | — | — | Not found |
| yosys `read_verilog -sv` | L0 | L0 | Local test, yosys 0.70: `class` is a syntax error | **Verified locally** |
| sv2v | L1 for a non-`virtual` parameterized class with static functions; rejects `virtual class` (Design Compiler's required form) and `new` | — | Local test, sv2v 0.0.13: output synthesized cleanly by yosys | **Verified locally** |
| yosys-slang | L1+ (static methods, `::`, parameterized and interface classes); objects, constructors, `this`, virtual methods and polymorphism "non-synthesizable" | L1 via SymbiYosys | [4] | Primary |
| Synlig / Surelog, Verific | Surelog and Verific parse classes; elaboration of classes for synthesis not documented | ? | — | Unverified |
| CIRCT Moore dialect | Models classes as heap objects (`class.new`); no lowering to hardware | — | [27] | Primary |
| Jasper, VC Formal, Questa Formal / OneSpin | — | Not found (L0 assumed) | — | Unverified (manuals are behind logins) |
| Palladium, Veloce, ZeBu (emulation compilers) | L0: classes stay on the host side, behind a struct or proxy-class split | — | [28] | Secondary (practitioner papers) |

**Standards.** IEEE 1800 defines no synthesizable subset. Sutherland's 2006
proposal for one listed `class`, `new`, `extends`, `virtual`, `this` and
`super` as non-synthesizable [21].

**Precedents outside SV:**
- **OSSS / FOSSY (University of Oldenburg)** synthesized C++/SystemC classes,
  templates, inheritance and *polymorphic objects* (`osss_polymorphic<>`) to
  VHDL [29]. It is the closest precedent for object-oriented hardware with
  polymorphism resolved for synthesis, and it showed the idea is feasible. It
  stayed academic, which is worth understanding before repeating it.
- **C++ high-level synthesis** (Catapult, Vitis HLS) synthesizes classes and
  templates, but as C++ at the HLS abstraction level.
- **Generator HDLs** (Chisel, SpinalHDL, ROHD, Amaranth) do object-oriented
  elaboration, but in a host language other than SV.

**Implications for the pitch:**
- Safe claim: *"fw-hdl lets SystemVerilog class objects built at elaboration
  serve as the hardware description, including inheritance and virtual methods
  resolved at elaboration, and emits plain Verilog that any synthesis or formal
  tool accepts."* No documented tool covers that combination.
- **Acknowledge Vivado.** It is real evidence that synthesizing SV class
  objects is practical: our tests reached statically-typed L3, with correct
  results. It is also limited:
  - one vendor's FPGA flow;
  - an undocumented subset (more than UG901 claims);
  - no polymorphism through base handles, which is the factory pattern fw-hdl
    relies on.

  Vivado's support is also *only RTL synthesis*. It treats a class as a
  struct of variables plus inlined functions inside an ordinary module. It has
  no component model, no abstraction levels above RTL, and no story for
  verification, formal or interoperability.
- **Formal is the stronger angle.** No formal tool is documented to take
  class-based design, so lowering to plain RTL is what makes class-based
  designs usable with SymbiYosys, Jasper and the others.
- **Fragmentation strengthens the argument.** The tools that support class
  idioms disagree. Design Compiler requires `virtual class` for static
  methods; sv2v rejects `virtual class` and every object; Vivado accepts both
  but no polymorphism. Users cannot write portable class-based RTL today, and
  fw-hdl's lowering to plain Verilog removes that problem.

**Class-level synthesis is not the value proposition; interoperable,
multi-abstraction design is.** Implementing synthesis for SV classes,
whether RTL-level as in Vivado or HLS-style as in Catapult for C++, is one
thing. Supporting a design that is refined through several abstraction levels
down to RTL, where every level interoperates, is another. In fw-hdl:
- one component model spans the whole abstraction ladder;
- blocks at different levels connect to each other and to existing Verilog
  RTL within one design (wrap, RTL subset, SPL, MLS/HLS);
- the same tests and formal properties apply at every level;
- the output is plain Verilog that drops into an existing flow.

No tool surveyed here offers that combination, and it does not depend on any
tool's class support. Pitch fw-hdl on interoperability, not on "we synthesize
classes". Otherwise Vivado, or any vendor extending its class subset, looks
like the competition.

## Closest precedent: PyMTL3 (new)

PyMTL3 (Cornell, Batten group) is the framework closest to the fw-hdl
vision. Details are in `research/pymtl3.md`.

**What it already does:**
- FL, CL and RTL components run together in one model.
- Components talk through method-based interfaces.
- Adapters between levels are inserted at `connect()`, for interface pairs
  the library already covers.
- The same pytest tests run from FL down to RTL [12].
- Existing Verilog is imported through Verilator.
- It has taped out chips [30].

A reviewer will ask "why not PyMTL3?". Five answers:

1. **The author's own lessons learned name fw-hdl's differentiators.** Batten's
   2025 retrospective [30] lists several gaps:
   - "interoperability with standard methodologies is essential … must
     support industry standard verification flows";
   - formal is "equally important" as testing;
   - a single clock domain with synchronous reset "is limiting";
   - Python cycle-level models are too slow.

   These are the gaps that fw-hdl's choices address (SV source, a written
   spec with a formal implementation, a domain model).
2. **No language boundary.** PyMTL3 embeds Verilog in Python, through
   Verilator only. cocotb embeds Python in the simulator. In fw-hdl, design,
   models, transactors and tests are all SV, running in the user's own
   simulator next to their UVM environment. Co-simulation with existing RTL
   is ordinary simulation, and PyMTL3 has no equivalent. Make this a
   headline point.
3. **Refinement in PyMTL3 is manual.** Nothing above RTL is synthesized. The
   fw-hdl ladder lowers every rung to RTL (SPL with inferred FSMs, and MLS/HLS
   through an engine). We found no precedent for that combination with
   interoperating levels.
4. **Readable, parameterized output.** PyMTL3 emits one specialized module
   per parameter set, with mangled or hashed names. fw-hdl emits one
   parameterized module per class.
5. **The semantics are a spec, not one Python implementation.**

> **Review: adoption lesson.** PyMTL3 is in maintenance mode: 6 commits since
> 2024, and no industry users found. Cornell's course now teaches RTL design in
> Verilog and keeps PyMTL3 as the test harness, and student tapeouts use it for
> testing more than for design [30]. Two conclusions for the story:
> - Teams adopt better *testing* before a new *design* language, which
>   supports the verification-engineers-first sequencing.
> - Longevity has to be designed in from the start (the project-architecture
>   split), not hoped for.
>
> Present PyMTL3 as *evidence that the multi-level idea works*, and fw-hdl as
> the version that lives inside the industry's existing SV flow.

## Traction of prior approaches (new)

Did tools that went down similar paths gain traction, and why or why not?
Details and sources are in:
- `research/traction-design-frameworks.md` (Chisel, SpinalHDL, Amaranth,
  MyHDL, Clash, Hardcaml, Bluespec, ROHD, Veryl, SystemC, OSSS);
- `research/traction-hls-verification.md` (HLS, XLS, MatchLib, SystemC TLM,
  UVM, cocotb, PSS, formal);
- `research/pymtl3.md`.

**Outcome.** Only two kinds of tool reached mainstream use:
- verification standards that run on the simulators teams already have (UVM
  at about 80% of ASIC projects, SVA, SystemC TLM, and increasingly cocotb);
- HLS, for algorithmic blocks, carried by a vendor.

Every alternative design language is niche or academic, or survives because a
single company owns it.

**Patterns behind success and failure:**

1. **A flagship owner that ships product.** Chisel has SiFive and XiangShan,
   Hardcaml has Jane Street, SpinalHDL has VexRiscv, Clash has QBayLogic. No
   design framework spread to unrelated companies on technical merit. OSSS
   (object-oriented SystemC synthesized to RTL), the closest precedent to
   fw-hdl, died when its grants ended.
2. **The host language sets the audience.** Teams adopt tools in a language
   they already use. Clients, foundries and vendors veto new host languages
   in mainstream SV shops. New verification languages without bottom-up
   content stall too (PSS).
3. **Generated RTL loses ASIC teams.** A logically equivalent Chisel
   re-implementation of SweRV-EL2 needed 15,000+ manual name matches for LEC
   (DVCon 2022). ECO and waveform debug are recurring complaints. Veryl was
   designed specifically to keep its output 1:1 with SV.
4. **The wins that convert people are verification wins.** Hardcaml's stated
   benefit is testbenches. Google's HLS team found "99% of the functional bugs
   in C++ before running any RTL simulation", with 7–8 orders of magnitude more
   test throughput. Design-side code reductions of 35–80% do not move teams if
   verification gets harder.
5. **Adoption has to be incremental and coexist with SV.** Google used HLS only
   for leaf blocks and had to build its own tool (Taffel) to connect them with
   Verilog. Tools that require a whole-design switch stall.
6. **Unfamiliar semantics need a vendor.** Bluespec's rules and OSSS's objects
   stayed niche. HLS succeeded where Catapult and Stratus carried the signoff
   burden, and Intel and Synopsys have since left HLS.

**What this means for the fw-hdl story:**

- **SV as the host language is the biggest structural advantage.** It removes
  the barrier that capped every embedded-DSL tool (pattern 2). It also puts
  the design in the same simulators as UVM, the one approach that reached the
  mainstream.
- **Our hypotheses, against the evidence:**
  - *"HLS is too big a jump" is only partly supported.* Where teams commit,
    HLS works: Google has used it for about ten years with 50–75% effort
    savings. The documented barriers are *fit* (algorithmic blocks, QoR
    budget) and *integration*, i.e. connecting HLS blocks with RTL (Google's
    Taffel, NVIDIA's MatchLib channels). Reframe the pitch as **the right
    level for each block, all in one interoperating design**. That is the gap
    Google and NVIDIA each filled with in-house tooling.
  - *"Verification adopts first" is supported, with a correction.* New
    languages enter through the testbench: Python is at 27% in verification
    while RTL stays SV. The likely first adopters are **designers writing
    block tests and formal checks**: they already spend 49% of their time
    verifying, and they prefer lightweight frameworks (VUnit, cocotb, formal
    apps, which are the fastest-growing formal category). UVM teams come
    later. The way in is method-level tests and properties on *wrapped
    existing RTL*, coexisting with UVM rather than replacing it.
- **Risks to address in the roadmap:**
  - *Readable, 1:1 lowering* at every rung, including inferred FSMs (pattern
    3).
  - *Predictable timing* for levels above RTL, visible in waveforms. This is
    the Bluespec trap and Bowyer's "one cycle later and suddenly it's broken".
  - *A flagship.* An open IP or a real design built and verified with fw-hdl
    (the VexRiscv model), and a credible owner or maintainer base. This is the
    largest risk, and it is not a technical one.

**The flagship: featherweight-ip, with featherweight-vip and fw-hdl-dv.**
Pattern 1 argues for investing in the companion libraries as the proof point.
They map onto the adoption funnel:
- featherweight-vip (protocol kits for UVM, cocotb and formal, with no fw-hdl
  adoption needed) reaches users;
- fw-proto kits and fw-hdl-dv convert them, through method-level tests and
  properties on wrapped RTL;
- featherweight-ip shows the destination, with core rewrites verified side by
  side against well-known reference cores.

What each must deliver is in `featherweight-ip-strategy.md`.

> **Review:** No survey measures method-level or transaction-level designer
> testing. "Order of magnitude better designer tests" therefore rests on our
> demo and on user interviews. Talk to a handful of designers who use cocotb
> or VUnit before the claim goes in a public pitch.

## Overlooked considerations (new)

1. **Debug and traceability.** The most common complaint about generator HDLs
   is generated Verilog that is hard to read and hard to map back to source
   (Chisel is the usual example; that evidence is anecdotal). There is an active
   research effort just to restore source-level types in waveforms [17].
   fw-hdl needs a stated plan:
   - stable, source-derived names in the emitted RTL;
   - `` `line `` or source-map annotations;
   - one parameterized module per class (already the direction in the sync
     lowering), so the RTL hierarchy mirrors the class hierarchy.
2. **Signoff runs on RTL, not on classes.** CDC, RDC, lint, DFT insertion,
   UPF/power intent and LEC all consume the generated Verilog. 95% of ASICs have
   two or more asynchronous clock domains, and CDC bugs need static RTL
   analysis [1]. Reports will point at generated code. The pitch should say that
   fw-hdl's emitted RTL is a first-class, reviewable artifact, and that domain
   and crossing information from the domains work can be exported to these
   tools (e.g. as CDC constraints).
3. **Simulation performance of the SV runtime.** Class-heavy SV, with heap
   objects, handles and garbage collection, is a known simulator performance
   problem [18]. The plain-SV executable must keep per-cycle work on static data
   paths, with no allocation after elaboration. sv-weave's per-component code
   generation is the mitigation, so state it in the pitch.
4. **Open-source simulator support.** Verilator's class support is partial but
   improving [19]. Icarus is weak [20]. If the reference runtime needs classes,
   decide which open simulators are supported, because they decide whether
   designers can try fw-hdl for free.
5. **Equivalence between implementations.** "As long as an implementation
   follows the defined semantics, it's equivalent" needs enforcement:
   - a conformance test suite that every implementation runs (planned in
     `core-layer1.md` §7);
   - a differential check between the SV runtime and the generated RTL;
   - where feasible, formal equivalence between the Zuspec IR and the emitted
     RTL.
6. **Positioning against cocotb.** Cocotb and Python testbenches are growing
   [1], and readers will compare. Answer it up front. Cocotb tests interact at
   the signal level, so they need the RTL to exist and must speak the wire
   protocol. fw-hdl tests start at the method level before RTL exists, reach
   the wires through protocol transactors, follow the design through each
   refinement, and share the interface with formal properties (see *Weak*,
   point 4). Present fw-hdl as complementary rather than as a replacement: a
   cocotb user gains the earlier, higher-level stages. The Python flavor of
   fw-hdl-dv makes this concrete. It runs on cocotb's runner, and it calls
   transactor methods rather than poking signals each cycle, so a cocotb user
   adds it to an existing testbench rather than switching tools.
7. **Standard subset definition.** No industry-standard SV synthesis subset
   exists, which Sutherland noted as early as 2006 [21]. fw-hdl is in effect
   defining one for classes. That is an opportunity (an Accellera-style
   contribution, like the SystemC synthesizable subset [6]), and it means the
   spec's allowed and forbidden constructs must be written down precisely and
   checked by the front end with good diagnostics.
8. **AI/LLM-assisted design.** LLMs are markedly worse at less common HDLs.
   Chisel has about 1/20 the public code of Verilog, and agent loops with
   compiler and simulator feedback are needed to reach parity [22]. A
   class-based SV subset faces the same problem. On the other hand, a precise
   spec, strong diagnostics and an executable reference model are what make
   such agent loops work [23]. This is worth a sentence either way.
9. **Ecosystem and longevity.** Projects judge a new HDL by whether it will
   survive. The project-architecture split (spec vs. implementations,
   versioning) answers this. Cite it from the pitch.

## Open questions for the pitch (new)

- Is the primary claim *portability across implementations* (spec-first) or
  *familiar language for higher-level design* (SV-first)? The evidence supports
  the combination better than either one alone.
- Which single demo proves the premise? Candidate: one fw-hdl description run
  on a stock simulator, lowered to RTL that passes yosys and SymbiYosys, and
  lowered to a C model, all passing the same test.
- Should "Better support for formal" stay in the pitch before a formal engine
  exists, or be phrased as "a structure that formal tools can consume directly"?

## Sources

1. Siemens / Wilson Research Group, *2024 IC/ASIC Functional Verification Trend Report*. https://static.sw.cdn.siemens.com/siemens-disw-assets/public/1NyfMZJ3nuPhMGQCGFDITG/en-US/ic-asic-functional-verification-trend-report-wp-86424-d3.pdf
2. Sutherland, *Synthesizing SystemVerilog*, SNUG 2013, §5.6.7. https://sutherland-hdl.com/papers/2013-SNUG-SV_Synthesizable-SystemVerilog_paper.pdf
3. AMD, *Vivado Synthesis User Guide* (UG901, 2025.1), SystemVerilog class support table. https://www.ecs.csun.edu/~smirzaei/docs/ece524/ug901-vivado-synthesis-en-us-2025.1.pdf
4. yosys-slang feature support. https://github.com/povik/yosys-slang/wiki/Feature-Support
5. sv2v README, unsupported features. https://github.com/zachjs/sv2v
6. Accellera, *SystemC Synthesizable Subset 1.4.7*. https://www.accellera.org/images/downloads/standards/systemc/SystemC_Synthesis_Subset_1_4_7.pdf
7. NVIDIA MatchLib. https://github.com/NVlabs/matchlib ; Khailany et al., DAC 2018. https://ctorng.com/pdfs/khailany-nvidia-matchlib-dac2018.pdf
8. Accellera, Portable Test and Stimulus Standard announcement. https://www.accellera.org/news/press-releases/267-accellera-approves-new-portable-test-and-stimulus-standard
9. B. Pierce, *Synthesizing SystemVerilog classes*. https://bradpierce.wordpress.com/2013/02/25/synthesizing-systemverilog-classes/
10. CIRCT architecture. https://circt.io/architecture.html ; Arcilator. https://arxiv.org/pdf/2508.02236
11. Formal verification for Chisel. https://arxiv.org/pdf/2102.13460
12. Batten et al., PyMTL3. https://www.csl.cornell.edu/~cbatten/pdfs/batten-pymtl3-xilinx2020.pdf
13. Amaranth simulator docs. https://amaranth-lang.org/docs/amaranth/latest/simulator.html
14. Bluespec bsc. https://github.com/B-Lang-org/bsc
15. Hardcaml. https://arxiv.org/pdf/2312.15035
16. Korbel, *ROHD*, WOSET 2022. https://woset-workshop.github.io/PDFs/2022/19-Korbel-paper.pdf
17. Source-level debugging of generated hardware. https://arxiv.org/html/2408.10082v1
18. *Yikes! Why is my SystemVerilog testbench so slooooow?*, DVCon. https://dvcon-proceedings.org/wp-content/uploads/yikes-why-is-my-systemverilog-testbench-so-slooooow.pdf
19. Verilator language support. https://verilator.org/guide/latest/languages.html
20. Icarus Verilog class-support bug. https://sourceforge.net/p/iverilog/bugs/1005/
21. Sutherland, *A proposal for a standard synthesizable SystemVerilog subset*, DVCon 2006. https://sutherland-hdl.com/papers/2006-DVCon_SystemVerilog_synthesis_subset_paper.pdf
22. LLM-based Chisel generation. https://arxiv.org/html/2505.19734v1
23. CorrectHDL. https://arxiv.org/pdf/2511.16395
24. AMD, *Vivado Synthesis User Guide* (UG901, 2022.2), Table 8-1. https://www.xilinx.com/support/documents/sw_manuals/xilinx2022_2/ug901-vivado-synthesis.pdf
25. Synopsys/Microchip, *FPGA Synthesis Language Reference* 2024.2. https://ww1.microchip.com/downloads/aemDocuments/documents/FPGA/swdocs/synopsys/fpga_hdl_reference_2024_2.pdf
26. Intel, Quartus Prime SystemVerilog support list (page now returns 404). https://www.intel.com/content/www/us/en/programmable/quartushelp/22.1/hdl/vlog/vlog_list_sys_vlog.htm
27. CIRCT Moore dialect. https://circt.llvm.org/docs/Dialects/Moore/
28. *Off to the Races with Your Accelerated SystemVerilog Testbench*, DVCon. https://dvcon-proceedings.org/wp-content/uploads/off-to-the-races-with-your-accelerated-systemverilog-testbench-a-methodology-for-hardware-assisted-acceleration-of-systemverilog-testbenches.pdf ; arXiv 1401.3554. https://arxiv.org/pdf/1401.3554
29. Grüttner et al., *SystemC Object-Oriented Extensions and Synthesis* (OSSS). https://www.researchgate.net/publication/228746060_SystemC_Object-Oriented_Extensions_and_Synthesis
30. Batten, PyMTL3 talk at Jane Street, May 2025 ("Six Lessons Learned"). https://www.csl.cornell.edu/~cbatten/pdfs/batten-pymtl3-jsxc2025.pdf

Not verified: Cadence Genus and Intel Quartus class support; class input in
commercial formal tools; exact language-adoption percentages in the Wilson
study (shown only in figures); how widely RTL designers know OOP SV.
