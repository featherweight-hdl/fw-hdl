# The verification IP market (AMBA focus)

Researched 2026-11-15. This note backs `../wedge-assessment.md` §4a
(verification IP as the wedge).

Confidence tags:
- **[P]** a primary source, read directly;
- **[S]** a secondary source;
- **[U]** unverified (several vendor pages blocked fetching, and the web
  search budget was exhausted, so some claims come from background knowledge);
- **[I]** our own inference.

## Summary

| Question | Finding | Conf. |
|---|---|---|
| VIP market size | About $0.5–1B a year; analyst figures are poorly sourced | U/I |
| Do the big three sell simulation, formal and emulation versions separately? | Yes, as separate products | P (Synopsys) / U |
| Does any vendor market one source across all three? | None found | I |
| Can Verilator run encrypted VIP? | No | P |
| Is there a push for UVM on Verilator? | Yes: CHIPS Alliance SV Tools project (Google, Antmicro), launched Mar 2026 | P |
| Open AXI4 / Lite / Stream / APB | Plentiful, fragmented, each serving one target | P |
| Open ACE / CHI | Essentially none | P |
| AMBA licensing | Royalty-free | P |

## Key evidence

### Market structure

- **Size.** Report-mill figures put VIP at about $0.5–1B a year, growing
  7–10% [U]. They are unreliable. Our estimate: a few percent of the EDA and IP
  market, with Synopsys and Cadence holding more than 60% [I].
- **Synopsys VC VIP:** "100% native SystemVerilog/UVM", with source-code test
  suites sold separately. AXI coverage runs through AXI5 and issues J/K/L;
  CHI through issue H. Also ACE, AHB, APB, ATB, AXI-Stream [P].
- **Cadence:** simulation VIP, Assertion-Based VIP for Jasper, Accelerated VIP
  for Palladium, TripleCheck compliance suites [U; page blocked]. It acquired
  Oski (formal services) in 2021 [U].
- **Siemens:** acquired Avery in November 2022 and merged it into Questa VIP.
  Claims "60+ standard protocols" and "20+ compliance test suites" [P].
- **Independents:**
  - Truechip: PCIe 6/7, CXL, UCIe, DDR, AMBA [P].
  - SmartDV: simulation VIP, assertion IP and synthesizable transactors
    across hundreds of protocols; reportedly now owned by Mirafra [U].
- **Arm** keeps AMBA royalty-free and leaves VIP to partners [P]. It has
  shipped SVA protocol checkers (BP063) in the past [U].
- **Consolidation:**
  - Siemens bought Avery (2022) [P].
  - Cadence bought Oski (2021) [U].
  - Synopsys bought Imperas (2023) [U].
  - Mirafra reportedly bought SmartDV [U].

  Independent VIP houses tend to be absorbed rather than stand alone [I].

### Pricing

- No price lists are published. Folklore puts mainstream AMBA at roughly
  $10–50k per licence per year, and CHI, PCIe and CXL at several times that
  [U].
- VIP is usually a line item in the big three's multi-year enterprise
  agreements [U]. Inside those accounts, third-party AXI VIP competes with a
  price that looks "already paid" [I].

### One product or three?

- **Synopsys:** VC VIP, VC Formal assertion IP and ZeBu transactors are
  separate products. No shared source is claimed [P; formal and ZeBu details
  U].
- **Cadence:** separate simulation, assertion-based and accelerated SKUs [U].
- **Siemens:** Questa VIP, Avery VIP and Veloce transactors are separate [U].
- **SmartDV** comes closest: per protocol it sells simulation VIP, assertion IP
  and synthesizable transactors, reportedly generated from internal tooling
  [U].
- **No vendor offers "one source, three targets" as a guarantee the buyer
  can see [I].**

### Encryption and Verilator

- Commercial VIP normally ships encrypted (IEEE 1735) or compiled [U]. AMD's
  AXI VIP is free with Vivado, but encrypted and tied to Vivado-supported
  simulators [U].
- **Verilator cannot use encrypted code [P]:** "Open-source simulators like
  Verilator cannot use encrypted RTL (i.e. IEEE P1735)." Its `--protect-lib`
  covers design blocks shipped as a DPI library, not class-based UVM VIP.
- **UVM on Verilator has institutional backing [P]:**
  - the CHIPS Alliance SV Tools project (launched 30 Mar 2026, with Google and
    Antmicro) aims at "enabling UVM testbenches in Verilator";
  - Antmicro reports UVM 2017 running upstream, plus four-state support
    (Jul 2026), constrained random (Nov 2026) and RISCV-DV (Nov 2026);
  - chipsalliance/uvm-verilator says support is "still in development".
