# Zuspec Semantics — Outline

*Status: outline of a normative specification. Sections marked **[draft]** carry proposed
rules; **[TBD]** marks decisions not yet made. Intended home: `zuspec-ir-core` documentation,
once it settles.*

**Companions:** `one-model-many-hosts.md` (why the IR is the center),
`ir-primitives.md` (kernel primitives and the consolidation of today's IR),
`integration-thesis.md` (SPL / HLS / CAG and the design-side expansion).

---

## 0. Conventions

- **MUST / SHOULD / MAY** are normative, in the RFC 2119 sense.
- **The IR** means the semantic model this document defines — not the Python dataclasses in
  `zuspec-ir-core`, which are one implementation of it.
- **Host**: a language environment a model is written or executed in (SV via fw-hdl,
  Python via zuspec-dataclasses, PSS, C, …).
- **Reference implementation**: `zuspec-be-bc`, the bytecode interpreter that executes IR
  directly. Where this document is silent or ambiguous, be-bc's behaviour is *not*
  automatically normative; the ambiguity is a defect in this document to be resolved.
- Diagnostics identifiers used below (`C1`, `T0`, …) are stable and appear in tool output.

---

## 1. Model overview [draft]

A **model** is a set of type declarations, of which some are **component types**. A model
is used in two **stages**:

1. **Elaboration** — a software-layer program, run before time zero, that creates the
   component instance tree, resolves parameters, wires bindings, and negotiates attributes.
   Its result is a frozen **instance graph**.
2. **Run** — the behaviour of the instance graph over time: processes, actions, and
   clocked logic, each in the layer its scope is qualified for.

Behaviour lives in **scopes** (functions, methods, processes, action bodies, activities,
module bodies). Every scope carries a **layer**: the vocabulary of constructs it may use
and the execution model those constructs obey (§4–§6).

---

## 2. Axes and layers [draft]

### 2.1 Axes of restriction

Layers are defined as points on independent axes. Each axis is ordered from least to most
restrictive; a more restrictive level admits a subset of the constructs of a less
restrictive one.

| Axis | Levels (least → most restrictive) |
|---|---|
| **C — creation** | `C2` objects may be created at any time · `C1` objects created only during elaboration · `C0` structure is declarative (no creation code) |
| **D — data bounds** | `D2` unbounded (growable containers, unbounded integers, recursion) · `D1` bounded at elaboration (fixed-capacity containers, no recursion) · `D0` fixed-width scalars and packed aggregates only |
| **M — communication** | `M2` shared object references across components · `M1` endpoints and claimed resources only |
| **T — time** | `T2` any time construct (absolute delays, cycles) · `T1` cycles of declared clock domains only · `T0` no time constructs |
| **N — determinism** | `N1` open choice points and choosing constraints · `N0` every choice resolved |

### 2.2 Named layers

| Layer | C | D | M | T | N | Typical use |
|---|---|---|---|---|---|---|
| **software** | C2 | D2 | M2 | T2 | N1 | reference models, scenarios, testbench logic |
| **elaborated software** | C1 | D2 | M2 | T2 | N1 | UVM-style environments: static structure, dynamic data |
| **SPL** | C1 | D1 | M1 | T1 | N0 | operation models, embedded C, behavioural design |
| **SPL-hw** | C1 | D0 | M1 | T1 | N0 | SPL that may lower to RTL (FSM) |
| **HLS** | C1 | D0 | M1 | T0 | N0 | statically scheduled datapath |
| **CAG** | any | any | M1 | any | **N1** | activity graphs; lowered by binding policies (N1 → N0) |
| **RTL** | — | D0 | signals | exact cycles | N0 | off the lattice: a distinct model of computation (§6.5) |

**[TBD]** whether "elaborated software" needs a name, or is simply software with `C1`.

### 2.3 Restriction and lowering

Two kinds of edge connect layers:

- **Restriction** — the same scope, rewritten to use fewer constructs. Performed by the
  author. Semantics unchanged where the program already qualified.
- **Lowering** — a tool transformation from one layer to another (§9). Reaches layers that
  are not restrictions of the source, notably **RTL**, which is reached only by lowering
  (from SPL-hw and HLS) or written directly.

```
software ─restrict→ elaborated ─restrict→ SPL ─restrict→ SPL-hw ─restrict→ HLS
                                                         │lower           │lower
                                                         ▼                ▼
                                    CAG ─lower (bind policies)→ SPL     RTL
```

---

## 3. Staging and elaboration [draft]

- Elaboration code is a software-layer program and **MUST** be representable in the IR.
  The IR stores the **generator**, not only its result, so parameterization survives
  translation between hosts.
- Elaboration **MUST** be executable by the reference implementation. Hosts **MAY**
  elaborate natively, but the resulting instance graph **MUST** equal be-bc's for the same
  parameters (conformance, §10). This removes the dual-elaborator divergence risk
  (diplomacy design O-D5).
- Elaboration **MUST** be deterministic: no time, no I/O except declared configuration
  inputs, no dependence on host iteration order.
- At the end of elaboration the instance graph is **frozen**. Under `C1` and below, any
  creation of components, endpoints or bindings during run is an error.
- Phases within elaboration (build, wire, negotiate, resolve) follow
  `reference/diplomacy-integration.md` §5. **[TBD]** which phases are kernel semantics and
  which are library conventions.

---

## 4. The kernel [draft]

### 4.1 Values

- Types: `bits[w]` (signed / unsigned), `bool`, enums with a base width, packed structs,
  fixed arrays, tuples; at `D2`, unbounded `int`, strings, and growable lists, maps, sets.
- Arithmetic on `bits[w]` is two's complement with wrap-around. Width changes (`sext`,
  `zext`, `trunc`) and signedness changes **MUST** be explicit. Front ends resolve their
  host's implicit rules (SV context-determined widths, Python unbounded integers) on entry.
