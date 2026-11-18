# The hardware/software interface in fw-hdl (exploration)

Status: **exploration, 2026-11-16.** This is research plus a proposal. Nothing
here is decided. The open decisions are in §9.

Related: [project-architecture.md](project-architecture.md) (repository
families), [core-domains.md](core-domains.md) (clock and reset domains, domain
drivers), [ip-library-focus.md](ip-library-focus.md) (the platform kit, the C
view, device trees), [verification-support-review.md](verification-support-review.md)
(the register model, the system model V7),
[dv-scenario-semantics.md](dv-scenario-semantics.md) (scenarios), and the DVCon
2027 paper draft *Separating Device Operations from Test Scenarios for Twice the
Portability* (`~/data/notes/2027/DVCon/paper_draft/ieee-paper/main.tex`).

## User benefit

**IP author or IP DV engineer**
- You write the programming sequences once, next to the RTL, in the same
  language.
- They are proved against the RTL, not only exercised by tests.
- They ship as C, SV, Python and a device-tree binding, with nothing written
  twice.

**Firmware, SoC or emulation integrator**
- You get operation libraries that already match the RTL, plus the device tree
  and init order derived from the assembled design.
- You write a plain sequential `boot()`. The tool finds which waits can overlap
  and emits one bare-metal poll loop, an interrupt-driven state machine, or RTOS
  threads.
- That generated code comes with a check that it behaves like the sequential
  version.
- On a large chip you don't wire initialization content by hand. Each IP
  contributes its init, suspend and resume content, which is gathered into
  phases automatically.
- You are told when content is unused, missing, conflicting, or out of order.
- A generated manifest says why each step runs where it does.
- Sequences that break clock, reset or power rules are flagged statically,
  for every flow (boot, suspend, resume, shutdown). No power-aware simulation
  is needed.

**DV**
- The same operations are the realization layer of every test, so regressions
  verify them as a side effect.
- Composition safety (register races, W1C clears, ordering) is checked
  statically, with a randomized-interleaving mode for simulation.

## 0. Status

| Step | State |
|---|---|
| Research: prior art in interface description, co-verification, firmware composition | done (§2, §3) |
| Inventory of what fw-hdl and Zuspec already have | done (§4) |
| Proposal (§5–§8) | draft for discussion |
| Composition at scale (§7.4) and power/clock sequencing (§7.5) | added 2026-11-16, draft |
| Flow: name, RAL placement, MMIO API, binding, executors, creation (§4a) | added 2026-11-16, draft |
| Standard constructs and the executor socket (§4b) | added 2026-11-16, draft |
| Descriptors and command queues (§4b.5) | added 2026-11-16, draft |
| DV-authored operations as core methodology (§4a.7) | decided 2026-11-16; details draft |
| Critical review and adoption strategy (§8a) | added 2026-11-16; proposes subordinating this plan to the lifting/assembly vehicle and cutting scope |
| Decisions (§9) | open |

---

## 1. The problem

The hardware/software interface (name open, §4a.1; not "HSI") is a contract with three parts. Today
each part lives in a different artifact, and none of them is checkably linked to
the RTL.

| Part | What it says | Where it lives today | Link to RTL |
|---|---|---|---|
| **Structure** | registers, fields, access policy, address map, IRQ lines, clocks/resets/power a device needs | SystemRDL/IP-XACT/hjson/SVD; device tree + YAML bindings | by construction for registers only; DT consistent only where one generator emits both (diplomacy, LiteX, Vivado DTG) |
| **Behavior** | how to make the device do something: programming sequences, waits, interrupt handling, pre/postconditions | UVM sequences, PSS exec blocks, DIFs/HALs, Linux drivers: N hand-written copies | simulation coverage at best (OpenTitan DIFs run in chip-level DV); otherwise none |
| **Composition** | how operations from many IPs combine: init order, sharing, concurrency | Linux fw_devlink / deferred probe, Zephyr init levels, hand-written boot code, PSS `parallel` | none |

