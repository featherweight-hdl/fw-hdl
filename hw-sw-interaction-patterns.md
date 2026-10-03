# Hardware/Software Interaction Patterns

**Research notes, conclusions, and recommendations for reusable fw-hdl (hardware) + PSS
operation-model (software) constructs.**

Date: 2026-08-26

---

## 1. Motivation and scope

Today, most HW/SW interface specification and verification happens at the level of
*individual register reads and writes*. That level is well-tooled (SystemRDL, IP-XACT, UVM
RAL, the PSS 2.1 register model), but it is the assembly language of the HW/SW interface.
The actual contract between a driver and a device is almost never "write bit 3 of
`CTRL`" — it is:

- "enqueue a work item and ring a doorbell; the device will complete it out of order and
  post a completion I can find without a lock"
- "negotiate features, then declare yourself ready; the device may not touch my memory
  before that point"
- "send a command message to firmware, wait for a response tagged with my sequence
  number, tolerate an unsolicited async event arriving in between"

These are *patterns*. They are re-invented, subtly differently, in every project — and
each re-invention brings its own crop of ownership, ordering, wrap-around, and
error-recovery bugs. The goal of this work is to name the patterns, give each one a
first-class construct in fw-hdl (the hardware/model side) and a matching PSS operation
model (the software/test-intent side), and thereby:

1. **Keep the interface consistent** — one description generating the RTL-facing,
   model-facing, and test-facing artifacts, so they cannot drift apart.
2. **Up-level the interface** — designers compose from `command_queue`, `mailbox`,
   `event_channel` rather than from `reg` + `always_ff`.
3. **Enable pattern-based verification** — each pattern ships with its own properties,
   coverage model, and PSS scenario library. Verification of a *use* of the pattern
   becomes configuration, not authorship.
4. **Reduce re-invention** — one correct, verified treatment of ownership and wrap-around
   per pattern.

Those goals are listed in the order §3 concludes they should be weighted, which is *not*
the order they are usually pitched in; §3 argues the case directly rather than assuming it.

The user-confirmed scope explicitly includes **in-memory queues** (descriptor rings,
queue pairs), which turn out to be the richest and highest-value family.

---

## 2. Survey: what the industry actually does

### 2.1 Layer 0 — register primitives (the substrate)

Harold Lawson's *Patterns in register map design* (devever.net) is the best single
catalog of the primitive layer. The recurring behaviors:

| Primitive | Mechanism | Why it exists |
|---|---|---|
| Plain / read-only / read-only-constant / hybrid | Field access policy | Version & capability reporting; mixed-mutability |
| **Doorbell register** | Write triggers an event; data may be ignored, be an argument, or be split across address+data | Decouples "I published work" from "the work itself" |
| **Indirect access (addr/data pair)** | Write index, then read/write data window | Exposes a large space through a small aperture; versionable |
| **Start/Wait/Done** | Write `START`, poll `DONE` | Simplest possible async op; degenerate command queue |
| **W1C** | Write 1 to clear a sticky event bit | Race-free event acknowledge without RMW |
| **Write-to-set / write-to-clear alias pair** | Two addresses, one storage | Atomic mask/unmask without RMW; critical for SMP drivers |
| **W1-to-flip** | Toggle | Rare; needs read-XOR-write |
| **FIFO push/pop register** | Same address, queue semantics, `FULL`/`EMPTY` status | Streaming through a fixed aperture (UART, TPM FIFO) |
| **Semaphore / mutex register** | Request + grant registers | Arbitration between multiple software agents |
| **Lock bits** | Set-once until reset | Secure boot, configuration freeze |
| **Register vectors with stride** | Array with a *stride register* | Forward compatibility as entries grow |
| **Aliased register blocks** | Same regs at secure/non-secure addresses | Privilege without binary incompatibility |
| **Ambient authority** | Behavior depends on requester identity | TrustZone / SMMU StreamID contexts |
| **Failure semantics** | All-ones read vs. trap | Device-removal detection (PCIe `0xFFFFFFFF`) |

Two observations matter for us:

- Several of these are **not** expressible as "a field with an access policy" — doorbells,
  indirect windows, FIFO apertures, and semaphores are *behavioral* constructs with a
  protocol. A register-description language alone cannot capture them; a component
  library can.
- The interrupt idiom is really a *stack*, not a register: `RAW_STATUS` (sticky, set by
  hardware event) → `ENABLE`/`MASK` (with set/clear aliases) → `STATUS` (masked) →
  aggregated output line, with W1C acknowledge and edge-vs-level policy. This appears
  near-identically in every SoC and is worth a single construct.

### 2.2 Layer 1 — message channels (mailbox family)

The mailbox family is the dominant pattern for *software talking to firmware*.

**ARM SCMI / MHU** (Zephyr, Linux, Xen docs) is the canonical form:

