# Open RISC-V SoC IP: inventory for lifting

Researched 2026-11-15. This note backs §0 of `../ip-library-focus.md`
("lift, prove, model").

Most of it was read from shallow clones of each repo at HEAD. Line counts are
non-blank, non-comment RTL lines; "reg" is the part produced by the register
generator.

Confidence tags:
- **[P]** a primary source, read directly;
- **[S]** a secondary source;
- **[U]** unverified.

## 1. What Cheshire instantiates [P]

Sources: `Bender.yml`, `hw/cheshire_soc.sv`, `sw/boot/cheshire.dtsi`.
Cheshire is SHL-0.51. Its own registers are generated with PeakRDL.

| Instance | Source and version | Licence | DT compatible |
|---|---|---|---|
| cva6 | pulp-platform/cva6 pulp-v2.0.0 | SHL-0.51 | `eth,ariane` |
| reg_uart_wrap (wraps obi_uart) | apb_uart 0.2.3, via obi_peripherals | SHL-0.51 | `ns16550a` |
| clint | pulp-platform/clint 0.3.0 | SHL-0.51 | `riscv,clint0` |
| rv_plic, i2c, spi_host, gpio | opentitan_peripherals 0.4.0, vendored from OpenTitan 9f497f6 | Apache-2.0 | `riscv,plic0`; `eth,i2c`; `opentitan,spi-host`; gpio has no DT node |
| clic | pulp clic 3.0.0 | — | — |
| irq_router | 0.0.1-beta.1, 205 lines | Apache-2.0 | — |
| dm_top, dmi_jtag | riscv-dbg 0.8.1 | SHL-0.51 | `riscv,debug-013` |
| iDMA | 0.6.4, about 6.1k lines, PeakRDL | SHL-0.51 | — |
| axi_vga | 0.1.3, 1,178 lines, reggen | SHL-0.51 | `eth,axi-vga` / `simple-framebuffer` |
| serial_link | 2.0.0, about 3.3k lines, PeakRDL | Apache-2.0 + SHL-0.51 | `eth,ddr-link` |
| axi_llc | 0.3.0, about 3.2k lines | SHL-0.51 | `eth,axi-llc` |
| axi_rt | — | — | — |
| spinal_usb_ohci | generated Verilog, 18.6k lines | MIT | `generic-ohci` |

**Other facts about Cheshire:**
- **Interconnect:** pulp axi 0.39.8, register_interface 0.4.5 and apb 0.2.4, all SHL-0.51.
- **No AIA,** and the zero-day-labs IOMMU is not a dependency.
- **Linux support is out of tree:** a CVA6-SDK fork adds an OpenTitan
  spi_host driver. Mainline Linux has no OpenTitan drivers.

**The UART has a history that is a precedent for this plan:**
- Up to v0.2.1, apb_uart was a VHDL 16750 (LGPL-2.1) converted to SV, about
  1.9k lines.
- It shipped `util/equiv_check.fm.tcl`, a Formality script that checks the
  VHDL against the SV. That is a lift-and-prove precedent.
- From v0.2.2 (June 2025) apb_uart wraps `obi_uart`, a new SHL-0.51
  implementation of about 1.26k lines.
- CVA6's corev_apu still pins the old LGPL version.

## 2. Block inventory

QEMU column:
- "upstream" is mainline QEMU;
- "fork" is lowRISC/qemu `ot-10.2.0`, which grades each device itself as
  near-complete, partial or sparse;
- mainline QEMU's `opentitan` machine has only ibex_uart, ibex_timer and
  ibex_spi_host, and uses the SiFive PLIC.

### PULP and Cheshire

| Block | HDL, size | Bus | Registers | DV | QEMU | Renode | Driver | Lifting hazards |
|---|---|---|---|---|---|---|---|---|
| obi_uart / apb_uart | SV, 1.26k | OBI, to APB or regbus | hand-written | simple tb | upstream `serial-mm` 16550 | NS16550 | Linux 8250, Zephyr ns16550 | RX 2-flop sync, oversampling, modem pins |
| clint | SV, 459 | regbus | PeakRDL | simple tb | upstream `riscv_aclint` | CoreLevelInterruptor | Linux timer-clint, OpenSBI, Zephyr | `rtc_i` edge synchroniser; 64-bit mtime |
| rv_plic (Cheshire configuration: 58 sources, 2 targets) | SV, 2.7k (about 2.5k reg) | regbus | reggen/ipgen | OT UVM (TL-UL) | `sifive_plic` | generic PLIC | Linux plic | claim/complete side effects; scales with sources |
| OT gpio (PULP port) | SV, 893 (771 reg) | regbus | reggen | OT UVM | fork, sparse | OpenTitan_GPIO | none | input sync and filter |
| OT spi_host | SV, 3.3k (2.0k reg) | regbus | reggen | OT UVM | upstream plus fork, near-complete | OpenTitan_SpiHost | Zephyr; Linux out of tree | single clock; command FIFOs |
| OT i2c | SV, 4.4k (2.7k reg) | regbus | reggen | OT UVM | fork, partial | OpenTitan_I2C | none upstream | open-drain, clock stretching, filters, host and target FSMs |
| irq_router | SV, 205 | regbus | reggen | simple | none | none | none | trivial; low software value |
| axi_vga | SV, 1.2k | regbus plus AXI master | reggen | simple | none | none | Linux simplefb | DMA fetch plus timing FSM |
| iDMA | SV, about 6k | regbus plus AXI | PeakRDL | monitors | none | none | none | heavily parameterised |
| riscv-dbg | SV, 2.8k | AXI/OBI plus DMI | hand-written | tb plus OpenOCD | fork `jtag-dm` | — | OpenOCD | **JTAG clock-domain crossing** |
| serial_link | SV, 3.3k | AXI | PeakRDL | several | none | none | none | **DDR, per-channel receive clocks** |
| USB OHCI | generated Verilog, 18.6k | AXI | Spinal | — | upstream sysbus-ohci [S] | — | Linux ohci-platform [S] | **PHY clock domain**; netlist-style |

