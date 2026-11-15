# PyMTL3: closest precedent for the fw-hdl vision

Researched 2026-11-15. This note backs the *Closest precedent: PyMTL3* section
of `../pitch.md`. It compares PyMTL3 with the fw-hdl **vision**, not with
fw-hdl's current implementation.

**Confidence marks:**
- **[P]** primary source (paper, docs, or source code read directly);
- **[S]** secondary source;
- **[U]** unverified, or our inference.

## What it is

PyMTL3 is a Python-embedded framework from Christopher Batten's group at
Cornell for modeling, generating, simulating and verifying hardware.
- PyMTL2 was released in 2014 and taped out three chips (IBM 130 nm, TSMC
  28 nm, TSMC 16 nm) [P][2].
- PyMTL3 is a rewrite, released in May 2020 [P][2].

## Abstraction levels and composition

- **The levels [P][1].**
  - FL (functional level): function only, no timing.
  - CL (cycle level): cycle-approximate behavior.
  - RTL: cycle-, bit- and resource-accurate.
- **One scheduler for all levels [P][2].** One scheduler (UMOC) runs every
  level in a single model.
  - RTL blocks (`@update`, `@update_ff`) communicate through signals, and
    their order is inferred from what each block reads and writes.
  - FL/CL blocks communicate through methods (`CalleePort`/`CallerPort`,
    `@non_blocking(rdy)`, `@blocking`). Their order comes from explicit
    constraints, e.g. `M(s.deq) < U(up)`.
- **Mixed-level composition [P].** An interface's `connect()` inserts an
  adapter between levels automatically, but only where the library already has
  a hand-written adapter for that interface pair (e.g. `RecvCL2SendRTL`,
  `MemIfcFL2RTLAdapter`).
- **Refinement is manual [P][2].** Nothing is synthesized from above RTL: "the
  DUT is manually refined to a CL and/or RTL model." The authors call HLS
  "complementary."
- **Single clock domain [P].** Every component gets an implicit `clk`/`reset`.

## Verilog interoperability

- **Import [P][3].** You subclass `VerilogPlaceholder` and supply metadata:
  source file, top module, integer parameters and a port map. Verilator compiles
  the module to a shared library, which Python calls through CFFI.
  - SV interfaces and arrays are flattened by name-mangling.
  - SV structs must be redeclared as same-width `Bits`.
  - Simulation is two-state, with X-init set to zeros, ones or random.
  - [U] We found no sign that SV `interface` ports or type/string parameters
    can be imported.
- **Translation [P].** The RTL subset (Bits/BitStruct, `@update`/`@update_ff`,
  if/for, a few helpers) is translated to SystemVerilog.
  - Hierarchy is kept, but each module is **specialized per parameter set** and
    named `Comp__p_v`, or `Comp__<hash>` once the name is long.
  - The output therefore has no parameterized modules.
- **Mixed designs [P].** Imported Verilog stays as an instance in the
  translated output, so a PyMTL3 design can contain existing RTL. The Cifer SoC
  wrapped DesignWare FPUs this way [4].

## Co-simulation

- **Python is always the master [P][2].** Verilog is embedded through Verilator
  (and SystemC black boxes). The paper contrasts this with cocotb: cocotb
  "embeds Python in a Verilog simulator… PyMTL3 takes the opposite approach by
  embedding Verilog in Python."
- **No live co-simulation with commercial simulators [P].** There is no
  VCS/Questa/Xcelium path. `VerilogTBGenPass` records interface traffic and
  emits a standalone Verilog testbench, so you can replay a test on
  four-state RTL or gates in a commercial simulator.
- [U] We found no way to place a PyMTL3 model inside a UVM environment, or a
  UVM testbench around a PyMTL3 model.
- **Performance [P][5].** PyMTL2 on CPython runs about 150× slower than a
  commercial simulator. Mamba (PyMTL3 on a modified PyPy) reaches about 2× the
  commercial simulator on one benchmark. Batten (2025): "Python CL models just
  too slow compared to C++ CL models" [4].

## Testing and formal

- **Tests reused across levels [P].** Tests use pytest, with test sources and
  sinks on stream interfaces. The same tests run on every level through class
  inheritance: the RTL test class inherits the CL tests and swaps the design
  under test. They can also drive translated-and-imported Verilog and an FPGA or
  ASIC prototype.
- **Property-based testing [P][6].** PyH2 adds property-based testing with
  hypothesis. It shrinks a failing case's transactions and design parameters
  together.
- **No formal [P].** The repo has no formal pass. Batten's 2025 lessons list
  says "productive testing and formal methods are equally important!" [4]

## Adoption and activity

| Item | Value | Mark |
|---|---|---|
| GitHub (pymtl/pymtl3) | 473 stars, 62 forks, 13 contributors, about 2,400 commits | P |
| Activity since 2024-01 | 6 commits (VCD fix, version bump); 3.1.17 released Sept 2026, previous release 3.1.16 in Nov 2023 | P |
| Status | Maintenance mode: teaching use, little feature development | our reading |
| Tapeouts | BRGTC5 (2022, 100% PyMTL3); Cifer SoC (GF 12nm, DARPA POSH, PyMTL3 tiles and NoC); Cornell teaching tapeout (4 projects use PyMTL3 for testing, 2 for design) | P [4] |
| Courses | ECE 4750 now teaches RTL design **in Verilog** and keeps PyMTL3 as the Verilator-backed test harness | P [7] |
| Industry users | None found | U |
| For scale | Chisel 4,834 stars; cocotb 2,579; Amaranth 2,128 | P |