1. Requester writes a message into a shared-memory channel.
2. Requester rings a request doorbell (MHU write, or an SMC call used *as* a doorbell).
3. Platform firmware reads, processes, writes the reply into the *same* buffer.
4. Firmware rings the reply doorbell (or the requester polls, e.g. during early boot
   before interrupts exist).

Key structural points worth generalizing:

- **Channel = shared memory area + one or more signaling channels.** Request and reply
  doorbells may be distinct signals. The transport is deliberately abstracted from the
  protocol — SCMI runs over MHU doorbells, SMC calls, or virtio.
- **Both polled and interrupt-driven completion must be supported** by the same channel,
  because early-boot and steady-state software differ.
- **Separate channel classes**: synchronous command channels (`A2P`) vs. asynchronous
  notification/delivery channels (`P2A`). Firmware-initiated events cannot share the
  request buffer.
- The **Linux common mailbox framework** formalizes TX-completion discovery as a
  three-way preference: `txdone_irq` (controller reports remote consumed it) →
  `txdone_poll` (controller can be read but not report) → `txdone_by_ack` (the *protocol*
  carries an ACK, so the client drives the state machine). This is a genuinely reusable
  distinction: "who knows the message was consumed, and how" is a first-class parameter of
  a message channel, not an implementation detail.

**PLDM over MCTP (DMTF)** shows the layering that mature firmware interfaces converge on:

- MCTP is a transport with an explicit **message type byte** (0x1 = PLDM, 0x4 = NVMe-MI…),
  i.e. multiplexing of several protocols over one physical channel.
- PLDM defines **command/response with completion codes** and **multi-step, long-running
  operations** — firmware update is `RequestUpdate` → `GetPackageData` → `PassComponentTable`
  → `UpdateComponent` → `ActivateFirmware`, a sequence with state that must survive
  errors.
- This is the "firmware looks like hardware" case in its purest form: the register
  interface is trivial (a few doorbells and a buffer), and *all* the semantics live in a
  message grammar and a state machine.

**RPMsg / OpenAMP / remoteproc** is the same family with a different bias: named
**endpoints** and a name-service announcement channel layered on top of virtio vrings in
shared memory, plus a **resource table** through which the remote declares what memory and
channels it needs. The resource table is the discovery/negotiation pattern applied to
firmware.

### 2.3 Layer 2 — in-memory queues (the core of the study)

This is where the real complexity — and the real verification value — lives. Four
reference designs, all structurally similar, differing mainly in *how ownership is
encoded*:

**virtio split virtqueue** — descriptor table + available ring + used ring. Driver writes
descriptors, chains them via `next`, publishes the chain head into the available ring, and
bumps `avail->idx`. Device consumes and publishes into the used ring with `used->idx`.
Ownership is encoded by **free-running indices** (producer index vs. consumer index),
which is why the rings are single-writer per side. Notification suppression is
bidirectional and symmetric: `used_event` / `avail_event` under `VIRTIO_RING_F_EVENT_IDX`
let each side say "don't interrupt me until index N". Explicit memory barriers are
mandated around index publication and before reading the suppression fields — *"the driver
MUST perform a suitable memory barrier before reading flags or avail_event, to avoid
missing a notification."* The **packed virtqueue** collapses the three structures into one
ring and switches ownership to a per-descriptor **wrap/available bit**, trading index
traffic for cache locality.

**NVMe queue pairs** — separate Submission Queue and Completion Queue, each circular, with
doorbell registers for SQ tail and CQ head. Completions carry a **phase tag**, inverted
each time the controller wraps the CQ; the host detects new entries by comparing the phase
bit rather than by reading a device-owned index. Commands carry a **command identifier**,
so completion is explicitly **out of order**. Admin queue (QID 0) is architecturally
separate from I/O queues — a *control-plane / data-plane split*. Interrupt coalescing is
programmable by count and time threshold.

**xHCI** — three ring *kinds* with different roles: Command Ring (host→controller control),
Transfer Rings (per-endpoint data), and an Event Ring (controller→host completions and
async events, with a hardware-managed Event Ring Segment Table). Ownership uses a **cycle
bit** per TRB, toggling on wrap; rings are made non-contiguous and resizable via **Link
TRBs**. This is the clearest example of the general shape: *N request rings multiplexed
onto one shared completion/event ring*.

**HSA AQL** — user-mode queues in ordinary memory processed as a ring by a hardware packet
processor, with a doorbell signal per queue and read/write index locations; packets are
typed (kernel dispatch, agent dispatch). The point of interest is **user-mode submission**:
no driver, no syscall in the fast path, which forces all safety into the queue structure
itself.

**UFS MCQ** (Linaro) confirms the same shape arriving in yet another standard: circular SQ
of UTRDs, driver is producer, controller is consumer, doorbell increments.

