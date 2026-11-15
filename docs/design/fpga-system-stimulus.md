# System-level stimulus for FPGA designs: market approach

Draft, 2026-11-15. This note follows `pitch.md` (*Who this is for*, item 4,
"a testbench for your FPGA design") and the evidence in
`research/emulation-traffic-generators.md` §8. Claims about competitors and
communities that the research did not cover are marked **[U]** and need a
research pass before they go into the pitch.

## 1. The offer in one sentence

Testbench hardware you drop next to your FPGA design: it drives and checks
the interfaces a processor can't reach, at line rate and with cycle-level
control. It is chosen by scenarios written in Python or SV, and it comes from
the same source as your simulation testbench.

## 2. Product shape

It has five layers. Each one reuses something the family already plans:

| Layer | What it is | Comes from |
|---|---|---|
| Transport | Synthesizable transactors for AXI4, AXI4-Stream and AXI-Lite: drive, receive, backpressure | `fw-proto-axi` (and an AXI-Stream kit) |
| Payload | Domain generators and checkers that ride on the transport: packets, video frames, sample streams, memory traffic | New fw-hdl collateral (the traffic-generator demo is the first) |
| Impairment | An in-line block on a stream: drop, delay, duplicate, corrupt, reorder, throttle | New. A processor cannot do this at all |
| Observation | On-chip checkers (sequence, CRC, ordering, latency) and statistics and coverage counters | fw-hdl-dv checkers, synthesized |
| Scenario | Host side: chooses profiles, builds descriptor chains, reads results | fw-hdl-dv (Python flavor on the board's Arm cores or a PC; SV in simulation) |

**Three ways to insert it:**
1. *Replace a source.* A generator stands in for a MAC, camera or ADC, so
   the design runs before the real interface is up.
2. *Loopback.* Inject at the transmit side and check at the receive side.
3. *In-line.* Pass real traffic through, adding impairments and observation.

**Packaging matters as much as the logic.** FPGA engineers integrate through
vendor block-design tools: Vivado IP Integrator, Quartus Platform Designer,
Lattice Propel. Ship each kit as a packaged IP block (IP-XACT, plain Verilog
inside), with a Linux userspace driver and a Python API. Following the
"build with fw-hdl, ship plain SV" principle, the user never needs fw-hdl to
use a kit. They need it to write new collateral or extend a kit.

**Debug build and production build.** The elaboration-time factory swaps the
collateral in and out. That is worth showing explicitly, because the first
FPGA-team objection will be "it costs me LUTs in production".

## 3. Protocols, in priority order

**The key choice is to target the client side of vendor IP, not the PHYs.**
FPGA designs meet the outside world through vendor hard or soft IP (Ethernet
MACs, PCIe DMA, MIPI receivers, JESD204 cores, memory controllers), and nearly
all of these present **AXI4-Stream or AXI4** to the user logic. So:
- generating at the AXI level reaches every domain;
- we never build or certify a PHY;
- the domain value lives in the payload layer.

| Tier | Protocols | Why |
|---|---|---|
| 1. Universal | AXI4-Stream (`tvalid/tready/tlast/tuser/tkeep`), AXI4 memory-mapped, AXI-Lite | In nearly every AMD design and many Intel and Lattice ones. An AXI-Stream generator and checker with programmable backpressure is useful to everyone on day one |
| 2. Domain payloads on AXI-Stream | Ethernet frames (MAC client side, 10/25G); video (the AMD AXI4-Stream video convention: start of frame on `tuser`, end of line on `tlast`); sample streams (JESD204 and RF data converter transport side) | One transport, three large FPGA domains |
| 2. Domain payloads on AXI4 | Memory traffic (DDR and HBM through the vendor controllers); PCIe DMA descriptor rings (QDMA/XDMA-style card side) | The traffic-generator demo; accelerator cards; ties to the emulation story |
| 3. Low-speed and niche | UART, SPI, I2C, CAN-FD (fw-proto kits partly exist); SpaceWire, MIL-STD-1553, ARINC 429 | Easy, but low value for line-rate stimulus. The aerospace protocols matter only if the aerospace domain is pursued (§4) |

The tier-1 kit set:
- `axis-gen` / `axis-chk` (with backpressure and impairment);
- `aximm-tg` (the demo generator);
- `axi-perf` (latency histograms and throughput).

## 4. Domains

| Domain | The pain on-board stimulus addresses | Fit | Competition and risk |
|---|---|---|---|
| **Networking and packet processing** (SmartNICs, network appliances, low-latency trading) | Line-rate traffic with flow mixes, bursts and malformed packets; external testers are expensive boxes [U]; latency must be measured precisely | Strong. AXI-Stream packets, impairments and latency histograms are exactly this. The KR260 has SFP+ for a loopback demo | Ixia/Spirent at the high end [U]; DPDK/TRex software generators [U]; teams' own packet generators |
| **Video, imaging and vision** (cameras, machine vision, broadcast) | Frame sources before the sensor works; resolution and timing corners (blanking, mode changes); backpressure through the pipeline; per-frame CRC checks | Strong. The AXI4-Stream video convention is standard, and the KV260 is a vision kit | Vendor test-pattern IP (fixed-function) [U]; MathWorks Vision HDL flows [U] |
| **Memory and accelerators** (data-center cards, compute offload) | Kernel and memory-system performance without the host as bottleneck; DMA-ring stress | Strong. This is the demo, and it links to the emulation story | Vendor traffic generators (shallow); Vitis profiling [U] |
| **Wireless, SDR and DSP** (RFSoC, radar) | Synthetic waveforms in place of the ADC; checking DSP output at sample rate | Medium. The payload is signal processing, and the value is in waveform content | MathWorks is entrenched (HDL Coder, HDL Verifier) [U]. Hard to displace |
| **Aerospace and defense** (DO-254) | DO-254 requires testing on the target hardware for the higher assurance levels; requirements-based tests run at speed | Potentially very strong. "Same test in simulation and on hardware" is close to what the certification process asks for [U] | Aldec's DO-254 compliance tool set already runs simulation vectors on target hardware [U]. Long sales cycles. Qualification of the tool itself |
| **ASIC prototyping on FPGA** (HAPS, S2C, custom boards) | The emulation problem at higher clock rates: traffic generators for performance runs | Strong. This is the same collateral as the emulation story | Prototyping vendors' own transactor libraries [U] |
| **Industrial and automotive** (TSN, EtherCAT, motor control) | Deterministic timing tests | Weak to medium; smaller and more fragmented | Protocol-specific vendors |

## 5. Recommendation

**Go first with the stream-and-memory core plus two domains, networking and
video:**
- both are AXI-Stream, so tier 1 serves both;
- both have a real line-rate and backpressure need that C on a processor
  cannot meet;
- both have a cheap demo board (KR260 for networking, KV260 for vision);
- MathWorks is less entrenched there than in DSP.

Keep memory and accelerators going as the emulation-linked demo already
planned.

**Watch two opportunities without leading with them:**
- *Aerospace (DO-254).* The fit is unusually good and the value is high, but
  sales are slow, there is an incumbent, and tool qualification is a
  project in itself. Do a research pass and interviews before committing.
- *ASIC prototyping.* This is the emulation story again and comes nearly for
  free once the traffic-generator collateral exists.

**Defer** wireless and DSP (MathWorks) and industrial (fragmented).

## 6. Channels

- **cocotb FPGA users.** "The scenario you run in simulation now runs on the
  board" is the hook. It extends the cocotb path from
  `featherweight-ip-strategy.md` §5.
- **PYNQ and Kria users [U].** PYNQ is AMD's existing Python-on-Zynq framework
  (overlays driven from Jupyter notebooks). Kits shipped as PYNQ overlays,
  driven by the Python flavor of fw-hdl-dv, reach users who already script
  the board from Python.
- **The vendor IP catalogs.** Packaged IP blocks that show up next to the
  vendor's own traffic generator.
- **Open-source FPGA projects** (Corundum, taxi, LiteX) [U]. They verify in
  simulation with cocotb. On-board kits that reuse those flows would be a
  visible contribution.

## 7. Demo ladder

| Step | Board | Shows |
|---|---|---|
| 1 | Any (simulation, then KV260) | `axis-gen` and `axis-chk` around a small user block (a FIR filter or a packet parser): backpressure sweep, injected fault caught, same scenario in simulation and on the board |
| 2 | KV260 | The memory traffic generator (`demo-traffic-generator.md`) |
| 3 | KR260 | 10G Ethernet loopback over SFP+: line-rate flow mixes, impairment, latency histogram, against a software packet generator on the Arm cores |
| 4 | KV260 | Video pipeline: frame source in place of the camera, mode-change corners, per-frame CRC checking |

Steps 1 and 2 serve every domain. Steps 3 and 4 are the domain proofs.

## 8. Open questions

- **Open source or commercial?** Which layers are open (transport,
  scenarios) and which, if any, are paid domain packs? This decides whether
  the vendor IP catalogs and PYNQ are channels or competitors.
- **Who writes the payload generators?** If most FPGA users only configure
  kits, writing collateral in fw-hdl is a power-user feature. Then the
  pitch to FPGA teams is "use the kits", and the fw-hdl pitch goes to those
  who extend them.
- **Intel and Lattice.** AXI dominates on AMD devices. Intel's Avalon-ST and
  Avalon-MM need either their own transport kits or reliance on AXI bridges.
- **Research needed:** PYNQ's adoption, the Aldec DO-254 tool set, how
  network test is done during FPGA development, the vendor test-pattern IP,
  and the MathWorks position in each domain.
