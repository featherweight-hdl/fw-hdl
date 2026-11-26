# Process-based synthesis: multi-process representation and lowering

This is the design for describing logic as stateful processes joined by
latency-insensitive connections, and lowering it to synthesizable RTL with a
timing that is chosen, not written. The same source becomes combinational
where the logic is small and multi-cycle, with flops, where it is large. The
lowered result is Zuspec IR at the sync level, which can be projected back to
sync fw-hdl source, so a designer can read it, keep it, or take over from it.

There are two entry points to the same machinery, and one way to teach it
(the pattern catalog, §16):

- **Dataflow regions in sync code** (§5, §6). Ready/valid logic in `comb()`
  whose payload is a pure function of its inputs ("on valid input, produce
  valid output via `f`") is a signal-level process. It is micro-pipelined:
  stages and a handshake controller are inserted from a richer model than RTL
  retiming has, because the protocol says which signals are handshake and
  which are data, and the handshake licenses a change of latency. This works
  on sync code that exists today, and comes first.
- **Process networks** (§3, §4, §9). Untimed processes joined by method
  calls, whose connections and internal schedules are chosen by engines.

It builds on:

- `docs/methodology/timing.md`: untimed and timed code, latency-insensitive
  ports, shared state (registers, resources), the engine interface
  (`zuspec.synth.proc.sched`) and its three engines. This doc extends that
  model from scheduling *within* a process to scheduling *across* processes,
  and to the signal level.
- `docs/design/automated-lifting.md` §5.3: the ladder of equivalence
  relations, E0 (cycle-exact) to E4 (effect-level), including causal
  constraints. Those relations license both lifting and lowering here.
- `docs/design/pitch.md` §"The abstraction ladder": the rungs.
- The protocol-kit and method-port work (`core-protocol-kit-prep.md`,
  `protocol-kit-followups.md`), which gives the API, endpoint, connection and
  bundle-protocol IR this design builds on.

Process synthesis is the next step after the protocol and method-port work.

## User benefit

1. **One source, several timings.** A block is lowered to a 1-cycle or an
   N-cycle implementation by a goal (clock period, `fw_ii`), not by editing.
   Today, changing the timing of a sync-style block means rewriting
   `step()`/`comb()` by hand.
2. **Existing ready/valid logic gets pipelined.** A user writes the function
   between ready/valid ports and nothing else; the tool chooses the number of
   stages and the stall scheme (global stall, elastic, or credits), and
   re-cuts chains of small stages where the delay model says, not where the
   class boundaries happen to fall.
3. **Related streams stay ordered without being serialized.** Aligned
   streams (AW/W), causal rules (completion after data) and hazards (read
   after write to the same address) are enforced only where they can be
   observed. Everything between is pipelined freely. Most of these rules are
   derived from the dataflow, shared state or the protocol, not written.
4. **Timing is closed across blocks, not inside each one.** The engine sees
   the path through a connection and decides where the flops go. Users stop
   hand-inserting pipeline registers at block boundaries, and stop paying for
   registers they did not need.
5. **No dead end at the top rung.** The lowered result is sync fw-hdl, which
   is readable and editable. A designer who needs exact control of one block
   drops just that block a rung, keeps the higher description as its
   reference model, and checks the hand-tuned version against it. HLS and MLS
   tools leave the user at one level; this is a gradient.
6. **Integration facts are stated once, outside the block.** How many calls
   may be in flight, which connections must stay combinational, and what is
   assumed about a black-box IP are annotations, which can come from outside
   the design. The block source does not change between integrations.
7. **Existing RTL joins on day one.** Wrapped or extracted Verilog takes part
   as a black box, and gets better treatment as annotations are added, before
   it is ever lifted.
8. **Faster simulation of the same design.** Process-level blocks run as
   transaction-level models, beside RTL-level blocks, in one model.

Before (sync style; the stage boundary is where the author put it, and a
2-stage version is a different class):

```systemverilog
class scale extends fw_component implements fw_combinational;
    (* fw_sp_comb = "valid,data" *) fw_rv_sp_out #(word_t) out;
    (* fw_sp_comb = "ready" *)      fw_rv_sp_in  #(sample_t) in;
    virtual function void comb();
        out.set_valid(in.get_valid());
        in.set_ready(out.get_ready());
        out.set_data(in.get_data().a * in.get_data().k + in.get_data().b);
    endfunction
endclass
```

After, dataflow-region form (the user writes `f`; the handshake is derived):

```systemverilog
class scale extends fw_rv_map #(sample_t, word_t);
    virtual function word_t f(sample_t s);
        return s.a * s.k + s.b;
    endfunction
endclass
```

After, process form (the same, as a process with method ports):

```systemverilog
class scale extends fw_component;
    fw_get_port #(sample_t) in;
    fw_put_port #(word_t)   out;
    virtual task run();
        sample_t s;
        forever begin
            in.get(s);
            out.put(s.a * s.k + s.b);
        end
    endtask
endclass
```

Lowered at a slow clock, `scale` is combinational between its neighbours'
registers. At a fast clock, the multiply is split over two stages with a
handshake controller. Both lowerings project back to a sync class like the
"before" one, and both pass the same transaction-level bench. (Syntax is
illustrative; `fw_rv_map` is a proposed library class, §5.3.)

## 0. Status

The plan (§15) does dataflow regions (D-steps) before process networks
(S-steps): they apply to sync code that exists now, and they build most of
what the S-steps need.

| Step | Status | Notes |
|---|---|---|
| Design (this doc) | **draft**, 2026-11-20 | decisions in §17 open; pattern index in §16 |
| D0 Feasibility on `rr_merge_pipe` | **done** 2026-11-20; D1 waits for G4 (`sync-task-domains.md`) | `micro-pipelining-feasibility.md`; results and go/no-go in `examples/rr_merge_pipe/RESULTS.md` |
| D1 Declared dataflow shapes and the region IR node | not started | §5.2–§5.3 |
| D2 Controller and realization library (sync components) | not started | §4.3, §5.5 |
| D3 Region engine: collapse, cut, choose controller | not started | §5.4–§5.5 |
| D4 Related streams, ordering automata, marked-graph analysis | not started | §6, §9.3 |
| D5 Inferring regions from `comb()` code and extracted RTL | not started | §5.3 |
| S0 Decide where the process network lives | not started | §14, §17 Q1–Q2 |
| S1 Connection node in the IR | not started | §4 |
| S2 Project scheduled processes to sync source (R2→R1) | not started | §10 |
| S3 Global engine v1: realizations + budgets across connections | not started | §9 |
| S4 Outstanding *N* and request/response split | not started | §4.4 |
| S5 Opaque blocks: black box + annotations + checks | not started | §7 |
| S6 Fusion of processes | not started | §9.2 |
| S7 Mixed-rung fast model | not started; may become its own plan | §11 |
| S8 Logic migration across connections | not started | §9.2 |
| S9 XLS as a local engine behind the same interface | not started | §13 |

## 1. Principles

1. **Two ladders over one set of rungs.** *Lift* existing RTL as high as it
   will go; *lower* higher descriptions toward synthesizable Verilog. Both
   move between the same rungs (§2), and both are licensed by the same
   interface declarations (§3.2).
2. **IR is the artifact; source is a projection.** Every step produces
   Zuspec IR. A rung is a subset of the IR. Anything in a rung's subset can
   be projected to source at that rung, and reading the projection back
   gives the same IR.
3. **The right rung for each block, and for each fragment.** Higher rungs
   give implementation freedom and fast simulation. Lower rungs give the
   designer control. The sync layer is a first-class description, not an
   intermediate form. A design mixes rungs freely, and a sync block can hold
   a dataflow region that is treated a rung higher (§5).
4. **Freedom comes from declarations already written.** Which connections
   may stretch, and which orders must hold, follow from the protocol, the
   dataflow and shared state. Users add annotations only to pin, cap or state
   assumptions (minimal-spec rule).
5. **Ordering is enforced where it is observable, not where it arises.**
   Inside a region or a network nothing is observed; order is restored at
   E-level ports (§6).
6. **Zuspec owns the network; engines are peers.** The cross-process view
   lives in Zuspec IR. Per-process scheduling engines (fw-hdl's own, XLS,
   others) sit behind one interface. Nothing outside the XLS adapter emits
   XLS IR or DSLX.
7. **Never miss a goal silently.** When a goal can't be met (a recurrence, a
   pinned connection, a capped *N*, an ordering cycle, a black box), the
   engine reports the path and the constraint that blocked it.

