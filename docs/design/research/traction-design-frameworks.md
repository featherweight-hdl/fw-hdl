# Traction of alternative hardware-design frameworks

Researched 2026-11-15. This note backs *Traction of prior approaches* in
`../pitch.md`. PyMTL3 has its own note, `pymtl3.md`. GitHub figures were taken
on 2026-11-15.

Confidence marks:
- **[P]** primary source;
- **[S]** secondary source (practitioner threads, summaries);
- **[U]** unverified, or our inference.

## Summary

| Tool | Traction | Key users | Main reasons |
|---|---|---|---|
| Chisel / FIRRTL / CIRCT | High in RISC-V, niche elsewhere | SiFive, Google Edge TPU (2018), XiangShan (11 tapeouts), Berkeley | Owned by companies that ship silicon. Held back by Scala, generated SV that is hard to read for LEC and ECO, compiler debt, a weak verification story |
| SpinalHDL | Niche (FPGA) | VexRiscv users, Elitestek, Tiempo, DatenLord | One killer IP consumed as plain Verilog; one maintainer |
| Amaranth / Migen / LiteX | Niche (FPGA, open source) | Great Scott Gadgets, Glasgow, ChipFlow, LiteX | Python and a good FPGA platform layer; fragile governance and funding |
| MyHDL | Stalled | none notable | One maintainer; overtaken by Amaranth (design) and cocotb (test) |
| Clash | Niche | QBayLogic clients, Google bittide | Kept alive by a consultancy; Haskell limits who can be hired |
| Hardcaml | Niche (one company) | Jane Street | An OCaml company; tests and CI in the host language |
| Bluespec | Niche / academic | MIT (through Minispec), Bluespec's RISC-V cores | Rule semantics unfamiliar to RTL designers; proprietary to one vendor for about 17 years |
| ROHD (Intel) | Niche, early | Intel teams (none named) | Gradual interop with SV; Dart is unfamiliar to hardware engineers |
| Veryl | Niche, growing | PEZY Computing (50k lines alongside 6M lines of SV) | SV output that maps 1:1 to the source and is ECO-friendly; young |
| SystemC for RTL | Stalled at RTL (high as HLS input) | HLS users (ST, NVIDIA via Catapult and Stratus) | Its value was only above RTL; at RTL it offered no advantage over SV |
| OSSS | Academic, dead | OFFIS EU projects | Grant-funded, with no vendor and no flagship IP |
| PyMTL3 | Academic, maintenance mode | Cornell | Survived as a test harness only |

## Key evidence

**Chisel: adoption.**
- SiFive says firtool is "production quality for SiFive flows" [P][1].
- XiangShan reports 11 tapeouts and has 7.4k stars, more than Chisel's own
  4.8k [P][2].
- Outside SiFive, professional use is "rare". Foundries and clients push teams
  back to SV [S][3].

**Chisel: the DVCon 2022 Quasar study [P][4].** This is a logically equivalent
Chisel version of the SweRV-EL2 core:
- 35–40% less code than the SV original, with equal PPA;
- LEC needed **15,000+ manual "user matches"** because signals were renamed;
- conclusion: converting to Verilog for verification "is the major
  bottleneck."

**Chisel: what its maintainers and critics say.**
- SiFive's Jack Koenig: verification is "3x to 10x harder than design" [P][5].
- Intel's ROHD paper says Chisel "treats verification as second class and
  generated hardware is netlist-like" [P][6].

**Veryl's rationale [P][7].**
- Embedded DSLs produce "voluminous Verilog code that has significantly
  different semantics from the original DSL."
- ASIC timing closure and ECO "frequently necessitate partial modifications
  to the Verilog code."
- This is the clearest primary statement of the generated-RTL problem.

**Hardcaml [P][8].** Andy Ray's account:
- the win is testing ("I can write my test benches in OCaml");
- Verilog "does not have a software core";
- Hardcaml plugs into the firm's existing build, expect tests and CI.

**Bluespec [P][9][S][10].**
- Open-sourced in 2020 after about 20 years as a commercial product.
- The company has since pivoted to selling RISC-V cores.
- MIT's course now teaches Minispec, a simplified language, because full
  Bluespec "takes a lot of time" to explain.

**OSSS [P][11].**
- Object-oriented SystemC with method-based communication, synthesized to RTL
  by FOSSY.
- Used in EU research projects; no use after the grants ended.
- The closest precedent for synthesizing object-oriented hardware.

**SystemC [P][12].** The 2010 case for SystemC was entirely about HLS. At RTL,
SystemC never displaced Verilog.

## Patterns

1. **A flagship owner that ships product.**
   - Every tool with traction has one: SiFive and XiangShan (Chisel), Jane
     Street (Hardcaml), VexRiscv (SpinalHDL), QBayLogic (Clash).
   - We found no tool that spread on merit alone to companies with no prior
     tie to it.
