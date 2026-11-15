# Architecture-to-design handoff and performance correlation

Researched 2026-11-15. This note backs the architecture-teams entry in
`../pitch.md` (*Who this is for*, item 3).

Confidence tags:
- **[P]** a primary source, read directly;
- **[S]** a secondary source (trade press, vendor material, job postings);
- **[U]** unverified.

## Summary

| Practice | Prevalence | Pain points |
|---|---|---|
| Spreadsheets and analytical models | Very common at the earliest stage [S] | Miss contention and dynamic effects; can never be run against RTL |
| SystemC TLM approximately-timed (in-house, Synopsys Platform Architect) | Common for SoC and interconnect [P/S] | Written independently of RTL; correlation is a "huge effort"; mixed TLM+RTL simulation runs at 64 transactions/s, against 50k for TLM alone |
| In-house C++ trace-driven CPU models | Standard at CPU vendors [P] | Labour-intensive; common-mode errors; each team builds its own correlation infrastructure |
| gem5 and research simulators | Research, plus some industry use [S] | 5–30% error against hardware |
| Python analytical or simulation models (ML accelerators) | Emerging; listed beside C++ in job postings [S] | No public data on carrying them into RTL |
| Specification document, then hand-written RTL | The default [P] | Specification churn and misreading; specification is a leading root cause of respins |
| Architecture model as the UVM reference (via DPI) | Done, but usually as a separately written predictor [S] | Ownership; performance and functional models kept apart |
| Shared model and implementation through HLS (MatchLib) | Niche but proven [S] | Needs an HLS flow and C++ skills; tied to one vendor |

## Key evidence

### The handoff is a document; models are written independently

**Intel (Zhou et al., DVCon) [P][1]:**
- "most of the implementation starts with hand written RTL."
- TLM models and RTL "are created independently by different teams."
- "Correlating RTL with TLM model is usually a huge effort… almost no
  automation tools."
- What they built: the same SystemC traffic drives the TLM model and the RTL,
  and analysis ports feed a correlation checker. RTL designers found it useful
  for quick unit tests.

**ESL refinement did not reach the mainstream [S][2].** "ESL Flow is Dead"
(2016): models stay "separated islands," and adopting the flow "require[s] a
process change within the user companies."

### Correlation is labour-intensive, and uncorrelated models are wrong

**Ampere, four core generations, 2026 [P][3]:**
- Method: a trace-driven C++/SystemC model compared with RTL on the ratio
  IPC_RTL / IPC_model.
- Target: 90% of tests within ±10%, up from 80% in earlier generations.
- Infrastructure: unified event streams and daily dashboards.
- Features are made configurable in both the model and the RTL, and enabled
  one by one as the RTL is ready.
- Bugs were found in both the RTL and the model.
- Warns of "common-mode errors where the same bug may exist in both."

**Black & Shen, IBM PowerPC 604 (IEEE Computer 1998) [P][4]:** a model
validated only by inspection matched 51.0% of instruction tests and 30.6% of
pipeline tests. After systematic calibration it matched 95.9% and 75.4%.

**Rotithor (Intel) [P][5]:**
- The high-level model "gets progressively more accurate… as RTL is coded and
  correlated."
- It then "serves as a reference in later stages."

**Tooling [P].** No general commercial correlation tool was found. Teams build
their own.

### Shared structure makes correlation cheap

**NVIDIA MatchLib + Catapult [S][6]:**
- The SystemC model is both the performance model and the synthesis source.
- Correlation: within about 3% of RTL cycle count, simulating about 30× faster
  than RTL.
- Productivity: RC18 was built by "fewer than ten engineers in six months";
  a 10× productivity claim.

**Arm [S][7].** Arm stopped writing cycle models by hand around 2008 and
derived them from RTL (Carbon). FireSim avoids correlation by simulating the
RTL itself on FPGAs. In both, the second model was too expensive to keep in
sync.

**Intel ROHD (WOSET 2022) [P][8]:**
- An IP team built "a microarchitectural model… for performance analysis…
  designed… to enable reuse of components for unit-level verification…
  cycle approximate where convenient and cycle accurate at critical hardware
  interfaces."
- This is the closest precedent to the fw-hdl architect story, written in
  Dart.

**Interface-preserving refinement [S][9].** SystemVerilog interfaces allow
refining one module from transaction level to RTL without disturbing the rest
(Doulos, SNUG 2008). Latency-insensitive channels serve the same purpose in
MatchLib and Bluespec.

### Python among architects

The evidence is thin.
- Job postings list "C++/SystemC/Python" for performance modelling, with Python
  mostly used for analytical models and analysis [S].
- NVIDIA's postings list only C++/SystemC [S].
- No survey covers architecture modelling languages. The Wilson study tracks
  Python only for testbenches.

### Specifications and respins

- First-silicon success fell to 14% in 2024 [P][10].
- Changing or incomplete specifications are a leading root cause of
  functional flaws [P]. The percentages are in figures we could not extract;
  quote them from the report.
