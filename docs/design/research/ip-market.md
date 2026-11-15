# IP market: what to build from scratch for featherweight-ip

Researched 2026-11-15. This note backs `../ip-library-focus.md`.

Confidence tags:
- **[P]** a primary source, read directly;
- **[S]** a secondary source (trade press, vendor material);
- **[U]** unverified, from background knowledge;
- **[I]** our own inference.

**Limits of this pass.**
- The session's web-search budget was used up, so the researchers fetched
  primary pages directly (GitHub, the QEMU, Linux and DPDK trees, arXiv,
  vendor sites).
- Market-size figures (IPnest, Semico) could not be fetched; SemiWiki
  returned 403. All of them are [U].
- Customer complaints about LiteX, Chipyard and configurable IP are from
  community knowledge [U]. They need interviews.
- Star counts are from the GitHub API on 2026-11-15.

## Summary

| Question | Finding |
|---|---|
| Where is the money? | Processor IP is about 40–45% of a roughly $8.5B market. Interface IP (PHY plus controller) is about 30% and growing fastest. System and interconnect IP is small in dollars but sticky [U] |
| What can a small open project credibly build? | Configurable digital IP: interconnect, DMA, register blocks, interrupt and platform controllers, stream infrastructure. Not PHYs, not CPU cores [I] |
| Which IP needs a software model? | Anything a driver touches. QEMU, Renode, VCML and Linux converge on one set: 16550/PL011, PLIC/ACLINT/AIA, the RISC-V IOMMU, virtio, SDHCI, AHCI, NVMe, xHCI, PL330, e1000/igb [P] |
| Does open RTL exist for those devices? | Thin or missing. The 16550 is only on old OpenCores-era repos. There is no open GIC, AHCI, xHCI or e1000. AIA and IOMMU RTL each come from one group and are "not formally verified". Open virtio RTL is close to non-existent [P] |
| Does model and RTL divergence hurt? | Yes. OpenTitan's QEMU fork pins to an old RTL tag, grades its devices from "near feature-complete" down to "dummy", and has purpose-built sync tools. LiteX's Renode generator has special cases wherever the models lag the RTL [P] |
| Does anyone generate the model from the RTL source? | Not for peripherals. Codasip does it for processors only, MatchLib only through Catapult HLS, and register generators cover only the register layer [P] |
| Does anything go from one SoC configuration to RTL plus an emulator machine plus a device tree? | Partly. LiteX generates the RTL, device tree, headers and a Renode *platform*. Chipyard's FireMarshal tool runs one image on QEMU/Spike and on FireSim. Peripheral *behaviour* is hand-written everywhere [P] |

## 1. Market structure

- **Size [U].**
  - IPnest: design IP was about $7B in 2023 and about $8.5B in 2024, up about 20%.
  - Processor IP is about 40–45%; Arm dominates.
  - Interface IP (PCIe, DDR/HBM, Ethernet/SerDes, USB, UCIe, MIPI) is about 28–30%. Forecast: over $5B by about 2029.
  - Physical IP is about 10–15%.
  - Other digital IP (system, interconnect, security, DSP) is about 10%.
- **Vendors [U].** Arm has about 40% or more. Synopsys has about 20% overall and about 55% of interface IP. Then come Cadence, Alphawave, Rambus, Imagination, CEVA, SiFive, Arteris and Verisilicon.
- **Interconnect is a franchise sold through tools.**
  - Arteris claims 1000+ design starts and 1B+ SoCs [P]. Its revenue is only about $55–70M a year [U].
  - It sells FlexNoC, FlexGen, Ncore, CodaCache, and Magillem connectivity and registers [P].
  - Baya Systems pairs its fabric generators with WeaverPro, a platform to "model, analyze, and optimize system architectures using real workloads… before implementation" [P].
- **Categories by feasibility [I]:**
  - *Commodity:* simple peripherals (UART, SPI, I2C, GPIO, timers).
  - *Closed to newcomers:* PHYs and SerDes, which need silicon and characterization. CPU cores: Arm commercially; Ibex, CVA6, Rocket and VexRiscv in the open.
  - *Credible:* interconnect and NoC, DMA, CSR blocks, memory-subsystem glue, stream infrastructure, and the digital controllers that sit above a PHY.