2. **Traction follows culture.** Teams adopt the host language they already
   speak: OCaml at Jane Street, Scala among Berkeley alumni. Mainstream SV
   teams, their clients and their vendors veto new host languages.
3. **The generated Verilog is the weak point.** Every source raises the same
   problems:
   - LEC name matching;
   - ECO;
   - waveform debug (tools like Tywaves exist only to restore source-level
     types);
   - second-class tool support.
4. **Verification decides productivity.** Design-side gains (35–80% fewer
   lines) do not move teams if verification gets harder. Hardcaml's stated win
   is testbenches.
5. **Adoption must be gradual.** Tools that need a whole-design switch stall.
   Tools that sit beside SV get further: Veryl, ROHD's stated goal, and
   VexRiscv delivered as IP.
6. **Higher-level semantics stay niche without a vendor.**
   - Bluespec rules and OSSS objects stayed niche.
   - HLS succeeded because vendors (Catapult, Stratus) took on the signoff
     burden.
7. **Projects with one maintainer or grant funding stall:** MyHDL and OSSS,
   and partly SpinalHDL and Amaranth.

## Implications for the fw-hdl story

**Strengths:**
- An SV host avoids the biggest barriers every embedded DSL hit: a new
  language to learn, a hiring pool, and vetoes from clients and vendors.
- The same choice makes commercial simulators and UVM available directly.
- Wrapping RTL plus an RTL subset that sits beside existing Verilog is the
  gradual path that patterns 4 and 5 call for.

**Where the risk moves:**
- **Readable lowering is mandatory.** Names and module structure must map 1:1
  wherever possible, including at the inferred-FSM and HLS levels.
- **The Bluespec/OSSS trap.** Higher-level semantics such as inferred FSMs
  need timing that is predictable, explainable and visible in waveforms.
- **Verification has to lead the story,** as Hardcaml and ROHD show.
- **A flagship and a maintainer base are the largest non-technical risk.**
  - Every tool that got traction had an owner shipping product.
  - A credible open IP built with fw-hdl (the VexRiscv model) may be worth
    more than features.
  - The OSSS precedent shows the cost of a tool that is only grant-funded.
- **Class support in simulators must be checked.** Questa, Xcelium, VCS,
  Verilator and xsim each support the SV class subset differently. Synthesis
  never sees classes.

## Sources

1. CIRCT talk, LLVM Dev Mtg 2021. https://llvm.org/devmtg/2021-11/slides/2021-CIRCT-LiftingHardwareDevOutOfThe20thCentury.pdf
2. XiangShan, Hot Chips 2024. https://hc2024.hotchips.org/assets/program/conference/day2/29_HC2024.ChineseAcademy.XiangShan.Kaifan.final.pdf
3. HN threads (practitioners, secondary). https://news.ycombinator.com/item?id=44292917 ; https://news.ycombinator.com/item?id=42793580 ; https://news.ycombinator.com/item?id=25645356
4. *A Comparative Study of CHISEL and SystemVerilog Based on Logical Equivalent SweRV-EL2 RISC-V Core*, DVCon 2022. https://dvcon-proceedings.org/wp-content/uploads/A-Comparative-Study-of-CHISEL-and-SystemVerilog-Based-on-Logical-Equivalent-SweRV-EL2-RISC-V-Core.pdf
5. CHIPS Alliance, *Spotlight: Jack Koenig*, Dec 2025. https://www.chipsalliance.org/news/spotlight-jack-koenig/
6. Korbel, *ROHD*, WOSET 2022. https://woset-workshop.github.io/PDFs/2022/19-Korbel-paper.pdf
7. Veryl, arXiv 2411.12983. https://arxiv.org/pdf/2411.12983 ; OSCAR 2025 slides. https://veryl-lang.org/docs/veryl_oscar2025.pdf
8. *Programmable Hardware*, Signals and Threads, Sep 2020. https://signalsandthreads.com/programmable-hardware/
9. Bluespec open-source announcement, 2020. https://bluespec.com/2020/09/06/bluespec-inc-to-open-source-its-proven-bsv-high-level-hdl-tools/ ; WOSET 2021. https://woset-workshop.github.io/PDFs/2021/a02.pdf
10. MIT 6.191 resources (Minispec). https://6191.mit.edu/spring26/resources
11. OFFIS, OSSS. https://www.offis.de/en/offis/publication/csp-with-synthesisable-systemc-and-osss.html
12. Accellera, SystemC for IC design. https://www.accellera.org/resources/articles/icdesigntrans
13. Others: QBayLogic https://qbaylogic.com/creators-clash-compiler/ ; bittide https://arxiv.org/pdf/2503.05033 ; LUNA https://github.com/greatscottgadgets/luna ; ChipFlow https://www.fuel.ventures/chipflow-raises-1-2m-in-pre-seed-funding ; Jane Street https://blog.janestreet.com/protocol-emulator-asic-competition/

Not verified: Esperanto's or Intel's use of Chisel; any named team that moved
from Chisel back to SV; a Bluespec retrospective on its limited adoption.