- **What open flows use for AXI today:** cocotbext-axi, PULP's AXI test
  classes, ZipCPU's formal properties and verilaxi. OpenTitan has no AXI agent
  (TL-UL only) [P].

### Open-source landscape (GitHub, 15 Nov 2026) [P]

| Project | Stars | Licence | Notes |
|---|---|---|---|
| pulp-platform/axi | 1758 | SHL-0.51 | Simulation-only random master/slave, drivers, scoreboard |
| ZipCPU/wb2axip | 714 | Apache-2.0 | Full AXI4, AXI-Lite and APB formal properties |
| taichi-ishitani/tvip-axi | 485 | Apache-2.0 | UVM AXI4/Lite on VCS, Xcelium, DSim; not Verilator |
| alexforencich/cocotbext-axi | 370 | MIT | AXI4, Lite, Stream, APB (APB slave only) |
| nelsoncsc/verilaxi | 31 | MIT | Task-based AXI BFMs and SVA on Verilator |
| featherweight-vip org | max 3 | Apache-2.0 | 12 repos (wb, spi, uart, i2c, gpio, rvfi, riscv, chi, core); no AXI yet |
| ACE / CHI | — | — | No credible open option |

**A cautionary precedent [P].** ZipCPU's full AXI4 formal properties were sold
as part of the SymbioticEDA Suite in 2019. They are now Apache-2.0, so a small
vendor's paid formal AXI VIP did not last as a product [I].

### Buyer pain points

Forums were unreachable, so these are from background knowledge [U]:
- cost per protocol per seat;
- encryption blocks debugging, so users can't step into or fix the BFM;
- slow vendor fixes;
- formal and emulation versions bought separately;
- lock-in to one simulator;
- a steep configuration learning curve.

Wilson 2026: first-silicon success fell to 5% [P]. Its VIP-usage figures were
not read [U].

### Formal assertion IP

- Jasper and VC Formal assertion IP are add-ons to formal licences [U].
- Axiomise sells services, training and apps (formalISA), with no AXI
  assertion IP listed [P].
- Buyers are formal teams at large companies that already own Jasper or VC
  Formal [I].
- Open alternative: ZipCPU's properties [P].

### Open-source EDA business models

| Model | Example | Conf. |
|---|---|---|
| Services, funded by sponsors | Antmicro (Verilator) | P/I |
| Commercial build of open tools, plus support | YosysHQ Tabby CAD Suite | P |
| Sponsor-funded, no product revenue | cocotb | U |
| Free tier plus paid models and test suites, then acquired | Imperas, bought by Synopsys | U |
| Closed library licensed to everyone | Verific | U |

What customers pay for:
- support and SLAs;
- compliance and coverage test suites, which Synopsys and Siemens already sell
  separately [P];
- early protocol revisions;
- qualification and indemnity;
- integration services.

### AMBA specifics

- "AMBA specifications are royalty free and platform independent" [P]. Many
  open AXI models exist with no visible enforcement [I]. Use the AMBA and AXI
  names nominatively, since they are Arm trademarks [I].
- AXI is at issue L, CHI at issue H [P]. The big three get pre-release specs
  through Arm partnerships, so a newcomer lags on new issues [I].
- Demand:
  - APB, AXI4-Lite, AXI4 and AXI-Stream are in every SoC and FPGA design;
  - AHB is used in microcontrollers;
  - ACE and CHI matter only in coherent CPU and server SoCs: high value, few
    buyers, tied to the big three [I].

## Supports the VIP wedge

1. **Verilator plus unencrypted VIP is a timely opening.** Encrypted VIP
   can't run on Verilator, and UVM-on-Verilator gained institutional backing
   in 2026. Only unencrypted SV VIP can follow that shift.
2. **Nobody offers one source for simulation, formal and emulation.** Buyers
   purchase three products today.
3. **Open options each serve one target:** PULP (simulation), ZipCPU (formal),
   cocotbext-axi (Python). Nothing spans UVM, cocotb, SVA and synthesizable.
4. **No licensing barrier** for AMBA.
5. **Buyers already pay separately for test suites,** so free core plus paid
   suites is a familiar model.

## Against, and risks

1. **Basic AMBA is a commodity.** It is effectively bundled at big-three
   accounts, and free options exist.
2. **A small vendor's paid formal AXI VIP failed** (ZipCPU/SymbioticEDA).
3. **The high-value protocols** (CHI, PCIe, CXL) need early spec access and
   large compliance suites, where incumbents are entrenched.
4. **UVM on Verilator is still in development,** and the open-flow market is
   small and price-sensitive today.
5. **featherweight-vip has negligible traction so far,** and no AXI repository.
6. **Independent VIP vendors get acquired** rather than standing alone.

## Gaps an open, plain-SV, multi-target AMBA VIP could fill