## 2. The rungs

| Rung | IR subset | Projects to | Who picks the cycles | Simulates as |
|---|---|---|---|---|
| R0 Opaque | an instance with ports, plus optional annotations (§7) | the wrapped or extracted Verilog | fixed | RTL (extracted or co-simulated) |
| R1 Sync | `step`/`comb` processes; ports with sync and comb fields; may contain dataflow regions (§5) | sync fw-hdl classes (`fw_steppable`, `fw_combinational`, struct ports) | the author, exactly, outside regions; the region engine inside them | sync kernel, cycle by cycle |
| R2 Timed process | `Proc(timed=True)`: edges written (`tick`), `fork`/`join`, timed calls | a `(* fw_timed *)` class with `run()` | the author, exactly | event-driven, edge by edge |
| R3 Untimed process network | `Proc(timed=False)` processes joined by connections (§4); method calls as calls | process-style fw-hdl classes (`run()` with port calls, no edges) | the engines | transaction-level |

R1 is lowered to SV modules as today: one parameterized module per class,
`step()` → `always_ff`, `comb()` → `always_comb`.

Lowering goes R3 → R2 → R1 → SV. A dataflow region in R1 is lifted, as a
fragment, to a one-process R3 description, transformed, and lowered back to
R1. Each arrow produces IR in the next subset and is checked (§12). Lifting
goes the other way and stops at the highest rung whose relation the block's
interfaces allow.

## 3. The process network

### 3.1 Elements

- **Process.** A stateful thread of control owned by a component: a `run()`
  task (R2/R3) or `step()`/`comb()` (R1). Its state is private, except
  through the shared-state rules of `timing.md` (registers, resources).
- **Port.** A component's endpoint for an API: an initiator (calls out) or a
  target (implements the API). Ports are the existing `ApiEndpoint`s.
- **Connection.** A binding of an initiator port to a target port. Today it
  is `ApiConnection`, with no timing meaning. Here it becomes first-class: it
  carries a *realization* (§4) chosen by an engine, within the limits set by
  the protocol and by annotations.
- **Call.** A method call on a port, inside a process. In R3 a call is one
  event of unknown latency. A call with a return value has a request half and
  a response half (the protocol hub's `REQ`/`RSP` split).

### 3.2 Meaning: the contract on each connection

The meaning of an R3 network is the sequential meaning of each process (as in
`timing.md`) plus, for each connection, the equivalence relation its protocol
declares:

| Relation | What must be preserved | What lowering may change |
|---|---|---|
| E0 cycle-exact | everything, every cycle | nothing: the connection is pinned, and so are the blocks' timings on it |
| E1 latency-tolerant, in order | the sequence of operations and data on the connection | when each operation happens; buffering |
| E2 per-interface order | the sequence on each connection, plus declared causal constraints | the interleaving across connections |
| E3 protocol reordering | the multiset, within the protocol's ordering rules | order where the protocol allows it (tagged responses) |

A connection's relation is the protocol's declaration
(`fw_latency_insensitive` gives at least E1). Sync-level and timed ports are
E0 unless their protocol says otherwise; a ready/valid struct port in a sync
block is E1 at its boundary even though the block itself is cycle-exact.
That is what makes dataflow regions (§5) possible.

The relation is what lowering must preserve and what lifting must prove. One
declaration serves both ladders.

## 4. Connections and their realizations

### 4.1 Vocabulary

| Realization | Latency | Breaks data path | Breaks `ready` path | Throughput |
|---|---|---|---|---|
| `comb` | 0 | no | no | full |
| `slice` (registered data/valid) | 1 | yes | no | full |
| `skid` (2-entry) | 1 | yes | yes | full |
| `zero_latency` (1-entry, bypass) | 0 | no | yes | full |
| `fifo(N, bypass)` | 0 or 1 | yes | yes | full; absorbs N of rate mismatch |
| `split(N)` (request/response, calls in flight) | ≥ 1 | yes | yes | up to N outstanding |

The names follow XLS's channel vocabulary (`FlopKind` none/flop/skid/
zero-latency, `FifoConfig` depth/bypass) on purpose; it is a good set. Here
it is Zuspec IR, chosen by the global engine, and lowered by Zuspec. §5.5
adds the controllers for pipelined regions, and §6.2 the ordering elements.

### 4.2 Where a realization lives

A realization is an element instantiated in the **parent** that owns the
connection, between the two ports. The component classes on either side do
not change. This keeps the one-parameterized-module-per-class hand-off: the
choice for one instance of a connection doesn't specialize the classes, and
the parent's module just instantiates a slice, skid or FIFO module.

A choice that is inside a class (how `scale` itself is scheduled or
pipelined) is per class, the same for every instance, unless it is made a
class parameter. Per-instance internal schedules are not supported in v1
(§17 Q4).

### 4.3 Realizations are sync components

Each realization is an ordinary R1 component in the std library (a
ready/valid slice, a skid buffer, a FIFO such as `rr_fifo`), parameterized by
the payload type. So the lowered design projects to sync source built from
parts a designer would use by hand, and the fast model (§11) can run them like
any other sync block. The same holds for region controllers (§5.5) and
ordering elements (§6.2).

### 4.5 The simulation side: crossing endpoints