## 2. Configurable and generator IP

| Area | Commercial | Open | How configuration is delivered |
|---|---|---|---|
| NoC / interconnect | Arteris; Arm CoreLink/CMN; Baya | PULP axi (1,758★); OpenTitan tlgen; Constellation; ESP; OpenPiton | GUI or generator; Baya and Platform Architect sell a model before the RTL [P] |
| DMA | Synopsys DW AXI DMAC; Arm PL330/DMA-350; AMD XDMA/QDMA | PULP iDMA; Taxi; LitePCIe | coreConsultant GUI [U]. QDMA is tied to AMD hard PCIe blocks [P] |
| Registers | Magillem Registers; Agnisys IDesignSpec; Synopsys coreTools | PeakRDL (SystemRDL); OpenTitan reggen | Spec-to-many-views generators; the most mature one-source market [P] |
| SoC assembly | Magillem; Platform Architect (TLM only, no RTL) | LiteX, Chipyard, topgen, ESP, Cheshire | See §5 |

**iDMA is the best published evidence for the configurability thesis [P]**
(arXiv 2305.05240).
- It separates a front-end, a mid-end (N-D, scatter-gather) and swappable back-ends (AXI4, AXI-Lite, AXI-Stream, OBI, TileLink).
- It reports "speedups up to 15.8x with only 1% additional area".
- It has been taped out in Snitch, PULP cluster, Occamy, MemPool and Cheshire.
- It also shows the cost: *one testbench per back-end configuration*.

**Verifying many configurations is a recognized cost [P].**
- iDMA needs a testbench per back-end configuration.
- Constellation advertises "almost 100 different tests across as many network configurations" and ships a deadlock checker.
- OpenTitan topgen validates the configuration and generates register models (RAL), but not testbenches.
- No open project generates RTL, a fast model *and* a configured scoreboard reference from one configuration for non-processor IP [P/I].

## 3. IP that needs a software model

**QEMU `hw/` [P].** QEMU has 73 subdirectories. The most active:
- **intc (97 files):** GICv2/v3/v5, `riscv_aclint`, `riscv_aplic`, `riscv_imsic`, `sifive_plic`.
- **virtio (84):** blk, net, console, rng, gpu, iommu, and many vhost-user devices, over MMIO and PCI.
- **net (72):** e1000, e1000e, igb, cadence_gem.
- **usb (68):** xhci, dwc2, dwc3.
- **char (47):** 16550, dw8250, pl011.
- **sd:** sdhci. **dma:** pl330, xilinx_axidma. **ide:** ahci. **nvme:** a full controller.
- **riscv:** `riscv-iommu`; `server_platform_ref` (Qualcomm), which uses ACLINT, APLIC, IMSIC, the IOMMU, AHCI and 16550; `tt_atlantis` (Tenstorrent, 2025).

**Renode [P]** (3,146★).
- It is weighted toward microcontrollers: 70 UART models, 33 DMA, 18 network.
- It has models of open RTL: LiteX_UART, LiteX_Ethernet, OpenTitan_*, Murax, NEORV32, PULP_uDMA.

**VCML (MachineWare, Apache-2.0, 207★) [P]** is the clearest independent list of devices worth modelling:
- 16550, pl011;
- aclint, aplic, clint, **iommu**, plic;
- virtio blk, console, net, rng, sound, mmio and pci;
- sdhci, xhci, gic400.

**Commercial [S].**
- Synopsys Virtualizer sells "DesignWare TLM peripherals" and hybrid runs with ZeBu and HAPS. It does not say whether the models derive from the RTL.
- Arm Fast Models are "developed and tested alongside Arm IP": separate code [I].

**Devices where unmodified upstream drivers work [P].**
- UART: 16550/8250/dw8250, PL011.
- Interrupts: PLIC, ACLINT, APLIC/IMSIC (Linux `RISCV_APLIC`, `RISCV_IMSIC`, `ACLINT_SSWI`).
- IOMMU: the RISC-V IOMMU (Linux v6.13, platform and PCI).
- Bus and storage: virtio-mmio and virtio-pci, SDHCI, AHCI, NVMe, xHCI, e1000/igb, PL330.
- GIC is excluded: it needs an Arm architecture licence [I].