- "70% of respins are design errors due to changes in the spec" (Synopsys)
  [S].

## Supports the architect pitch

1. **Independent models are the root cause of the correlation effort.** Intel
   names it directly; a shared semantic model attacks it.
2. **Unchecked models are badly wrong,** and even mature correlation targets
   only ±10% on 90% of tests.
3. **Shared structure makes correlation close to automatic:** MatchLib within
   3%; Arm and FireSim reached the same answer from the RTL side.
4. **Intel's "same traffic into model and RTL" checker was useful but built by
   hand.** Protocol kits and the factory swap make it standard.
5. **Interface-preserving, block-by-block refinement is established practice,**
   and ROHD's micro-architectural model is a near-exact precedent.
6. **Specification problems drive respins.** An executable model that becomes
   the design's starting point addresses that.

## Against, and risks

1. **ESL top-down refinement has failed before.** It required process change,
   and the industry has heard this pitch since about 2005.
2. **Common-mode errors.** A reference model that shares structure with the
   RTL can share its bugs. Verification teams value independence.
3. **Performance and functional models are kept separate on purpose** (Ampere,
   Intel).
4. **Mixed-level simulation speed.** Intel measured 64 transactions/s with RTL
   in the loop, against 50k for TLM alone.
5. **Python is not the incumbent language** for performance models; C++ and
   SystemC are. Python may be too slow for CPU-class trace workloads.
6. **Internal timing correlation stays manual.** The successful precedents
   share code through HLS or derive the model from RTL. Where internals are
   hand-written RTL behind stable interfaces, only the interface behaviour is
   shared.
7. **Ownership after handoff is undocumented.**

## Interview questions

1. How often are architecture models discarded rather than reused, by company
   type (CPU, SoC, ML startup)?
2. How much effort goes into correlation, in headcount or share of schedule?
3. How many respins or late fixes are caused by performance shortfalls?
4. Would architects accept design-oriented semantics (ports, channels,
   clocking) in their models?
5. Would verification leads accept an architect-derived reference model,
   given the common-mode concern?
6. How much Python do ML-accelerator architects use, and how fast must their
   models run?
7. Who owns the model once RTL starts, and how do designers' changes flow back
   to the architects?

## Sources

1. Zhou et al., *Bridging the Gap Between TLM-2.0 AT Models and RTL*, DVCon. https://dvcon-proceedings.org/wp-content/uploads/bridging-the-gap-between-tlm-2-0-at-models-and-rtl-experiments-and-opportunities.pdf
2. Bailey, *ESL Flow is Dead*, SemiEngineering 2016. https://semiengineering.com/esl-flow-is-dead/
3. Ampere, Panthera performance model and RTL correlation, arXiv 2026. https://arxiv.org/html/2608.19300
4. Black & Shen, *Calibration of Microprocessor Performance Models*, IEEE Computer 1998. https://users.ece.utexas.edu/~ljohn/teaching/382m-15/reading/black.pdf
5. Rotithor, performance assurance at Intel. https://arxiv.org/pdf/1304.3767
6. Khailany et al., MatchLib, DAC 2018. https://ctorng.com/pdfs/khailany-nvidia-matchlib-dac2018.pdf ; Venkatesan et al., Hot Chips 2019. https://people.eecs.berkeley.edu/~ysshao/assets/papers/venkatesan2019-hotchips.pdf ; Siemens/DVCon HLS performance validation. https://dvcon-proceedings.org/wp-content/uploads/early-design-and-validation-of-an-ai-accelerators-system-level-performance-using-an-hls-design-methodology.pdf
7. Arm Cycle Models end of life. https://community.arm.com/arm-community-blogs/b/soc-design-and-simulation-blog/posts/ip-exchange-and-cycle-models-end-of-life-update ; FireSim https://github.com/firesim/firesim
8. Korbel, *ROHD*, WOSET 2022. https://woset-workshop.github.io/PDFs/2022/19-Korbel-paper.pdf
9. Doulos, *Seamless refinement from transaction level to RTL using SystemVerilog interfaces*. https://www.doulos.com/knowhow/systemverilog/seamless-refinement-from-transaction-level-to-rtl-using-systemverilog-interfaces/
10. Siemens / Wilson Research Group, 2024 IC/ASIC verification trend report. https://static.sw.cdn.siemens.com/siemens-disw-assets/public/1NyfMZJ3nuPhMGQCGFDITG/en-US/ic-asic-functional-verification-trend-report-wp-86424-d3.pdf
11. Others: gem5 accuracy https://www.researchgate.net/publication/377680553_Performance_Error_Evaluation_of_gem5_Simulator_for_ARM_Server ; Timeloop https://accelergy.mit.edu/timeloop.pdf ; Mirabilis https://www.mirabilisdesign.com/visualsim/ ; ESL flow https://semiengineering.com/first-time-silicon-success-plummets/