Distilling the family, an in-memory queue is parameterized by a small number of
orthogonal choices:

| Axis | Options seen in practice |
|---|---|
| Ownership encoding | free-running indices (virtio split, NVMe SQ) · phase/cycle bit (NVMe CQ, xHCI) · per-descriptor owner/wrap bit (packed virtqueue) |
| Directionality | request-only · request+separate completion queue · paired SQ/CQ · shared event ring for many request rings |
| Completion order | in-order · out-of-order with tag/CID |
| Element linkage | flat · chained (`next` descriptors) · scatter-gather list · link/segment (xHCI Link TRB, ERST) |
| Notification: SW→HW | doorbell write · doorbell coalescing/batching · polling by device |
| Notification: HW→SW | interrupt (MSI/MSI-X vector per queue) · polling by software · suppression via event index · coalescing by count/time |
| Placement | coherent memory · non-coherent + explicit flush/invalidate · device-local |
| Multiplicity | single queue · per-core/per-context queues · control-plane vs data-plane queues |
| Flow control | queue-full backpressure · credit-based · doorbell throttle |

Every one of those axes is a place where implementations diverge and where bugs live.
Every one is also a natural *parameter* of a reusable construct and a natural *coverage
axis*.

### 2.4 Layer 3 — lifecycle, discovery, and negotiation

Under-appreciated and very re-inventable. Virtio's device-status sequence is the model:

`reset` → `ACKNOWLEDGE` → `DRIVER` → read/negotiate features → `FEATURES_OK` (device may
refuse) → set up queues → `DRIVER_OK` → running; `FAILED` on error, which **requires a
reset before re-initialization**. The spec bothers to state the hardware obligation that
makes the whole thing safe: *"the device MUST NOT consume buffers or send any used buffer
notifications to the driver before DRIVER_OK"*, and that a device which accepted a feature
set once SHOULD NOT refuse the same set after reset (so suspend/resume works).

Generalized, the lifecycle family contains:

- **Capability/version discovery** — capability lists, ID/version registers, register
  vectors with a stride register, RPMsg resource tables, NVMe Identify.
- **Feature negotiation** — offered set ∩ accepted set, with a commit point.
- **Readiness handshake with a hardware obligation attached** (nothing touches host memory
  before the commit point).
- **Quiesce / drain / abort** — the hard part of every real driver. Storage and USB show
  the shape: an abort command that must itself complete, defined interaction between the
  abort's status and the aborted command's status, and the "already in execution phase"
  case where the device must terminate internal tasks before posting completion.
- **Error state + mandated recovery path** (FAILED → reset).
- **Power/clock request-acknowledge handshakes** — the same request/ack shape as a
  doorbell but with a state machine and a "no traffic in flight" precondition.

### 2.5 Cross-cutting concerns

- **Memory ordering.** Every in-memory-queue spec spends real text on barriers. Producer
  must publish payload before publishing the index/ownership bit; consumer must read the
  ownership bit before the payload. On some ISAs, MMIO needs explicit sync between
  operations or the machine hangs. Any pattern library that hides queues must also
  *specify* and *check* the ordering obligations, or it hides the bug too.
- **Coherence / visibility.** Non-coherent placement changes the driver contract (explicit
  cache maintenance) without changing the register map at all.
- **Ambient authority and multiple software agents.** Secure/non-secure aliases,
  per-VM/per-context queues, and semaphore registers all exist because more than one
  software agent shares the device.
- **Timeouts and liveness.** Everything above is a liveness contract in disguise: doorbell
  ⇒ eventually a completion; command ⇒ eventually a response or a timeout. These are the
  properties most worth formalizing and least often written down.

---

## 3. Analysis: is this actually an area where componentization pays?

The survey establishes that the patterns exist and recur. That is *not* the same as
establishing that a component library is the right response. This section argues the
question directly, because the answer materially changes what we should build.

### 3.1 What the evidence actually shows

Every success in the survey is a reused **specification**, not a reused engine.

virtio is the strongest possible case for this entire effort — one queue design reused
across dozens of device classes, two decades, hardware and software implementations alike —
and virtio ships **no** implementation that everyone uses. It ships a specification, and
every device and every driver implements it natively. The same is true of NVMe, xHCI,
SCMI, and PLDM: the reuse is in the contract; the implementations are all bespoke.

The Linux mailbox framework and OpenAMP are the closest things to widely-reused *code* in
this space, and it is worth noticing exactly what they factor out: channel management,
txdone discovery, endpoint naming, the resource table — the plumbing *around* the message.
Neither factors out the message semantics, and neither factors out a datapath.