- One AXI, APB and AXI-Stream source yielding:
  - a UVM agent;
  - a cocotb API;
  - SVA checkers that run in both open (SBY) and commercial formal tools;
  - a synthesizable traffic generator.
- One spec and one set of assertions shared by the checker and the BFM across
  all targets.
- First-class Verilator and DSim support alongside VCS, Xcelium and Questa.
- Source users can debug and fix.
- AXI5 features (atomics, MTE, untranslated transactions) in open form.
- Later, an open ACE-Lite / CHI subset: empty territory today.
- FPGA hardware-in-the-loop traffic generation without an emulator licence.

## Business-model options

1. **Open core, plus paid compliance and coverage suites and support.**
   Precedents: Synopsys and Siemens test suites; YosysHQ Tabby.
2. **Open basic AMBA, paid premium protocols** (AXI5 extensions, ACE, CHI,
   later PCIe/CXL). Precedent: Imperas.
3. **Services-led:** integration, custom transactors, FPGA test setups.
   Precedents: Antmicro, Axiomise.
4. **Sponsored development** through CHIPS Alliance, with Google, lowRISC or
   FPGA vendors as funders. Precedent: SV Tools, Verilator UVM.
5. **A paid "qualified release"** with indemnity: a frozen version,
   regression-certified on each commercial simulator.

## Interview questions for VIP buyers

1. Which AMBA VIP do you use, on which simulators, and is it bought
   separately or inside an enterprise agreement?
2. What do you pay per protocol per year, and who approves it?
3. Do you buy separate formal or emulation versions of the same protocol?
   Have the versions ever disagreed?
4. How often has encryption blocked a debug? How long do vendor fixes take?
5. Do you run, or plan to run, regressions on Verilator or DSim? What blocks
   you?
6. Would you take unencrypted source with paid support over encrypted vendor
   VIP? What would you pay?
7. Which AXI5 or CHI features do you need, and when?
8. Do you need FPGA or hardware-in-the-loop AXI traffic? What do you use now?
9. What would make you trust an open VIP: a compliance suite, coverage proof,
   tapeout references, indemnity?
10. Is cocotb or Python in your flow? Would one spec across UVM and cocotb
    matter to you?

## To verify next

- Cadence's assertion-based and accelerated VIP product structure.
- SmartDV's product lines and its ownership.
- AMD AXI VIP licensing (the "Licensing and Ordering" section of PG267).
- The exact licence wording in the AMBA spec.
- The VIP-adoption figures in the Wilson 2026 data.
- Analyst market-size reports.

## Sources

- Synopsys VIP: https://www.synopsys.com/verification/verification-ip.html ; AXI https://www.synopsys.com/verification/verification-ip/amba/amba-axi.html ; CHI https://www.synopsys.com/verification/verification-ip/amba/amba-chi.html
- Siemens acquires Avery: https://news.siemens.com/en-us/siemens-avery-design-systems/ ; Questa One VIP https://www.siemens.com/en-us/products/ic/questa-one/verification-ip/
- Truechip: https://www.truechip.net/ ; Mirafra: https://www.mirafra.com/ ; Axiomise: https://www.axiomise.com/
- Verilator and encryption: https://verilator.org/guide/latest/languages.html ; `--protect-lib`: https://www.verilator.org/guide/latest/exe_verilator.html
- CHIPS Alliance SV Tools: https://www.chipsalliance.org/news/sv-tools-project-launch/ ; four-state: https://www.chipsalliance.org/news/initial-implementation-verilator/ ; https://github.com/chipsalliance/uvm-verilator
- Antmicro: https://www.antmicro.com/blog/2026/11/riscv-dv-compatibility-in-verilator-for-faster-agentic-verification ; https://www.antmicro.com/blog/2026/11/constrained-random-in-verilator-with-near-uniform-result-distribution
- Open repositories: https://github.com/pulp-platform/axi ; https://github.com/alexforencich/cocotbext-axi ; https://github.com/taichi-ishitani/tvip-axi ; https://github.com/ZipCPU/wb2axip ; https://github.com/nelsoncsc/verilaxi ; https://github.com/lowRISC/opentitan/tree/master/hw/dv/sv ; https://github.com/featherweight-vip
- ZipCPU formal AXI: https://zipcpu.com/formal/2019/05/13/axifull.html ; https://zipcpu.com/formal/2018/12/28/axilite.html
- YosysHQ Tabby: https://www.yosyshq.com/tabby-cad-datasheet
- AMBA royalty-free: https://www.arm.com/architecture/system-architectures/amba ; https://en.wikipedia.org/wiki/Advanced_Microcontroller_Bus_Architecture
- Wilson 2026: https://blogs.sw.siemens.com/verificationhorizons/2026/09/08/the-2026-functional-verification-study/
