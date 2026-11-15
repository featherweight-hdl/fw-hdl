# Synthesizable traffic generators for emulation and FPGA

Researched 2026-11-15. This note backs `../pitch.md` (*Who this is for*,
item 4) and `../demo-traffic-generator.md`.

Confidence tags:
- **[P]** a primary source, read directly;
- **[S]** a secondary source (vendor pages, trade press);
- **[U]** unverified;
- **[I]** our own inference.

## Summary

| Area | Key finding | Conf. |
|---|---|---|
| Host boundary | The number of host syncs dominates. ADI cut syncs 470x and run time fell 15x | P |
| Transaction size | About 10 clocks per AXI transfer is too little work per crossing; batch and stream | P |
| Mode speeds | Transaction-based acceleration (TBA) ≤ about 1 MHz; in-circuit about 1–2 MHz; FPGA prototyping 25–100 MHz | S |
| Cost of a synthesizable testbench | "As complicated, if not more, as the RTL itself" (PMC) | P |
| Arm ATP | The spec calls for low-gate-count hardware generators; Arm ships only a C++ engine | P |
| AMD AXI TG (PG125) | 256 commands per direction, register-programmed, no descriptor chains | S |
| FireSim | Batch tokens, keep models on the FPGA, slow host handlers stall everything | P |
| Prior art | Bluespec pitched high-level synthesizable testbenches around 2009 | P |
| FPGA escapes | 87% of FPGA projects had non-trivial bug escapes (2024) | S |
| Processor-driven tests | Still need transactors for I/O (Breker TrekBox) | S |
| On-chip stimulus | No general flow found; only vendor IP and research | I |

## Key evidence

### 1. The host boundary in transaction-based acceleration

**SCE-MI 2.x (Accellera) [P].** It offers three ways to cross the boundary:
- DPI function calls;
- transaction pipes (buffered, one-way streams);
- direct memory access (v2.2 and later).

The HDL side is a synthesizable, clocked bus functional model (BFM) that turns
each message into many design clocks.

**Veloce TBX / XRTL [P] (van der Schoot, DVCon).**
- *The split.* The testbench divides into a synthesizable HDL side
  (interfaces holding tasks and functions) and an untimed host-side proxy.
- *XRTL* is a behavioral subset that synthesizes implicit FSMs, behavioral
  clocks, variable delays, assertions and covergroups.
- *Amdahl's limit.* If the testbench is 20% of the load, speed-up is capped
  at 5x. About 10% overhead from DPI, constraint solving and assertions caps
  it below 10x.
- *Granularity.* A simple AMBA transfer is about 10 clocks, too little work
  per crossing. An Ethernet packet is thousands.
- *Advice:* build meta-transactions, stream rather than react, use deep pipes,
  never flush per transaction, use one-way calls.

**Analog Devices (DVCon 2022) [P].**
- *Syncs and run time:*

  | Syncs | Run time |
  |---|---|
  | 4.7M | 60 min |
  | 1.28M | 35 min |
  | 9,871 | 4 min |

  Simulation took about 360 min.
- *Recommendation:* move rarely used, complex BFM logic back into C, because
  synthesizable code costs effort and emulator area.

**Clock rates [S].** TBA runs at about 1 MHz or less (Rizzatti), and
in-circuit about 1–2 MHz. FPGA-based systems run faster: Protium X3 up to
about 100 MHz, Veloce Strato CS about 25 MHz.

**Counter-evidence: PMC (Chan, DVCon) [P].**
- The host cable "is rarely a bottleneck".
- Synthesizable testbenches are "very difficult and time consuming to
  implement, ... as complicated, if not more, as the RTL itself".
- They reused the simulation VIP and kept the in-emulator BFM a "dumb pipe".
- Results: 40–67x speed-up, against a break-even of 30–40x.
- They concede that simulation acceleration "can never run nearly as fast as
  ICE mode".

**Bluespec white paper (about 2009) [P].** With 99% of the work in hardware,
Amdahl caps speed-up at 100x. Fully synthesizable testbenches are "required to
reach 1,000X–10,000X".

### 2. Commercial emulation-ready VIP and virtual testers