- Shifts by amounts ≥ width yield zero (logical) or sign-fill (arithmetic).
- **[TBD]** division and remainder by zero; out-of-range array index (error in simulation,
  clamp in hardware, as XLS does?).
- Values are two-state. SV four-state and X-propagation are **outside the IR**.

### 4.2 Object model (part of the execution kernel)

- **Classes** with single implementation inheritance, plus multiple **interfaces**
  (pure method signatures). Multiple implementation inheritance is excluded: SV cannot
  represent it, so it is outside the shared subset.
- **Handles**: references to class instances; nullable; equality is identity.
  Dereferencing null is a run-time error.
- **Dispatch**: methods are virtual unless declared otherwise.
- **Allocation**: `new`; storage is garbage-collected; there is no explicit free.
- **Construction**: fields default-initialize, then the constructor runs; constructor
  chaining follows the base-first rule.
- **Errors**: there are no exceptions in the kernel. An error terminates the run with a
  diagnostic (`$fatal` in SV, an uncaught exception in Python). Exceptions are outside the
  shared subset.
- **[TBD]** static members; generics versus parameterized classes; copying semantics.

### 4.3 Structure

Components, instances, interfaces (operations, each `may_suspend` or `immediate`),
endpoints (`port` / `export`), bindings, parameters, attributes, bundles. Specified in
`ir-primitives.md` §3 (P1); to be moved here as normative text.

---

## 5. Scopes and regions [draft]

- Every behavioural scope carries exactly one **layer**. Its constructs **MUST** belong to
  that layer's vocabulary; an IR validator enforces this.
- A scope **MAY** contain a nested `Region(layer, body)`. This is the only way to mix
  vocabularies. A front end that encounters mixed constructs splits the scope into nested
  regions.
- A nested region's layer **MUST** be compatible with its parent's (**[TBD]** the exact
  rule; at minimum, an HLS region nests in SPL, an SPL action body nests in CAG).
- Pure functions (values layer) are callable from any layer.

---

## 6. Execution models per layer

Each subsection specifies: vocabulary, state, time, concurrency, communication,
determinism.

### 6.1 Software [draft]

- **Concurrency**: processes (coroutines) interleave cooperatively, only at suspend points.
  The order in which ready processes resume is **unspecified**.
- **Communication**: shared object references are permitted (`M2`). Programs whose
  behaviour depends on resume order are **racy**; equivalent behaviour across hosts is
  guaranteed only for race-free programs. The validator **SHOULD** flag possible races.