A connection's realization is sync (§4.3). When one side of it is task code
(an R2 process run as a class, a sequence, a test), that side reaches the
connection through a **crossing endpoint**: a sync component whose
`step()` gives the default (drop `valid` or `ready` after a handshake) and
whose blocking method (`put()`, `get()`) drives the field for the next edge
and returns at the handshake edge. The rules (C1–C8) and the edge model are
in [`sync-task-domains.md`](sync-task-domains.md) §3.2 and §6.5; which
signals task code may touch (its own ports and its direct children's) is
§6.6 there, checked statically as `FW-E-RUN-SYNC-ACCESS`.

The library has them for ready/valid: `fw_rv_put_ep`/`fw_rv_get_ep` in
`src/std/sync/`, and `fw_rv_initiator`/`fw_rv_get_ep` in the spec std
(fw-hdl-rt-sv). They are simulation-only: task code is never lowered
(zuspec-be-sv rejects a `TASK` block). So the endpoint is how an R2 call
meets an R1 connection in simulation. Where this design lowers the R2 side
itself, the call becomes logic on the connection and no endpoint is
involved.
`examples/wb_initiator` is the worked case: a sync Wishbone core that
lowers to RTL equivalent to fw-proto-wb's, with `access()` as `put` then
`get` on the two endpoints.

### 4.4 Calls in flight ("outstanding")

| What | Owner | Where it lives |
|---|---|---|
| **Capability**: can calls overlap; in order or tagged | the protocol | the API class / protocol kit |
| **Requirement**: the least *N* that meets the goals and avoids deadlock | the global engine | derived: *N* ≥ ⌈callee latency / `fw_ii`⌉, plus what the graph's cycles need (§9.3) |
| **Choice**: the *N* actually built | the integrator | an optional annotation on the port or connection (§8) |

- The default is no annotation: the engine uses the requirement.
- An annotation raises *N* (headroom) or caps it (area). A cap below the
  requirement is reported, with the path that needs more.
- An annotation outside the protocol's capability is an error.
- A port has a value on each side (what the initiator issues, what the
  target accepts); a connection's effective *N* is the smaller one.
- For tagged protocols, *N* sets the tag/ID width, so it changes the pins.
  *N* is then a parameter of the kit's binding and of the generated module.
- On E1 in-order connections *N* changes timing only. On E2/E3 connections
  it changes which cross-connection orders can occur, so it is part of the
  relation that checks (§12) and the fast model respect.

A call with a return value that is not combinational becomes `split(N)`: the
request and response halves are separate events, which the protocol kits
already expose. This moves the "outstanding *N*" row of `timing.md` from
*(later)* to required.

## 5. Dataflow regions in sync code

### 5.1 The idea

Much ready/valid logic in `comb()` has the form "on valid input, produce
valid output via `f`", where `f` is a pure function of the payload. That is a
process (`forever { in.get(x); out.put(f(x)); }`) written at the signal
level. Recognized as such, it can be lifted as a fragment to R3, put through
the same transforms as a method-level description, and lowered back to R1
with stages and a handshake controller chosen by the engine.

This is **micro-pipelining**, not retiming. RTL retiming must keep cycle
behaviour at the pins: flops move across logic, but the number of flops on
each path is fixed. Here the ready/valid boundary (E1) licenses *changing*
the latency, and the bundle protocol in the IR says which signal is `valid`,
which is `ready` and which is payload. RTL has neither fact.

### 5.2 Shapes

A region is built from a few stateless shapes:

| Shape | valid | ready | data |
|---|---|---|---|
| map | `o.v = i.v` | `i.r = o.r` | `f(i.d)` |
| join | `o.v = a.v & b.v` | `a.r = b.r = o.r & a.v & b.v` | `f(a.d, b.d)` |
| filter | `o.v = i.v & p(i.d)` | `i.r = o.r \| !p(i.d)` | `i.d` |
| fork (eager) | per branch | per-branch "taken" state, cleared when all branches have taken | copies |

The fork's "taken" bits are the one piece of state in the family; they are
part of the shape's template, not user state.

A **dataflow region** is a maximal connected group of these shapes. Its
boundary is anything that holds user state or isn't E1: registers, FIFOs,
arbiters, `step()` state, and ports whose protocol isn't latency-insensitive.

Within a region the intermediate handshakes are bookkeeping. The engine
collapses a chain `map(f1) → map(f2) → map(f3)` into one graph `f3∘f2∘f1` and
re-cuts it where the delay model says. Most of the gain is here: hand-written
code puts stage boundaries where the class boundaries happen to fall.

v1 collapses within one class: the `comb()` of a class, or a parent whose
children are dataflow shapes, which the parent absorbs into its own module
(§17 Q8). Children used elsewhere keep their own modules.

### 5.3 Recognition: declared first, inferred later

- **Declared (D1).** Library classes where the user writes only the
  function: `fw_rv_map #(I, O)` with `f`, `fw_rv_join` with `f(a, b)`,
  `fw_rv_filter` with `p`. The handshake is derived from the bundle protocol.
  Certain and cheap.
- **Inferred (D5).** Pattern-match the shapes in sync IR, so the feature
  works on existing `comb()` code and on Verilog extracted at R0. This is a
  lift, so it needs a check: a structural match on the IR, or a small formal
  proof that the handshake logic is one of the templates. Inference is the
  "lift" side of the same feature.

D0 findings (`examples/rr_merge_pipe/RESULTS.md` A3, A4):
- **Roles can be derived.** A port's holder shape (`valid` forward,
  `ready` backward, `data` forward) is enough to give each flattened port
  field a channel role, kept as field pragmas. That's what D1's region node
  needs, and what projecting back to source needs.
- **Inference is cheap on the statement structure.** A spike matches maps,
  one lane or N, and names the reason for every rejection.
- **How users write maps is constrained.** `fw_settle` orders `comb()` by
  top-level statement, so `out.data` and `in.ready` must be in separate
  statements. A combined statement makes a false comb loop through any peer
  whose dependencies are coarse. The declared shapes avoid the problem, and
  the catalog page must say so.

### 5.4 Side inputs and state

- **Side inputs.** If `f` reads a configuration register, a value can change
  while data is in flight. The default is to **sample side inputs with the
  token** at region entry: always correct, at some area cost. An annotation
  can declare a side input quasi-static (not sampled), and that assumption is
  checked by an assertion (§7). Sampling at entry changes *which* token first
  sees a new value; that is legal under E1 unless the side input is ordered
  against the stream, which is then a causal rule (§6).
- **State ends a region.** An accumulator or any loop-carried value is a
  boundary. A later step can pipeline the part of the logic outside the
  recurrence, under an II bound, as `fw_ii` does for processes.
- **Protocols.** Ready/valid is the core. Valid-only (no backpressure) and
  credit-based protocols fit with small changes. Anything else is a boundary.
  The model is narrow, but much datapath logic lives in it.

### 5.5 Controllers

Once a region is cut into *k* stages, the handshake controller is a choice,
and joins the realization vocabulary:

| Controller | Cost | Catch |
|---|---|---|
| `stall` (one `ready` drives every stage enable) | fewest flops | the `ready` fan-out becomes the long path |
| `elastic` (skid per stage) | about 2× the data flops | short paths; bubbles collapse |
| `credit` (valid-only stages, output FIFO of depth *k* + 2, credits to the input) | a FIFO | no backpressure inside the pipe; usually best for deep datapaths. D0: *k* + 2 entries keep one beat per cycle |

The region engine picks one per region from the delay model and the area
goal, the same way the global engine picks a connection realization. A pin
in the intent layer (§8) can fix it.

**D0: cut by retiming, not at operators.** In `rr_merge_pipe` the multiply
is ~95% of `f`. Cutting `f` between its operators (`mul | add`) takes
W = 32 from 113 to 108 levels. Inserting the K registers in front of or
after `f` and retiming with ABC takes it to 47 (K = 1) and 37 (K = 2).
zuspec-synth's `DelayEngine.place` also cuts only between operators. So the
engine should:
- choose K and the controller, from a delay estimate of `f` (cheap from
  sync IR);
- insert the registers;
- leave the balancing to a retiming step (yosys/ABC or the vendor tool),
  or expand wide operators before cutting.

The check (§5.6) is unaffected: the controller is the same either way.

### 5.6 Checking a pipelined region

Because `f` is pure, a region checks in two parts:

- **The datapath**: combinational equivalence that the stages compose back to
  `f` (or to the collapsed `f3∘f2∘f1`).
- **The controller**: a template, proven once per template and parameter
  range.

Transaction-level benches cover the whole. This is a stronger story than
general retiming.

D0 did this for the `stall` template (`RESULTS.md` A7):
- datapath ≡ `f` delayed by K, at full width with the sink ready;
- controller properties at a 2-bit payload: the j-th beat out is `f` of the
  j-th beat in, occupancy ≤ K, `out.ready → in.ready`, a stalled output
  stays;
- K = 1..3, each with a mutant that must fail.

The step from a 2-bit payload to any payload rests on the controller never
reading the data (data independence). That is argued from the structure, not
checked. A structural check that next-state control doesn't depend on the
stage data would close the gap.

## 6. Related streams and ordering

### 6.1 Ordering is not serializing

Several streams are often related: a fork that later rejoins, AXI's AW/W/B,
a data stream and its status, a write path and a read path into one memory.
Their rules can be enforced without serializing them, by enforcing each rule
only at the point where it can be observed and leaving everything between
free to pipeline.

The semantics already have the language. `timing.md` rule 4: effects on
different ports are not ordered except through data, a resource, or a
register; to order two ports, use a resource. At the signal level a resource
becomes one of the mechanisms below, built by the engine.

**Stateful merges (D0).** An arbiter's interleaving isn't ordered against
the latency of anything around it. In `rr_merge_pipe`:
- a stage before the arbiter changes the packet order at the output within
  a few packets;
- under backpressure, so does a stage after it, because it changes when
  `ready` reaches the arbiter;
- per-source order and content are always kept.

E1 allows this. It means that a check of a merge is per source, and that a
design needing a fixed interleaving must state it as an ordering rule
(§6.6).

### 6.2 Four relationships

| Relationship | Example | Enforcement | Cost to pipelining |
|---|---|---|---|
| **Aligned**: the *i*-th item on A pairs with the *i*-th on B | a fork that rejoins; AXI AW with W | FIFO order on each stream, pairing at the join; a balancing FIFO on the shorter branch | none, if the balancing depth ≥ the latency difference |
| **Causal**: B's event must not be seen before A's | completion after the data is written; status after the interrupt cause | a data-less token stream from A's commit point to B's issue point | latency on B only; full throughput with enough token buffering |
| **Conditional (hazard)**: ordered only when keys match | read after write to the same address | keyed in-flight tracking (scoreboard), stall or forward on a match | only on collisions |
| **Reorder, then restore** | tagged responses (E3); out-of-order units | sequence numbers or tags at issue, a reorder buffer at the merge | buffer area; none to throughput |

One mechanism underlies all four: **each transaction gets a position in an
order where it enters, and each rule is a relation between positions,
checked where streams meet.** Implicit positions (FIFO order) give
alignment; explicit tags give reordering; key comparison gives hazards; a
token stream gives causality. The engine picks the cheapest that is enough.
The elements (balancing FIFO, token stream, scoreboard, reorder buffer) are
R1 library components, like the realizations (§4.3).

### 6.3 Where to enforce, and what it costs

1. **Enforce at the latest observable point.** Inside a region or a network
   nothing is observed; order matters only at E-level ports. Streams may run
   out of step internally and be put back in order at the boundary: execute
   out of order, commit in order. Late enforcement leaves the most freedom
   upstream.
2. **A rule costs throughput only if it closes a cycle.** "B after A" adds
   latency to B and nothing more. If B's completion also gates the next A (a
   round trip, a credit return), that is a cycle in the marked graph, and
   its tokens over its latency bound the rate. Ordering rules are edges in
   the same throughput and deadlock analysis as realizations (§9.3), not a
   separate one.

### 6.4 Where the rules come from

Following the minimal-spec rule, most are derived:

- **Alignment** from the dataflow: a fork, then a join.
- **Hazards** from shared state: a memory written from one stream and read
  from another is a resource with a key, which the proc IR already models
  (`Lock(res, key, rw)`).
- **Protocol ordering** from the kit: AXI orders within one ID and not
  across IDs. These are the causal constraints of E2/E3.
- **Declared** only when nothing else captures it: a causal rule between two
  ports joined by neither data nor state. One relation, "B after A", in the
  intent layer (§8) or on the protocol.

### 6.5 Unequal rates

AW/W is not 1:1: one AW goes with `len+1` W beats.

- **Static rates** (synchronous dataflow): balancing and buffer sizes are
  static. Supported first.
- **Rates set by a payload field** (`len`): the join holds a counter, and
  balancing FIFOs are sized from the field's maximum. Supported second.
- **Anything else** is a boundary.

### 6.6 Ordering automata and their implementation

The rules of §6.2 are enforced by gating. A comb block passes a transfer only
when the ordering state allows it, and that state advances on transfers
(`valid & ready`) of the related streams, inbound or outbound:

```
out.valid = in.valid  & allowed
in.ready  = out.ready & allowed
```

Two rules for the gates:

- **No comb loop through the gate.** `allowed` comes from registered state or
  from transfers on *other* streams, never from this stream's own handshake
  in the same cycle.
- **The protocol's dependency rules hold at its ports.** AXI forbids `valid`
  waiting on `ready`. Gating `valid` on another stream's `ready` is fine
  inside a region, but at an AXI port it may break the rule, so the engine
  checks it there.

