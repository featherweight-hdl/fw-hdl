
# Featherweight-HDL Protocol Kit

A protocol kit defines a set of class-level **APIs** and provides **transactors**
that connect those APIs to a signal-level protocol (ready/valid, wishbone, etc.).
A component written against the API never touches pins; the transactor does.

A complete, runnable reference kit (ready/valid) lives in
`references/example/` — read it alongside this guide. The build below was lifted
from the proven `tests/rv_proto/rv_proto_tb.sv`. Every kit ships **two required
back-to-back components**: a **back-to-back simulation test** that wires the full
transactors together and proves end-to-end integrity through the whole stack (see
"Back-to-back simulation test" below), and a **back-to-back formal verification
component** that proves the protocol contract on the cores with SymbiYosys (see
"Back-to-back formal verification component" below). Neither alone is sufficient —
they cover different layers (see the table in the sim section).

## Roles
- **initiator**: often called a 'master'. Provides an **export** (passive; driven
  when its API method is called).
- **target**: often called a 'slave'. Provides a **port** (active; samples the
  protocol and calls into the connected export). Must be connected to an export.
- **monitor**: passively taps the bus and republishes each beat through a port to
  a subscriber (a multi-cast port, conceptually; the fw library is single-binding
  today, so the example wires one subscriber). Implemented in the example.

Each role may define its own API, or some may be shared. The monitor API is always
distinct, because monitor APIs do not block (they are functions, not tasks).

## Decomposing a protocol into streams
Before building elements, split the protocol into its **independent activity
streams**. A stream is one self-contained flow of beats with its own handshake and
its own backpressure — i.e. one channel that can make progress without waiting on
another. This decomposition is the heart of designing a kit: **each stream becomes
its own API task + its own FIFO(s) + its own clocked drain/fill in the
transactor-interface, and its own segment of the core FSM.** Streams are
independent, so they pipeline concurrently.

How to find the streams: count the independent handshakes. Each direction with its
own valid/ready (or req/ack) pair that advances on its own is a separate stream.
A stream typically has a **request** FIFO (outbound beats this side issues) and,
if the protocol returns something, a **response** FIFO (inbound beats). A pure
one-way dataflow has just one FIFO.

- **Ready/valid** (the example): a single one-way data stream → one task
  (`send`/`recv`) and one FIFO. Simplest case.
- **Wishbone**: a single command stream with a request and a response phase → one
  req FIFO + one rsp FIFO and one task (e.g. `xfer(rsp, req)` — outputs lead,
  see fw-api-kit "Parameter order"), one core FSM that
  drives the cycle and collects `ack`.
- **AXI**: five independent channels — AW, W, B (write) and AR, R (read). Each is
  its own ready/valid stream, so each gets its own task and its own req/rsp FIFO
  with its own clocked drain/fill. They run concurrently (issue AW while R returns).
  Channels that are *logically* coupled (W follows AW; B completes the write) stay
  separate streams at the transactor level; a higher-level API method (`write()`)
  *composes* them — push AW, push W, await B — while the transactor keeps each
  pipelined.

Rule of thumb: **one stream ⇒ one task ⇒ one FIFO (per direction) ⇒ one internal
ready/valid link ⇒ one core-FSM segment.** A multi-stream protocol is just several
copies of the single-stream machinery bundled into one transactor-interface (with N
FIFOs/tasks), one core (with N channel FSMs), and one wrapper exposing all the
pins. Map streams onto roles: an initiator drives the request side of each channel
and consumes the response side; the target mirrors; a monitor taps whichever
channels it reports.

## The core elements (per role)
For each role you build six things (for a multi-stream protocol, replicate the
per-stream pieces — task, FIFO, link, core-FSM segment — once per stream). See the
matching files in `references/example/src/`.

1. **API interface-class** (`rv_<role>_if.svh`) — the class-level contract:
   `interface class` with `pure virtual task`s (blocking). Parameterize the data
   type with `#(type T = ...)`. EVERY API ships an implementation macro (next).

2. **Implementation-template macro** (`rv_proto_macros.svh`) —
   `` `FW_<PROTO>_<ROLE>_IMP(T, IMP, NAME) ``. EVERY implementation of an API MUST
   use this macro rather than hand-rolling the `fw_export` proxy. The macro
   declares a nested class `extends fw_export #(<api>) implements <api>` whose each
   API method redirects to `IMP.NAME``_<method>(...)`, and ends with a member
   declaration `NAME``_imp_t NAME` — so **the macro call needs a trailing `;`**.