On the other side of the ledger: there is no widely-reused descriptor-ring RTL engine, and
the reason is structural rather than accidental. Real DMA/queue engines are exactly where
the performance engineering lives — descriptor prefetch depth, descriptor caching,
out-of-order fetch, multi-queue arbitration, pipelining against the bus, credit
management, error-path handling. A generic engine is either rejected by designers as too
slow or too large, or it survives by accumulating parameters until it is unmaintainable.
That is the classic configurable-IP failure mode, and for a data-plane queue engine it
should be treated as the *default* outcome, not as a risk to be mitigated.

### 3.2 The load-bearing distinction: contract reuse vs. implementation reuse

These are different products with different track records, and conflating them is the main
way this kind of effort goes wrong:

- **Contract reuse** — the ownership discipline, the ordering obligations, the liveness
  property, the wrap/full/empty invariants, the checkers, a golden model, the coverage
  model, the PSS scenario library. Historically successful. Portable across wildly
  different implementations *by design*, because that is what a specification is for.
- **Implementation reuse** — a synthesizable engine that ships in silicon. Historically
  successful only for undifferentiated structure, and historically unsuccessful wherever
  the block is on a performance-critical path.

Both are legitimate deliverables. They should not be promised for the same construct
without checking which side of that line it falls on.

### 3.3 The governing heuristic

> **Reuse value is inversely proportional to how performance-critical the implementation
> is.**

Applied to the catalog:

- **Control-plane structure** — interrupt stacks, doorbells, indirect windows, FIFO
  apertures, lifecycle state machines. Nobody differentiates on these. They are re-typed
  near-identically every project and are reliably buggy in boring ways (edge/level policy,
  W1C races, set/clear alias consistency, "who may touch memory before READY"). Individually
  low-value, cheap to build, and they compound. **Near-certain reuse win, both contract and
  implementation.**
- **Message channels and command protocols** — the software-to-firmware case. This is where
  componentization pays *most*, and it is easy to under-rank because it looks less
  interesting than queues. There is no tuned datapath to conflict with: the channel is pure
  overhead, not product. Sequence tags, timeouts, retry, out-of-order responses, unsolicited
  events interleaved with replies, multi-step long-running operations — entirely
  re-invented, entirely undifferentiated, entirely bug-prone. **Highest ratio of
  undifferentiated structure to effort in the whole catalog.**
- **Data-plane queue engines** — **contract reuse yes, implementation reuse no.** Expect the
  synthesizable `fw_queue` to be a reference implementation and a modeling vehicle, not the
  block that ships. Its value is that it makes the contract executable and gives the
  checkers something to check against.

### 3.4 Where the parameterization claim is weakest

§2.3 presents the queue axes as orthogonal. On close inspection they are not, quite.
virtio's indirect descriptors, xHCI's Link TRBs plus the Event Ring Segment Table, and
NVMe's SQ/CQ asymmetry (index doorbell in one direction, phase tag in the other) each carry
idiosyncratic structure that does not decompose into the axis table.

The common 80% is factorable — but that 80% is the *easy* part, and the residue is where
the design work and the bugs actually are. The honest expectation is a framework that
models the skeleton of every queue and the specifics of none. That is a fine outcome if the
deliverable is a contract plus a checker; it is a disappointing outcome if the deliverable
was supposed to be a drop-in device model. Plan for the former.

### 3.5 Design productivity and verification productivity pull in opposite directions

The two goals disagree about abstraction. Design wants the construct to *disappear* into
efficient RTL; verification wants it to stay visible, instrumented, and observable. Each
catalog entry should state which it optimizes. The reasonable split: **verification-first
for queues, design-first for the mailbox / interrupt / lifecycle family.**

### 3.6 The strongest justification is consistency, not saved re-invention

The most durable argument in this document is not "stop re-inventing" — that claim is real
but frequently disappointed, since a pattern library needs roughly three or more uses to
break even and teams reliably prefer their own queue. The stronger argument is
**single source of truth**: one description generating the fw-hdl register block, the
properties, the golden model, and the PSS register model and actions.

This pays *even when every project's queue is bespoke*, because the failure it prevents —
RTL, model, and test drifting apart on descriptor layout, ownership encoding, or register
map — is both expensive and extremely common. Lead with this; treat re-invention savings as
the secondary benefit.

### 3.7 Findings

1. **The patterns are few and stable.** Five families cover the overwhelming majority of
   real HW/SW and SW/firmware interfaces: *(A) control/status idioms*, *(B) message
   channels (mailbox)*, *(C) in-memory queues*, *(D) lifecycle & negotiation*,
   *(E) event/notification delivery*. Everything surveyed — SCMI, PLDM, RPMsg, virtio,
   NVMe, xHCI, AQL, UFS — is a configuration of these five.

2. **Instances differ mostly by parameter choice** — ownership encoding, completion
   ordering, notification policy, placement — but see §3.4: the axes are *mostly*
   orthogonal, not cleanly so.