**The FSM is the specification, not the implementation.** A rule is stated
as an *ordering automaton*: a state machine over transfer events, describing
**one** transaction. For an AXI write it steps AW → W beats → W-last → B.
Built as one FSM, it has one current state, so the next AW waits until the
current B is done. That is *N* = 1: a serialized pipeline.

With several transactions in flight, each is at its own phase, so the
automaton is replicated per transaction. For transactions in FIFO order, the
replicas factor into small per-stream counters (or zero-data token FIFOs):

```
aw_cnt, wlast_cnt, b_cnt               // each advances on its stream's transfers
B allowed  when  b_cnt  < min(aw_cnt, wlast_cnt)
W allowed  when  w_txn  < aw_cnt       // only if the protocol orders W after AW
```

Counter width is log₂ of the number of calls in flight, so *N* (§4.4) sizes
them directly. The causal token stream of §6.2 is such a counter pair.

| Level | What it is | Who writes it |
|---|---|---|
| Ordering automaton | the rule, per transaction, over transfer events | derived from the protocol kit or the dataflow; declared only when neither captures it (§6.4) |
| Implementation | one FSM when the rule allows one transaction at a time or *N* = 1 is chosen; counters or token FIFOs when transactions overlap in order; a scoreboard for keyed hazards; a reorder buffer for tagged streams | the engine |
| Checks | the same automaton as a monitor or assertion on the observable ports | generated (§12) |

One automaton thus drives enforcement and checking. Protocol kits are the
natural home for it: AXI's ordering rules, as a per-ID automaton, give both
the gating for a pipelined design and the protocol checker.

Counters cover rules that are per-transaction automata over transactions in
FIFO order: alignment and causality. Keyed hazards need key comparison, and
reordering needs tags; the automaton remains the way the rule is stated.

## 7. Opaque blocks and annotations

A block whose IR the engines can't see inside (hard IP, Verilog not yet
lifted, an XLS-built block, §13) is a black box, or carries annotations that
state assumptions about it. Each level of annotation unlocks more:

| What is known | Comes from | What the global engine may do |
|---|---|---|
| Black box: ports only | nothing | choose realizations on *our* side. Its boundary is taken as unregistered with unknown delay, so the engine registers our side, and says so |
| Timing arcs: which input→output paths are combinational; delay budget per port; registered outputs | annotation, or extracted from a netlist / `.lib` | budget the clock period across its connections; keep a connection `comb` where the arcs allow |
| Transaction contract: E-level, call capability, latency and II range, ordering rules | annotation; the protocol kit gives most of it | retime, buffer and order around it; include it in the marked-graph analysis |
| Functional model: what outputs compute from transaction data | annotation pointing at a model, or a lifted description | move logic across its boundary (§9.2) |

**Annotations are assumptions, so they are checked where the block runs.**
Whatever the engine relied on is emitted as checks on the real block: SVA or
run-time monitors in RTL simulation, assertions in the fast model, formal
where the block is small enough. Assume while scheduling; assert on the
implementation. A wrong annotation shows up as a failure that names the
assumption.

This is a gradient of its own: a block climbs the annotation ladder (arcs are
extracted, the contract comes from its kit) and gets most of the scheduling
benefit before it is lifted.

## 8. The implementation-intent layer

Outstanding *N*, connection and controller pins, quasi-static side inputs,
declared causal rules, black-box assumptions, per-instance `fw_ii` and
latency bounds are all *implementation intent*: facts about an integration,
not about a block's behaviour. They share one mechanism:

- optional, and absent by default;
- may come from outside the design;
- names ports and connections by hierarchical path or by class and member,
  resolved onto IR nodes at elaboration (nothing keys on name strings at
  run time);
- stored as an annotation layer over the IR, separate from the description.

The surface format is deliberately open (§17 Q3). Flexibility is preferred:
SV attributes in the source, a constraint file, dfm task parameters, or a
Python API may all feed the same layer.

## 9. Scheduling

### 9.1 Two levels

- **Global (network) engine, in Zuspec.** Owns the network: realizations,
  budgets, fusion, migration, *N*, ordering elements. Only it can see the
  whole network, so it is ours, whatever local engines are used. The region
  engine (§5) is the global engine applied inside one class.
- **Local (process) engines.** Schedule one process within the constraints
  the global engine hands down: an input-arrival and output-required time per
  port, latency bounds, `fw_ii`. Today's `proc.sched` engines (as-written,
  random, delay) are local engines. XLS is another (§13).

The two iterate: the global engine sets budgets, local engines schedule,
the global engine re-times paths that cross connections and adjusts budgets
or realizations, until the goals hold or the blocking path is reported.

### 9.2 What "across processes" covers, in build order

1. **Realization choice.** Pick `comb`/`slice`/`skid`/`fifo`/`split` per
   connection, and a controller per region. Latency-insensitive design (LID)
   proper.
2. **Budgeting.** On a `comb` connection the producer's output delay plus
   the consumer's input delay fits one period; split the period between
   them, as hierarchical physical design budgets blocks.
3. **Fusion and fission.** Merge small processes joined by `comb`
   connections into one for scheduling (what XLS's proc inlining did, but per
   connection and by choice); split a large one. Collapsing a chain of
   dataflow shapes (§5.2) is the signal-level case.
4. **Migration.** Move logic from the producer into the consumer or back.
   Legal under E1 when the moved logic is a pure function of the transaction
   data. Needs both sides visible as IR (or a functional-model annotation,
   §7) and the checks of §12.

### 9.3 Throughput and deadlock

The design, with its realizations, controllers and ordering edges, is a
marked graph. Its throughput is bounded by its worst cycle (tokens over
latency, the maximum cycle ratio); buffers that are too small on a cycle or
on reconvergent paths deadlock. The engine sizes buffers for both, derives
*N* (§4.4) and balancing depths (§6.2), and reports a throughput-limiting
cycle the way `fw_ii` reports a recurrence path.

### 9.4 Goals and pins

Goals are the existing ones: clock period, `fw_ii`, latency bound *(later)*.
Pins come from the protocol (E0) and the intent layer (§8). The as-written
engines reproduce today's netlists: `comb` wherever today's wiring is
combinational, and a region left as written. That is the regression baseline
for D1–D3 and S1–S3.

## 10. Lowering and projection

```
R3 network ──global engine──▶ R3 network + realizations + ordering elements
           ──local engines──▶ R2 timed processes + realization instances
           ──R2→R1─────────▶ R1 sync components (FSM state, registers, comb)
           ──existing──────▶ SV modules (one parameterized module per class)

R1 region  ──lift fragment──▶ one-process R3 ──region engine──▶ R1 stages + controller
```

Each arrow yields IR in the next rung's subset, and each rung can be
projected to source:

- R2 projects to a `(* fw_timed *)` class with `run()`: what
  `proc/emit_src.py` emits today (a `<cls>_sched extends <cls>` class with
  `tick(1)` per edge and `fork` per `Par`).