3. **Transactor-interface** (`rv_<role>_xtor_if.sv`) — an SV `interface` that
   implements the API methods (`send`/`recv`) against an **internal FIFO** and is a
   **ready/valid endpoint** on an internal link to the core. `send`/`recv` only
   touch the FIFO; a clocked `always` block drains/fills it across the link. This
   FIFO is what gives **pipelining** (see rule 4).

4. **Core transactor module** (`rv_<role>_xtor_core.sv`) — a **clocked FSM** that
   is a ready/valid endpoint on the internal link and runs the actual pin-level
   protocol on the bus. For ready/valid it is a 1-deep skid; for a richer protocol
   (wishbone) it is a larger FSM. The internal-link contract is unchanged.

5. **Transactor module** (`rv_<role>_xtor.sv`) — instances the transactor-interface
   + core and wires them with the plain link nets, exposing clock/reset + the
   protocol pins. A testbench reaches `u_if` to bind a bridge's virtual interface.

6. **Bridge class** (`rv_<role>_bridge.svh`) — holds a `virtual` transactor-interface
   handle and implements (initiator: `extends fw_component`, uses the IMP macro) or
   consumes (target: `extends fw_port #(<api>)`, runs an active `run()` loop) the
   API. Bridges contain the processes that work with the transactor-interface FIFO
   methods, and form the connection to the model (export ↔ port).

### Monitors
A monitor is the same six-element shape with two differences (see the
`rv_monitor_*` files in the example):
- Its **API is non-blocking** — `pure virtual function void observe(...)`, not a
  task. Monitor APIs may not block.
- Its **core only WATCHES** the bus — `valid`/`ready`/`data` are inputs it never
  drives. On each observed transfer (`valid && ready`) it pushes the beat onto the
  internal ready/valid link; the transactor-interface buffers it in a FIFO and
  exposes a **blocking** `get()`. The bridge blocks on `get()` then propagates via
  the non-blocking `observe()`. Because a monitor cannot backpressure the bus,
  size the FIFO to absorb bursts (and note a 1-deep core skid can drop at full bus
  rate — a zero-drop monitor needs a deeper capture path).

## Adapters: higher-level APIs over the protocol API
The transactor APIs (`send`/`recv`/`xfer` per stream) express the protocol's *own*
vocabulary. That is all a simple protocol needs — for ready/valid or even Wishbone,
user code can talk to the low-level API directly. As protocols get richer (multiple
streams, ordering, bursts), you want **adapters**: pure CLASS-layer logic that sits
on top of the low-level role API and carries out higher-level user intent. An
adapter adds NO new transactor, interface, or pins — it is just a component that
consumes one API and provides another.