- **Reference behaviour**: be-bc resumes in a deterministic order by default and **SHOULD**
  offer a seeded, randomized order to expose races.
- **Time**: absolute delays and clock-domain cycles (`T2`).

### 6.2 SPL [draft]

- **Communication** only through endpoint calls and claimed resources (`M1`). A `Call` on a
  `may_suspend` operation is a suspend point.
- **Time**: `Wait(n, domain)` advances `n` cycles of a declared clock domain. Each suspend
  point is a beat; lowering to RTL preserves beats as FSM states.
- **Ordering**: program order within a process is the order of effects.
- **Determinism class** (derived): a component using only blocking channel operations and
  no `Select` is **latency-insensitive** (Kahn); `try_*`, `Select` and `Wait` make it
  latency-sensitive.

### 6.3 HLS [draft]

- SPL without time constructs (`T0`), with fixed-width data (`D0`). The loop body between
  channel operations is one **activation**.
- Observable behaviour is the per-channel sequence of values, which **MUST** equal the SPL
  reading of the same scope. Cycle timing is chosen by a scheduler subject to declared
  throughput (initiation interval) and clock-period attributes.
- Being HLS-*eligible* does not make a scope scheduled; scheduling **MUST** be opted into
  (§8.4).

#### 6.3.1 The static subset: value and proc semantics [draft, X0]

These are the semantics the HLS engines implement: the XLS back end first
(`xls-phase0.md`). **2-state SV semantics are normative**: a model written as fw-hdl SV
classes means what the SV means, and an engine inserts any difference from its own ops
explicitly. The construct-by-construct table is `xls-phase0.md` §3, and the conformance
tests in `fw-hdl/tests/xls` pin each rule against Verilator, our interpreter and XLS.

**Values.**
- All values are 2-state bit vectors of fixed width. 4-state declarations are rejected,
  except 1-bit `logic`. A constant with x/z bits is rejected.
- A **packed struct** is a bit vector: its first member is the most significant. A field
  access is a part select at the member's offset; an assignment pattern is a
  concatenation.
- A **packed array** is a bit vector: element `i` of a `[N-1:0]` dimension is at bits
  `[i*W +: W]`. Ascending packed ranges are rejected in X0.
- An **unpacked fixed array** `T a[N]` is an array value, indexed `0..N-1`.

**Widths and signedness.**
- Follow IEEE 1800 §11.6–11.8. After the front end, every width is explicit in the IR
  as a cast, and an expression's width follows bottom-up from its operands (the contract
  in `zuspec-be-xls/width.py`).
- An operand converted **by propagation** (a context-determined operand, §11.8.2) takes
  the propagated type and is sign-extended only if **that** type is signed. For example,
  in `signed a * unsigned b` the `a` is zero-extended.
- An operand converted **by assignment or by an explicit cast** is extended by its
  **own** signedness. A size cast keeps the operand's signedness.
- The IR `ExprCast` extends by its operand's signedness, so the front end retags
  first for a propagated conversion.

**Operators.**
- `+ - *` wrap at the result width.
- Shifts:
  - `<<` and `>>` are logical;
  - `>>>` is arithmetic only on a signed left operand;
  - the shift amount is always unsigned;
  - a shift by the width or more gives 0, or all sign bits for `>>>` on a signed value.
- A comparison is signed only if both operands are signed.
- `&&`, `||`, `!`, the reductions and comparisons are 1 bit.
- **Division and modulo** (resolves S3 for this subset): a divisor **MUST** be a
  non-zero constant, or the division **MUST** be under a condition `d != 0` on the same
  value. Anything else is rejected, because SV's result (x, so 0 in 2-state) differs
  between simulators and XLS gives all ones.

**Out-of-range access** (resolves S3 for this subset).
- A read of an unpacked-array element out of bounds gives 0, and a write out of bounds
  is a no-op.
- A bit select or part select reads 0 for every bit outside the operand and writes only
  the bits inside it. This includes a negative base.
- Verilator does not follow §11.5.1 for packed selects (it wraps the index), so the
  conformance tests take those cases from an LRM model, not Verilator.

**Procs.**
- `run()` is `<prologue>; forever <B>`. One iteration of `B` is one **activation**.
- Class properties and prologue locals are **state**; their initial values come from
  their initializers and then the prologue, which must fold to constants.