**Siemens VirtuaLAB PCIe/NVMe.**
- A QEMU virtual host (real OS, drivers and applications) runs on a co-model
  server [P/S].
- Siemens claims SSD performance and latency within 5% of silicon [S].
- The PCIe page markets "autonomous traffic generation" at "up to 4–5 times
  the normal packet traffic" [S].
- The Ethernet packet generator/monitor (EPGM) targets 1.6 Tbps ports. Whether
  it generates in the emulator or on the host is unclear [U].
- Siemens acquired Avery (QEMU host plus PCIe/NVMe/CXL VIP) in FY2023 [S].

**Synopsys ZeBu [S].** Synthesizable BFMs with C++ APIs; Virtual Host and
device models for PCIe 5, NVMe, SATA and others; ZEMI-3 compiles behavioral SV
into transactors.

**Cadence [S].** Accelerated VIP (up to 100x over simulation); "Embedded
AVIP", where testbench and DUT both run on Palladium or Protium; a System
Traffic Library with PCIe/NVMe performance tests.

**Cost.** No prices are published. Emulation capacity costs roughly 1–5 cents
per gate [S]. Transactors and virtual labs are licensed add-ons [U].

### 3. Existing synthesizable traffic generators

- **Arm AMBA Adaptive Traffic Profiles (ATP, IHI 0082A) [P].** Note the name:
  "Profiles", not "Generation".
  - *What a profile describes:* address patterns (linear, 2-D, random), a
    FIFO timing model, rates (peak, constrained peak, average), and
    synchronization between profiles.
  - *Stated intent:* "a low-gate-count hardware component can be used as a
    traffic generator ... for high-speed hardware emulation or FPGA
    prototyping".
  - *Reality:* Arm's ATP Engine is C++ for gem5, with no RTL.
- **AMD AXI Traffic Generator, PG125 [S].**
  - Advanced mode: a command RAM with 256 write and 256 read entries, a
    parameter RAM and an 8 KB data RAM.
  - Each command can repeat with a constant, incrementing or random address,
    and supports delays, a loop bit and read/write dependencies.
  - It cannot express data-dependent control, descriptor chains in DUT memory,
    multi-queue protocols or closed-loop rate control.
- **AMD Versal Performance AXI TG [P].** Driven by a CSV file (length, size,
  transaction count, loop count); about 14 GB/s peak.
- **AXI Performance Monitor (PG037) [S].** Throughput; average, minimum and
  maximum latency; an 8-bin histogram; an event log.
- **Altera EMIF Traffic Generator 2.0 [S].** Register-configured patterns,
  aimed at memory test.
- **Open source:**
  - Forencich's verilog-axi and taxi, and Corundum, test through cocotb
    Python models, in simulation only [P].
  - FPGA NVMe hosts exist (axi-nvme, mcrl/NVMe, DUNE pl-nvme), but they are
    data movers, not generators [S].
  - ZipCPU's `axiperf` is an open-source performance monitor [S].
- **Gap [I].** Existing generators are either shallow and register-programmed
  (PG125, Altera TG2) or a rich spec with no hardware (ATP). Nothing found
  combines descriptor chains, multiple streams and rate control in hardware.

### 4. How teams build generators today

**There are two camps:**
1. *Thin BFM in the emulator, generation on the host* (Mentor, PMC). This is
   the norm.