Shape of an adapter (it is a normal component, like any other):
- It **provides** a higher-level API (an export, declared with that API's
  `` `FW_*_IMP `` macro) and **holds a port** to the lower-level protocol API.
- Its method bodies translate: one high-level call becomes one or more low-level
  calls, composing the streams. Because the low-level streams pipeline, the adapter
  can issue/await across them efficiently.
- Adapters stack: high-level API → adapter → protocol API → bridge → transactor →
  pins. You can layer more than one (e.g. a burst adapter over a single-beat one).

The big win is a **`std` (protocol-independent) API** — e.g. memory access
`read8/16/32/64`, `write8/16/32/64` (and bursts). Write user/test logic and models
against `std`, then pick a protocol by dropping in its adapter; the user code does
not change. Examples:
- **Wishbone → std memory:** a `wb_to_std` adapter provides `std_mem_if`
  (read/write) and holds a port to the Wishbone `xfer` API. `read32(addr)` issues
  one read `xfer`; `write32(addr,data)` issues one write `xfer`; narrower/wider
  accesses set byte enables / iterate. Simple, but it decouples the model from
  Wishbone.
- **AXI → std memory:** the adapter composes channels — `read*` drives AR then
  collects R (handling bursts/`RLAST`); `write*` drives AW + W then awaits B. The
  std API hides all of that.

Adapters exist per role, in both directions: an **initiator-side** adapter turns
high-level requests into protocol activity; a **target-side** adapter turns
incoming protocol activity (received via the low-level target API) into `std` calls
on a model (e.g. a memory model implementing `std_mem_if`). Keep adapters in the
class layer of the kit package (`.svh`), alongside the bridges.

## Design rules (non-negotiable — learned the hard way)
1. **Everything is clocked.** Every interface and module has clock/reset. In this
   flow a module/core output is only reliably observed by another block's clocked
   sampling when it is REGISTERED — a combinational drive into an interface input
   port is lost to a delta-cycle race.
2. **The interface↔core link is ALWAYS plain ready/valid** (`up_valid`/`up_data`/
   `up_ready`); it never adopts the external protocol's language. And it is a real
   clocked handshake, **not a bare registered passthrough** — a passthrough merely
   delays the signals and lets the consumer re-sample a beat the producer has not
   advanced past (duplicated beats). A proper handshake transfers exactly one beat
   per `(valid && ready)` cycle on each side.
3. **Cores are clocked FSMs** translating ready/valid ↔ protocol pins. (A real
   protocol core has an FSM anyway.)
4. **Pipeline via a FIFO in the transactor-interface.** `send` blocks only when
   full, `recv` only when empty; a clocked block drains/fills. The caller runs
   ahead by up to DEPTH beats, decoupled from the link/bus round-trip. Tasks poll
   on `@(posedge clock)`, NOT `wait()` (robust against queue-mutation sensitivity).
5. **Parameterize SYMMETRICALLY, end to end — or not at all.** A parameter on the
   transactor-interface is fine, but it mangles the interface's type (e.g.
   `rv_initiator_xtor_if__D4`), so EVERY element that names that type must carry the
   same parameter: the `virtual` handle (vif) in the bridge, the bridge class
   itself, any typedefs, and the wrapper that instances it. A parameterized
   interface ⇒ a parameterized vif. The failure mode is ASYMMETRY — a
   `#(.DEPTH(4))` instance bound to a plain `virtual rv_initiator_xtor_if` handle
   ("expected ... interface but ... is a different interface"). If a property is
   fixed for the protocol (e.g. FIFO `DEPTH`), the simplest path is to keep it an
   internal `localparam` so no parameter has to be threaded through every element;
   parameterize only what callers genuinely vary. The CLASS layer (APIs, bridges)
   is independently parameterized with `#(type T)`.
6. Gotcha: `checker` is a reserved SystemVerilog keyword (checker/endchecker) —
   don't name a class `checker` (the example uses `sink`).

## Layout & build
```
references/example/
  flow.yaml              # package; fragments: [src, tests]
  src/                   # THE KIT (reusable)
    rv_proto_pkg.sv      # package: import fw_pkg::*; include macros, APIs, bridges
    rv_proto_macros.svh  # the IMP macros
    rv_<role>_if.svh     # API interface-classes
    rv_<role>_bridge.svh # bridge classes
    rv_<role>_xtor_if.sv # transactor-interface (FIFO + ready/valid link)
    rv_<role>_xtor_core.sv  # clocked protocol FSM
    rv_<role>_xtor.sv    # transactor module (interface + core)
    flow.yaml            # FileSet 'files' (kit) + 'fw-src' (fw modeling lib)
  tests/                 # REQUIRED back-to-back sim test (+ it doubles as the
    rv_proto_tb.sv       #   demonstrator of how an APP uses the kit)
    flow.yaml
    formal/              # back-to-back FORMAL proof of the cores (see below)
      rv_proto_fv.sv     # wires init core <-> target core; SVA properties
      flow.yaml          # cores FileSet + formal.sby.BMC task
      PROPERTIES.md      # spec -> invariants -> checkers mapping for this kit
```
SV interfaces/modules cannot live in a package — list them in the FileSet next to
the package file (mirrors `src/flow.yaml` in fw-hdl). The package only `include`s
class/interface-class `.svh` and the macros.

**Inclusion guards — only `<proto>_macros.svh`.** The macros file is the *one*
file that gets an `` `ifndef ``/`` `define ``/`` `endif `` guard, because it is
the only one pulled into more than one place (it is `` `include ``d before the
package *and* may be re-included by tests), and re-`` `define ``ing a macro warns.
Every other `.svh` (API classes, bridges, adapters) is `` `include ``d exactly
once — inside the package — and every `.sv` (interfaces, cores, wrappers,
type/`_pkg`) is its own compilation unit; **none of these carry a guard.** Adding
one is clutter at best and, on a `.sv` compiled standalone, dead text.