**Open RTL for these devices is thin [P].**

| Block | QEMU | Open RTL |
|---|---|---|
| 16550 | yes | `freecores/uart16550` (45★, OpenCores era); RoaLogic apb4 (9★) |
| PLIC, CLINT/ACLINT | yes | only inside generators (Rocket, OpenTitan rv_plic, PULP) |
| AIA (APLIC+IMSIC) | yes, and VCML | `zero-day-labs/riscv-aia` (48★): "not formally verified... very likely to have bugs" |
| RISC-V IOMMU | yes (v1.0, pci+sys+hpm) | `zero-day-labs/riscv-iommu` (122★): not formally verified, no PCIe features. The spec repo has a C reference model |
| Debug module | spike/openocd | `pulp-platform/riscv-dbg` (329★), adequate |
| virtio | yes | `tymonx/virtio` (50★, unclear coverage); `RSPwFPGAs/virtio-fpga` (30★, a co-simulation prototype) |
| SDHCI | yes | under 10★ |
| GIC, AHCI, xHCI, e1000, PL330-compatible | yes | none found |

**The RISC-V platform pattern [P/I].** AIA and the IOMMU each have:
- a ratified spec;
- a QEMU model;
- VCML TLM models;
- a C reference model (the IOMMU);
- an upstream Linux driver;
- only single-group, unverified open RTL.

Ventana drives the QEMU and kernel IOMMU work [P]. Commercial AIA and IOMMU IP from SiFive, Andes, Codasip, MIPS and Tenstorrent was not checked [U]. An FPGA study of the open IOMMU measured shared virtual addressing at 4–18% runtime overhead without an LLC and under 1% with one (arXiv 2502.17398) [P].

**Virtio in hardware [P].**
- Linux vDPA has hardware drivers for:
  - Intel IFC VF (FPGA-based);
  - NVIDIA mlx5;
  - Alibaba ENI;
  - SolidRun;
  - AMD/Pensando;
  - Marvell Octeon.
- DPDK adds Xilinx and Netronome.
- All of them are closed. Commercial virtio hardware exists in quantity, but no one has visibly asked for open virtio RTL [U].
- The MMIO transport needs only an AXI-Lite port plus a DMA master, so it suits FPGA and RISC-V SoCs; the PCI transport needs a PCIe endpoint [I].

## 4. Evidence that model and RTL drift apart

**OpenTitan's QEMU fork (lowRISC/qemu, `ot-10.2.0`) [P]** is the strongest evidence:
- The device models are hand-written C by Rivos and lowRISC.
- Earlgrey is **pinned to the 1.0.0 RTL tag**; Darjeeling tracks development.
- Its docs grade each device as "near feature-complete", "partially implemented", "sparsely implemented" or "dummy". Examples:
  - UART: "missing RX timeout, TX break not supported".
  - KMAC: "masking not supported".
  - Pinmux, PWM and the pattern generator are dummies.
- They built tools to manage the drift:
  - `checkregs.py` checks QEMU register addresses against the generated `*_regs.h` ("bit assignment is not validated");
  - `autoreg.py` and `autotop.py` generate device and machine *skeletons*;
  - `verilate.py` runs "the very same binaries as QEMU [on Verilator] comparing the outcome".

This is a hand-built, partial version of what fw-hdl claims to provide [I].

**LiteX to Renode [P].**
- `litex_json2renode.py` (about 1,125 lines) generates the platform from `csr.json`.
- Peripheral behaviour is in hand-written C# models.
- The generator carries `_CSR32` model variants for each RTL CSR-width option, and comments such as `'model in Renode currently doesn't support interrupts'`.

**Effort to add a machine [P].**
- **Renode:** a new SoC built from existing models is a short `.repl` file, but every new peripheral needs a C# model first.
- **QEMU:** a machine is a C file plus a C device per new block. Upstreaming is expensive enough that OpenTitan keeps a fork.
- **When no model exists:** run the RTL instead, through Antmicro's Renode–Verilator integration or Xilinx `libsystemctlm-soc` (312★, QEMU to SystemC to Verilator).