2. *Embedded, synthesizable testbench* for maximum speed (Bluespec, part of
   ADI's approach).

**The compilers already accept behavioral code [P/S].** Veloce XRTL takes
implicit FSMs and behavioral clocks; Palladium IXCOM has "rich behavioral
construct support"; ZeBu has ZEMI-3.

**Reported effort:**
- PMC: porting to simulation acceleration went from more than a year to
  3 months to 3 weeks.
- Bluespec: synthesizable testbenches for an Ethernet MAC and router took
  under 9 person-weeks and under 3k lines, fewer lines than the VMM version
  (a vendor claim).
- Mentor (DVCon): a multi-descriptor, multi-queue DMA was "difficult to model
  in testbench based verification". They solved it with real software in
  QEMU, not with a hardware generator.

### 5. Performance verification of storage under emulation

- The dominant flow is a QEMU virtual host, real drivers and fio-class tools
  over a virtual PCIe link [P/S].
- Claimed accuracy is about 5% [S].
- The bottleneck becomes the host stack and the co-model link. No public paper
  quantifies IOPS under emulation; expect the data to be confidential [U].

### 6. High-level languages for verification collateral

- Catapult generated SystemC transactor wrappers around 2005 [S].
- Bluespec with EVE ZeBu offered synthesizable BSV transactors, and BSV ships
  SCE-MI libraries [P/S]. This is the closest prior art to the pitch, and it
  did not become mainstream [I].
- **FireSim bridges [P]:**
  - *Design:* an FPGA-resident module plus an optional host driver; MMIO for
    configuration; wide DMA for bulk token streams.
  - *Batching:* tokens are batched up to the target link latency without
    losing cycle accuracy. Smaller batches lose performance in proportion.
  - *Failure mode:* slow host handlers stall the whole simulation.
  - *Lesson:* keep models on the FPGA (for example the FASED DRAM model) and
    decouple the rest with deep queues.
  - *Speed:* about 150 MHz for a single node.

### 7. Low-cost boards

| Board | Price | Memory | Host link |
|---|---|---|---|
| Arty A7-100T | $322 [S] | 256 MB DDR3 | USB-UART, Ethernet |
| Nexys Video | $577 [S] | 512 MB DDR3 | FMC LPC, USB |
| Genesys 2 | $1,183 [S] | 1 GB DDR3 | FMC HPC, USB |
| Kria KV260 / KR260 | $249 / $349 [S] | 4 GB DDR4, reached through the processor-side ports | Ethernet; SFP+ on the KR260 |
| LiteFury / NiteFury | $109 / $329, LiteFury often out of stock [S] | 256 / 512 MB DDR3 | M.2 PCIe x4 Gen2 |
| ULX3S | ~$130–190 [U] | 32 MB SDRAM | USB |
| Alveo U50, used | $650–2,200 [S] | 8 GB HBM2 | PCIe Gen4 x16 |

### 8. On-board testing of FPGA designs

**How FPGA teams test on hardware today:**
- **ILA/VIO and SignalTap.**
  - Trace depth is limited by on-chip RAM: SignalTap goes up to 128K samples,
    and a 1K-deep trace takes about 29 block RAMs [S].
  - Access is over JTAG. JTAG-to-AXI gives host register access, but it is
    slow: several JTAG operations per 32-bit word [S].
  - Exostiv streams trace through the transceivers to external memory (up to
    50 Gbps, 8 GB) to escape the RAM limit [S].
- **MathWorks HDL Verifier** [S]: FPGA-in-the-loop co-simulation, plus the
  AXI Manager IP for MATLAB register and memory reads and writes over JTAG,
  PCIe or Ethernet. It is host-driven register and memory testing, not
  cycle-level stimulus.
- **Processor-driven testing:** test software on soft or hard cores. Agnisys
  IDS-Validate generates C register and memory tests [S].

**"Write C that runs on the core" vendors:**
- **Breker TrekSoC-Si** [S]:
  - It generates multi-threaded, self-checking C tests for in-circuit
    emulation, FPGA prototypes and silicon.
  - In a Cavium example, 96 cores ran coherency tests while 48 more cores
    generated PCIe traffic.
  - For external ports, Breker generates a "TrekBox" that drives transactors
    synchronized with the C tests. Processors alone do not cover the I/O.
- **Valtrix STING** [S]: bare-metal constrained-random tests, portable from
  simulation to silicon. Synopsys acquired Valtrix in July 2024.
- **PSS tools** (Perspec, Questa, Breker) generate bare-metal C for
  post-silicon [S]. A common pattern is a processor write that triggers a VIP
  command, again because external I/O needs a transactor.
- **FPGA-focused startups:** only debug-visibility vendors (Exostiv) were
  found. None offers synthesizable on-chip stimulus [U]. This looks like a
  gap.

**Synthesizable on-chip checkers and coverage:**
- Emulators accept the synthesizable subset of SVA; Palladium supports SVA
  and functional coverage [S].
- Academic SVA-to-hardware compilers exist [S].
- Hassert (RISC-V Summit Europe 2025) maps SVAs onto the FPGA and switches
  them dynamically, noting that ILA "can monitor only a few signals" [P].
- FireSim ships assertion synthesis, printf synthesis, AutoILA and
  AutoCounter [S].
- For *stimulus*, there are only vendor IP (PG125, Altera TG2) and research
  systems. No general flow for writing on-chip stimulus was found [I].

**FPGA verification practice (Wilson Research):**
- 2024: 87% of FPGA projects had non-trivial bug escapes into production [S].
- 2022: only 17% had none, and 70% were behind schedule [P].
- Many teams still rely on lab validation as the primary strategy. Projects
  with no escapes used more simulation techniques [P/S].

**Limits of processor-driven testing:**
- *Reachability.* A processor reaches only what is memory-mapped. Streaming
  ports (AXI-Stream, Ethernet, ADC/DAC, PCIe endpoint) need a transactor or a
  loopback. Breker's TrekBox and the PSS processor-to-VIP pattern exist for
  exactly this reason [S].
- *Rate.* Core loads and stores are serialized by caches and the
  interconnect, so line-rate multi-stream traffic needs a DMA engine or many
  cores (Breker's 48 cores for PCIe) [I/S].
- *Cycle-level control.* Software cannot insert backpressure on a given
  cycle, inject protocol errors, or line up concurrent corner cases
  deterministically. Its timing depends on caches, interrupts and the OS [I].
  No quantitative source was found.
- *Observability.* Checking is limited to what software can read back, and
  ILA is shallow. That is why Hassert and Exostiv exist [P/S].

## Supports the pitch

1. **An in-emulator generator is the documented fix for the host
   bottleneck.** Vendors and users agree that host syncs and testbench load
   cap TBA speed-up.
2. **The barrier practitioners name is effort, not value:** "as complicated as
   the RTL itself". That is exactly what higher-level constructs address.
3. **Arm's ATP spec asks for low-gate-count hardware generators, and none
   exists.** PG125 and Altera TG2 are too shallow for descriptor chains or
   NVMe-style queues. An fw-hdl generator that implements ATP profiles would
   fill a named gap.
4. **10% overhead on testbench logic is cheap** when emulation capacity costs
   cents per gate [I].
5. **Vendors market "autonomous traffic generation"** (VirtuaLAB), which
   confirms demand.
6. **FireSim proves the architecture academically:** FPGA-hosted models,
   batched host traffic.

7. **FPGA teams need a testbench that runs on the FPGA.** 87% of FPGA
   projects had bug escapes (Wilson 2024), and lab validation is often the
   primary strategy.
8. **Processor-driven tools already depend on transactors for I/O** (Breker
   TrekBox, the PSS processor-to-VIP pattern). No FPGA vendor or startup
   offers general synthesizable on-chip stimulus.
9. **ILA's limits are pushing checkers into hardware** (Hassert, FireSim).
   fw-hdl-dv checkers shared between simulation and formal could also
   synthesize onto the board.

## Against, and risks

1. **PMC found the host link often isn't the bottleneck,** and recommends
   reusing simulation VIP.
2. **Storage performance validation has standardized on QEMU plus real
   software,** which is more realistic than synthetic traffic. ADI also moves
   complex logic back to the host. Position the generator as a complement,
   for stress, line rate and determinism, not as a replacement for the
   virtual host.
3. **Bluespec pitched this around 2009 and it didn't take off.** Find out
   why: the language, tool cost, or emulator lock-in.
4. **Higher-level constructs partly exist already** in vendor behavioral
   synthesis (XRTL, IXCOM, ZEMI-3). fw-hdl's case is portability across
   emulators and FPGA, a matching class model in simulation, the link from
   scenarios to descriptors, and an open implementation.
5. **On FPGA-based emulators (ZeBu, Protium, HAPS), a 10% QoR cost may reduce
   the clock,** not only add area [I].
6. **NVMe performance-under-emulation data is not public,** so the size of the
   pain is hard to quantify.

7. **FPGA teams may not write class-based SV collateral.** They lean on lab
   bring-up, MATLAB and C on the core. The same maturity gap that Wilson
   describes could slow adoption.
8. **Others own parts of the lab workflow** (Exostiv, MathWorks, the FPGA
   vendors' debug tools).

## Interview questions

1. In your last emulation project, what share of wall-clock time was the
   host or co-model side, and how did you measure it?
2. Do you write synthesizable generators today? How many person-weeks did
   they take, and who wrote them (DV or RTL engineers)?
3. For SSD/NVMe performance, do you use a vendor virtual host, a custom
   generator, or both? Where does the virtual host fall short (IOPS ceiling,
   determinism, queue depth)?
4. Would you trust a synthetic descriptor-chain generator's numbers over a
   QEMU+fio run? What correlation would you need?
5. What do XRTL, IXCOM or ZEMI-3 fail to accept that you want?
6. Which matters more: area and frequency overhead, or portability across
   Palladium, Veloce, ZeBu and FPGA?
7. What would make you pay for this, or switch away from, versus vendor
   accelerated VIP and VirtuaLAB?
8. Have you used AXI TG, ATP or Bluespec? Why did you stop?

9. For FPGA designs, how much verification happens in the lab versus in
   simulation, and which bugs escaped?
10. When you test from a soft or hard core, which interfaces can't you reach
    or stress (streaming, backpressure, error injection)?
11. Would on-chip checkers or coverage change your sign-off, and what overhead
    is acceptable?

## Sources

- SCE-MI 2.4: https://www.accellera.org/images/downloads/standards/sce-mi/SCE-MI_v24-Nov2016.pdf
- ADI SCE-MI (DVCon 2022): https://dvcon-proceedings.org/wp-content/uploads/efficient-standard-co-emulation-modeling-interface-sce-mi-usage-to-accelerate-tba-performance.pdf
- van der Schoot, UVM and Emulation: https://dvcon-proceedings.org/wp-content/uploads/uvm-and-emulation-how-to-get-your-ultimate-testbench-acceleration-speed-up.pdf
- Off To The Races (DVCon 2011): https://dvcon-proceedings.org/wp-content/uploads/off-to-the-races-with-your-accelerated-systemverilog-testbench-a-methodology-for-hardware-assisted-acceleration-of-systemverilog-testbenches.pdf
- PMC / Chan, simulation acceleration methodology: https://dvcon-proceedings.org/wp-content/uploads/a-methodology-to-port-a-complex-multi-language-design-and-testbench-for-simulation-acceleration.pdf
- Mentor, hybrid testbench and software emulation: https://dvcon-proceedings.org/wp-content/uploads/hybrid-approach-to-testbench-and-software-driven-verification-on-emulation.pdf
- Rizzatti: https://eetimes.com/author.asp?doc_id=1327651&section_id=36 ; https://www.rizzatti.com/lauro-on-cdns-palladium-xp2-vs-ment-veloce-2-vs-snps-zebu-3/
- DeepChip DAC'24: https://www.deepchip.com/gadfly/gad062424.html
- Siemens computational storage: https://www.electronicdesign.com/technologies/test-measurement/article/21133398/siemens-computational-storage-device-verification-a-challenging-task
- Veloce PCIe: https://www.siemens.com/en-us/products/ic/hav/veloce-interfaces/pcie-interfaces/
- EPGM: https://www.siemens.com/en-us/products/ic/hav/ethernet-packet-generation-monitor/
- Avery acquisition: https://www.design-reuse.com/news/52934/siemens-avery-design-systems-acquisition.html ; QEMU host https://www.design-reuse.com/news/48985/avery-qemu-virtual-host.html
- Cadence AVIP: https://www.cadence.com/en_US/home/tools/system-design-and-verification/verification-ip/accelerated-vip.html
- ZeBu: https://www.synopsys.com/verification/emulation/zebu-solutions.html ; https://news.synopsys.com/2014-02-25-Synopsys-Delivers-Industrys-Fastest-Emulation-System
- Emulation cost: https://www.electronicdesign.com/technologies/eda/article/21801171/11-myths-about-hardware-emulation
- Arm ATP: https://armkeil.blob.core.windows.net/developer/Files/pdf/white-paper/amba-adaptive-traffic-profiles.pdf ; https://github.com/ARM-software/ATP-Engine
- PG125: https://www.xilinx.com/content/dam/xilinx/support/documents/ip_documentation/axi_traffic_gen/v2_0/pg125-axi-traffic-gen.pdf
- Versal Performance AXI TG: https://github.com/Xilinx/Vivado-Design-Tutorials/tree/2023.2/Device_Architecture_Tutorials/Versal/NoC_DDRMC/Versal_Performance_AXI_Traffic_Generator/Synthesizable_Traffic_Generator/Lab_1_Introduction
- APM: https://www.xilinx.com/products/intellectual-property/axi_perf_mon.html ; ZipCPU axiperf https://zipcpu.com/blog/2021/08/14/axiperf.html
- Altera TG2: https://fpgawiki.intel.com/wiki/Traffic_Generator_2.0
- taxi: https://github.com/fpganinja/taxi ; cocotbext-axi https://github.com/alexforencich/cocotbext-axi
- FPGA NVMe: https://github.com/krishna-swaroop/axi-nvme ; https://github.com/mcrl/NVMe ; SwarmIO https://github.com/VIA-Research/SwarmIO
- Bluespec synthesizable testbench: https://web.eecs.utk.edu/~dbouldin/protected/BluespecSynthesizableTestBenchWP.pdf ; BSV SCE-MI https://web.ece.ucsb.edu/its/bluespec/doc/BSV/scemi.pdf ; Bluespec/EVE https://www.edn.com/bluespec-eve-add-esl-to-emulation/
- FireSim: https://sagark.org/assets/pubs/firesim-isca2018.pdf ; https://docs.fires.im/en/latest/golden-gate/bridges/ ; https://groups.google.com/g/firesim/c/03GMvjpddkc ; Golden Gate https://people.eecs.berkeley.edu/~biancolin/papers/goldengate-iccad19.pdf
- Wilson 2024 FPGA: https://verificationacademy.com/topics/planning-measurement-and-analysis/wrg-industry-data-and-trends/2024-siemens-eda-and-wilson-research-group-fpga-functional-verification-trend-report/ ; Wilson 2022 FPGA: https://www.innofour.com/static/default/files/documents/pdf/fpga-trend-report_2022-wilson-research-verification-study_hfoster.pdf
- MathWorks HDL Verifier: https://www.mathworks.com/help/hdlverifier/ref/aximanager.html ; https://www.mathworks.com/help/hdlverifier/gs/get-started-with-fpga-debug.html
- JTAG-to-AXI (PG174): https://docs.amd.com/api/khub/documents/_wIZFMh6Bz4ocCQqsDO2~g/content ; xvcSupport note: https://github.com/paulscherrerinstitute/xvcSupport/blob/master/README.md
- Signal-tracing cost: https://www.researchgate.net/publication/302631498_Signal-Tracing_Techniques_for_In-System_FPGA_Debugging_of_High-Level_Synthesis_Circuits ; Exostiv: https://www.exostivlabs.com/debugging-fpgas-at-full-speed/
- Breker: https://brekersystems.com/products/treksoc-si/ ; https://www.eejournal.com/article/20130815-breker/ ; https://brekersystems.com/inside-portable-stimulus-introducing-a-processor/
- STING: https://www.synopsys.com/verification/sting.html ; Valtrix acquisition: https://www10.edacafe.com/blogs/editorial/2024/08/01/amkor-to-get-chips-act-funds-startup-funding-synopsys-acquires-valtrix-liquid-cooling-growth/
- Agnisys IDS-Validate: https://www.agnisys.com/products/ids-validate/
- Hassert: https://riscv-europe.org/summit/2025/media/proceedings/2025-05-14-RISC-V-Summit-Europe-P2.1.01-ZHANG-abstract.pdf ; SVA synthesis: https://www.researchgate.net/publication/221341094_Synthesis_of_System_Verilog_Assertions
- Boards: https://digilent.com/shop/arty-a7-100t-artix-7-fpga-development-board/ ; https://www.amd.com/en/products/system-on-modules/kria/k26/kv260-vision-starter-kit.html ; https://www.amd.com/en/products/system-on-modules/kria/k26/kr260-robotics-starter-kit.html ; https://www.crowdsupply.com/rhs-research/nitefury