Build/run (IVPM env per the build-run-flow notes), from the example dir. The
formal proof additionally needs yosys/sby/boolector on PATH:
```
export IVPM_PACKAGES=<.../packages>
export PATH=$IVPM_PACKAGES/python/bin:$IVPM_PACKAGES/verilator/bin:$IVPM_PACKAGES/yosys/bin:$PATH
dfm run rv.proto.tests.rv-proto      # back-to-back sim test, expect: [rv_proto] PASS
dfm run rv.proto.formal.fv           # formal proof,          expect: DONE (PASS)
```

## From spec to checkers: identifying invariant properties
The hard part of formal is not writing assertions — it is deciding *what* to
assert. Work from the protocol specification and extract **invariants**:
statements that must hold on *every* cycle (or every cycle after some trigger),
expressible from the current state plus a bounded history (`$past`). Each
invariant maps to a small **synthesizable checker** — a register or two plus an
`assert`. Build the list once per protocol; it is the same list for sim
assertions and for the back-to-back formal harness.

**How to mine a spec for invariants.** Read each "shall/must/never/always"
sentence and sort it into one of these recurring classes. Most protocols are
fully covered by them; the right-hand column is the synthesizable checker shape.

| Invariant class | What the spec says | Synthesizable checker pattern |
| --- | --- | --- |
| **Handshake stability** | once asserted, a request stays asserted and its payload is held until accepted | clocked `$past`: `$past(valid) && !$past(ready)` ⇒ `valid && $stable(data)` |
| **No phantom transfer** | a beat moves only on a full handshake | a transfer event is *defined* as `valid && ready`; assert nothing moves otherwise (counters only advance on the event) |
| **Range / capacity** | a FIFO never overflows; a pointer/counter stays in range | `assert (count <= DEPTH)`, `assert (ptr < DEPTH)` — direct on the state reg |
| **One-hot / legal state** | the FSM is always in exactly one legal state; illegal encodings never occur | `assert ($onehot(state))` or `assert (state inside {legal...})` |
| **Mutual exclusion** | two actions never happen together (e.g. read and write same slot) | `assert (!(a && b))` |
| **Ordering** | beats are delivered in the order issued | the *anyconst-index* tracker (below): the N-th out is the N-th in |
| **Conservation / integrity** | nothing is lost, duplicated, or corrupted end to end | two counters (issued/accepted) + an anyconst-index data capture |
| **Framing** | `last`/`first` rules, no data after `last`, packet length matches a count | a clocked flag reg tracking frame phase + `assert` on illegal transitions |
| **Liveness** (caution) | a request is *eventually* accepted | NOT a safety invariant — BMC can't prove "eventually". Approximate with a **bounded** check (`assert` a stall counter never exceeds K, under a fairness `assume` that the peer eventually grants), or a `cover` that the grant is reachable. True liveness needs unbounded engines + fairness and is usually out of scope for the kit proof. |

**Two synthesizable building blocks** carry most of the weight:
- **`$past`/`$stable`/`$rose`/`$fell`** — bounded history. Synthesizable because
  yosys turns them into shadow registers (only under `read_verilog -formal`).
  Guard with an `f_past_valid` reg so the first cycle is not checked.
- **Free-flowing tracker with `(* anyconst *)`** — for ordering/conservation,
  pick an arbitrary fixed index `f_idx`, count issued and accepted beats, capture
  the payload of the `f_idx`-th issued beat, and assert the `f_idx`-th accepted
  beat equals it. One symbolic constant proves the property for *all* positions.
  This is pure RTL (counters + comparisons), so it is fully synthesizable.

**Rules for keeping checkers synthesizable (yosys-friendly):**
- Use registers, wires, `$past` family, `(* anyconst *)`/`(* anyseq *)`. Avoid SV
  queues, classes, dynamic memory, `real`, and DPI — the same things that keep the
  *cores* synthesizable (it is why the proof targets the cores, not the
  transactor-interfaces).