- R1 projects to a sync class (`step()`/`comb()`, struct ports with sync and
  comb fields). **This projection is new** (D3 for regions, S2 for
  processes): today a scheduled process goes from proc IR straight to Verilog
  (`proc/lower.py` → `proc/emit.py`). The step to R1 makes the stages, FSM,
  registers and comb logic explicit as sync IR.

Invariants for every projection:

- read back through the front end, it gives the same IR, and lowers to the
  same netlist;
- it runs on the same benches as the source it came from;
- between R1 and the netlist, behaviour agrees cycle for cycle on the pins;
- between R3 (or a region) and anything below it, behaviour agrees per
  connection under its relation (§3.2).

**Taking control of a block.** Lower it, keep its R1 projection as the new
source of that block, and keep its higher description as its reference model
and fast model. The pair is checked under the block's interface relations
(§12). Other blocks stay where they are.

## 11. The fast model over mixed rungs

The fast model executes Zuspec IR at whatever rung each block sits on: R3
processes as transaction-level threads, R1 blocks under the sync kernel, R0
blocks as extracted RTL. Lifting is not needed for a block to run; it only
makes it faster. A dataflow region can run as its `f`, one call per token.

Where rungs meet, an adapter converts calls to cycles and back. These are the
same things lowering inserts: protocol-kit transactors and the realization
components of §4.3. Simulation and synthesis share one boundary mechanism.

Direction matters (`automated-lifting.md` §5.3): a platform fast model must
*refine* the RTL (pick one legal timing); a DV predictor must *cover* all
legal timings. The adapters choose a timing for the first use and expose the
choice for the second.

This step (S7) may become its own plan; it is here so the IR choices of D1
and S1 don't preclude it.

## 12. Checks

| Move | Relation checked | How |
|---|---|---|
| R1 region → pipelined R1 | per boundary port, E1; datapath ≡ `f` | combinational equivalence of the datapath; controller templates proven once; transaction benches |
| ordering elements | the rules of §6.2 at the observable ports | generated assertions on the rules; transaction benches with randomized stalls |
| R3 → R2 (engine) | per connection, its relation | by construction (the rules of `timing.md`), plus the random engine as a soundness harness, plus transaction benches |
| R2 → R1 | cycle-exact on ports | equivalence by construction, then simulation; formal where small |
| R1 → SV | cycle-exact on pins | existing checks |
| hand-tuned R1 vs. its higher description | the block's interface relations | transaction benches from the higher model; scoreboards per connection |
| annotations | the stated assumptions | generated assertions (§7) |
| lifting a block up a rung | its interface relations | `automated-lifting.md` §4–§5 |

Cycle-by-cycle comparison against reference RTL stops working for blocks
whose timing an engine chose. Their benches must check transactions per
connection, which is what fw-hdl-dv's interface operations already give.
Randomized backpressure on every E1 port is part of every such bench: a
pipelined design that only passes with `ready` held high is not checked.

## 13. XLS

From the XLS sources (checkout `~/projects/xls/xls` at `dff59c1a1`,
2025-04-09; newer upstream not checked):

- Each proc is scheduled on its own: `PipelineSchedulingPass` loops over the
  procs (`xls/scheduling/pipeline_scheduling_pass.cc:70`). The proc
  elaboration is built only to resolve proc-scoped channels.
- Proc inlining, the only way procs were scheduled together, was removed in
  Feb 2025 (`edf45dc44`) in favour of multi-proc codegen: one block per proc,
  wired together.
- Channel realizations (`FifoConfig`, `FlopKind` in `xls/ir/channel.h`) are
  inputs set by the user, not choices of the scheduler.
- `IOConstraint` bounds the latency between two channel operations within one
  proc; it relates nothing across procs.
- Combinational paths through `none`/bypass channels are not timed across the
  procs they join.

So XLS schedules *within* a process; our requirement includes *across*. XLS
fits as a **local engine** (§9.1): the global engine hands it one process and
the port budgets, which the adapter turns into XLS's I/O constraints and delay
options. Two limits follow:

- XLS returns RTL, not IR in a rung's subset, so an XLS-built process can't
  be projected back to source. It comes back as an **R0 block with timing
  arcs** known from its schedule (§7). That is acceptable for a peer engine
  and keeps the higher description as the source of truth.
- Migration and fusion (§9.2 items 3–4) can't cross into an XLS-built block.

Today XLS sits behind a different interface (`zuspec.ir.core.engine`:
`accepts`/`build` → RTL) from the `proc.sched` engines. Bringing it behind the
local-engine interface is S9.

## 14. Where things are today

From a survey of the repo (2026-11-20):

- **Process IR** is `zuspec.synth.proc.ir` (`packages/zuspec-synth/src/zuspec/synth/proc/ir.py`):
  `Proc` (with `timed`, `comb`, `obj`, `task`), `Region` (a call region
  carries `CallSite`), `Par`, `Lock`, kept `Loop`s, and a `Design` holding
  the procs of one module plus `Instance`/`Conn`/`Port`. A call to another
  object is a `Region` with `call` set. **There is no connection or channel
  node**; `Conn` is an instance pin.
- **Engines**: `proc/sched/__init__.py` (`Scheduler.schedule(Design) →
  Design`, registry, `finish`). `AsWritten`, `RandomEngine`, `DelayEngine`
  (`proc/sched/{aswritten,random,delay}.py`).
- **Delay model**: `proc/delay.py` `DelayModel` (table: clk-to-q, setup,
  wire, margin, per-op points; `unit` built in; target models such as ECP5
  characterized in fw-picorv32). Arrival times in `proc/timing.py`.
- **Lowering**: `proc/lower.py` → `proc/emit.py` (Verilog);
  `proc/emit_src.py` emits the R2 projection.
- **Driver**: `python/fw/hdl/fe/elab/flow.py` `lower_design(schedule=...,
  emit_sched=...)`; the `fw_latency_insensitive` rule is enforced in
  `fe/elab/translate.py` (untimed→timed calls only through such APIs).
- **Network IR in zuspec-ir-core**: `protocol_hub.py` has `ApiEndpoint`
  (port/export/socket), `ApiConnection`, `ProtocolApi` with `REQ`/`RSP`,
  `ProtocolConverter`; components list `api_endpoints`/`api_connections`.
  Also `DataTypeGetIF`/`PutIF`/`DataTypeChannel(depth)`, used by the XLS path.
- **Sync lowering**: `fe/elab/sync_param.py` → `emit/sync.py`, one
  parameterized module per class. Struct ports with sync/comb fields,
  `fw_sp_comb` (`src/sync/fw_sp_comb.svh`, weaver `python/fw/hdl/weave/sp_comb.py`).
  The bundle protocol (which field is valid, ready, data) is in the protocol
  IR from the kit work, but not in sync IR. D0 spikes it as field pragmas
  (`channel`, `channel_role`, `channel_side`), set in `sync_param.py`.