3. **"Firmware behind a hardware-looking interface" is not a separate category** — it is
   family (B) plus (D), with the semantics pushed into a message grammar. The right fw-hdl
   answer is a message-channel construct whose behavior is supplied by a behavioral model
   (SV class, or a synthesizable process), and whose *contract* — timing class, ordering,
   liveness — is declared separately from the implementation. This is also the case with
   the best reuse economics (§3.3), and the one where a single PSS operation model can
   drive an RTL implementation, a firmware implementation, or a C model unchanged.

4. **The register layer is necessary but not where the value is.** fw-hdl already has
   `fw_reg`/`fw_reg_block`. The leverage is in the layer *above* it: constructs that
   *compose* registers into a doorbell, an interrupt stack, an indirect window, a queue.

5. **Ownership and wrap-around are the bug-dense core.** Phase/cycle bits, index
   comparison, ring wrap, notification-suppression races, and the barrier obligations
   around them account for a large share of real HW/SW integration bugs. The reusable
   asset here is the *discipline and its checkers*, not the engine that implements it.

6. **Verification value comes from pattern-attached properties.** Each construct ships
   (a) SVA/formal properties, (b) a coverage model over the pattern's own axes (wrap, full,
   empty, out-of-order completion, suppression race, abort-during-execution), and (c) a PSS
   scenario library. "Verify our queue" becomes "instantiate the queue's verification
   package and constrain it" — and this holds even when the DUT's queue engine is entirely
   in-house, which is what makes it the robust part of the plan.

7. **Two things must be modeled that are usually left implicit**: the *memory ordering
   contract* and the *liveness contract*. Making them declarative
   (`ordering: publish_payload_before_index`, `liveness: doorbell ⇒ eventually completion
   within N`) is both checkable and a genuine differentiator from every register-centric
   tool on the market.

### 3.8 Verdict

Yes — componentization is productive here, but **the productive unit is the specified
contract plus its checkers, golden model, and PSS package**, with reusable *implementations*
only for the undifferentiated control-plane pieces. Build the catalog; be explicit per
entry about which kind of reuse it offers.

---

## 4. Recommendations

### 4.1 A pattern catalog, prioritized by reuse economics

Ordering follows §3.3 — undifferentiated structure first, performance-critical structure
last — rather than by how interesting the pattern is. Each entry declares its **reuse mode**:

- **full** — contract *and* implementation are reusable; expect the construct to be
  instantiated as-is.
- **contract** — the specification, checkers, golden model, and PSS package are reusable;
  the shipping implementation is expected to be bespoke, and ours is a reference/modeling
  vehicle.

Naming is illustrative.

#### Tier 1 — build first

**`fw_mailbox` + `fw_cmd_protocol` — shared-memory message channel and its protocol.**
*Reuse mode: full.* The highest-value entry in the catalog (§3.3): pure structure, no
datapath to differentiate on, universally re-invented.

- `fw_mailbox`: buffer + request signal + reply signal; polled *and* interrupt completion
  from the same channel; `txdone` discovery policy (`irq` / `poll` / `by_ack`, per the
  Linux mailbox framework); optional message-type multiplexing (MCTP-style); separate
  requester-initiated and platform-initiated channel classes (SCMI A2P / P2A).
- `fw_cmd_protocol`: sequence tags, completion codes, timeouts, retry, out-of-order
  responses, unsolicited events interleaved with responses, and **long-running multi-step
  operations** (the PLDM firmware-update shape) with progress and cancel.
- This pair is where "software interacts with hardware-looking firmware" is actually
  specified, and where one PSS operation model drives an RTL, firmware, or C
  implementation unchanged.

**`fw_irq_block` — the interrupt stack.**
*Reuse mode: full.* `raw_status` (sticky, edge/level policy per source) → `enable` with
set/clear aliases → `status` → aggregation → output line; W1C acknowledge; optional
coalescing by count and time (NVMe-style); optional event-index suppression
(virtio-style). Generates its own register content so it cannot drift from `fw_reg_block`.

**`fw_doorbell` — signal-published-work.**
*Reuse mode: full.* Not just a register write: a typed construct with variants (simple
trigger, argument, address-encoded, split-write), an optional coalescing/batching policy,
and the `doorbell ⇒ eventual service` liveness property. Pairs with `fw_queue`.