- Prefer **immediate** assertions (`assert(expr)` in `always @(posedge clk)` /
  `always @(*)`) over rich SVA sequences — yosys's concurrent-SVA support is
  limited; a hand-rolled `$past` expression is more portable than a multi-cycle
  `|=> ##[1:3]` sequence.
- Classify each property as **`assert` (the DUT must guarantee)** vs **`assume`
  (the environment/peer guarantees)**. In the back-to-back harness the cores' own
  outputs are `assert`ed; the free producer/consumer stimulus is left
  unconstrained (or lightly `assume`d if the protocol restricts legal inputs).
- Add a **`cover`** for every key property so a vacuous pass is caught (e.g. cover
  that a beat actually traverses end to end).
- Remember the **safety/liveness split**: the classes above except *Liveness* are
  safety invariants — BMC finds any violation within `depth`, and `mode prove`
  (k-induction) can close them unboundedly. Liveness needs a different engine.

**Worked example — ready/valid (the kit).** Mining the one-line ready/valid spec
("a beat transfers when `valid && ready`; the source holds `valid`/`data` until
accepted; beats are delivered in order, none lost") yields exactly the three
invariants the harness checks: *handshake stability* (bus + link contracts),
*ordering*, and *conservation/integrity* — the last two collapsed into the single
anyconst-index tracker. A richer protocol adds rows: **Wishbone** adds a *framing*
invariant (`ack` only inside an active `cyc && stb` cycle) and a *range* invariant
on any pipelined outstanding-count; **AXI** adds *framing* per burst (`RLAST` after
exactly `ARLEN+1` beats, no `R` without an outstanding `AR`) and *ordering* per ID.
Each new row is one more small checker in the same `` `ifdef FORMAL `` block.

## Back-to-back simulation test (required)
Every kit ships a **back-to-back simulation test** that wires the **full
transactors** together — `initiator_xtor` directly to `target_xtor` over one
shared bus (plus a `monitor_xtor` tapping it) — and proves data integrity end to
end through the *complete stack*. This is a deliverable on the same footing as the
formal proof: the kit is not done until it passes (expect `[<proto>] PASS`).

**Why it is distinct from the formal proof.** The formal harness deliberately
drives only the synthesizable **cores** (the queue-based `*_xtor_if.sv` and the
bridges are not synthesizable, so yosys never sees them). That leaves the entire
**transactor-interface FIFO + bridge + class-API path unproven**. Only a
*simulation* back-to-back run exercises the full path the user actually
instantiates:

| | Wired back-to-back | Covers |
| --- | --- | --- |
| **sim test** (`<proto>_tb`) | full **transactors** (bridge + `xtor_if` FIFOs + cores) | the whole stack — incl. the FIFO/bridge path formal can't see |
| **formal** (`<proto>_fv`) | just the synthesizable **cores** | the protocol contract, exhaustively |

It catches the class of bug formal cannot: FIFO depth/ordering errors,
bridge/`run()`-loop deadlocks, request↔response pairing, blocking semantics, and
the registered-handshake/delta-cycle rules (design-rules 1–2) as they play out
across the real FIFOs.

**What it must do.** Instance the full transactor modules on one shared bus; drive
a directed mix of traffic from a component over the initiator API against a
**model** behind the target API (a memory model for a memory-mapped protocol);
**check true round-trip integrity** — for a protocol that returns data (wishbone,
AXI), assert each read returns the previously written value, not merely
count/order (the rv demonstrator only checks count/order because ready/valid is
one-way; a request/response protocol must read back). Exercise **backpressure on
both sides**, every **termination/response variant** the protocol defines (e.g.
wishbone ERR/RTY), and any **multi-beat framing** (block/RMW/burst). Have the
**monitor** observe every completed beat and assert its stream matches what was
issued. Add a **watchdog** `$fatal` so a broken handshake fails fast. Place it at
`tests/<proto>_tb.sv`, run via `dfm run <proto>.tests.<proto>` — it doubles as the
demonstrator of how an app uses the kit.

## Back-to-back formal verification component
Every kit ships a **formal proof that wires two cores back-to-back** and checks
the protocol contract on the kit's real RTL with SymbiYosys (via
`dv-flow-libformal`'s `formal.sby.BMC` task). See
`references/example/tests/formal/`.

Why the cores: the **cores are the only synthesizable RTL in the kit** — clocked
FSMs that yosys can reason about. The transactor-INTERFACES use SV-queue FIFOs
and are not synthesizable, so the harness drives/drains the cores' internal
ready/valid LINK directly — exactly the link the transactor-interface would
otherwise sit on:
```
free src --up link--> [initiator core] --bus--> [target core] --up link--> free snk
```
The producer feeding the initiator and the consumer draining the target are
**free formal inputs**, so the solver explores every legal interleaving and every
backpressure pattern — no testbench stimulus to write. The harness (`rv_proto_fv`)
asserts, in an `` `ifdef FORMAL `` block (yosys defines `FORMAL` under
`read_verilog -formal`):

1. **Bus contract** — the initiator core (bus producer) holds `valid`/`data`
   stable while the target stalls (`$past(valid) && !$past(ready)` ⇒ still valid,
   data unchanged). This is the ready/valid handshake rule.
2. **Link contract** — the target core (up-link producer) likewise holds
   `up_valid`/`up_data` stable while the sink stalls.
3. **Data integrity, end to end** — the classic *anyconst-index* method: capture
   the data of the `f_idx`-th beat that enters the initiator, then require the
   `f_idx`-th beat leaving the target to equal it. Proves no loss, no duplication,
   in order, no corruption — i.e. the back-to-back pair is a lossless in-order
   channel.

How to apply it to a new kit / multi-stream protocol:
- One FileSet lists **only the synthesizable cores** (never the queue-based
  `*_xtor_if.sv` / package files — yosys chokes on `logic q[$]`); the harness
  FileSet adds `rv_proto_fv.sv`; the `formal.sby.BMC` task `needs` both with
  `top: rv_proto_fv`.
- Drive each core's request/up-link side from free inputs and wire the bus
  between cores. For a **multi-stream** protocol, replicate the per-stream
  source/sink + integrity tracker once per channel (each channel is an
  independent ready/valid stream — same contract + integrity proof per stream).
- Keep the SMT state small so BMC stays fast: a narrow tracked-index counter
  (`CW`), and a `depth` just large enough for a few beats to traverse (the
  1-deep-skid cores cross a beat in ~3 cycles; depth 14 proves in well under a
  second). Wider FIFOs/deeper pipelines need proportionally more depth.
- **Always confirm the proof has teeth**: inject a bug (e.g. corrupt one data bit
  on capture) and check sby reports `Assert failed` / `DONE (FAIL)`. A proof that
  can't fail is verifying nothing — and note that *without* `read_verilog
  -formal`, yosys silently drops all assertions and everything "passes." The
  teeth check is what catches a *vacuous* proof (asserts present but the tracked
  beat never reaches them), not just a wrong one — so it is mandatory, not
  optional.
- **If the cores use SystemVerilog the bundled yosys can't read** (packed
  structs, packages, enums — an older yosys rejects these), preprocess the cores +
  harness with **`sv2v`** into plain Verilog before SymbiYosys, and have the
  `formal.sby.BMC` task consume that generated `.v` (e.g. a `shell: bash` task that
  runs `sv2v` and emits the FileSet via `dfm-out`). **Pass `sv2v --exclude=Assert
  -DFORMAL`**: `--exclude=Assert` is mandatory — without it sv2v *silently strips
  every `assert`/`assume`/`cover`*, producing a vacuous always-passing proof (the
  same silent-drop failure as above, and again caught only by the teeth check).
  Make the sv2v step `needs` the core/harness FileSets so a source edit re-runs it
  (else the proof runs against a stale conversion).
- **The proof always re-runs (`uptodate: false`).** `formal.sby.BMC` carries
  `uptodate: false` in its base definition (in `dv-flow-libformal`, exactly as
  `hdlsim.SimRun` does) — a formal proof is a *run*, not a build artifact, so a
  cached "PASS" never stands in for an actual run after a change. You inherit this;
  don't set it per-instance. **But** any *custom* convert step you add (e.g. the
  `sv2v` `shell: bash` task) is your own task and is NOT covered — mark it
  `uptodate: false` yourself, or a stale conversion reintroduces the vacuous-proof
  trap above. Input FileSets stay content-hashed as normal.