- **Examples**: `examples/rr_merge` (sync ready/valid, with `LOWERING.md`;
  `rr_fifo` has a comb `out.ready → in.ready` path); `examples/wb_initiator`
  (a sync core with task code reaching it through crossing endpoints, §4.5);
  `examples/xls/*` (XLS path); picorv32 retiming is in the fw-picorv32 packet, not here.

Gaps this design must close:

1. No region node in sync IR, and no library of declared shapes (D1).
2. No R1 projection of anything an engine produced (D3, S2).
3. No delay analysis of sync `comb()` logic as a region; the delay engine
   works on proc IR (D3).
4. Two IRs: the network is in zuspec-ir-core, the processes in
   `zuspec.synth.proc.ir`, and nothing links a `Region.call` to the
   `ApiConnection` it travels over (§17 Q1).
5. No connection node with a realization (S1).
6. Two engine interfaces (`proc.sched` and `ir.core.engine`) (S9, §17 Q2).
7. No cross-process timing: the delay engine sees one `Design` at a time;
   paths through calls are cut at the call region.

Found by D0 (`examples/rr_merge_pipe/RESULTS.md`; G-numbers from
`micro-pipelining-feasibility.md` §0.1):

8. **G4, the class model is one edge late.** Comb logic computed from a
   register and driven to a pin reaches the pin one edge late, because
   `fw_rv_pin` corrects only for sync fields read directly. Every pipelined
   design run as classes hits this. Fix before D2. **Closed 2026-11-21**
   (`sync-task-domains.md` X2, §8.3: the two-phase edge).
9. **G3, no arrays of child components** in the parameterized lowering.
10. **G5, sv-weave identifies specializations by spelling**, so
    specializations of one class from different packages collapse into one.
11. **G6, `fw_settle` works per statement** (see §5.3).
12. **No delay model of generic gates or targets in this tree.** The only
    built-in model is `unit`, which gives every operator one level, whatever
    its width. D0 characterized one from yosys.
13. **The cosynth equivalence harness is specific to AES.** Only its pattern
    carries over. Also, sv2v drops `assert`/`assume`, and SBY's default
    solver (yices) isn't installed.
14. **Composite nesting (G1) and packed composite wires (G2)** in the
    parameterized lowering were fixed in D0.

## 15. Plan

Each step ends green on the root suite, with a Verilator run where RTL is
produced, and every bench on an E1 port runs with randomized backpressure.

Each D-step delivers patterns from §16.2 with all four artifacts (§16.1).

**Dataflow regions first.** They apply to sync code that exists, and they
build the realization library, the controllers, delay analysis across a
boundary, the marked-graph analysis and transaction benches, which the
process network reuses.

- **D0 Feasibility (done).** See `examples/rr_merge_pipe/RESULTS.md`. It
  is go, with the changes folded into D1–D5 below.
- **G4 first.** Fix the class model's comb-from-register pin timing
  (§14 item 8), so that pipelined designs run as classes. Plan:
  `sync-task-domains.md` (separate sync and task domains, a crossing between them, and a two-phase edge).
  D1 waits for it.
- **D1 Declared shapes and the region node.** `fw_rv_map`, `fw_rv_join`,
  `fw_rv_filter`, eager fork, in the sync library; a region node in sync IR
  built from them, with its boundary ports and `f`. D0 suggests the node is
  the channel-role field pragmas (now set by `sync_param`) plus an
  annotation on the `comb` process naming its shape and `f`, not a new node
  type. The as-written region
  engine leaves the region as written. *Exit:* a block written with the
  shapes lowers to the same netlist as its hand-written `comb()` twin.
- **D2 Controller and realization library.** `slice`, `skid`,
  `fifo(N, bypass)`, and the `stall`/`elastic`/`credit` controllers, as R1
  components parameterized by payload and stage count. D0's answer key
  (`examples/rr_merge_pipe/src/*_key.svh`) and its SBY harnesses are the
  starting point. A class can't vary its state with K, so a K-generic class
  needs a stage-array form or one class per K. *Exit:* Verilator
  tests per component, with randomized backpressure; controller templates
  proven with SBY for small parameters.
- **D3 Region engine.** Collapse chains, choose K from the delay model,
  pick a controller, insert the registers, and leave the balancing to
  retiming (§5.5, D0); project the result to R1 source. The D0 spike
  (`python/fw/hdl/spikes/pipeline.py`) already does map → stall-K as IR to
  IR and emits it with no back-end change. Delay comes from sync IR through
  `Term`s (route i in D0); `DelayEngine.place` doesn't fit. *Exit:* a block with a deep
  `f` and a chain of three maps, each at two clock periods: a 0-stage and a
  *k*-stage build from one source, both passing one transaction bench; the
  datapath proven equivalent to `f`; the critical path within the period.
- **D4 Related streams.** Alignment with balancing FIFOs, causal token
  streams, ordering automata implemented as an FSM or as counters (§6.6),
  keyed hazards, reorder buffers; the marked-graph analysis; static and
  field-set rates. *Exit:* an AXI-style write path (AW, W, B):
  AW and W pipelined to different depths and re-aligned, B after the last W,
  full throughput, and a deliberately undersized buffer reported as a
  deadlock with its cycle.
- **D5 Inference.** Recognize the shapes in hand-written `comb()` and in
  extracted Verilog, with a check per match. D0's map recognizer
  (`python/fw/hdl/spikes/dataflow.py`) is the starting point. *Exit:* `rr_merge`'s
  ready/valid paths and the D3 hand-written twins are recognized.

**Process networks next.**

- **S0 Decisions.** Settle §17 Q1–Q2: where the network lives and how
  `proc.ir` relates to it.
- **S1 Connection node.** `ApiConnection` (or a sibling) gains a realization
  and its relation; fe-sv fills them from the protocol; each `Region.call`
  refers to its connection. The as-written global engine sets `comb`
  everywhere today's wiring is combinational. *Exit:* every existing netlist
  is unchanged.
- **S2 R2→R1 projection.** A scheduled process becomes sync IR and projects
  to a sync class. *Exit:* for the existing `proc.sched` tests, the R1
  projection reads back to the same IR and lowers to the same netlist as the
  direct path.
- **S3 Global engine v1.** Realization choice and budgets from the delay
  model, across connections; local engines get port budgets. *Exit:* a
  three-process chain and `rr_merge`, each at two clock periods, from one
  source, passing one transaction bench.
- **S4 Outstanding *N*.** Derived *N*; `split(N)` for calls with return
  values over the kit's `REQ`/`RSP` halves; caps reported. *Exit:* a
  call-graph cycle that deadlocks with *N* = 1 is sized correctly; a cap below
  the requirement is reported with its path.
- **S5 Opaque blocks.** Black-box treatment; timing-arc and contract
  annotations; generated assertions. *Exit:* a wrapped Verilog block with
  arcs gets a `comb` connection; a wrong arc is caught by its assertion.