**`fw_lifecycle` — reset / discover / negotiate / ready / fail / recover.**
*Reuse mode: full.* The virtio device-status sequence generalized: a declared state machine
with *hardware obligations attached to states* ("no host-memory access before READY",
"FAILED requires reset before re-init", "a feature set accepted once must be re-acceptable
after reset"). Very high verification value at near-zero modeling cost, and cross-cutting —
it applies to every other entry.

#### Tier 2 — the queue family (contract-first)

**`fw_queue` — in-memory work queue.**
*Reuse mode: contract.* Parameterized by the axes in §2.3, with §3.4's caveat: lead with
named profiles, treat raw-axis generality as a non-goal until something demands it.

- Roles: `producer`, `consumer`, `monitor` (matches the fw-proto-kit role structure).
- Ownership policy as a pluggable strategy: `idx_pair` (virtio split / NVMe SQ),
  `phase_bit` (NVMe CQ), `cycle_bit` (xHCI), `owner_bit` (packed virtqueue).
- Element type is a user-supplied descriptor struct; the construct owns *only* the
  ownership/linkage fields.
- Options: chaining, scatter-gather, link/segment entries, out-of-order completion by tag.
- Backed by an `fw_mem_if` master for descriptor/payload access, so it works identically
  against a memory model, an RTL memory, or a bus transactor.
- **The deliverable that matters**: full/empty/wrap properties, "no consumer read of a
  producer-owned entry", "payload visible before ownership transfer", the suppression-race
  property, and coverage of wrap × full × empty × out-of-order × suppression — all of which
  apply to an in-house queue engine just as well as to ours.

**`fw_queue_pair` — request/completion pair.**
*Reuse mode: contract.* SQ+CQ (NVMe), or request ring + shared event ring (xHCI). Adds tag
allocation and retirement, out-of-order completion, completion routing from N request
queues to M completion queues, and the tag-leak / double-completion properties.

**`fw_event_channel`** — *reuse mode: full.* HW→SW async notification independent of any
request: xHCI event ring, SCMI P2A notifications, NVMe AEN. Distinct from completions
because there is no outstanding request to correlate with, which changes both the delivery
mechanism and the overflow policy — what happens when the event ring fills is a real and
frequently-buggy question.

**`fw_abort`** — *reuse mode: full.* Cancel/drain as a reusable sub-protocol: the abort must
itself complete, the abort's status and the aborted operation's status must be jointly
defined, and the "already in execution phase" case must terminate internal tasks before
posting completion. Promoted from Tier 3 — this is where drivers break most often.

#### Tier 3 — the register-composition primitives

*Reuse mode: full* across the board; cheap, low-risk, and they compound.
**`fw_indirect_window`** (addr/data aperture), **`fw_fifo_reg`** (push/pop aperture),
**`fw_semaphore`** (multi-agent arbitration), **`fw_start_done`** (degenerate async op),
**`fw_capability_list`** (discovery plus versioned register vectors with a stride register).

#### Tier 4 — on demand

**`fw_stream`** (credit-based flow-controlled data channel),
**`fw_power_handshake`** (request/ack with a quiesce precondition).

### 4.2 What each pattern must define

To be usable and verifiable, every catalog entry should specify **eight** things. I'd make
this the required template:

0. **Reuse mode and optimization target** — `full` or `contract` per §4.1, and whether the
   entry is design-first or verification-first per §3.5. Stating this up front prevents the
   entry from over-promising, and tells a reader whether to instantiate it or to instantiate
   only its checkers against their own implementation.
1. **Roles and their APIs** — producer/consumer/monitor, in fw-hdl class-level form
   (consistent with fw-proto-kit).
2. **State and encoding** — what lives in registers, what lives in memory, exact ownership
   encoding.
3. **Obligations** — separately for hardware and software, including the *memory-ordering*
   obligations and the *no-access-before-ready* style obligations.
4. **Liveness contract** — what must eventually happen, and any bound.
5. **Verification package** — properties (SVA + formal), a coverage model over the
   pattern's own axes, and the failure-injection points (queue full, wrap during
   suppression, abort during execution, completion of an already-completed tag).
6. **PSS operation model** — see below.
7. **Single-source-of-truth manifest** — the one description from which the register block,
   the descriptor layout, the properties, the golden model, and the PSS register model and
   actions are all generated (§3.6). If any of those is hand-written twice, the entry is
   incomplete.

### 4.3 The PSS side

The natural PSS mapping is:

- **Each pattern operation is a PSS `action`.** `queue_submit`, `queue_reap`,
  `mailbox_cmd`, `negotiate_features`, `abort_tag`, `set_power_state`.
- **Buffers/streams/states carry the data-flow.** A descriptor is a PSS `buffer` object
  produced by `queue_submit` and consumed by `queue_reap`; a queue's occupancy is a
  `state` object, which is exactly how PSS expresses "you cannot reap what you did not
  submit" and how the solver is made to generate legal orderings for free.
- **Tags and queue slots are PSS `resource` pools.** Out-of-order completion, tag
  exhaustion, and queue-full become resource-contention scenarios the solver explores
  rather than hand-written tests. This is probably the single biggest verification win
  available here.
- **Address spaces for in-memory queues.** PSS address spaces / `addr_claim` are the right
  mechanism for placing rings and payload buffers, and address-space *traits* are the
  right mechanism for expressing coherent vs. non-coherent vs. device-local placement.
  Placement then becomes a randomizable axis of the test, not a hard-coded constant.