### OpenTitan Earlgrey

All Apache-2.0, all TL-UL, all with reggen registers and UVM DV [P]. Pin the
revision: at HEAD, pwm, pattgen and flash_ctrl are gone and rram_ctrl, i3c and
others have been added, while the lowRISC QEMU fork targets `earlgrey_1.0.0`.

| Block | Total lines (reg) | QEMU | Renode | Driver | Hazards |
|---|---|---|---|---|---|
| uart | 2,444 (1,791) | upstream ibex_uart; fork near-complete (no RX timeout or break) | OpenTitan_UART | Zephyr | RX sync |
| rv_timer | 797 (638) | upstream ibex_timer; fork near-complete | OpenTitan_Timer | — | none |
| gpio | about 860 hand-written | fork sparse | yes | — | filters |
| spi_host | 3,359 (1,793) | upstream plus fork near-complete | yes | Zephyr | — |
| i2c | 6,743 (3,722) | fork partial | yes | — | as for the PULP port |
| pattgen | 1,236 (923) | none | — | — | simple |
| aon_timer | 1,517 (1,270) | fork near-complete | yes | Zephyr | **aon clock-domain crossing** |
| spi_device | 21.8k | fork | yes | — | **SPI clock domain** |
| usbdev | 11.6k | fork partial | — | — | **48 MHz domain, analog** |
| sysrst_ctrl / adc_ctrl | 7.1k / 4.3k | — | sysrst only | — | **aon domain; analog** |
| rv_plic (Earlgrey) | 17.3k, mostly reg | sifive_plic / fork `ot_plic_ext` | OpenTitan_PLIC | — | — |
| aes, hmac, kmac, otbn, csrng | large | fork near-complete | yes | — | masking, entropy; poor first targets |

### Other sources

- **CVA6 APU** (`corev_apu`):
  - Its peripherals are the old LGPL apb_uart, an older PLIC, apb_timer, a
    CLINT (307 lines, AXI-Lite), riscv-dbg and ariane-ethernet.
  - Its SPI and GPIO are Xilinx `axi_quad_spi` and `axi_gpio`. These are
    proprietary and cannot be lifted.
  - It has no QEMU or Renode machine. It is a weaker target than Cheshire.
- **zero-day-labs riscv-aia** (Apache-2.0 WITH SHL-2.1):
  - SV, about 1.9k lines; the APLIC is configured over regbus and the IMSIC
    uses AXI.
  - Registers are hand-written; DV is cocotb.
  - Supported by upstream QEMU (aplic, imsic), Linux and Zephyr. Renode has
    no model.
  - Its authors say it is "not formally verified".
- **zero-day-labs riscv-iommu:**
  - About 9.7k lines of SV, tested with a bare-metal suite plus Linux.
  - Supported by upstream QEMU (`riscv-iommu-sys`) and Linux.
  - Lift it late.
- **LiteX** (BSD-2, Migen):
  - Small peripherals: uart 461 Python lines, timer 68, gpio 81, i2c 208,
    spi 222.
  - Renode has models for all of them, and Linux and Zephyr drivers are
    upstream. There is no QEMU model.
  - Because it is Migen, lifting means working from the generated Verilog or
    the Migen AST.
- **freecores:**
  - uart16550: Verilog, about 1.65k lines, Wishbone, LGPL, last commit 2004.
    It works with QEMU, Renode and the 8250 driver.
  - i2c (ocores): 1.0k lines, a BSD-style licence, Linux `i2c-ocores` and a
    Renode model; no QEMU model.
  - spi: 517 lines, LGPL; no driver or model found.
- **NEORV32** (VHDL, BSD-3): fw-hdl has no VHDL front end, so treat it as a
  reference only.

## 3. Ranked shortlist for lifting

1. **obi_uart (Cheshire).** Small. Checkable against QEMU's 16550, Renode's
   NS16550 and the 8250 driver; Cheshire boots Linux on it. The Formality
   precedent comes from its predecessor.