## The author's own lessons learned (Batten, 2025 [4])

These are the most useful findings for fw-hdl. Of the six lessons, four name
gaps in PyMTL3 that the fw-hdl vision targets directly:
- "Interoperability with standard methodologies is essential … must support
  industry standard verification flows."
- "Productive testing and formal methods are equally important."
- "Single clock domain and synchronous reset are limiting."
- Simulation speed of Python CL models.

The other two lessons (physical design is the real bottleneck, and the value
of open-source tooling) are out of fw-hdl's scope.

## Comparison with the fw-hdl vision

| Capability | PyMTL3 | fw-hdl vision |
|---|---|---|
| Several abstraction levels in one design | Yes (FL/CL/RTL) | Yes (wrap, RTL subset, SPL, MLS/HLS) |
| Composition across levels | Adapters inserted by `connect()`, but each pair is written by hand | Protocol transactors on a shared method interface |
| Reaching RTL from above RTL | Manual refinement | Each level lowers to RTL (SPL infers FSMs; MLS/HLS goes through a synthesis engine) |
| Reuse existing Verilog | Black-box import through Verilator | Wrap as a subclass of the class it realizes |
| Run inside a commercial simulator / UVM | No (Verilator only; replay testbench) | Native: the source *is* SV |
| Tests reused across levels | Yes (test-class inheritance) | Yes (method-level API) |
| Formal | No | Properties on the method interface |
| Clocking | Single clock, synchronous reset | Multiple domains with crossing analysis |
| Emitted RTL | One specialized module per parameter set, hashed names | One parameterized module per class |
| Semantics | Defined by the Python implementation | Written spec, several implementations |
| Host language | Python | SystemVerilog |

## What this means for the story

1. **PyMTL3 validates the core idea.** Multi-level modeling, method-based
   interfaces, and tests reused from FL to RTL have taped out real chips.
   Cite it as evidence that the approach works, not as a competitor to wave
   away.
2. **Our differentiators match its author's own lessons.** Interoperability
   with industry verification flows, formal, multiple clock domains and
   simulation speed are the gaps Batten names [4], and they are the gaps
   fw-hdl's choices address (SV source, a written spec, a domain model).
   This is the strongest single argument we have for "why not PyMTL3?".
3. **The co-simulation story is the main difference.** PyMTL3 embeds
   Verilog in Python, and cocotb embeds Python in the simulator. fw-hdl has
   **no language boundary**: design, models, transactors and tests are all SV
   in the user's own simulator, alongside their UVM environment. So
   "co-simulation" with existing RTL is just simulation. This needs to be a
   headline point in the pitch.
4. **Adoption warning: design versus test.** At Cornell, students use PyMTL3
   for testing more than for design, and the course moved RTL design back to
   Verilog. Read with HLS's adoption history, this supports the ladder:
   - teams adopt better testing first (our verification-engineers-first
     sequencing);
   - the design language has to stay close to what designers already write
     (the RTL subset).
5. **What to avoid:**
   - hashed, per-parameter module names;
   - a single-clock model;
   - performance that depends on a special runtime;
   - stalling once the founding group moves on. PyMTL3 is in maintenance
     mode, which is the longevity question the project-architecture split
     must answer.
6. **The real gap is synthesis above RTL.** PyMTL3 shows that multi-level
   modeling alone does not reach designers: refinement stays manual. fw-hdl's
   claim that every rung lowers to RTL (SPL with inferred FSMs, MLS/HLS through
   an engine) is the part with no precedent. The roadmap should make that
   story concrete early.

## Sources

1. Lockhart, Zibrat, Batten, *PyMTL: A Unified Framework for Vertically
   Integrated Computer Architecture Research*, MICRO 2014.
   https://www.csl.cornell.edu/~cbatten/pdfs/lockhart-pymtl-micro2014.pdf
2. Jiang et al., *PyMTL3: A Python Framework for Open-Source Hardware
   Modeling, Generation, Simulation, and Verification*, IEEE Micro 2020.
   https://www.csl.cornell.edu/~cbatten/pdfs/jiang-pymtl3-ieeemicro2020.pdf
3. PyMTL3 docs, Verilog import.
   https://pymtl3.readthedocs.io/en/latest/ref/passes-import-intro.html ;
   source https://github.com/pymtl/pymtl3
4. Batten, PyMTL3 talk at Jane Street, May 2025 ("Six Lessons Learned").
   https://www.csl.cornell.edu/~cbatten/pdfs/batten-pymtl3-jsxc2025.pdf
5. Jiang et al., *Mamba: Closing the Performance Gap in Productive Hardware
   Development Frameworks*, DAC 2018.
   https://www.csl.cornell.edu/~cbatten/pdfs/jiang-mamba-dac2018.pdf
6. Jiang et al., *PyH2: Using PyMTL3 to Create Productive and Open-Source
   Hardware Testing Methodologies*, IEEE D&T 2021.
7. Cornell ECE 4750, Verilog section.
   https://cornell-ece4750.github.io/ece4750-sec02-verilog/

Not verified: industry users of PyMTL3; import of SV interfaces or type
parameters; any Batten-group successor to PyMTL3.