**Chipyard [P].**
- Software bring-up uses Spike plus hand-written `riscv-spike-devices`, which are separate from the RTL.
- FireSim (1,064★) solves the problem by running the RTL fast on an FPGA rather than modelling it.

**Single-source precedents [P/S].**
- Codasip Studio: RTL, compiler and SystemC model from CodAL, but processors only.
- MatchLib (303★): one SystemC source for simulation and HLS, but requires Catapult.
- Register generators: the register layer only.
- No vendor ships peripheral RTL with a behaviour-level QEMU or TLM model generated from the same source.

## 5. SoC and platform assembly

| Tool | Device tree | Headers | Emulator | Testbench |
|---|---|---|---|---|
| LiteX (4,206★) | yes (Linux, Zephyr) [P] | `csr.h`, `soc.h`, `csr.json` [P] | Renode *platform* generated; peripheral models hand-written [P] | Verilator sim only |
| Chipyard (2,461★) | yes, from diplomacy [U] | yes [U] | FireMarshal: the same image on QEMU/Spike and FireSim [P] | Verilator/VCS harnesses |
| OpenTitan topgen | no | yes [P] | separate QEMU fork, skeletons generated [P] | RAL models; hand-written UVM |
| ESP | yes [P] | yes [P] | full-system simulation [P] | per accelerator [U] |
| PULP Cheshire (387★) | yes [P] | yes [P] | none | Questa |
| Synopsys Platform Architect | — | — | SystemC performance models, no RTL [P] | — |
| Vivado IP Integrator | via XSA and SDT [U] | `xparameters.h` [U] | QEMU (Xilinx fork) driven by device tree, not generated from the block design [U] | no |
| Intel Platform Designer | sopc2dts [U] | yes [U] | — | testbench system [U] |

**Complaints [U].**
- **LiteX:** Migen and Python-embedded HDL put off SV teams; the generated Verilog is hard to read; QoR and timing are mediocre at high clock rates; the documentation is mostly the source; it suits FPGAs much better than ASICs.
- **Chipyard:** the Scala, Chisel and diplomacy learning curve; config-fragment errors surface deep in elaboration; long builds; output that is hard to take into sign-off.
- **topgen:** tied to the Earlgrey and Darjeeling tops and to Bazel.
- **Vendor block-design tools:** vendor-locked, GUI-centric, hard to diff.

## 6. Open IP that stuck, and why

| Project | Stars | Why it stuck | Software model |
|---|---|---|---|
| OpenTitan | 3,760 | Google anchor; ships in Chromebooks [P] | Hand-written QEMU fork and Renode models |
| LiteX | 4,206 | Many boards; Linux; consulting by Enjoy-Digital [P] | Generated Renode platform; hand-written models |
| Rocket/Chipyard/FireSim | 3,907 / 2,461 / 1,064 | Berkeley and SiFive tapeouts | Spike plus separate devices; FPGA-accelerated RTL |
| PULP axi / iDMA / Cheshire | 1,758 / — / 387 | ETH tapeouts; narrow, excellent scope | RTL only |
| Forencich verilog-ethernet / Corundum / Taxi | 3,155 / 2,512 / 1,022 | A whole problem (a NIC); proven on boards; Taxi is dual-licensed CERN-OHL-S or commercial [P] | cocotb models; no emulator model |
| VexRiscv / SpinalHDL | 3,314 / 2,062 | Linux-capable FPGA core | Renode Murax model |

**Common factors [I]:**
- an anchor customer or funder;
- silicon or boards that prove it works;
- a permissive or dual licence;
- a whole problem solved, in a narrow scope;
- a services company behind it (lowRISC, Enjoy-Digital, Antmicro, FPGA Ninja).

lowRISC's revenue includes paid QEMU work [P].

## Open questions