- Locals declared in `B` are **temporaries**: 0 on every entry, never state.
- Channel operations:
  - `p.t.get(x)` is a blocking receive and `p.t.put(v)` a blocking send;
  - under a condition they are predicated;
  - their effects happen in **program order**.
- In X0, each channel takes at most one operation per activation and none inside a
  loop. A time-consuming call, a timing control, `break`/`continue`, `casez`/`casex` and
  non-blocking assignment are rejected, with a diagnostic at the SV location.
- The observable behaviour is the per-channel sequence of values. An activation that
  blocks on an empty input has completed the effects before it; the state update does
  not happen.

### 6.4 CAG [draft]

- **Actions** fire when their input flow objects are available, their claims can be
  granted, and their guards hold. **Activities** compose actions (sequence, parallel,
  schedule, select, repeat, replicate, conditional, traversal, bind).
- **Choice points** are explicit. Each **constraint** **MUST** classify as *defining*
  (determines a value; compiles to logic or a check) or *choosing* (attached to a choice
  point). An unclassifiable constraint is an error at hardware targets.
- A model with unbound choice points denotes a **set of legal behaviours** (specification).
  Binding a **policy** to each choice point refines it to one behaviour (implementation).
- **[TBD]** action inferencing semantics; pool binding; the minimum policy vocabulary.

### 6.5 RTL [draft]

- **Synchronous, two-state, cycle-based.** Registers update at their clock edge; combinational
  logic **MUST** be acyclic; there are no delta cycles in the semantics.
- Processes within a module communicate through shared signals.
- Clock-domain crossings **MUST** be declared; an undeclared crossing is an error.
- **Bundles** (§7.2) are first-class.
- **[TBD]** reset semantics (synchronous/asynchronous, polarity as attributes); memories.

### 6.6 Observation (all layers) [draft]

`Assert`, `Assume`, `Cover`, `TraceSite`, `Tap`. Meaning per layer: per-cycle and temporal
in RTL, at a program point in SPL and software, over action occurrences in CAG. Every
lowering **MUST** define what it does with each: preserve, simplify (for example, drop
string formatting, keep the site identity and fields), or strip. Observation constructs are
never qualification violations.

---

## 7. Boundaries between layers [draft]

### 7.1 Boundary constructs

| Boundary | Construct |
|---|---|
| any → values | pure function call |
| SPL ↔ HLS | channels; the HLS region interacts only through channel operations |
| CAG ↔ SPL | action bodies are SPL scopes; claims resolve to resources or endpoints |
| SPL ↔ RTL | an endpoint whose protocol has a **method view**, a **bundle view**, and an **abstractor** relating them |
| software ↔ anything below | endpoints; a software-layer component may drive or observe any endpoint |

### 7.2 Protocols, bundles, abstractors

- A **protocol** is declared once, with a method view (operations and suspend classes) and
  a bundle view (signals), both parameterized by the protocol's parameters.
- A **bundle** has fields, nesting, vectors of bundles, and directions relative to a role;
  each role is a **flip** of the base bundle.
- **Connection**: bulk connect (type- and direction-checked); connect by name with explicit
  tie-off of unmatched fields; connect through an adapter; read-only taps. Unconnected
  fields are errors unless explicitly tied off.
- An **abstractor** maps method calls to signal activity. Standard **calling conventions**
  (always-ready, fixed latency, maximum outstanding, in-order — today's
  `IfProtocolProperties`) **SHOULD** let tools derive abstractors for common protocols;
  others are supplied as transactors.
- **[TBD]** whether guarded methods with ready/enable (Bluespec-style) are a native RTL
  construct.

---

## 8. Qualification and target levels [draft]

### 8.1 Qualification

- Front ends and the IR validator **MUST** compute, for every scope, its level on **every**
  axis, and the most restrictive named layer it satisfies.