- **Registers via the PSS 2.1 register model**, generated from the same source as the
  fw-hdl `fw_reg_block` — one description, two outputs, guaranteed consistent.
- **`exec body` targeting a thin C driver layer** per pattern: `fwq_submit()`,
  `fwq_reap()`, `fwmb_cmd()`. The pattern library supplies a reference implementation of
  this layer, so PSS scenarios are portable across simulation, emulation, and post-silicon
  without per-project driver work.
- **PSS 3.0 behavioral coverage** to express "we exercised the wrap-while-suppressed
  interleaving", i.e. coverage over *scenarios*, which is what pattern-based verification
  actually wants to measure.

Concretely, each catalog entry ships as a triple:
`fw-hdl construct` + `verification package (properties + coverage)` + `PSS package
(actions, buffers, states, resources, reference C layer)`.

### 4.4 Fit with existing fw-hdl assets

- **`fw_reg` / `fw_reg_block`** — the substrate for `fw_doorbell`, `fw_irq_block`,
  `fw_indirect_window`, `fw_fifo_reg`, `fw_semaphore`. These constructs should *generate*
  register content rather than sit beside it.
- **`fw_mem_if`** — the access path for every in-memory-queue construct. This is why the
  queue work is tractable: the DMA-agent side already has an abstraction.
- **`fw_reqrsp_if`, `fw_put_if`, `fw_get_if`** — the transaction shapes for command
  channels and completions.
- **Multi-view components** (`multi-view-rearchitecture.md`) — exactly the right mechanism
  for pattern constructs: one logical `fw_queue` protocol with a class-level/TLM view for
  fast modeling, a signal-level view for RTL, and a formal view. A pattern with three
  views is far more valuable than a pattern with one.
- **fw-proto-kit** — the existing initiator/target/monitor + transactor + back-to-back
  sim/formal test structure is the template; the pattern kits should follow it exactly so
  the tooling and idioms are shared.
- **The debug domain (`src/dbg`)** — high leverage here. Each pattern emits structured
  events (`submit`, `doorbell`, `fetch`, `complete`, `suppress`, `wrap`, `abort`), which
  gives a pattern-aware trace/waveform view and, incidentally, the trace that a
  pattern-aware checker consumes.

### 4.5 Suggested sequencing

Revised from the original ordering to follow the reuse economics of §3.3 — cheap
certain-value structure first, the firmware-interaction goal early, the queue family once
the deliverable format is proven.

1. **Template + cheapest exemplar.** Write the eight-part template from §4.2, then do
   `fw_doorbell` + `fw_irq_block` end-to-end (construct, properties, coverage, PSS package,
   single-source manifest). Small, immediately useful, near-zero risk, and it proves the
   triple-deliverable format before anything expensive depends on it.
2. **`fw_mailbox` + `fw_cmd_protocol`**, validated against an SCMI-shaped and a PLDM-shaped
   firmware model. Moved up from step 4: best reuse economics in the catalog, and it
   delivers the "software vs. hardware-looking firmware" goal directly. If only two things
   get built, they should be steps 1 and 2.
3. **`fw_lifecycle`**, then retrofitted onto steps 1–2. Cross-cutting, so it wants at least
   one thing to cut across, but it should not wait until the end.
4. **`fw_queue` with one ownership policy** (`idx_pair`), single direction, no chaining —
   built contract-first: properties, golden model, and PSS actions/buffers/states before the
   engine. Validate against a virtio-split-style toy device.
5. **Add ownership policies** (`phase_bit`, `cycle_bit`) and **`fw_queue_pair`** with
   out-of-order tags; validate against an NVMe-style and an xHCI-style toy. Treat this as
   the explicit **go/no-go test of §3.4**: if modeling both from one construct requires
   per-profile escape hatches rather than parameter settings, stop generalizing, freeze the
   profiles, and keep only the contract and checkers.
6. **`fw_abort`** and **`fw_event_channel`**, retrofitted onto steps 2, 4, and 5.
7. Tier 3 primitives opportunistically — each is cheap enough to add whenever a project
   needs one. Tier 4 on demand.

A useful checkpoint: after step 3, the effort should already be net-positive on its own
terms even if the queue work never happens. If it isn't, the plan is wrong.

### 4.6 Risks worth naming up front

- **Over-parameterization of the queue family.** The axes in §2.3 multiply out to hundreds
  of configurations, and per §3.4 they are not as orthogonal as they look. Mitigation: ship
  a small number of named *profiles* (`virtio_split`, `virtio_packed`, `nvme_qpair`,
  `xhci_trb`, `aql`) as the primary and recommended interface, with raw axes underneath but
  undocumented for external use. Treat "the profile needed an escape hatch" as a signal to
  stop generalizing, per step 5 above.