1. Which vendors sell AIA and IOMMU IP, at what price, and with which models?
2. Is there explicit demand for open virtio RTL (RISC-V SIGs, FPGA forums)?
3. Do the RVA23 server SoC and server platform specs require AIA plus the IOMMU, and at what level?
4. Do Synopsys DW TLM models share any source with the DW RTL? Does tooling keep Caliptra's software emulator in sync with its RTL?
5. Integration route for fw-hdl models: a C model compiled into QEMU or Renode, Renode external peripherals, QEMU remote-port, or vfio-user?
6. Licensing: QEMU is GPLv2, and Apache-2.0 is not GPLv2-compatible. Generated QEMU device code needs a compatible licence.
7. Would SoC and FPGA teams take a generated SV interconnect or DMA over PULP axi or iDMA? On what terms (QoR, readability, support)?
8. Who pays for emulator models today (Antmicro and lowRISC contracts), and how much?
9. Confirm the IPnest and Semico 2024–25 figures and Arteris revenue.

## Sources

- QEMU hw tree: https://github.com/qemu/qemu/tree/master/hw ; RISC-V IOMMU: https://www.qemu.org/docs/master/specs/riscv-iommu.html
- Renode: https://github.com/renode/renode-infrastructure ; platform format: https://renode.readthedocs.io/en/latest/advanced/platform_description_format.html
- VCML: https://github.com/machineware-gmbh/vcml ; MachineWare: https://www.machineware.de/
- Linux Kconfig: vDPA https://github.com/torvalds/linux/blob/master/drivers/vdpa/Kconfig ; irqchip https://github.com/torvalds/linux/blob/master/drivers/irqchip/Kconfig ; RISC-V IOMMU https://github.com/torvalds/linux/blob/master/drivers/iommu/riscv/Kconfig
- DPDK vDPA: https://doc.dpdk.org/guides/vdpadevs/index.html
- zero-day-labs: https://github.com/zero-day-labs/riscv-iommu ; https://github.com/zero-day-labs/riscv-aia
- RISC-V IOMMU spec and reference model: https://github.com/riscv-non-isa/riscv-iommu
- Virtio RTL: https://github.com/tymonx/virtio ; https://github.com/RSPwFPGAs/virtio-fpga
- lowRISC QEMU fork: https://github.com/lowRISC/qemu (`docs/opentitan/`, `scripts/opentitan/`)
- LiteX: https://github.com/enjoy-digital/litex ; tools: https://github.com/enjoy-digital/litex/tree/master/litex/tools
- Chipyard Spike: https://github.com/ucb-bar/chipyard/blob/main/docs/Software/Spike.rst ; FireMarshal: https://firemarshal.readthedocs.io/en/latest/
- Xilinx libsystemctlm-soc: https://github.com/Xilinx/libsystemctlm-soc
- iDMA: https://arxiv.org/abs/2305.05240 ; https://github.com/pulp-platform/iDMA
- PULP axi: https://github.com/pulp-platform/axi ; Cheshire: https://github.com/pulp-platform/cheshire
- Constellation: https://github.com/ucb-bar/constellation ; ESP: https://www.esp.cs.columbia.edu/
- OpenTitan: https://opentitan.org/ ; topgen: https://opentitan.org/book/util/topgen/index.html ; lowRISC: https://www.lowrisc.org/about/
- CVA6: https://github.com/openhwgroup/cva6
- Corundum: https://github.com/corundum/corundum ; Taxi: https://github.com/fpganinja/taxi
- PeakRDL: https://peakrdl.readthedocs.io/
- Arteris: https://www.arteris.com/ ; Baya: https://www.bayasystems.com/
- Synopsys Virtualizer: https://www.synopsys.com/verification/virtual-prototyping/virtualizer.html ; Platform Architect: https://www.synopsys.com/verification/virtual-prototyping/platform-architect.html
- Arm Fast Models: https://www.arm.com/products/development-tools/simulation/fast-models
- Codasip Studio: https://codasip.com/products/codasip-studio/ ; MatchLib: https://github.com/NVlabs/matchlib
- AMD QDMA PG302: https://docs.amd.com/r/en-US/pg302-qdma
- arXiv: 2304.01721 (Virtio-FPGA), 2311.00442 (TLM-to-RTL gap), 2502.17398 (IOMMU on FPGA), 2409.02381 (FlexBSO)
- Wikipedia, SIP core: https://en.wikipedia.org/wiki/Semiconductor_intellectual_property_core