- Qualification runs twice:
  - **type-level** — conservative, over all parameter values;
  - **instance-level** — exact, after elaboration (portable, because elaboration runs in
    be-bc).
  Diagnostics **MUST** state the configuration they apply to ("qualifies for SPL when
  `DEPTH > 0`").

### 8.2 Target levels

- A **target** is a per-axis bound, usually written as a named layer. It is an
  **attribute**, inherited down the component tree (nearest setting wins), so a testbench
  can target software while the design under test targets SPL-hw.
- A scope **MAY** target below its parent. **[TBD]** whether above is also allowed.

### 8.3 Outcomes

| Outcome | Meaning | Severity |
|---|---|---|
| at or below target | qualifies | — |
| eligible lower, not selected | e.g. HLS-eligible, not opted in | info |
| **above target** | per-axis gap, with source locations and the responsible constructs | warning or error, set per project phase |
| **regressed** | previously achieved a lower level, no longer does | error in CI |

Example diagnostic:

```
run() [dma_chan] above target SPL-hw:
  C2 > C1  'new' at dma_chan.py:42
  D2 > D0  unbounded queue 'pending' at dma_chan.py:57
  fix both → qualifies SPL-hw
```

### 8.4 Selection vs eligibility

Qualification establishes **eligibility**. Transformations that change timing (static
scheduling, policy binding) **MUST** be selected explicitly by attribute. Inference never
changes behaviour on its own.

### 8.5 Ratchet, waivers, burn-down

- **Ratchet**: each scope's achieved level is recorded; losing a level fails CI; lowering a
  target is a deliberate change. **[TBD]** whether achieved levels live in the model
  repository or in CI state.
- **Waivers**: an above-target finding **MAY** be waived with a recorded reason.
  **[TBD]** fixed waiver categories (debug-only, simulation-only, …) versus free-form.
- **Burn-down**: the count of scopes and axis gaps above target, tracked over time, is the
  project's measure of distance to implementation.

---

## 9. Lowerings [draft]

- Every lowering declares its source and target layer and is either **equivalence-preserving**
  (form changes, behaviour does not) or **refining** (fixes a choice; narrows behaviour).
- Every node a lowering produces **MUST** carry provenance (pass and source nodes).
- Regions produced by lowering are **derived**: read-only in host views; edits to them do
  not lift (`one-model-many-hosts.md` §4).
- Catalog (to fill): CAG → SPL (activities to coroutines; policies to arbitration); SPL-hw
  → RTL (beats to FSM — `zuspec.synth.spl`); HLS → RTL (schedule and pipeline);
  **proposed** (`refinement-views.md`): HLS → CAG (operations as actions with resource
  claims) and HLS → SPL-hw (schedule into a stage-granular TLM), so that HLS → RTL
  passes through checkable architecture views;
  software → C (be-sw, with a garbage-collected heap); observation lowering per layer.

---

## 10. Conformance [draft]

- A **conformance suite** owned by zuspec contains tests per construct and per layer.
- Conformance means **agreement with the reference implementation** (be-bc) on the
  observable behaviour defined for that layer: channel traces for latency-insensitive SPL
  and HLS; legal-set membership for latency-sensitive and CAG; cycle traces for RTL.
- A binding **claims** a construct as native only by passing its tests. Capability
  matrices are **generated from test results**, not written by hand.
- Elaboration conformance: a host's native elaboration **MUST** produce the same instance
  graph as be-bc.

---

## 11. Open questions

| # | Question | Section |
|---|---|---|
| S1 | Does "elaborated software" need to be a named layer? | §2.2 |
| S2 | Which elaboration phases are kernel semantics vs library convention? | §3 |
| S3 | Division by zero; out-of-range indexing (resolved for the static subset in §6.3.1) | §4.1 |
| S4 | Static members, generics, copy semantics in the object model | §4.2 |
| S5 | Compatibility rule for nested regions | §5 |
| S6 | Action inferencing, pool binding, policy vocabulary | §6.4 |
| S7 | Reset semantics and memories in RTL | §6.5 |
| S8 | Guarded methods as a native RTL construct | §7.2 |
| S9 | May a scope target above its parent? | §8.2 |
| S10 | Where achieved levels are stored; waiver vocabulary | §8.5 |
| S11 | Is `Call` the primitive with `Channel` a standard interface, or the reverse? | `ir-primitives.md` Q1 |
| S12 | Serialization format and compatibility promise | `one-model-many-hosts.md` §6 |