2. **pulp clint (Cheshire).** 459 lines with PeakRDL registers; Linux and
   OpenSBI drivers; QEMU and Renode models. The only crossing is the
   `rtc_i` synchroniser.
3. **OT rv_timer.** Under 800 lines, with UVM and QEMU and Renode models.
   It isn't in Cheshire, but it is the cleanest proof of the reggen lift
   path.
4. **OT gpio (Cheshire).** About 120 lines of logic plus reggen.
5. **rv_plic (Cheshire's configuration).** Almost entirely reggen output, the
   standard Linux driver, QEMU, Renode and UVM. It exercises a parameterised
   generator.
6. **OT uart (Earlgrey).** A second UART with a different register map, and
   a direct comparison with the fork's "near-complete" model.
7. **OT spi_host (Cheshire).** UVM, QEMU, Renode and Zephyr. Cheshire's Linux
   uses it for the SD card.
8. **OpenCores i2c (ocores).** 1k lines, a mainline Linux driver and a
   Renode model.
9. **OT i2c (Cheshire).** Harder: filters and clock stretching.
10. **zero-day-labs APLIC.** The AIA path for a future Cheshire.
11. **axi_vga.** No model exists, so a generated one would be new.

**Defer:** riscv-dbg, serial_link, usbdev, spi_device, aon_timer,
sysrst_ctrl, USB OHCI, iDMA, the IOMMU and the crypto blocks. Each has
clock-domain crossings, analog, generated code or a large size.

**Reusing OpenTitan DV.** The PULP ports replace TL-UL with `reg_req_t` and
strip countermeasures, through patches in opentitan_peripherals. The OT UVM
environments therefore need a TL-UL-to-regbus shim, or the upstream TL-UL
versions should be lifted instead [U, inference].

## 4. Does Cheshire have an emulation platform?

- **Upstream:** no. Upstream QEMU `hw/riscv` has no Cheshire, Carfield or
  Ariane machine. Renode's `platforms/` has no cheshire, carfield or cva6
  platform, and the Cheshire repo mentions neither tool [P].
- **Forks:** not searched [U].
- **Building one:** most Cheshire peripherals already have stock QEMU models
  (16550, CLINT, PLIC). The gaps are the OT i2c, spi_host and gpio, axi_vga,
  serial_link and iDMA [U, inference].

## 5. Licences

- **QEMU is GPLv2-only overall.** Apache-2.0 is generally held to be
  GPLv2-incompatible [S], and SHL-0.51 and SHL-2.1 are Apache-based [P].
  - A QEMU model *generated from* Apache or SHL RTL is plausibly a
    derivative. It cannot go upstream unless it is relicensed or the owners
    dual-license [U, legal judgement].
  - lowRISC's fork models are hand-written GPLv2.
- **Renode is MIT.** Generated models derived from Apache or SHL IP can go
  there, with notices kept. **This is the cleaner target.**
- **LGPL:** freecores uart16550 and spi, and the old apb_uart. Lifted
  versions stay LGPL. Prefer Cheshire's SHL obi_uart.
- **Permissive:** ocores i2c (BSD-style), LiteX (BSD-2), NEORV32 (BSD-3),
  OHCI (MIT).
- **Unclear:** zero-day-labs "Apache-2.0 WITH SHL-2.1" (the IOMMU's licence
  file is misnamed `LICENSE.Solerpad`). serial_link ships both licences, so
  check the per-file SPDX headers.
- **Not liftable:** the Xilinx IP in the CVA6 APU.

## Sources

- **Cheshire and its dependencies:**
  - https://github.com/pulp-platform/cheshire
  - https://github.com/pulp-platform/carfield
  - https://github.com/pulp-platform/apb_uart
  - https://github.com/pulp-platform/obi_peripherals
  - https://github.com/pulp-platform/clint
  - https://github.com/pulp-platform/opentitan_peripherals
  - https://github.com/pulp-platform/irq_router
  - https://github.com/pulp-platform/axi_vga
  - https://github.com/pulp-platform/serial_link
  - https://github.com/pulp-platform/iDMA
  - https://github.com/pulp-platform/riscv-dbg
- **OpenTitan:**
  - https://github.com/lowRISC/opentitan (`hw/top_earlgrey/data/top_earlgrey.hjson`)
  - https://github.com/lowRISC/qemu (`docs/opentitan/ot_earlgrey.md`)
- **Emulators:**
  - https://gitlab.com/qemu-project/qemu (`hw/riscv/opentitan.c`)
  - https://github.com/renode/renode-infrastructure
  - https://github.com/renode/renode
- **Other IP:**
  - https://github.com/openhwgroup/cva6
  - https://github.com/zero-day-labs/riscv-aia
  - https://github.com/zero-day-labs/riscv-iommu
  - https://github.com/enjoy-digital/litex
  - https://github.com/freecores/uart16550
  - https://github.com/freecores/i2c
  - https://github.com/freecores/spi
  - https://github.com/stnolting/neorv32
- **Operating systems:**
  - https://github.com/torvalds/linux
  - https://github.com/zephyrproject-rtos/zephyr