- **Promising implementation reuse where only contract reuse is real.** Per §3.1–3.3, a
  generic data-plane queue engine will lose to a tuned in-house one. If `fw_queue` is
  presented as shippable IP it will be evaluated on area and throughput and it will fail
  that evaluation, taking the (genuinely valuable) contract and checkers down with it.
  Present it as a reference model and a checker package from day one.
- **Hiding the ordering contract.** If the construct hides barriers, it hides barrier bugs.
  Ordering obligations must be *declared and checked*, not merely implemented.
- **PSS/RTL divergence.** The register map, descriptor layout, and ownership encoding need a
  single source of truth generating both sides (§4.2 item 7). If they are written twice they
  will drift — and since consistency is the primary justification (§3.6), that failure
  inverts the entire value proposition rather than merely reducing it.
- **Adoption economics.** A pattern library needs roughly three or more uses to break even.
  Tier 1 and Tier 3 clear that bar trivially; `fw_queue` clears it only if fw-hdl genuinely
  becomes the substrate for modeling across projects. Sequence accordingly (§4.5) so the
  cheap wins land before the bet is placed.
- **Formal tractability.** Ring properties over parameterized depths need abstraction
  (small-depth induction, symbolic-index arguments). Plan the proof strategy with the
  construct, not after it.

---

## Sources

Register and interrupt primitives:
- [Patterns in register map design (devever.net)](https://www.devever.net/~hl/regmap)
- [Making interrupt design firmware friendly (EE Times)](https://www.eetimes.com/making-interrupt-design-firmware-friendly/)
- [Design Patterns for Device Driver Design (PLoP 2006)](https://hillside.net/plop/2006/Papers/Library/PLoP-Article_1_v6.pdf)

Mailbox / firmware interfaces:
- [ARM SCMI — Zephyr Project documentation](https://docs.zephyrproject.org/latest/hardware/arch/arm-scmi.html)
- [ARM SCMI — Xen hypervisor guide](https://xenbits.xen.org/docs/unstable/hypervisor-guide/arm/firmware/arm-scmi.html)
- [firmware: ARM SCMI support (LWN)](https://lwn.net/Articles/738161/)
- [The Common Mailbox Framework — Linux kernel docs](https://docs.kernel.org/driver-api/mailbox.html)
- [DMTF PMCI / MCTP / PLDM standards](https://www.dmtf.org/standards/pmci)
- [MCTP on Linux introduction — Code Construct](https://codeconstruct.com.au/docs/mctp-on-linux-introduction/)
- [PLDM protocol analysis](https://acutena.com/en/protocols/pldm-mctp/)
- [RPMsg protocol details — OpenAMP docs](https://openamp.readthedocs.io/en/latest/protocol_details/rpmsg.html)
- [RPMsg communication flow — OpenAMP docs](https://openamp.readthedocs.io/en/latest/protocol_details/rpmsg_comms.html)

In-memory queues:
- [VIRTIO 1.4 specification (OASIS)](https://docs.oasis-open.org/virtio/virtio/v1.4/virtio-v1.4.html)
- [Split ring — virtio-spec source](https://github.com/oasis-tcs/virtio-spec/blob/master/split-ring.tex)
- [Virtqueues and virtio ring: how the data travels (Red Hat)](https://www.redhat.com/en/blog/virtqueues-and-virtio-ring-how-data-travels)
- [Packed virtqueue: how to reduce overhead with virtio (Red Hat)](https://www.redhat.com/en/blog/packed-virtqueue-how-reduce-overhead-virtio)
- [Overview of NVMe architecture (Oracle)](https://blogs.oracle.com/linux/overview-of-nvme-architecture)
- [Introduction to NVMe technology (OSR)](https://www.osr.com/nt-insider/2014-issue4/introduction-nvme-technology/)
- [XHCI ring data structures (ReactOS)](https://reactos.org/blogs/xhci-ring-data-structures/)
- [HSA Platform System Architecture Specification 1.2](http://hsafoundation.com/wp-content/uploads/2021/02/HSA-SysArch-1.2.pdf)
- [Multi-Circular Queue support in the UFS subsystem (Linaro)](https://www.linaro.org/blog/multi-circular-queue-mcq-support-gets-added-to-the-ufs-subsystem/)
- [Techniques for coalescing doorbells in a request message (US10884970B2)](https://patents.google.com/patent/US10884970B2)

Portable stimulus:
- [Accellera announces PSS 3.0](https://www.accellera.org/news/press-releases/402-accellera-unveils-portable-test-and-stimulus-standard-3-0-ushering-in-a-new-era-of-verification-efficiency)
- [Celebrating the approval of PSS 3.0 (Siemens Verification Horizons)](https://blogs.sw.siemens.com/verificationhorizons/2024/10/09/celebrating-the-approval-of-portable-test-and-stimulus-standard-pss-3-0/)