Data points (sources in §10):
- About 38% of Linux driver bugs are mismatches with the device spec, and
  about 40% are device-protocol violations (Ryzhyk, EuroSys'09).
- Drivers have 3–7× the kernel's error rate.
- First-silicon success fell to 24% (2022) and lower in 2024. Firmware is a
  tracked respin cause, and spec errors are the leading root cause.

The DVCon paper fixes *behavior* duplication: one operation model in PSS,
projected to every consumer. This document asks what becomes possible when the
contract is captured **in the same language as the hardware**, inside the same
elaborated design. That makes three things possible:

1. **Co-verification.** Operations are *proved* against the RTL, not only
   exercised.
2. **Derivation.** The structure (device tree, bindings, init order, effect
   footprints) falls out of the assembled design instead of being written.
3. **Composition.** Independently authored operations are combined and
   scheduled by a compiler that knows their exact hardware footprints.

## 2. Prior art: description and co-verification

Each existing system covers one part of the contract. None links all of them to
the RTL.

| Work | Captures | Verifies | Can't |
|---|---|---|---|
| SystemRDL/PeakRDL, IP-XACT, OpenTitan reggen | register layout, access policy, side-effect enums | the register block itself (RAL bit-bash/reset) | sequences, cross-register rules, post-write device behavior |
| CMSIS-SVD → svd2rust → typestate HALs | fields, enums, IRQ numbers | field misuse at compile time; hand-encoded ordering via typestate | anything against RTL; vendor SVDs need patch sets (stm32-rs) |
| OpenTitan DIFs + chip-level DV | hand-written C driver primitives | DIFs exercised in DV sim, Verilator, FPGA, silicon from one binary | formal link; sequences aren't in the spec |
| Chisel diplomacy / LiteX / Vivado DTG | address map, IRQ routing → DTS by construction | DT ↔ RTL addresses/IRQs (by construction) | register semantics, sequences, binding parameters |
| dt-schema, Zephyr edtlib, Linux fw_devlink | DT vs binding schema; dependency edges from phandles | schema conformance; init order (Zephyr static, Linux runtime) | DT values vs RTL generics; ordering *within* a device |
| **ILA / ILAng** (Malik) | device as MMIO "instructions" with state updates | ILA ↔ RTL refinement; firmware against ILA | ILA is hand-written beside the RTL; no DT, no driver output |
| **Termite / Termite-2** (Ryzhyk, Walker) | formal device spec + OS spec | synthesizes drivers (game-based) | the device spec cost as much as the driver; never reached production |
| v2c / CoVerif / Btor2C (Kroening et al.) | RTL translated to C, model-checked with firmware | assertions over HW+FW | state explosion; no intended-sequence contract |
| **Velosiraptor** (ASPLOS'25) | one spec → simulated MMU HW + verified OS config code | by synthesis | limited to translation units |
| **PSS tools** (Perspec, Trek, inFact) | action graphs + HSI layer → bare-metal C tests | tests run on RTL | no tie to shipping code; correctness = self-checking C; polling invisible to tool |
| Devil, NDL, HAIL | typed register IDLs | accessor usage | separate artifacts that drifted; dead |
| Sockeye / decoding nets (ETH) | formal address decoding, interrupt routing | page tables, routing configuration | not device behavior |

**The pattern.** Formal approaches (ILA, Termite, Velosiraptor) die or stay
narrow because the device spec is a *second* artifact written beside the RTL.
Industrial approaches (DIFs, diplomacy, PSS) stay consistent only where one
generator emits everything, and then they capture structure, not behavior.
In fw-hdl the device spec is the hardware source. That removes the cost that
killed the formal line of work.

## 3. Prior art: firmware composition and scheduling

The user's example: three teams each write an init operation that polls. The
integrator calls all three. Today that becomes three sequential poll loops. The
loops could overlap, but nobody can see that at authoring time.

| Work | Mechanism | What we take from it | Gap |
|---|---|---|---|
| **Rust async / Embassy** | each `async fn` → fixed-size state machine; `join!`/`select!` compose statically; interrupt or WFE wakers | ops as stackless resumable state machines; one `await` backed by IRQ *or* poll | no hardware-effect analysis; borrow checker covers memory only |
| Protothreads, C++20 coroutines | stackless continuations in C/C++ | emission target for bare-metal C | no analysis |
| **Esterel / Lustre / SCADE, Céu** | parallel composition compiled into one sequential step function; causality analysis rejects conflicts; `par/or` aborts the loser | the static merge; `par/or` = completion-or-timeout; reject rather than guess | conflicts are on declared signals, not on device registers |
| **RTIC** | tasks declare resources; compile-time priority-ceiling (SRP) analysis emits lock-free code | *declared footprint → conflict graph → generated synchronization* is the template | footprints hand-declared, per peripheral |
| Lingua Franca | declared ports/dependencies → deterministic schedule; bare-metal C | determinism by construction | not device-aware |
| Linux CCF/genpd, fw_devlink; Zephyr init ordinals | supplier→consumer edges from DT; refcounted clocks/power | derive edges from the hardware description; refcount shared supplies | runtime (Linux) or hand-chosen priorities (Zephyr) |
| PSS bare-metal realization | `parallel` → one thread per core + shared-memory barriers | multi-core partitioning | no merging of blocking actions on one core; resource claims coarse |
| Termite | driver synthesis | a warning: *composing* given sequences scales; *synthesizing* them doesn't | |

**What is new here, relative to all of the above:**
1. **Effect footprints derived from the hardware.** Footprints are computed at
   field granularity, with access kinds (W1C, RC, RMW, same-word coupling), from
   the register model and the assembled design. They are not declared by the
   author.
2. **Composition across independent authors.** The compiler sees sharing that
   only exists at integration: a shared clock-and-reset generator (CRG) or
   power-management unit (PMU) register, a shared IRQ mux, a common clock
   parent.
3. **Effectful reads are modeled.** A read of a read-to-clear (RC) or
   write-1-to-clear (W1C) status register becomes a shared event source that is
   demultiplexed to its waiters. No prior system models this.
4. **The schedule is checked against the RTL.** The composed schedule can be
   proved equivalent to the sequential reference on the RTL (§7.3).

## 4. What fw-hdl and Zuspec already have

**fw-hdl (root library; not yet in `packages/fw-hdl-spec`)**
- **Register classes:** `fw_reg_block`, `fw_reg #(T, W)` and watch-sets, in
  `src/fw_reg_*.svh`.
- **Python front end:** `python/fw/hdl/fe/reg_mapper.py` resolves offsets,
  masks and resets. `fe/reg_consumer.py` records hardware use of registers.
  `regmap.py` is a flat register IR.
- **Synthesizable register blocks and formal:** `emit/regblock.py` emits
  synthesizable regblocks plus a formal harness. `fe/mmio.py` lowers
  MMIO-driven FSMs.
- **Nothing in `packages/fw-hdl-*` yet.** There is no register construct, no
  interrupt construct, no C output and no device tree.

**Zuspec**
- **Register models (two):**
  - `zuspec-be-py` model: `RegFile`, `Reg[T]` (async write, RMW by dict),
    `AddressSpace`, `AddrHandle`, `MemIF` read/write 8–64.
  - `zuspec-dataclasses/mmr`: `@regfile`/`@reg`, with SystemRDL-style
    `onread`/`onwrite`/`stickybit` access enums.
  - The two need reconciling.
- **IR:** `DataTypeRegister`, `DataTypeAddressSpace`, `DataTypeAddrHandle`,
  `DataTypeEvent` (meant for interrupts), and the full PSS activity set
  (`activity.py`).
- **`zuspec-be-sw` C back end:**
  - `mmr/c_header.py` emits C headers. `mmr/py_driver.py` emits a typed
    Python driver.
  - `passes/mem_reg_lower.py` lowers register access to
    `SwRegRead`/`SwRegWrite`/`SwRegRmw`, in either ISS or BFM mode.
  - Also present: `activity_lower`, `async_lower`, and PSS→C.
- **Blocking processes to FSMs:** `zuspec-synth` proc lowering and `sprtl`
  turn `Await`-bearing processes into FSMs with `FSMRegRead`/`FSMRegWrite`
  operations.

**Docs:** device trees, the C view, a firmware HAL and interrupt modelling all
appear as *plans* (ip-library-focus, verification-support-review §4.6/V7,
automated-lifting). None is implemented.

**Takeaway.** Most of the *projection* machinery exists in Zuspec: C headers, a
register-access lowering, async lowering, and proc-to-FSM. What's missing is the
*semantic layer* that makes co-verification and composition possible:
operations as first-class IR objects with footprints, waits and contracts; a
platform model; and a register model in the new spec.

---

## 4a. Flow: how the interface is created and bound to the hardware

### 4a.1 Name

The name is open. **Don't use "HSI"**, which is taken twice in this space:
- **Vayavya Labs** calls its patented specification format "Hardware Software
  Interface (HSI) specifications". It drives their DDGen driver generator, and
  Vayavya led HSI standardization in Accellera's Portable Stimulus Working
  Group ([Vayavya HSI](https://vayavyalabs.com/solutions/virtual-platforms-systemc-modeling%e2%80%8b/),
  [DDGen](https://vayavyalabs.com/device-driver-generatorddgen/)).
- **AMD/Xilinx** uses "HSI" for its hardware-handoff Tcl API (`hsi::open_hw_design`,
  BSP and device-tree generation)
  ([AMD wiki](https://xilinx-wiki.atlassian.net/wiki/spaces/A/pages/18841693/HSI+debugging+and+optimization+techniques)).

Candidates (decision §9 #10):
- **"Programmer's model"** is the established, product-neutral term from Arm
  TRMs for exactly this content. Its weakness is the abbreviation: "PM" reads as
  power management, which §7.5 also uses.
- **"Device interface"** collides mildly with OpenTitan's DIFs (Device
  Interface Functions).
- **"Software interface"** is plain, but a "SWI" abbreviation reads as software
  interrupt.

Until a name is decided, this doc says *the software interface*.

### 4a.2 The layers, and where the RAL goes

A UVM RAL mixes three things, and this design separates them:
- a **register declaration**: fields, access policies, reset values;
- a **front-door accessor**: read, write and modify through a bus;
- **verification machinery**: a mirror, prediction, a backdoor, coverage,
  randomized values, and built-in reset and bit-bash sequences.

The first is shared by hardware and software. The second belongs to the
software interface. Only the third is DV.

```
           shared vocabulary  (fw-hdl-spec)
           register declarations · interrupt sources · MMIO API
                 │                                     │
   hardware side ▼                                     ▼ software interface
   regblock = MMIO *target*                 register accessors = MMIO *initiator*
   (generated; emit/regblock.py)            operations · lifecycle · contributions
   behavior consumes regs                   platform: per-executor address maps
   (reg_consumer: wait_change, set_rd)                 │
                 └──────── binding (4a.4) ─────────────┘
   DV (fw-dv): extends the accessors (mirror, prediction, backdoor, coverage,
               random values, reset and bit-bash sequences); calls operations
```

- **One declaration feeds both sides.** The hardware regblock is the MMIO
  target generated from it, and the software accessor is the MMIO initiator
  generated from it. They can't drift apart, and C2 (§7.3) checks the one
  thing they can't share: what the hardware behavior does with the values.
- **DV extends; it doesn't redeclare.**
  - The backdoor is derived from where the regblock emitter put the storage.
    This is the "backdoor without VPI" item in the roadmap.
  - Reset and bit-bash sequences are derived from the access policies.
  - A `uvm_reg` model is a projection, for UVM interoperability.
- **Firmware never depends on fw-hdl-spec.** It receives projections: C
  headers and accessors, operations, the device tree.

### 4a.3 The MMIO API

This is the paper's import API, made precise. It is the only way an operation
touches hardware, so it has to cover what firmware actually does:

| Group | Operations | Notes |
|---|---|---|
| Access | read/write 8, 16, 32, 64; byte enables | attributes: privilege, security (AxPROT-like), and an optional initiator ID |
| Block | burst read/write, incrementing (memory) or fixed address (FIFO port) | lowers to a loop, DMA, or a bus burst |
| Atomic | swap, fetch-add/and/or/xor/min/max, compare-and-swap | RISC-V A, AXI5 atomic transactions, CHI, PCIe AtomicOp |
| Exclusive | load-reserved / store-conditional pair | AXI exclusive access, LR/SC |
| Ordering | `barrier()`, read-back flush | posted writes must be flushed before polling (§8) |
| Errors | an access response (OK, slave error, decode error) | today `fw_reg_block_if` has no error path |

**What a path supports is derived, not assumed.** For each (executor, target)
pair, the platform (§7.1) knows the fabric path. From the bus kits, it knows
whether that path supports atomics, exclusives and 64-bit single-beat access,
and whether writes are posted. Register-level intent then lowers per path:

- `modify()` on a field becomes one of:
  - a write to a hardware set/clear alias, if the register has one;
  - an atomic memory operation (AMO), if the path supports atomics;
  - otherwise read + write. That form is non-atomic and is marked as such in
    the footprint (§7.2).
- A 64-bit read over a 32-bit APB path becomes two accesses, with a
  **tearing warning** if the register is a live counter (e.g. `mtime`).
- An atomic on a path that can't do one is an error, or it lowers to a
  software lock, whichever the platform policy says.

Today `fw_reg_block_if` (`src/fw_reg_block_if.svh`) has only `read_val`,
`write_val` and `size`. It is the seed of the MMIO target role. It needs byte
enables, a response, and the optional atomic and exclusive operations.

### 4a.4 Binding: yes, through transactors, using the protocol-kit pattern

The MMIO API is a class-level protocol with **initiator** and **target**
roles. That is exactly the role-API shape of a protocol kit
(core-protocol-kit-prep). Binding operations to hardware is therefore not a new
mechanism:

| Environment | MMIO initiator is bound to |
|---|---|
| class-level simulation (fast) | the regblock's target role directly: a zero-time call |
| SV simulation with RTL | a bus kit's initiator **transactor** (AXI, APB, OBI, Wishbone), through the kit's MMIO↔bus bridge |
| cocotb / Python | the same kit's Python transactor |
| DV backdoor | the regblock storage, located statically |
| fast C model | a direct call into the model's target role |
| bare-metal C | volatile pointers plus fences; atomics become ISA AMO instructions where the path supports them |
| Linux kernel / user space | `readl`/`writel` accessors; UIO or a PCIe BAR `mmap` |
| hardware sequencer | the operation lowered to an FSM (proc→FSM) driving an initiator port |

**Each bus kit adds one bridge, MMIO↔its protocol.** It needs no second
transactor, which respects "the kit owns the single transactor". Open
question: is MMIO built into the language like ready/valid (decision D4), or
is it a kit? It is the common denominator of every memory-mapped bus, so built
in is the likely answer (§9 #11).

### 4a.5 Executors: where operations run

An operation is written once. **Where it runs is a binding.** PSS calls the
thing it runs on an *executor*:

| Executor | Example | Projection |
|---|---|---|
| application CPU | the SoC's main core running Linux or bare metal | C for that ISA + platform headers |
| **management processor** | a power/security/system-control RISC-V subsystem | C for *its* core, against *its* address view |
| hardware sequencer | a boot or power sequencer, an FPGA testbed init engine | RTL via proc→FSM |
| testbench | UVM/fw-dv/cocotb | SV / Python |
| host | a PC over PCIe or JTAG, bring-up scripts | Python / C |

**Address maps are relative to the executor.** The platform derives each
executor's view from the fabric decode. The management processor may see a
peripheral at a different address, or see peripherals the main CPU cannot see.
Firewall and security settings are part of the same view. That makes access
rules ("only the management processor may touch the PMU") a static check.

**Behavior that lives on a hardware block.** When the operations live *on* a
management processor, the block's outward face is no longer registers. It is a
**service**: a mailbox or doorbell protocol, e.g. SCMI-style "set power domain
state". In this design a service is just another class-level API kit:
- **The initiator role** is what the main CPU's operations call. It is
  projected to C like any other operation.
- **The target role** is implemented by software: operations and contributions
  bound to the management-processor executor. Underneath, they use that core's
  MMIO view of the devices it controls.

This gives two-level interfaces with no new concepts: main CPU → service API →
management firmware → device registers. It also gives something more useful,
because **the hardware/software partition becomes a late binding:**
1. Early on, the service target is a class model. Firmware on the main CPU
   can start against it before any RTL exists.
2. Later it is firmware on the management core.
3. For a latency-critical service, it is the same operations lowered to a
   hardware FSM.

The same service-level tests run against all three, and the C4 equivalence in
§7.3 applies between them.

The composition compiler (§7.2) runs per executor. Ordering edges that cross
executors become service messages or barriers. The §7.5 checks span executors,
because domain state is global.

### 4a.6 How the interface is created

| Flow | Who | Steps |
|---|---|---|
| **Interface first** (architecture) | architect, with firmware | declare registers, interrupts, service APIs and operation *signatures* → a class-level target model gives firmware a platform before RTL → design implements the regblock (generated) and the behavior → DV/design fill in operation bodies → C1/C2 prove them |
| **Design first** | designer | the component declares its regblock and interrupts as it is built → the interface is published from the elaborated component → operations are added by the IP's DV |
| **Import / lift** | integrator, lifting | SystemRDL/hjson/IP-XACT import gives the register declarations (never hand-lifted) → operations are retrofitted from existing UVM sequences or drivers (the paper's retrofit) → existing tests now exercise them (C0) |

In all three flows the register declaration is the joint between hardware and
software. Every artifact on either side is derived from it or checked against
it.

**What this changes in the earlier recommendation.** The shared vocabulary
(register declarations, interrupt sources, the MMIO API) lives in
`fw-hdl-spec`, because both hardware and software use it. The software-interface
family holds the rest: accessors, operations, lifecycle, contributions,
services, executors, the platform view and projection configuration. It
depends on `fw-hdl-spec`. `fw-dv` depends on it and extends the accessors. The
RAL as such is no longer a DV artifact.

### 4a.7 Core methodology: the DV team writes the operations

**Decision (2026-11-16): this is part of the core DV methodology, not an
optional adoption path.** Every block DV environment puts its directed core
operations in an operations class under the subset described below. The
existing sequences call those operations, and the IP's programming cookbook is
generated from them. This holds whether the design was written in fw-hdl or is
existing SV. The fw-hdl-dv methodology documents it as the standard structure.

The common retrofit is a DV team that wraps existing SV RTL in an fw-hdl
component to get a simpler testbench. The wrap already provides the bus
transactor (an `fw-proto` kit), and the registers come from IP-XACT,
SystemRDL or hjson. The proposal: that team writes its core directed
operations (init, configure, start, wait for done, clear status, recover from
errors) as interface operations rather than as UVM sequences.

**What the DV team writes today.** Every block testbench has these operations,
hidden inside `config_seq`, `init_vseq` and driver helper tasks. They are the
first code written at bring-up and almost never randomized internally. Writing
them as operations costs little more, because the operation subset is
roughly what those sequences already use. Randomization moves to the
parameters, which is where it belongs (§6.4).

**The request DV already gets.** Emulation, firmware, SoC, and
post-silicon validation teams all ask the block DV team "how do I do XYZ on
this IP?" Today the answer is a UVM sequence. None of them can run it:

- *Emulation* wants it without UVM: on the emulated CPU, or as a synthesizable
  sequencer.
- *Firmware* wants a C function.
- *SoC DV* wants it on the SoC CPU.
- *Post-silicon* wants a script over the debug port.

Each team then reverse-engineers the sequence, and DV answers follow-up
questions. DV is already paying for portability, as a recurring support load
and as bugs where the copy diverged from the original.

**The adjustment is small.** DV keeps writing SV inside its existing
environment. The only change is to put the directed core operations in an
operations class, separate from the sequences, and keep to the subset there:

- decisions arrive as arguments (no `rand`, no `uvm_config_db` lookups);
- waits use `fw_await` with a timeout, not `#delay` or clock counts;
- register access goes through the interface accessors, and the operation
  never chooses the access path.

The access path is outside the operation model. Whether an access goes
frontdoor or backdoor is the register model's business, set by testbench
policy through the accessor binding (§4a.2, `fw-dv`): per test, per seed or
per register. The same operation runs either way, and the C, Python and
emulation projections simply have no backdoor binding.

A lint enforces the subset. The existing sequences randomize the arguments
and call the operations, so nothing else in the testbench changes.

**No wrap required for this.** The operations class needs an MMIO executor,
and one backed by the existing `uvm_reg_map` or bus sequencer works in an
unmodified UVM environment. The projections run offline through Zuspec. So
the entry cost is a class library plus a tool, not an fw-hdl wrap (this
lowers F3 in §8a). The wrap (below) adds the derived bus binding and formal.

**The answer becomes a link.** Each operation has a name, typed parameters
and a doc comment. From these, a per-IP *programming cookbook* is generated:
one entry per operation, each with the C, SV and Python projections, the
registers it touches, its waits, and the interrupts it uses. Every requester
gets something runnable on their side:

| Requester | Gets |
|---|---|
| Emulation | C on the emulated CPU, or the synthesizable-sequencer projection |
| Firmware | a C function over the generated headers |
| SoC DV | the same SV operation, or C on the SoC CPU |
| Post-silicon | Python over an MMIO backend on the debug port (e.g. OpenOCD) |

Two lines in the cookbook are recorded, not authored: which regressions
exercised each operation (C0) and whether it is proved on the RTL (C1). The
requester can see how far to trust it.

**What the DV team gets, beyond portability:**

| Benefit | Mechanism | Why the DV team cares |
|---|---|---|
| Faster bring-up | MMIO binding derived from the wrap's transactor; no adapter, predictor or map setup; typed fields; `fw_await` with timeout and interrupt binding | first directed test runs with the register file and a handful of operations, not a RAL environment |
| Stimulus/scenario split | tests are "choose parameters, call operations"; randomization and coverage sit on operation parameters and return statuses | functional coverage of the programming model comes almost for free: which operations, with which parameters, returning which statuses |
| Checks from derived facts | the footprint (§6.2) gives: a test touching registers no operation declares; RMW on W1C/RC fields; reads of RC fields outside an operation | catches testbench bugs that today show up as flaky mismatches |
| Contracts become assertions | pre/post conditions (§6.3) generate SV assertions and scoreboard checks around each call | a self-checking layer that the test author did not write |
| Safe concurrent stress | the conflict graph (§7.2) says which operations may overlap; a generated stress sequence interleaves non-conflicting operations at random | concurrency testing without hand-built virtual-sequence locking; an overlap that breaks the design but passes the graph is a design bug, not a test bug |
| Fast configuration | a testbench policy, not part of the operation: for an operation with no waits and a known footprint, the policy can apply its final register state by backdoor (zero sim time) and keep the frontdoor path for some seeds | long init sequences stop dominating sim time; the equivalence is derived, not hand-maintained |
| Debug at operation level | operation begin/end, parameters and status are recorded as transactions and waveform annotations | triage reads "`dma.transfer_single(ch=2)` timed out waiting for `csr.done`" instead of a register trace |
| Formal on existing RTL | C1/C2 (§7.3) need only the operation, the transactor and the RTL, all of which the wrap already has | the team can prove its init/transfer operations on the RTL it was given, without rewriting it |
| Spec bugs found early | the operations are an executable programming guide that firmware can review before RTL freeze; awkward operations (races on clear, missing status bits, no safe abort) surface as review comments | interface bugs found in block DV instead of in post-silicon bring-up |
| Vertical reuse | the same operations run in subsystem and SoC tests on the CPU (C projection) or the testbench | the SoC DV team, usually a different team, does not rewrite block init |
| Less support load | "how do I do XYZ" is answered with a cookbook link, and the copies other teams would have made never exist | fewer interruptions, and fewer bugs filed against someone else's divergent copy |

Two of these are portability under another name: vertical reuse and the
reduced support load. They are listed because DV already pays for them today.
The others pay off inside the block testbench, before any other team consumes
the operations. That is the argument for the DV team: it does this work
anyway, and writing it in this form buys checks, coverage, speed, debug and
fewer support requests.

**Coexistence with UVM.** The SV projection of the operations is callable from
an existing UVM sequence, and `fw-dv` provides the RAL-compatible accessor
(§4a.2), so a team can convert one sequence at a time. Existing tests exercise
the converted operations (C0) with no other changes.

**Where the case is weak:**

- *Testbench-only habits leak in.* DV-written operations may rely on
  zero-delay polling, a reset state that firmware never sees, or behavior that
  happens to hold only under a backdoor policy. One example is skipping a wait
  that is needed when the access really goes over the bus. The executor
  binding (§4a.5) flags zero-delay polling when the operation is projected to
  C. Running some seeds under a frontdoor policy catches dependence on the
  backdoor. Firmware review catches the rest. Until reviewed, the
  operations should be marked "DV-authored, unreviewed" in the platform view.
- *Register metadata quality.* Footprint checks are only as good as the
  imported access kinds. IP-XACT exports often mark W1C fields as RW. The
  import should report fields with suspicious access kinds rather than trust
  them.
- *Interrupt binding is manual on a retrofit.* Nothing in plain SV says which
  pin carries which interrupt source. The wrap has to declare it; this is a
  few lines per IP.
- *Sunk RAL investment.* Teams with a mature UVM RAL and sequence library get
  less from bring-up speed. Their gain is the checks, the stress and the
  downstream deliverable, so the pitch to them should lead with those.

**Recommendation.** Make this the standard structure of a block DV
environment (decided above):
1. import the registers;
2. write the operations;
3. call them from the testbench;
4. generate the cookbook.

The wrap is optional and adds the derived bus binding and formal. Pilot on a third-party SV IP with an existing UVM
environment (separate from the `wb_dma` design-first pilot) and measure lines
of DV code replaced, bugs found by the derived checks, and sim time saved by
backdoor lowering.

## 4b. Standard interface constructs and the executor socket

### 4b.1 The idea

If operations bind to executors (§4a.5), then the hardware model of a
management core provides a **"firmware goes here" box**: an *executor socket*.
The socket has a defined boundary: what the payload can see and use.

Around the socket, and between any two parties that talk across the
hardware/software line, the same handful of constructs recur on every chip:
interrupts, doorbells, mailboxes, shared memory, rings, hardware locks, timers.
Today each one is rebuilt per project. The rebuild covers the registers, the
interrupt wiring, the DT nodes, the driver glue and the protocol conventions,
and each rebuild carries its own bugs.

The proposal is to **make these standard constructs with defined semantics**:
- They are part of the language's library, as ready/valid is for hardware.
- Each construct is an API kit with roles, a normative semantics, a
  conformance suite and several realizations.
- The tools understand them. A mailbox send is an ordering edge between
  executors, a hardware lock is a lock in the conflict analysis, and an
  interrupt is an event source for waits.

### 4b.2 Precedents

| Precedent | What it standardizes | Lesson |
|---|---|---|
| **virtio** (OASIS) | the device/driver split over shared-memory *virtqueues*, notifications, feature negotiation | one abstract semantics with many implementations: hypervisor software, hardware (SmartNICs, FPGA), simulators. The closest model for "construct with HW or SW realization" |
| **OpenTitan "comportable IP"** | every IP uses the same interrupt register triple (`INTR_STATE`/`INTR_ENABLE`/`INTR_TEST`), alerts, bus and register conventions | conventions make generic tooling, DV and drivers possible. Here they are *types*, not conventions |
| Linux mailbox / hwspinlock / remoteproc / rpmsg; OpenAMP | client APIs for mailboxes, hardware locks, loading and booting a remote core, messaging over virtio rings | the software-side API shapes firmware teams already know; the projection targets |
| Arm MHU, SCMI shared-memory transport | hardware mailbox + doorbell; a message protocol over shared memory + doorbell | the same "channel" is realized in hardware or over shared memory |
| System Device Tree + Lopper | per-execution-domain views of one platform | the executor socket's view is a projection |
| PSS executors | where actions run | the binding concept, with no socket contract |
| NVMe / AHCI queues | submission/completion descriptor rings with doorbells | ring semantics: ownership, wraparound, doorbell coalescing |

### 4b.3 The catalog (first cut)

| Construct | Abstract semantics | Hardware realization | Software realization / projection | What tools know about it |
|---|---|---|---|---|
| **Interrupt source** | level/edge event with pending, enable, ack (the triple, as a type) | the register triple + IRQ output, generated | ISR entry + ack operation; Linux/Zephyr IRQ binding | event source for waits; C3 ack contract (§7.3); DT `interrupts` |
| **Interrupt controller** | routing, priority, targets per executor | PLIC, ACLINT, AIA (the platform kit's lead; ip-library-focus) | controller driver; the per-executor vector table | which executor sees which source; routing derived for the DT |
| **Doorbell** | a one-bit notify from A to B | write register → IRQ on the other side | `ring()` / an ISR | a cross-executor ordering edge |
| **Message channel (mailbox)** | typed messages, depth, optional response, ordering | hardware FIFO + doorbell (MHU-like) | shared-memory ring + doorbell; Linux mbox client, Zephyr mbox | ordering edge; overflow and lost-message checks; wait cycles across executors (deadlock) |
| **Shared region** | memory shared between executors, with ownership and coherency attributes | RAM/TCM on the fabric | linker sections; cache-maintenance operations inserted where the path is non-coherent | ownership in the footprint; missing cache maintenance is a static error |
| **Descriptor ring** (§4b.5) | producer/consumer queue of descriptors with ownership transfer; four disciplines (ownership bit, index + doorbell, phase bit, chain) | DMA engine consuming descriptors | ring operations; virtio driver/device | ownership races; wraparound; doorbell coalescing |
| **Hardware lock** | mutual exclusion across executors | hwspinlock bank | `lock`/`unlock`; Linux hwspinlock | a lock in the conflict analysis (§7.2); release-by-non-owner and lock-order checks |
| **Timer / watchdog** | a time source + deadlines; a kick contract | timer IP | `delay`, `deadline`, `kick` | backs timeouts and minimum delays (§7.2 timing); watchdog kick within period on every path |
| **Service** | typed request/response API (§4a.5) | — (built on a channel) | client stubs + server dispatch | cross-executor operation call; same tests whatever realizes the target |
| **Executor socket** | "firmware goes here" (§4b.4) | a processor or sequencer + its memories | the payload | the boundary that payloads are checked against |

**Each construct is defined once, with endpoints bound independently.** An
endpoint can be hardware or software, so the same construct covers three
cases:

| Endpoints | Example | Realization chosen |
|---|---|---|
| SW ↔ SW, coherent memory | two cores in one cluster | shared-memory ring + IPI doorbell |
| SW ↔ SW, non-coherent or separate fabric | application CPU ↔ management core | hardware mailbox, or shared memory with cache maintenance |
| SW ↔ HW | CPU ↔ accelerator | registers + IRQ in the accelerator (generated) |

The realization is chosen from the platform: coherency, the fabric path and
area policy. It can also be forced. The semantics and tests stay the same.

### 4b.4 The executor socket

A socket is a capability on a hardware component, following the capability
layer pattern. Nothing is added to `fw_component`. It declares or derives the
following:

| Aspect | Source |
|---|---|
| executor kind: ISA and profile (e.g. RV32IMC), or "hardware sequencer" | declared, one line |
| memories: boot ROM, TCM, RAM, with sizes and addresses | derived from the elaborated subsystem |
| MMIO view: what the payload can address | derived from fabric decode and firewalls (§4a.5) |
| interrupt inputs and vector routing | derived from controller wiring |
| constructs it participates in: channels, locks, shared regions | derived from the assembly's connections |
| its clock, reset and power domains | domains layer (§7.5) |
| boot contract: reset vector, who loads the payload (ROM, remoteproc, the debug port) | declared |

**Payloads bind at assembly**, e.g. `fw_exec::bind(pmu_core, pmu_fw)`. Three
kinds of payload satisfy the same socket:

1. **A behavioral payload.** A class that runs the operations and service
   targets directly in simulation. It is available on day one, it is fast,
   and the system model (verification-support-review V7) needs it.
2. **A firmware image.** Projections plus the team's own C, compiled for the
   socket's ISA, running on an instruction-set simulator (ISS), a fast model,
   or the RTL core.
3. **A hardware realization.** The operations lowered to an FSM that replaces
   the core. The socket's interface stays the same.

**What the socket produces for its payload team:**
- a BSP: linker script from the memories, startup code, the vector table, and
  headers for its own MMIO view;
- the executor's device tree (System-DT style);
- client and server stubs for its services and channels.

The socket is the payload team's complete, generated contract with the
hardware.

**What gets checked:**
- the payload uses only what the socket provides (addresses, interrupts,
  memory budget);
- every service the socket's peers import is served;
- every interrupt routed to it has a handler;
- watchdog contracts hold;
- there are no wait-for cycles across executors.

### 4b.5 Descriptors and command queues as first-class constructs

**Short answer: yes, the gain is large.** For any IP with DMA or a command
interface (NICs, storage, DMA engines, accelerators, crypto engines) the
software interface is mostly *not* registers. It is descriptors in memory and
the queues that carry them. The registers are reduced to base addresses,
indices and doorbells.

**A descriptor is the memory-resident counterpart of a register declaration.**
Fields, widths, reserved bits, enums and access rules carry over directly.
Without a first-class descriptor, that half of the interface sits outside
everything in §4a–§7. Today each descriptor format is written separately:
- in specification prose;
- in hand-written RTL parse and build logic;
- as a C struct with `__le32` fields or non-portable bitfields;
- as a DV transaction class.

**What a declaration adds beyond a register:**
- **Layout rules:** endianness, alignment, size, padding.
- **Variants:** the layout depends on an opcode (a tagged union). Real formats
  need this: NVMe commands, xHCI transfer request blocks (TRBs), and
  extended descriptors.
- **Chaining:** next pointers, link entries, scatter-gather lists.
- **Typed address fields.** A field holding a DMA address is typed by the
  *device's* initiator view (§4a.5): an IOVA or bus address, not a CPU
  pointer. The platform knows that view, so "the driver wrote a CPU virtual
  address into a DMA field" becomes a type error.
- **Ownership phases:** which fields each side may write, and when. This is
  where a descriptor differs most from a register.

**There are few queue disciplines.** So the construct is a small fixed set,
much as ready/valid covers streaming handshakes:

| Discipline | Ownership signalled by | Examples |
|---|---|---|
| ownership-bit ring | an OWN/valid bit in each descriptor | many Ethernet MACs, simple DMA engines |
| index ring + doorbell | producer/consumer indices; tail doorbell | NVMe submission queue, virtio split ring, AHCI |
| phase-bit completion ring | a phase bit that flips on each wrap | NVMe completion queue, virtio packed ring |
| linked list / chain | next pointers; end-of-chain marker | DMA linked-list items, scatter-gather, xHCI link TRBs |

Each discipline has a normative semantics with **producer** and **consumer**
roles. Either role can be hardware, firmware or a host driver, which is the
binding idea of §4b.3. A **command queue** is a submission ring plus a
completion ring plus a correlation tag, built from the above.

**What we would gain:**

| Gain | Why first-class matters |
|---|---|
| **The ordering bug class goes away.** Missing write barrier before the doorbell, reading a descriptor before checking ownership, missing cache maintenance on non-coherent DMA, index wrap off-by-one | The discipline says where barriers and cache maintenance go, and the platform says whether the path is coherent. Generated code places them, and a static check flags hand-written code that misses them. These are among the most common driver concurrency bugs (Linux has a long history of missing `dma_wmb()`/`dma_rmb()` fixes; barrier-pairing checkers such as OFence target exactly this class [verify citation]) |
| **One spec, both sides, proved** | The hardware realization (fetch engine, writeback, prefetch) and the software producer are each checked against the discipline's properties: no descriptor consumed twice, no overrun, ownership respected, every completion matches one submission. This is a well-trodden formal target. Having one normative spec is what's new |
| **Asynchronous operations** | Operations today are synchronous: program, then wait. With queues, an operation is `submit()` → token, then a completion event. The operation model can express many commands in flight, which queue-based devices need |
| **Composition optimizations** | The §7.2 compiler can batch submissions behind one doorbell (doorbell coalescing), and reap many completions in the merged poll loop or one interrupt. That is the same as-if-sequential argument, applied to queues |
| **DV for free** | Descriptor fields are declared, so randomization with legality constraints comes from them, as do coverage of ring states (empty, full, wrap, phase flip), malformed-descriptor injection, and a scoreboard keyed by tag. That is queue VIP derived from the declaration |
| **HW/FW partition of command processors** | Many SSD and NIC controllers consume queues in firmware. The queue is the stable host-facing contract whether the consumer is RTL or firmware on a management core (§4b.4) |
| **Projection targets with real reach** | A device whose queues match virtqueue semantics can be offered as a virtio device. That is a direct path to existing Linux/QEMU drivers, and to the platform kit's virtio item (ip-library-focus) |

**Costs and risks:**
- **Real formats are quirky:** variable length, inline data, unions by
  opcode, vendor extensions. Without variants and an escape hatch (a
  discipline-less "raw region" with hand-written operations), lifting
  existing IP fails.
- **Don't over-generalize.** Four disciplines plus composition covers the
  common cases. Add more only when a real IP needs one.
- **Zuspec IR needs memory-resident struct types** with layout and ownership
  phases. The pieces that exist are `DataTypeMemory` and `AddrHandle`, and
  PSS has packed-struct read/write through address handles. Extending them is
  real IR work.
- **Small register-only IP gains nothing.** The construct must cost nothing
  when unused.

**Recommendation.** Make the descriptor declaration part of the shared
vocabulary next to registers, in `fw-hdl-spec`, since hardware parses it. Make
the four disciplines and the command-queue composition standard constructs in
the interface family. Pilot with a DMA engine using an index ring and a
completion ring: `wb_dma` already has linked-list descriptors, which makes it a
natural first case.

### 4b.6 Where they live

- **Abstract constructs, roles and semantics:** in the software-interface
  family's standard library, with a conformance suite. Interrupt source and
  MMIO are in `fw-hdl-spec` (§4a.6), because hardware needs them directly.
  - Like ready/valid, the core constructs are language-level, so each
    implementation (SV runtime, the Zuspec IR) treats them natively. They
    need Zuspec IR representation for analysis (AGENTS.md: represent in
    Zuspec).
- **Hardware realizations:** small IP in featherweight-ip, e.g. a mailbox, a
  doorbell, a hwspinlock bank, timers, and the interrupt controllers that
  ip-library-focus already names as the platform kit's lead. These give
  featherweight-ip a natural, small, high-reuse first set.
- **Software realizations:** projections from Zuspec back ends. The construct
  supplies the semantics, the back end supplies the C/Linux/Zephyr shape.

## 5. Proposal overview: one contract, three layers

```
            fw-hdl source (SV classes)            other front ends
  ┌────────────────────────────────────────┐     (PSS op-model subset,
  │ hardware   : components, regblocks,    │      Python zdc)
  │              domains, interrupts       │            │
  │ operations : fw_ops classes over the   │            │
  │              register model            │            │
  │ assembly   : the elaborated design     │            │
  └───────────────────┬────────────────────┘            │
                      ▼                                 ▼
                 Zuspec IR: registers + operations (footprint, waits,
                 contracts) + platform graph (address map, IRQs, suppliers)
                      │
    ┌─────────────┬───┴──────────┬──────────────┬─────────────────┐
    ▼             ▼              ▼              ▼                 ▼
 RTL / formal   C / SV / Py    device tree +  composition       co-verification
 (sequencer     op libraries   bindings +     compiler          (contracts on RTL,
  FSM too)                     init graph     (poll loop / IRQ  schedule ≡ sequential)
                                              FSM / threads)
```

- **Layer H — hardware-side declarations.** The register model with access
  semantics. Interrupt sources as a capability. Software-visible clock, reset
  and power control, linked to `fw_domain` drivers.
- **Layer O — operations (§6).** Typed procedural sequences over the register
  model. The *operation model* from the paper, made first-class in the IR.
- **Layer P — platform (§7.1).** The assembled design read as a software
  platform: address map, IRQ routing, supplier graph, device-tree nodes.

Packaging follows the earlier recommendation:
- `fw-ops` is a peer family to `fw-dv`, depending on `fw-hdl-spec` (which owns
  the register model and interrupts).
- Per-IP operation models live in the IP repo under `ops/`.
- `fw-dv` scenarios call operations.
- Projections are Zuspec back ends, mostly `zuspec-be-sw`.

## 6. Layer O: operations, made analyzable

### 6.1 Authoring (illustrative syntax)

```systemverilog
class wb_dma_ops extends fw_ops #(wb_dma_regs);     // reg type from the IP
  task transfer_single(int ch, bit [31:0] src, dst, bit [11:0] n,
                       output wb_dma_status_e st);
    regs.ch[ch].adr0.write(src);
    regs.ch[ch].adr1.write(dst);
    regs.ch[ch].sz.write('{tot_sz: n, default: 0});
    regs.ch[ch].csr.modify('{ch_en: 1});
    `fw_await(regs.ch[ch].csr.get().done, 100us)    // predicate + timeout
    st = regs.ch[ch].csr.get().err ? WB_DMA_ERR : WB_DMA_OK;
  endtask
endclass
```

Under the minimal-user-spec rule, the author writes **only the body**.
Everything below is derived.

### 6.2 What the tool derives

| Fact | Derived from | Used by |
|---|---|---|
| **Footprint**: read/write sets per field, access kind (RW/W1C/W1S/RC/WO), same-word coupling, indexed over-approximation (`ch[*]` unless `ch` is constant) | register model + body | conflict analysis (§7.2), the contract frame (§7.3) |
| **Wait points**: predicate, timeout, and the **event binding**: if the awaited field is an interrupt-capable field routed to an IRQ line in this assembly, the wait can be interrupt-backed (enable/mask/ack registers join the footprint) | register model + interrupt capability + platform IRQ map | scheduler choice per projection (poll vs IRQ) |
| **Preconditions from suppliers**: the device's clock/reset/power domain is driven by a software-controlled supplier (a CRG output gated by a register field) → `crg.enable(k)` must precede any access | `fw_domain` drivers (core-domains §3, decision 10) + the supplier's own ops | init ordering (§7.1), the device tree's `clocks`/`resets`/`power-domains` |
| **Blocking structure**: the body as a coroutine (await points → states) | Zuspec proc/async lowering (exists) | C state machines, SV tasks, Python `async` |
| **API surface**: export (public tasks), import (memory access + declared platform services), notification (ISR entry per interrupt source) | class declaration | projections |

### 6.3 Optional contracts

Most operations need no annotation. Where an IP team wants proof and not just
exercise, it adds pre- and postconditions over the register model and optional
ghost state:

```systemverilog
  `fw_op_pre (regs.ch[ch].csr.get().ch_en == 0)
  `fw_op_post(regs.ch[ch].csr.get().done && !regs.ch[ch].csr.get().ch_en)
```

Contracts feed §7.3 (proofs on the RTL), runtime assertions in debug builds of
the C projection, and Rust/C++ typestate where the target supports it (gap 7 in
the research). Typestate is then derived from the hardware rather than
hand-encoded by the HAL author.

### 6.4 The subset

As in the paper: a procedural subset with no `rand`, constraints, coverage or
allocation. Every decision arrives as a parameter. Tools reject anything outside
the subset. This is what keeps operations analyzable and separates them from
fw-dv.

## 7. The new capabilities

### 7.1 Derivation: the platform falls out of the assembly

The elaborated design already contains the bus fabric, address decode,
interrupt wiring, and domains with their drivers. Read as a software platform:

- **Device tree.** Emit one node per software-visible instance:
  - `reg` from the decode;
  - `interrupts` and `interrupt-parent` from the IRQ wiring;
  - `clocks`, `resets` and `power-domains` from the domain drivers (§6.2);
  - `compatible` from the class name, never a user string. Version
    parameters can feed into it.
- **Bindings derived from parameters.** Class parameters marked
  software-visible (FIFO depth, channel count, DMA width) become binding
  properties with their schema, and their values come from the elaborated
  parameters. Checking a hand-written DTS against the design is then a diff.
  Today nothing checks binding parameters against RTL generics.
- **Supplier graph.** The same edges give Zephyr init ordinals, Linux device
  links, and the static init order for bare metal (§7.2). Cycles are reported
  where they arise, in the design.
- **Platform headers and models.** The address map and IRQ map become C
  headers. A Renode `.repl` or QEMU machine description comes from the same
  graph. This is the platform-assembly story in ip-library-focus, with
  operations attached.

Diplomacy and LiteX already get address/IRQ/DT consistency by construction.
What this adds is supplier edges, binding parameters, and operations bound to
the same nodes.

### 7.2 Composition: as-if-sequential firmware

**Semantics.** The integrator writes ordinary sequential code against the
composed operation model:

```systemverilog
class soc_ops extends fw_ops_assembly;     // instances mirror the design
  crg_ops crg;  uart_ops uart[2];  wb_dma_ops dma;  spi_flash_ops flash;
  task boot();
    uart[0].init(115200);
    uart[1].init(9600);
    dma.reset_all();
    flash.wake();
  endtask
endclass
```

The defined meaning is the sequential one. The compiler may overlap operations
only where the result is indistinguishable from it ("as-if" sequential, like an
out-of-order core or an optimizing compiler). The integrator does not write
`fork`. Explicit `par`/`par_or` exist for the cases where the author wants to
state concurrency (e.g. completion versus timeout), with Céu-style abort
semantics.

**Analysis passes, all over derived facts:**
1. **Ordering.** Expand supplier preconditions. Here
   `uart[*].init` needs `crg.enable(CLK_UART*)` first, so it is inserted or
   checked. Then topologically sort, with refcounted shared supplies (CCF-style)
   so one operation releasing a clock can't break another.
2. **Conflict graph** from footprint intersections. Each pair is classified as:
   independent; independent if each RMW is made atomic (set/clear aliases, or a
   short critical section); or must serialize. Every serialization is reported
   with its reason, e.g. "uart[0].init and uart[1].init both RMW `crg.clk_en`".
3. **Shared effectful reads.** Two waiters on fields of the same RC/W1C status
   register share one read per pass, demultiplexed. An ack clears only its own
   bits.
4. **Timing.** Waits carry timeouts, and steps may carry minimum delays
   (`plat_delay_us`). In a merged loop these become per-operation deadlines on a
   shared tick, so a long loop pass can't silently break a minimum delay.
5. **Priority ceilings (RTIC/SRP)** when the output is interrupt-driven.

**Emitted schedulers, one per consumer:**

| Target | Form |
|---|---|
| bare-metal C, single core | **one poll loop**: each op is a stackless state machine; each pass evaluates pending predicates (shared status reads fanned out); WFI when all waits are IRQ-backed |
| bare-metal C, interrupts | ISR-driven state machines, ceiling-based critical sections, generated IRQ demux for shared lines |
| RTOS | thread per op + mutexes from the conflict graph |
| multi-core | PSS-style partitioning, barriers on cross-core order edges |
| SystemVerilog | `fork…join` / `join_any`, semaphores per conflict class; **randomized interleaving** mode for DV |
| Python | `asyncio.gather` / `wait(FIRST_COMPLETED)` |
| RTL | the composed schedule as a synthesizable sequencer (boot ROM replacement, FPGA testbed init engine), via proc→FSM |

The last row is something no software-only approach can offer. Because the
operations are written in the hardware language, a composed boot sequence can
become hardware.

### 7.3 Co-verification: a ladder

Operations are in the same language as the RTL. They lower through the same
proc→FSM path, and the import API is a protocol-kit initiator role whose
transactor core is synthesizable. So an operation plus the bus transactor plus
the IP RTL is **one closed, synthesizable formal model**. There is no C-to-RTL
translation (v2c) and no separately written device spec (ILA, Termite).

| Rung | Claim | Method | Prior art status |
|---|---|---|---|
| C0 | every op is exercised by every regression | ops are the realization layer of all tests (the paper's methodology) | OpenTitan-style, simulation only |
| C1 | **op contract holds on the RTL**: from any state satisfying `pre`, the op terminates within its timeouts and `post` holds | BMC/k-induction on op-FSM ∥ initiator xtor ∥ RTL; `pre` as an assumption | not done anywhere for production sequences |
| C2 | **footprint soundness**: an op's writes change only the fields the register model says they change | formal frame check on the RTL; finds hidden side effects that would make §7.2 unsound | not done |
| C3 | **interrupt contract**: the op's ISR acknowledge sequence deasserts the RTL IRQ line and loses no events | formal on the IRQ output | not done |
| C4 | **composition ≡ sequential**: the generated merged schedule reaches the same final register and device state as `boot()` run sequentially | equivalence (sequential schedule as reference) on the assembled RTL, bounded; randomized-interleaving simulation as a fallback | not done |
| C5 | **platform consistency**: DT/bindings/headers match the elaborated design | by construction, plus a diff check of hand-written DTS | by construction only in diplomacy/LiteX |
| C6 | **model consistency**: ops run identically on the RTL and on the lifted fast model | ops become the conformance tests for fast models (automated-lifting E-levels) | not done |

C1 and C4 are the headline results. C2 is what makes §7.2 trustworthy: derived
footprints are only as good as the register model, and C2 checks the register
model against the RTL. **Errata** fit the same mechanism. An erratum is a delta
to the register model or an operation; its workaround is an operation; C1 proves
the workaround on the affected RTL revision.

### 7.4 Content management: lifecycle, contributions and phases

**The problem at scale.** A large chip has thousands of IP instances, each with
initialization content (and suspend, resume, deinit and recovery content).
Today someone hand-writes the boot code that calls all of it. That is tedious,
and it fails silently:
- an IP's init is never called;
- it is called before its clock is up;
- two teams program the same shared pinmux or clock-mux field differently;
- shutdown order is the wrong reverse of boot order.

**Prior art for gathering content.**

| System | Mechanism | Lesson |
|---|---|---|
| Linux initcalls | fixed levels (`core`, `postcore`, `arch`, `subsys`, `fs`, `device`, `late`); link order within a level | levels as coarse barriers work; **order inside a level by link order is a notorious source of fragility** |
| Zephyr `SYS_INIT` | level + numeric priority; build checks priorities against DT dependency ordinals | numeric priorities rot; the DT check exists because they do |
| systemd | units with `Wants`/`Requires`/`After`/`Before`, gathered into `.target` milestones; stop order is the reverse of start | dependency-based ordering + named milestones; reverse order for teardown comes for free |
| UEFI PI | phases (SEC, PEI, DXE, BDS); inside DXE, a dispatcher runs each driver when its dependency expression (DEPEX) over published protocols is satisfied | **phases between, dependencies within**; drivers never name each other |
| init.d / rc.d | a directory per runlevel; drop a script in to contribute | contribution without editing a central file is what makes it scale |

The design that survives in all of these: a few **named milestones**, content
**contributed** to them without a central list, and ordering **inside** a
milestone by dependency rather than by number. fw-hdl can go further than any
of them, because the dependencies are derived from the design (§6.2, §7.1)
rather than declared.

**Proposal: three pieces.**

1. **Device lifecycle state.** Each operation class has a small lifecycle
   state machine. The default is `unpowered → reset → initialized → active`,
   plus `suspended`, and an IP may refine it.
   - Every operation requires a lifecycle state; the default is
     `initialized`.
   - Contributions declare the transitions they make.
   - This is ghost state in the sense of §6.3: no register holds it, but
     contracts and checks can refer to it.
2. **Contributions.** Content attached to a lifecycle transition, written
   as a class:

   ```systemverilog
   class wb_dma_init extends fw_contrib #(fw_init, wb_dma_ops);
     task body();                 // `ops` is bound to one instance
       ops.reset_all();
       ops.set_burst(cfg.burst);  // cfg from the configuration publisher
     endtask
   endclass
   `fw_contrib_utils(wb_dma_init)
   ```

   - **The role is a type** (`fw_init`, `fw_suspend`, `fw_resume`,
     `fw_deinit`, user-registered roles), never a string. Roles are
     registered the same way as domain kinds.
   - **Nobody wires contributions.** The assembly walks the elaborated
     design and binds each contribution to every instance whose operation
     class matches. The association from operation class to register type
     to IP is derived, not declared. This is the init.d property.
   - **Parameters come from the design.** They are the elaborated
     parameters, the instance's base address, and the configuration
     publisher and consumer from core-protocol-kit-prep §3.4. There are no
     hand-passed arguments.
   - **Override is hierarchical.** A subsystem replaces or wraps a child's
     contribution through the factory, e.g. to apply its own configuration.
     That is how integration-level policy is applied without editing the IP.
3. **Phases.** Phases are typed milestones with a partial order, defined by
   the platform. For example:
   `power_up < clocks_stable < resets_released < memory_ready < devices < late`.
   - A contribution names its phase only when its dependencies don't place
     it already. Most never do.
   - **Order inside a phase is derived:** supplier edges, lifecycle
     preconditions, and dataflow through register footprints. A contribution
     may say `after` by type, but numeric priorities don't exist.
   - A phase is either a **barrier**, observable outside (e.g. "before
     hand-off to the OS"), or **ordering-only**. Across ordering-only phases,
     the as-if-sequential compiler (§7.2) may still overlap work.
   - **Teardown and suspend order are derived** as the reverse of the
     dependency order, as in systemd. Nobody writes them.

**Checks (the "managing complexity" part), cheapest first:**

| Check | Level | Example |
|---|---|---|
| **Unreferenced content** | warning | `wb_dma_init` exists, but no flow in this platform runs `fw_init` for `dma0` (e.g. the platform's boot flow omits the `devices` phase) |
| **Missing required content** | error | an operation on `dma0` needs `initialized`; no contribution in any earlier phase makes that transition |
| **Use before ready** | error | an `uart0` operation in phase `clocks_stable` precedes the contribution that enables its clock |
| **Conflicting contributions** | error | `uart0_init` and `spi1_init` both write `pinmux.pad7` with different values. Same-field writes from different contributors are found from footprints |
| **Ordering cycles** | error | reported as the dependency path, in source terms |
| **Empty phases, dead roles** | info | a phase with no contributions; a registered role that no flow uses |
| **Phase misplacement** | warning | a contribution pinned to `late` whose dependencies would let it run in `devices` (boot-time opportunity) |

**The boot manifest.** The output that makes this manageable for people is a
generated manifest. For every flow (boot, suspend, resume, shutdown) it lists
each contribution, its instance, its phase, and **why it is ordered where it
is** (which edge or footprint). It also lists what the compiler overlapped.
It answers "why is X before Y" and "who touches this register during boot"
without reading code. It also diffs cleanly between SoC revisions.

### 7.5 Power and clock sequencing rules

**The problem.** Software sequences break hardware power and clock rules in
ways functional simulation rarely sees:
- accessing a register in a gated or powered-off domain hangs the bus, or the
  write is silently lost;
- gating a clock while a DMA is mid-transfer;
- powering off without isolation, or releasing a reset with no clock running.

Industry practice:
- **Static power-intent checkers** (Synopsys VC LP, Cadence Conformal Low
  Power) check the *structure* against UPF: are the isolation and level-shifter
  cells present? They don't check the software sequence.
- **Power-aware simulation** (Questa PA, VCS NLP) catches sequence errors, but
  only on the paths a test happens to run, and slowly. It isn't available in
  our Verilator-only flow anyway.
- **Linux CCF/genpd and Arm SCMI** enforce reference counting at run time,
  without a static check.

So there is no static check of power and clock sequences in firmware against
the hardware's power intent. This is the same gap as §2, one level down.

**The rules are mostly generic, per domain kind.** They come from the kind,
not from each IP:

| Kind | Rule (examples) |
|---|---|
| clock | register access needs the domain's clock `on`; disabling a parent needs all child consumers idle (reference-counted); a glitch-free mux switch needs both sources running |
| reset | access needs `deasserted`; deassert needs the clock `on` and stable (PLL locked); a synchronous reset needs N clock cycles while asserted (a kind property, core-domains §4) |
| power | `off` needs the domain quiesced (no outstanding transactions or active DMA), isolation enabled toward powered-on neighbours, and retention saved; `on` needs power-good before reset release and clock enable; de-isolate last |
| voltage/frequency (DVFS) | raise voltage before frequency; lower frequency before voltage |
| timing | minimum settle times (PLL lock, power-switch ramp) as timed waits on the supplier's operations |

IP-specific rules (e.g. "quiesce means `csr.busy == 0` on every channel") are
the IP's own lifecycle contract. The `suspended` transition in §7.4 has a
postcondition of idle.

**Where the facts come from:**
- **Which domain each register and IP belongs to:** the domain association,
  core-domains §2.
- **Which register field controls which domain:** the domain *driver*,
  core-domains §3 / decision 10. If the clock-and-reset generator (CRG) is
  written in fw-hdl, the path from register field to gate to domain is in the
  elaborated design. For a foreign or lifted CRG, its operations declare the
  effect (`clk_en[k]` → `dom(uart0_clk).on`). That is one annotation per CRG
  output, not per consumer.
- **Power domains, isolation and retention:** a `power` domain kind in the
  same `fw_domain #(K)` framework.
  - Isolation and retention are kind properties.
  - The crossing analysis (core-domains §6) already finds every crossing
    between domains. That is exactly the set of places that need isolation.
  - UPF becomes a projection (export) and an import, not the source.

**The checking mechanism reuses footprints.** Domain states are treated as
**pseudo-registers** in operation footprints:
- An operation that touches `uart0` registers *reads* `uart0_clk.state`,
  `uart0_rst.state` and `uart0_pwr.state`, and requires them to be
  `on`/`deasserted`/`on`.
- The CRG's `enable(k)` *writes* `uart0_clk.state`.
- So the conflict and ordering analysis in §7.2 orders and serializes them
  with no new machinery. An emitted schedule that would let the CRG gate
  `uart0_clk` while a UART operation is pending is a conflict like any other.
- The power and clock rules are the kind-level transition guards, checked by
  abstract interpretation over each lifecycle flow (boot, suspend, resume,
  shutdown). Checking every flow is what matters: errors cluster in suspend
  and resume, which few tests run.

**Checks across the ladder:**

| Where | What |
|---|---|
| static (compile, per flow) | every access happens in a legal domain state; every transition meets its kind's guards; reference counts balance on every path; settle times are respected under the emitted schedule (§7.2 timing) |
| simulation (Verilator) | generated SV assertions on the RTL from the same rules (no bus access into a domain whose enable is low, isolation asserted before the power switch opens); protocol-kit monitors flag accesses that hang |
| formal | the domain preconditions are part of each operation's contract (C1). C2 extended: a supplier operation's effect on the domain matches the RTL (writing `clk_en[k]` really gates domain k) |

The static check is especially valuable here. It gives power-sequence checking
**without power-aware simulation**, which we don't have (Verilator only), and
which most consumer teams (firmware, emulation) don't run either.

## 8. Risks and pitfalls

- **Hidden coupling outside the register model:** fabric ordering (posted
  writes need a read-back before polling), device-memory ordering, address
  aliasing. Footprints must carry barrier semantics. C2 catches only what the
  RTL in scope shows.
- **Formal scalability.** C1 is per IP and bounded by the timeouts, so it
  should be tractable for typical IPs. C4 on an assembled SoC is probably not;
  fall back to per-pair commutation proofs plus randomized-interleaving
  simulation.
- **Data-dependent footprints** (a runtime channel index) need conservative
  over-approximation or a runtime lock.
- **Abort and error paths.** `par_or` and timeouts must leave hardware
  quiescent, so they need authored abort operations, which IP teams rarely
  write.
- **Who authors in SV.** Firmware teams consume projections and don't author.
  IP design and DV teams author, and they already write SV. A PSS front end
  (the paper) and Python `zdc` remain peers on the same IR.
- **Over-serialization** makes the compiler useless. Every serialization needs
  a reported reason, and the defaults must be word-level (safe), refined by
  set/clear aliases.
- **Scope creep toward driver synthesis.** Termite shows synthesis doesn't
  scale. Stay at composing and scheduling *authored* sequences.
- **Two Zuspec register models** must be reconciled before anything builds on
  them.
- **Foreign supplier IP.** Clock-and-reset generators (CRGs) and power-management
  units (PMUs) are often foreign or vendor IP. If their effects on domains are
  declared rather than derived, a wrong declaration makes the §7.5 checks
  unsound. C2 on the CRG (does `clk_en[k]` really gate domain k?) is the
  mitigation.
- **Phase taxonomy wars.** Every SoC team has its own boot phases. The platform
  defines phases; fw-hdl defines only the mechanism and a small default set.
  Because ordering inside a phase is derived, phases stay few.
- **Ghost lifecycle state can drift from the RTL.** Lifecycle postconditions
  (`suspended` ⇒ idle) should be backed by register predicates wherever possible,
  so C1 can check them.

## 8a. Critical review: if we build it, will anyone come?

### Verdict

The technical case holds. The adoption case, as written, does not. As written,
the plan is a technology roadmap: nine phases and fifteen decisions. Its
distinctive value (composition, the co-verification ladder beyond C1, power
rules) arrives late. It also asks the IP producer to pay for benefits that
other teams receive.

### Why it could fail

| # | Failure mode | Evidence or reasoning |
|---|---|---|
| F1 | **The producer pays, the consumer benefits.** IP designers or DV write the operations; firmware and SoC teams get the drivers and platform. | Programming guides drift out of date for the same reason: nobody downstream pays the person who maintains them. *Partly answered by §4a.7:* DV writes this code anyway, already pays the support cost of "how do I do XYZ", and gets in-testbench gains. Making it core methodology removes the separate decision to adopt. |
| F2 | **Portability alone has been on offer and has not taken over.** | Agnisys ISequenceSpec (one sequence spec → UVM, C and more) [verify], Vayavya DDGen, and the PSS approach (the DVCon paper's own framing). Each has users; none changed how most teams work. Portability is necessary, not sufficient. |
| F3 | **Compound adoption.** A user must adopt fw-hdl, Zuspec and the interface family. | The probabilities multiply. The retrofit path (§4a.7) still requires an fw-hdl wrap. |
| F4 | **Firmware will not author in SV and distrusts generated drivers.** | Firmware teams have their own HAL, style rules (MISRA, kernel style) and debug habits. If the consumer rejects the output, the producer's work buys nothing downstream. |
| F5 | **The early phases are not distinctive.** | H0–H1 (registers, operations, C/SV projections) overlap with SystemRDL + PeakRDL plus sequence generators. The differentiators (H2 proofs, H4 composition, §7.5 power) come later and are research-grade. |
| F6 | **Scope sprawl.** Constructs, descriptors, executors, services, power, composition. | Each piece is defensible; together they form a platform nobody can evaluate in an afternoon. |
| F7 | **AI-written drivers as a free substitute.** | By 2026 a team can ask an LLM for a driver from the register description and the programming guide. That is "good enough and free" for the portability pitch. |

### What has worked elsewhere

The register and platform formats that succeeded share three traits. SystemRDL
with PeakRDL, device tree, and OpenTitan's generated register headers all do
this:

1. the input is something people already write;
2. the output is something someone needs this week;
3. the person who writes the input gets the output.

The earlier framework research ([featherweight IP strategy](featherweight-ip-strategy.md))
adds a fourth: a flagship owner shipping product with it.

The plan as written misses the third trait (F1) and the fourth.

### What shifts the odds

**S1. Don't ship it as a product. Make it load-bearing in the vehicle already
chosen.** The lift / prove / model / assembly strategy
([automated lifting](automated-lifting.md), [IP library focus](ip-library-focus.md))
needs this layer, and it does not exist anywhere else:

| The lifting strategy needs | This layer supplies |
|---|---|
| a fast model that boots real software | the platform view (§7.1): device tree, bindings, drivers |
| software sync points for effect-level equivalence (E4, lifting §5.3) | operation boundaries and footprints (§6.2) |
| the in-situ harness: wrap the original RTL, no DV changes (lifting §5.5) | the same wrap as the retrofit flow (§4a.7) |
| a demo that the lifted platform is real | the generated driver running on RTL, on the fast model and on Renode/QEMU |

This fixes F1: the team doing the lift is also the team that needs the
operations, both for equivalence and to run software on the model. It also
softens F3: users adopt a fast platform and get the interface along with it.
The headline stays "assembly produces the RTL SoC and the emulation platform";
this layer is what makes the software half of that claim true.

**S2. Ship the outputs with featherweight-ip, under the same rule as the RTL
("build with fw-hdl, ship plain").** Each IP ships plain SV, a C driver, a
Zephyr (and later Linux) driver, a device-tree binding, and a Renode/QEMU
model. Users adopt the IP; open IP is often chosen or rejected on whether it
has drivers. Nobody has to adopt the method to get the benefit.

**S3. Treat "upstreamable" as the acceptance test for the C projection.** This
answers F4. Getting a generated driver merged into Zephyr, unmodified except
for review comments the generator then learns from, is a visible credibility
signal. If maintainers keep rewriting the generated code, the projection is
wrong; better to learn that early than at H5.

**S4. Lead with one acute, schedule-driven pain.** Ranked:

1. *Software bring-up before RTL is stable, on a fast platform.* Teams are
   already pressed to deliver this. It is the same lead as the lifting
   strategy.
2. *Init and power-sequencing bugs that escape to silicon.* Acute and
   expensive, but hard to demonstrate without a customer's bug history. Keep
   it as the second act (§7.5).
3. *Drift between the programming guide, the RTL and the driver.* A real
   problem, but chronic; nobody buys a tool for it this quarter.

**S5. Turn F7 around: AI proposes, the interface checks.** The barrier to
adoption is writing the operations. The lifting pipeline already ingests
existing DV. An agent can lift existing UVM configuration sequences and
existing C drivers into operations. The derived checks (footprint, access
kinds), C0 regression and C1 proofs then confirm or reject them. That turns
the retrofit cost from writing into reviewing, and turns the AI substitute
into an ally. The pitch becomes "your AI writes the driver; this proves it
matches the RTL", which a plain LLM-written driver cannot claim.

**S6. No lock-in.**
- Consume SystemRDL, IP-XACT and hjson.
- For the register part, prefer being a PeakRDL plugin over competing with
  PeakRDL.
- Make every output readable code that a team keeps if it leaves.
- Keep operations callable from existing UVM.

**S7. Cut to a minimum and gate everything else on demand.**
- *Minimum:* imported registers, operations, C and SV projections, the
  platform view (DT + Renode/QEMU), and C1 on one IP, all in service of the
  lifting pilot.
- *Deferred until someone outside the project asks for it by name:* the
  composition compiler, the power kind, descriptors and queues, and the
  constructs beyond interrupts.
- *Composition stays a paper.* The DVCon follow-on is a cheap way to probe
  demand without building the compiler.

**S8. Probe demand before H1.**
- Treat the DVCon 2027 paper as a probe: track who follows up, and from which
  role.
- In the organization named as a potential flagship owner (lifting §9), ask
  one firmware lead and one DV lead to name the operations they would want
  for one block, and whether they would ship generated C.
- If either says no, find out why before building.

**S9. Make the authoring language optional: lift C firmware to Zuspec when
the analysis is worth it.** The operation model is a Zuspec IR concept. SV,
PSS and Python are front ends to it, and a C front end can be one too.

- *This answers F4.* Firmware keeps writing C. Nobody has to author in SV.
- *It keeps S7's gating honest.* Analysis is built only when someone wants
  it, and it then runs on code that already exists.
- *It offers a checker before a generator.* Run against existing drivers and
  boot code, it can report:
  - read-modify-write on write-1-to-clear or read-to-clear fields;
  - a doorbell written without the preceding barrier;
  - clock or power rule violations in a boot flow (§7.5);
  - init content that nothing references (§7.4).

  That is "lint your driver against the hardware". The input already exists,
  the output is useful this week, and the person who runs it gets the
  benefit.
- *It enables C1 on existing code.* A lifted driver function becomes an
  operation FSM, which can be proved against the RTL through the transactor.

What makes it tractable, and where it stops:

| Concern | Handling |
|---|---|
| Recognizing register accesses | Reliable when the code uses headers generated from the register declaration (accessor macros, struct overlays). Otherwise, constant addresses resolved against the platform address map. Report accesses that cannot be resolved; don't guess. |
| Polling and waits | Recognize the idioms: bounded poll loops, wait-for-interrupt, RTOS waits. Map them to wait points (§6.2). |
| Decisions arriving as globals and config structs, not parameters | Treat them as inputs to the operation. Lifted operations have no contracts until someone adds them. |
| Function pointers, inline asm, unbounded loops, ISR/RTOS concurrency | Best effort. Each operation is labeled with what the analysis understood and what it did not. |
| Rewriting (the composition compiler) on lifted C | Later than checking. Report what could overlap first; emit rewritten C only if teams ask for it. |

Precedent: Microsoft's SLAM / Static Driver Verifier checked C drivers
against an interface model; Linux uses Coccinelle for API-misuse patterns;
and CBMC and Frama-C are used on firmware. The new part is checking against a
model derived from the hardware itself. A C front end (clang-based) is new
work in Zuspec, separate from the RTL lifting front end.

### Continue / stop criteria

| After | Continue if | Otherwise |
|---|---|---|
| the lifting pilot (`obi_uart`) | the operations were needed by the lift itself (E4 sync points, booting software on the model) | stop treating this layer as a separate effort; keep only what the lift used |
| the first generated driver | a firmware team or an upstream project takes it with review changes only | fix the C projection before anything else |
| one external use | a team outside the project writes operations for a block without being asked | keep the deferred items deferred |

### Revised ordering (if accepted)

1. H0, reduced to imported registers and the interrupt capability.
2. H1 on the `obi_uart` lift (not `wb_dma`): operations, then the C and SV
   projections.
3. H3: device tree, Renode/QEMU, and the generated Zephyr driver booting on
   RTL and on the model.
4. C1 on the UART.
5. An attempt to upstream the driver.

Everything else in §9 waits on the criteria above.

## 9. Decisions for discussion

| # | Question | Recommendation |
|---|---|---|
| 1 | Is the software interface (registers + interrupts + operations + platform) in scope for fw-hdl, as a peer family to fw-dv? | Yes. The shared vocabulary (register declarations, interrupts, MMIO API) goes in `fw-hdl-spec`; the interface family sits above it, and `fw-dv` extends it (§4a.2, §4a.6). The RAL stops being a DV artifact. |
| 2 | Composition semantics: implicit (as-if-sequential, compiler overlaps) or explicit (`par` only, PSS-style)? | Implicit as the default, explicit `par`/`par_or` available. Implicit is what lets independently written code compose without coordination. |
| 3 | Which co-verification rungs are in the first cut? | C0 + C1 + C2 on one IP; C4 by simulation first. |
| 4 | Which register model is canonical in Zuspec? | Decide before H1. Proposal: the IR's `DataTypeRegister` + the `mmr` access enums, with the be-py `RegFile` as a runtime view. |
| 5 | Pilot IP | `wb_dma` (the paper's running example: ops already exist in PSS for comparison), then `obi_uart` (the lifting pilot) plus a CRG, for supplier edges. |
| 7 | Content gathering: central hand-written boot code, numeric levels (Linux/Zephyr), or contributions + typed phases + derived in-phase order? | Contributions + typed phases + derived order (§7.4). Roles and phases are registered types, never strings or numbers. |
| 8 | Power intent source: import UPF, or a `power` domain kind in fw-hdl with UPF as a projection? | A `power` kind in `fw_domain` (same capability layer as clock/reset), with UPF export and import. |
| 9 | First-cut checks in §7.4/§7.5 | Unreferenced/missing content, use-before-ready, conflicting contributions, plus clock/reset access rules. Power-off isolation and retention come later, once the power kind exists. |
| 10 | Name for the software-interface layer (not "HSI": Vayavya and AMD both use it) | Open; candidates in §4a.1. |
| 11 | MMIO API: built into the language (like ready/valid, D4) or a protocol kit? | Built in; every memory-mapped bus kit adds one MMIO↔bus bridge (§4a.4). |
| 12 | Executors and services: model where operations run as a binding, and management-processor services as API kits whose target role is implemented in software? | Yes (§4a.5). This makes the hardware/software partition a late binding. |
| 13 | Standard interface constructs (interrupt, doorbell, channel, shared region, ring, lock, timer, service) and an executor socket, each with semantics, roles and HW/SW realizations? | Yes (§4b). Start with interrupt source + controller, doorbell, channel and the socket; rings and locks next. |
| 14 | Descriptors and command queues first-class? | Yes (§4b.5): descriptor declarations (layout, variants, typed DMA addresses, ownership phases) next to registers; four queue disciplines plus command-queue composition as constructs; asynchronous operations (submit → completion). Pilot on a DMA engine with rings. |
| 15 | Should block DV write its directed core operations as interface operations? | **Decided 2026-11-16: yes, as core DV methodology** (§4a.7): an operations class under the subset, called by the existing sequences, with a generated per-IP cookbook that answers "how do I do XYZ" for emulation, firmware, SoC and post-silicon. A UVM-backed MMIO executor means no wrap is required. Lead the pitch with in-testbench gains and reduced support load. Pilot on a third-party IP with an existing UVM environment. |
| 16 | Is this a product or a component? | A component of the lift / prove / model / assembly vehicle, shipped through featherweight-ip outputs (§8a S1, S2). Minimum scope only; composition, power, descriptors and most constructs gated on outside demand (S7). Revised ordering in §8a. |
| 17 | Lift existing C firmware into the Zuspec operation model? | Yes, as the analysis on-ramp (§8a S9). Checker mode first (lint drivers and boot code against the hardware), rewriting later. Authoring language becomes a front-end choice, not a requirement. |
| 6 | Relationship to the DVCon paper | Same operation-model concept and IR. The paper is the PSS front end and methodology; this is the fw-hdl front end plus co-verification and composition. A follow-on paper candidate: "as-if-sequential firmware composition". |

### Proposed phases (if accepted)

If decision 16 is accepted, the revised ordering in §8a replaces this table's
order, and the phases not listed there are gated on demand.

| Phase | Content | Demonstrates |
|---|---|---|
| H0 | Register model + interrupt capability in `fw-hdl-spec`; reconcile Zuspec register models | foundation |
| H1 | `fw_ops` + derived footprint/waits; C, SV, Python projections via `zuspec-be-sw`; `wb_dma` ops | the paper's result in fw-hdl |
| H2 | C1/C2 on `wb_dma`: op-FSM ∥ initiator xtor ∥ RTL under SBY | first op proved on RTL |
| H3 | Platform layer: DT + bindings + supplier graph from an assembly; DTS diff check | derivation |
| H3a | Constructs: interrupt source/controller, doorbell, channel (HW mailbox + shared-memory realizations); executor socket with behavioral payload, then a firmware image on an ISS or core; BSP generation | "firmware goes here": an application CPU ↔ management core service running three ways |
| H4 | Composition compiler: ordering, conflict graph, poll-loop and IRQ emitters; C4 by randomized-interleaving simulation | the multi-team boot demo |
| H3b | Lifecycle + contributions + phases (§7.4); unreferenced/missing/conflict checks; the boot manifest | the lowest bar, at scale |
| H4b | Domain states as pseudo-registers; clock/reset rules (§7.5) checked statically per flow; generated SV assertions | sequencing violations found without power-aware sim |
| H5 | `power` domain kind, isolation and retention rules, UPF projection; C3 interrupts, C4 formal on small assemblies, typestate projection, errata deltas | depth |

**Demo target for H4.** Three IPs from three "teams", each with a polling init.
An integrator writes a sequential `boot()`. The compiler emits one poll loop,
reports the one forced serialization (a shared CRG register) with its reason,
and shows the boot-cycle reduction in Verilator against the sequential version.
C4 shows the two end in the same state.

## 10. Sources

- Ryzhyk et al., *Dingo*, EuroSys'09 — driver bug taxonomy:
  https://dl.acm.org/doi/pdf/10.1145/1519065.1519095
- Ryzhyk et al., *Termite-2*, OSDI'14:
  https://www.usenix.org/conference/osdi14/technical-sessions/presentation/ryzhyk
- Ryzhyk et al., *Improved device driver reliability through hardware
  verification reuse*, ASPLOS'11:
  https://trustworthy.systems/publications/nicta_full_text/4136.pdf
- Huang, Malik et al., *Instruction-Level Abstraction*, TODAES 2018:
  https://dl.acm.org/doi/10.1145/3282444 ; ILAng:
  https://link.springer.com/chapter/10.1007/978-3-030-17462-0_21
- Mukherjee, Kroening et al., v2c / co-verification:
  http://www.kroening.com/papers/tacas2016-2.pdf ,
  http://www.kroening.com/papers/dac2017.pdf ; CoVerif:
  https://arxiv.org/pdf/2001.01324
- Velosiraptor: https://arxiv.org/abs/2608.07966 ; Sockeye:
  https://arxiv.org/pdf/2510.27485
- OpenTitan DIFs: https://opentitan.org/book/doc/contributing/sw/device_interface_functions.html
- Linux device links / fw_devlink: https://docs.kernel.org/driver-api/device_link.html
- RTIC resources: https://rtic.rs/2/book/en/by-example/resources.html ; SRP
  (Baker'91): https://www.math.unipd.it/~tullio/RTS/2009/Baker-1991.pdf
- Embassy: https://embassy.dev/book/ ; Céu: http://www.ceu-lang.org/chico/ceu_tecs17_pre.pdf ;
  Lingua Franca: https://www.lf-lang.org/docs/
- PSS 3.0: https://accellera.org/images/downloads/standards/pss/Portable_Test_Stimulus_Standard_v3.0.pdf ;
  AMD/Perspec DVCon: https://dvcon-proceedings.org/wp-content/uploads/test-driving-portable-stimulus-at-amd.pdf
- Wilson Research Group 2022 / 2024 functional verification studies (Siemens).

Some items in §2 come from the research agent's memory rather than a checked
source: SystemRDL/IP-XACT details, the Zephyr init-priority check, System Device
Tree/Lopper, Chou SOSP'01, and the 2024 first-silicon figure. Verify these
before citing them externally.