- **S6 Fusion.** Merge `comb`-connected processes for local scheduling.
- **S7 Mixed-rung fast model.** Likely its own plan.
- **S8 Migration.** Move pure logic across E1 connections.
- **S9 XLS as a local engine.** Port budgets to XLS I/O constraints; the
  result returns as R0 with arcs.

## 16. Pattern catalog

The mechanisms above form a pattern language that designers can learn and
apply. The catalog is how the approach is taught, and also how the plan is
accepted.

### 16.1 One pattern, four artifacts

Each pattern is delivered as:

1. **a catalog page** for designers;
2. **a library class**, its declared form (`fw_rv_map`, …);
3. **a recognizer**, its inferred form, which also serves lifting (§5.3);
4. **a probe**: runnable, with randomized backpressure, at two clock periods.

A pattern is done when its page has a working example. The user-facing
catalog (`docs/methodology/`) grows as each step lands, so no page describes
something that doesn't run; this section is the index until then.

Each page has the same parts: *Problem* → *What you write* → *What the tool
derives* → *Implementations and their costs* → *Checks generated* →
*Pitfalls*. The "what you write / what the tool derives" pair carries the
minimal-spec message.

### 16.2 Patterns

| # | Pattern | Problem | Design | Delivered by |
|---|---|---|---|---|
| 1 | Map stage | on valid input, produce valid output via `f` | §5.2 | D1–D3 |
| 2 | Join | combine one item from each of two streams | §5.2 | D1–D3 |
| 3 | Filter | drop items that fail a test, without stalling | §5.2 | D1–D3 |
| 4 | Eager fork | one item to several consumers that each take it independently | §5.2 | D1–D3 |
| 5 | Fork–rejoin | branches of different depth meet again in step | §6.2 | D4 |
| 6 | Causal token | B must not be seen before A | §6.2, §6.6 | D4 |
| 7 | Ordering automaton | multi-phase transactions (AW → W → B) with several in flight | §6.6 | D4 |
| 8 | Keyed hazard | read after write to the same address | §6.2 | D4 |
| 9 | Tag and restore | execute out of order, deliver in order | §6.2 | D4 |
| 10 | Rate alignment | 1 : `len` streams | §6.5 | D4 |
| 11 | Side input | configuration read by a pipelined `f` | §5.4 | D3 |
| 12 | Recurrence boundary | accumulator or loop-carried state; II bound | §5.4 | D3 (boundary), later (pipelining outside the recurrence) |
| 13 | Annotated black box | IP you can't see inside: assume while scheduling, assert at run time | §7 | S5 |
| 14 | Drop a rung | take control of one block, keep the higher model as its reference | §10 | D3 (regions), S2 (processes) |
| 15 | Pin | fix a connection, a controller or *N* from the intent layer | §8 | D3 (controller), S3–S4 (connections, *N*) |

D5 adds recognizers for patterns 1–11.

### 16.3 Anti-patterns

These may teach more than the patterns. Each gets a page with the pattern
that replaces it, and, where it can be detected, a diagnostic.

| Anti-pattern | Why it breaks | Replace with |
|---|---|---|
| **Ordering by timing**: "status arrives one cycle after the data" | holds only while the design is cycle-exact; breaks silently once anything is pipelined | an explicit rule: causal token (6) or ordering automaton (7) |
| `valid` depending on `ready`; a gate depending on its own stream's handshake in the same cycle | protocol violation; comb loop | gates from registered state or other streams (§6.6) |
| Config changes assumed to take effect instantly inside a pipeline | tokens in flight see the old or the new value depending on depth | side input (11), sampled with the token or declared quasi-static |
| Ordering through a shared register with no resource behind it | the order is a timing accident | a resource (`timing.md` rule 4), giving a keyed hazard (8) or a causal token (6) |

## 17. Open questions

| # | Question | Leaning |
|---|---|---|
| Q1 | Where does the process network live: extend zuspec-ir-core (`ApiConnection` + processes), or extend `proc.ir` with connections? | zuspec-ir-core holds the network and connections (it already has endpoints, connections and `REQ`/`RSP`); `proc.ir` stays the per-process scheduling form, linked to it by connection references. Prefer Zuspec IR, per AGENTS.md |
| Q2 | One local-engine interface for `proc.sched` engines and XLS? | yes: a local engine takes one process plus port budgets and returns IR (R2) or R0 with arcs |
| Q3 | Surface format of the intent layer | open; several front ends into one IR layer |
| Q4 | Per-instance internal schedules | no in v1: per class, or via a class parameter |
| Q5 | Does R2→R1 produce one sync class per process class, or may it emit helper components (FSM, datapath)? | one class per process class, so the projection reads like the source's structure |
| Q6 | Are realization, controller and ordering components visible in the user's hierarchy (debug, introspection) or folded into the parent module? | visible as instances in the parent; named from the connection or region |
| Q7 | Combinational connections between processes in different clock domains | not allowed: a crossing is always a CDC realization (async FIFO), from the domains work |
| Q8 | Do regions span classes? | v1: within one class, or a parent absorbing children that are all shapes; general cross-class regions only with the network engine. D0: the maps around `rr_merge` are separate classes, and pipelining each is enough; a stateful merge between them is a boundary in any case |
| Q9 | Where is the region node: sync IR in zuspec-ir-core, or a fw-hdl structure? | zuspec-ir-core, as an annotation over the `comb` process and its ports, so other front ends (zdc) get it too. D0: the port half works as `Field.pragmas`; promote to typed fields once D1 settles the shape |
| Q10 | Default for side inputs | sample with the token; quasi-static only by annotation, with an assertion |
| Q11 | Rates | static first, field-set (`len`) second, anything else a boundary |
| Q12 | Whose retiming balances the inserted stages: yosys/ABC in the flow, the vendor tool, or our own on `Term`s? | the downstream tool's; the engine guarantees K and the controller, and reports the estimate. D0 measured ABC only, and didn't check its equivalence |
| Q13 | G4: a look-ahead settle for pin bridges, or the kernel committing after the steps? | look-ahead settle; moving the commit breaks `after_tick` and the early-write guard |
| Q14 | Where does the latency-insensitive bench live? | fw-proto, parameterized by beat type, source-of function and model, once a second user appears |

## 18. Related work

- Latency-insensitive design (Carloni et al.): relay stations, the throughput
  of marked graphs.
- Elastic circuits (Cortadella et al., SELF) and dynamically scheduled HLS
  (Dynamatic, Josipović et al.): buffer placement and sizing for timing and
  throughput; eager forks.
- Synchronous dataflow (Lee and Messerschmitt): static rates, balancing and
  buffer bounds.
- Out-of-order execution (Tomasulo; reorder buffers): execute out of order,
  commit in order; scoreboards for hazards.
- Bluespec: guarded atomic methods, and composing them with schedules chosen
  by the compiler.
- XLS procs and channels: per-proc scheduling, channel FIFO configuration
  (§13).
- MatchLib (NVIDIA): latency-insensitive channels in SystemC HLS.
