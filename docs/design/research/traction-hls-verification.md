# Traction of HLS and verification-side methodologies

Researched 2026-11-15. This note backs *Traction of prior approaches* in
`../pitch.md`. Each claim is marked:
- **[P]** primary source;
- **[S]** secondary source;
- **[U]** unverified.

The Wilson survey percentages come from secondary summaries; the original
charts are images.

## Summary

| Approach | Traction | Who | Why / why not |
|---|---|---|---|
| Commercial C++ HLS (Catapult, Stratus) | Real but niche: video/DSP, ML, crypto | Google, NVIDIA, Qualcomm, ST, Sony | Large wins on algorithmic blocks, mostly from verification. Loses on quality of results (QoR), engineering change orders (ECOs), debug, interface timing and culture. |
| FPGA HLS (Vitis, Intel) | Wide in academia; Intel exited | FPGA and accelerator developers | Free and bundled with the vendor tools. Software engineers lack hardware skills, and vendors are consolidating. |
| Synopsys HLS | Exited twice (Behavioral Compiler 2004, Synphony C) | — | Not core business. |
| Google XLS | Very active development, few public users | Google, Antmicro | Pre-1.0, a new language (DSLX), no confirmed tapeouts. |
| SystemC TLM | Standard for virtual platforms | Every large vendor and SoC company | Serves software and architecture teams; never had to replace RTL. |
| SystemC/C++ as a design language | Failed to replace RTL; survives as HLS input | Catapult/Stratus users | "Too far from RTL." |
| MatchLib / object-oriented HLS | Strong showcase results, small community | NVIDIA Research, some tapeouts | Productivity claims partly hedged; needs Catapult. |
| UVM | About 80% of ASIC projects | Verification engineers | A standard that runs on existing SV simulators. |
| cocotb / Python | 27% use Python in verification; 11% use a Python methodology; rising | Small teams, FPGA, startups | Python, free, runs on existing simulators. |
| PSS (Portable Stimulus) | Slow | Large SoC companies | New language, no bottom-up content, weak tooling. |
| Formal apps | 32% of projects, fastest-growing | Designers and verification engineers | Push-button; little expertise needed. |

## Key evidence

### HLS where teams commit

**Google's VCU video codec ASIC.**
- From the Hot Chips 2021 talk [P][1]:
  - The team has used HLS "for almost 10 years."
  - 5–10x less code than RTL.
  - "99% of the functional bugs found in C++ before running any RTL
    simulation."
- From the ASPLOS 2021 paper [P][2]:
  - "7-8 orders of magnitude" more test throughput than RTL simulation.
  - HLS was chosen because data-center ASICs have "somewhat relaxed power and
    die-area constraints."
  - In-house tool **Taffel** generated the C++ and Verilog fabric that
    connected HLS leaf blocks. HLS was used for leaf blocks; the composition
    and the interoperation with Verilog had to be built by hand.

**NVIDIA MatchLib (DAC 2018) [P][3].**
- 2K–20K gates per engineer-day.
- QoR within ±10% on datapath blocks.
- RTL simulation was used mainly for "scaffolding around HLS-generated
  blocks."
- The paper hedges: "future work is needed to study quantitative
  improvements."

**Vendor-published success stories [P, vendor][4].**
- NVIDIA: 50% less design time, 40% less total time, 1000x more tests.
- Google WebM: 50% faster.

### Why HLS stays niche

**Lahti & Hämäläinen, IEEE Access 2025 [P][5].**
- HLS saves 50–75% of the effort.
- Hand-written RTL still wins slightly on QoR.
- Barriers:
  - verifying the generated RTL;
  - incremental changes and ECOs;
  - no standard across tools;
  - too few trained engineers.
- The number of commercial HLS tools fell from 13 to 9 between their 2016 and
  2020 surveys.

**Interface timing [S][6].**
- Bowyer (Mentor): "scheduling would move something one cycle later, and
  suddenly it's broken."
- Wakabayashi (NEC): code that gives good results and code needed for
  simulation are "often not compatible."

**HLS still requires hardware skill [S][7].** Siemens: "Not anyone can do
hardware design using HLS."

**Vendors leaving [P][8][S][9].**
- Intel discontinued its HLS compiler, then dropped FPGA support from oneAPI
  in 2025.
- Synopsys has exited HLS twice.

### Verification-side adoption

**UVM.** About 80% of ASIC projects [S][10].

**Python and cocotb.**
- 27% of ASIC projects use Python in verification; only 11% use a Python
  methodology (Wilson 2024) [S][11].
- cocotb 2023 user survey [P][12]:
  - about 60% are mainly industry users;
  - ASIC use rose from 26% to 42% since 2020;
  - teams are usually 10 people or fewer;
  - people choose it because "it is Python," it is free, and it runs on
    existing simulators.
- cocotb is downloaded about 1M times a month from PyPI (inflated by CI).

**PSS.** Adoption is slow [S][13]. Reasons given:
- "no bottom-up content to leverage" (Siemens);
- missing tools and debug (Synopsys);
- new languages "require many years" (Breker).

**Formal.** Property checking is used on 35% of projects and formal apps on
32% [S]. Apps grow faster: 8.7% CAGR versus 5.8% for property checking. Wilson
credits tools that "democratize formal… accessible to non-experts" [P][10].

**Designers verify.** Designers spend 49% of their time on verification. The
verification workforce grows at 3% a year versus 2.4% for designers.
First-silicon success was 14% in 2024 and 5% in 2026 [P][14].

**Lightweight frameworks.** In open-source repositories, lightweight unit-test
frameworks (VUnit, cocotb) are more common than UVM [P][11].

**No metric found.** No survey measures method- or transaction-level designer
testing.

## Patterns

**What succeeded:**
- It runs on the simulator and language teams already use: UVM on SV, cocotb
  through VPI, SVA, TLM-2.0 inside C++.
- It can be adopted one block or one test at a time. At Google, HLS covered
  leaf blocks inside Verilog fabric.
- It fills a gap without displacing the RTL signoff flow (virtual platforms,
  formal apps).
- It needs little expertise; formal apps outgrew property checking.
- The payoff shows up in verification: bugs found earlier, far more tests.

**What failed:**
- A new language with no bottom-up content (PSS, DSLX, SystemC as an RTL
  language).
- A tool tied to one vendor, with no standard.
- Generated RTL that designers can't read or patch.
- Interface timing that designers can't predict.

## Evidence on our two hypotheses

### H1: HLS is too big a jump for designers. Partly supported; reframe.

**Supports it:**
- Culture, debug, ECOs and readability are recurring barriers.
- HLS still needs RTL expertise.
- Scheduling breaks interface timing.
- Vendors have exited.

**Undermines it:** where teams commit to HLS, it works (Google's ten years,
50–75% less effort).

**Reading:** the barrier is fit and integration, not abstraction distance.
- *Fit:* HLS suits algorithmic blocks and data-center QoR budgets.
- *Integration:* Google had to build Taffel to connect HLS blocks with Verilog,
  and MatchLib exists to give HLS RTL-like structure: explicit,
  latency-insensitive channels and modules.

Both are the middle of the fw-hdl ladder. Pitch "use the right level per block,
all in one interoperating design," not "HLS is too hard."

### H2: verification engineers adopt first. Supported, with a correction.

**Supports it:**
- New languages enter through the testbench (Python at 27%, while RTL stays
  SV).
- SystemC succeeded on the modeling side and failed on the design side.
- The best-quantified HLS benefits are verification benefits.

**Correction:**
- Verification-side adoption is not automatic: PSS is slow.
- The likely first adopters are **designers writing block tests and formal
  checks**, who already spend half their time verifying and prefer light
  frameworks (VUnit, cocotb, formal apps), rather than UVM teams.
- The wedge is tests and properties on method interfaces that run on wrapped
  existing RTL, coexisting with UVM rather than replacing it.

**Gap:** no survey covers method-level designer testing. User interviews would
close it.

## Sources

1. Kuusela, Google VCU, Hot Chips 2021. https://hc33.hotchips.org/assets/program/conference/day2/HC2021.Google.AkiKuusela.v03.pdf
2. Ranganathan et al., *Warehouse-scale video acceleration*, ASPLOS 2021. https://gwern.net/doc/cs/hardware/2021-ranganathan.pdf
3. Khailany et al., *A Modular Digital VLSI Flow for High-Productivity SoC Design*, DAC 2018. https://ctorng.com/pdfs/khailany-nvidia-matchlib-dac2018.pdf
4. Siemens white papers: NVIDIA https://resources.sw.siemens.com/en-US/white-paper-working-smarter-not-harder-nvidia-closes-design-complexity-gap-with-hls/ ; Google WebM https://resources.sw.siemens.com/en-US/white-paper-google-develops-webm-video-decompression-hardware-ip-using-high-level/
5. Lahti & Hämäläinen, *High-Level Synthesis for FPGAs: A Hardware Engineer's Perspective*, IEEE Access 2025. https://cris.tuni.fi/ws/portalfiles/portal/138717284/High-Level_Synthesis_for_FPGAsA_Hardware_Engineers_Perspective.pdf ; Lahti et al., *Are we there yet?*, TCAD 2019. https://researchportal.tuni.fi/en/publications/are-we-there-yet-a-study-on-the-state-of-high-level-synthesis/
6. *The Evolution of High-Level Synthesis*, SemiEngineering. https://semiengineering.com/the-evolution-of-high-level-synthesis/
7. *High-Level Synthesis: It's Still Hardware Design*, SemiEngineering. https://semiengineering.com/high-level-synthesis-its-still-hardware-design/
8. Intel, discontinuation of the HLS Compiler. https://www.intel.com/content/www/us/en/docs/programmable/683456/24-1/discontinuation-of-the.html
9. DeepChip on Synphony C. http://www.deepchip.com/items/0552-01.html
10. 2024 Wilson Research Group IC/ASIC verification study. https://verificationacademy.com/topics/planning-measurement-and-analysis/wrg-industry-data-and-trends/2024-siemens-eda-and-wilson-research-group-ic-asic-functional-verification-trend-report/
11. Asplund, verification practices on GitHub. https://larsasplund.github.io/github-facts/verification-practices.html
12. cocotb user survey 2023. https://www.cocotb.org/2023/06/17/user-survey-2023.html
13. *What Happened to Portable Stimulus?*, SemiEngineering. https://semiengineering.com/what-happened-to-portable-stimulus/
14. 2026 Wilson Research Group verification study. https://verificationacademy.com/topics/planning-measurement-and-analysis/2026-siemens-eda-and-wilson-research-group-functional-verification-study/
15. Others: XLS/Antmicro https://antmicro.com/blog/2023/09/accelerating-digital-block-design-with-googles-xls ; TLM-2.0 https://www.electronicdesign.com/news/products/article/21789944/tlm-20-apis-open-systemc-to-mainstream-virtual-platform-adoption ; DARPA CRAFT https://eri-summit.darpa.mil/docs/ERIPoster_Designs_CRAFT_NVIDIA.pdf
