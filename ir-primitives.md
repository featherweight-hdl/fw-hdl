# Zuspec IR as the Semantic Core — Primitive Sketch

*Status: sketch, for discussion. Grounded in `packages/zuspec-ir-core` as it exists today.*

**Premise** (follow-on to `integration-thesis.md`): the core semantics live in zuspec IR.
Front ends (fw-hdl SV, zuspec-dataclasses Python, PSS, …) are entry points that produce
IR; back ends regenerate executable, *readable* artifacts from it. zuspec owns
translation; bindings such as fw-hdl ship translator plugins (front end + back end +
runtime library). Design in Python, hand SV classes to the DV team, lower to RTL, emit C
for firmware — all from one IR.

---

## 0. Two observations about today's IR

**It is a union of front-end shapes, not a semantic core.** The same concept is encoded
several ways depending on which front end produced it:

| Concept | Current encodings |
|---|---|
| channel / API endpoint | `DataTypeChannel`, `DataTypeGetIF`/`PutIF`, `QueueType` + `FieldKind.QueueField`, `IfProtocolType`, `FieldKind.Port/Export/CallablePort/ProtocolPort/…` |
| process | `sync_/comb_/wire_/proc_processes` lists, `Process`, `ScCoroutine`, pipeline IRs |
| concurrency | `SpawnStmt`/`SelectStmt`, `ScSpawn`/`ScSelect`/`ScJoin`, `ActivityParallel`/`ActivitySelect` |
| pipeline | `pipeline.py` (`PipelineRootIR`, stages) and `pipeline_async.py` (`IrPipeline`, hazards) |
| clock | `Field.clock`, `Function.metadata['clock']`, `DataTypeComponent.clock_domain`, pragmas |
| comments | `Function.comment` only; `Field.pragmas` from `# zdc:` comments |

And some nodes are Python-only: `ExprRefPy`, `DataTypePyObj`, `DataType.py_type`,
comprehensions/lambdas (`expr_phase2.py`), `width_expr` as a Python lambda.

**Interchange IR and pass IR are mixed in one package.** `Sc*` (scenario coroutines),
the FSM/pipeline forms, and `DomainNode` are *lowering-internal* representations. They are
useful, but they are not something a front end should emit or a translator should
consume.

The sketch below therefore proposes: **a small kernel with defined semantics**, organized
into **profiles**, with **presentation carried alongside but never semantic**, and a hard
line between the **interchange IR** (stable, serialized, versioned) and **pass IRs**
(free to change).

---

## 1. Design rules

1. **Every primitive has execution semantics written down**, precise enough that two
   back ends producing different languages can be checked against each other.
2. **One encoding per concept.** Sugar is a front-end/back-end concern, recorded as a
   presentation hint (§2), not as a second node type.
3. **Explicit beats implicit.** Widths, extensions, truncations, signedness, and
   suspend points are explicit in the IR. Front ends resolve their language's implicit
   rules (SV context-determined widths, Python unbounded ints) on the way in.
4. **Components interact only through endpoints and declared resources.** No shared
   mutable state across components. This is what makes cross-language execution
   equivalent (§4).
5. **Type-level and elaborated IR are both first-class.** Translation between source
   languages happens at the *type* level so parameterization survives; lowering happens on
   the *elaborated* instance graph.
6. **Stripping all presentation must not change behaviour.** This is a testable
   invariant.

---

## 2. Presentation layer (on every node)

Move from `Function.comment` to a general carrier on `Base`:

```python
@dc.dataclass(kw_only=True)
class Base:
    loc:   Optional[Loc]        = None   # exists
    prov:  Optional[Provenance] = None   # exists (provenance.py), promote to Base
    doc:   Optional[Doc]        = None   # NEW
    hints: Dict[str, Any]       = {}     # NEW: namespaced, non-semantic

@dc.dataclass
class Doc:
    lead:     List[str]      # comment block immediately above
    trail:    Optional[str]  # end-of-line comment
    docstring: Optional[str] # Python docstring / SV `/** */` header
```

- **`hints`** carry idiom and naming intent, namespaced by binding:
  `{"fw.idiom": "FW_PUT_IMP"}`, `{"py.decorator": "zdc.proc"}`,
  `{"name.src": "rx_fifo"}`. A back end uses hints from its own namespace to re-sugar,
  ignores the rest, and must produce correct code with none.
- **Capture.** pyslang exposes comments as trivia on tokens. Python's `ast` discards
  comments (docstrings survive), so the Python front end needs a `tokenize` pass to
  re-attach them by line.
- **Granularity.** Declarations and statements carry `Doc`. Comments inside expressions
  are dropped, by policy.
- **Names.** IR keeps the source name. Each back end legalizes deterministically
  (keyword collisions, case rules) and records the map, so debug output can be traced
  back.

---

## 3. The kernel, by profile

Profiles layer; each binding declares which it can read (front end) and write (back
end). `profile_rgy.py` is the existing hook, and zuspec-dataclasses already has IR-level
profile checkers (`ir_checker/`: `python_profile`, `retargetable`,
`sprtl_synthesizable`). Those move to zuspec and run on IR from any front end, so the
same "can't lower this because…" diagnostics apply to SV and Python sources alike.

### P0 — Values and pure computation

| Primitive | Notes |
|---|---|
| `Bits(w, signed)`, `Bool`, `Enum(base)` | bit-accurate; all width changes explicit (`Sext`, `Zext`, `Trunc`, `Cast`) |
| `Struct` (packed / unpacked), `Array[N]`, `Tuple` | packed = has a bit layout |
| `Param` (type / value), `Specialize` | elaboration-time; replaces Python lambdas in `width_expr` |
| `Function` (pure) | no suspend, no side effects outside locals and return. The HLS unit of computation |
| expressions, statements | today's `expr.py`/`stmt.py` minus Python-only forms; bounded `For` |

Semantics: two's-complement, fixed width, defined overflow (wrap), defined
out-of-range indexing (choose: error in sim, clamp in synthesis — XLS clamps).

### P1 — Structure

| Primitive | Notes |
|---|---|
| `ComponentType` | fields, children, endpoints, behaviours, attributes, parameters |
| `Instance` | child component, with parameter bindings |
| `Interface` | a set of `Operation`s: signature + **suspend class** (`may_suspend` = SV `task` / Python `async`; `immediate` = function) |
| `Endpoint(role=port\|export, iface)` | fw-hdl's `fw_port`/`fw_export`; zdc's ports/exports |
| `Bind(port → export)` | today's `Bind`/`bind_map` |
| `Attribute(name, value, rule)` | the negotiation bag from `reference/diplomacy-integration.md`: clock domain, address map, widths |
| `Extern` | an implementation outside the IR (exists: `DataTypeExtern`) |

Elaboration produces an **instance graph**: resolved parameters, resolved bindings
(port → terminal implementation), negotiated attributes.

### P2 — Behaviour and communication (CSP core)

| Primitive | Notes |
|---|---|
| `Process` | a coroutine owned by a component, started at run; replaces the four process lists, `Process`, and (as interchange) `ScCoroutine` |
| `Call(endpoint, op, args)` | the one way to cross a component boundary. Suspends iff the op is `may_suspend` |
| `Channel[T](depth)` | a **standard interface** with built-in semantics: `put`, `get`, `try_put`, `try_get`, `peek`, `can_put`, `can_get`. Depth 0 = rendezvous. Replaces `DataTypeChannel`/`GetIF`/`PutIF`/`QueueType` |
| `Wait(cycles, domain)` | time, in cycles of a clock domain. fw-hdl `tick(n)`, zdc `cycles(n)` |
| `Event` (component-local) | level-sensitive notify/wait, local to a component (the `wait(flag)` idiom) |
| `Fork(branches, join=all\|any\|none)` | structured concurrency; replaces `SpawnStmt`/`ScSpawn` |
| `Select(guarded ops)` | wait for the first ready operation among several; replaces `SelectStmt`/`ScSelect` |
| `ClockDomain(period, parent, divisor)`, `ResetDomain` | one encoding; replaces `Field.clock`/metadata/pragmas |
| `Process.timing` | `explicit` (author-written beats, today's default) \| `static` (scheduler chooses stages, with II / period attributes) \| `dynamic` (CAG) — the "one knob" from the thesis |

Ordering: program order within a process is the effect order (XLS's tokens are implicit).

### P3 — Actions and activities (CAG)

| Primitive | Notes |
|---|---|
| `ActionType` | inputs/outputs (flow objects), claims, constraints, body (a P2 `Process` body) — exists as `DataTypeAction` |
| `FlowObject(kind=buffer\|stream\|state\|resource)` | exists as `FlowKind` |
| `Pool(T, capacity)`, `Claim(lock\|share)` | exist (`Pool`, `ClaimMode`) |
| `Activity` | seq, par, schedule, select, repeat, replicate, if/match, traverse, bind — exists in `activity.py` |
| `ChoicePoint(domain)` | NEW: an explicit point of legal nondeterminism (which action, which resource instance, which order) |
| `Policy(choice, kind)` | NEW: binds a choice to priority / round-robin / age / random. Unbound = specification; bound = implementation |
| `Constraint` | exists (`constraint.py`); each must classify as **defining** (compile to logic) or **choosing** (attached to a `ChoicePoint`) |

`Sc*` stays as the lowering of activities to coroutines — pass IR, not interchange.

### P4 — RTL

| Primitive | Notes |
|---|---|
| `Pin(dir, type)` | today's `FieldInOut` |
| `Reg(domain, reset)` | today's `Field(is_reg=True)` + `reset_value` |
| `Sync(domain)`, `Comb`, `Assign` | the clocked / combinational / continuous behaviours |
| `ModuleInstance` | should reference an `Extern` or `ComponentType`, not a bare string |

### P5 — Observation and verification (cuts across all profiles)

| Primitive | Notes |
|---|---|
| `Assert`, `Assume`, `Cover` | exist (`StmtAssert`/`Assume`/`Cover`); must survive lowering into RTL |
| `TraceSite(name, fields)` | NEW: structured, named observable event. fw-hdl's `fw_dbg` site; XLS's `trace_fmt!`. Feeds derived coverage (`dynamic-coverage.md`) |
| `Rand` fields, `Randomize` | exist |
| `Covergroup` | exists (`coverage.py`) |
| `Tap(endpoint)` | NEW: passive observation of an endpoint (monitor role) |

### P6 — Host software (testbench-only)

Strings, dynamic lists/maps/sets, class handles, file I/O, `Native` blocks. This is where
Python-only expressiveness lands. It is legal in Python and SV-class back ends, illegal in
RTL, and the profile checker says so at the source line.

### Escape hatch — `Native`

An opaque block with **one implementation per target language**, attached as a
multi-view. A model using `Native` is translatable only to targets that have an
implementation; the tool lists which are missing.

---

## 4. Execution semantics (the part that makes translation trustworthy)

- **Processes interleave only at suspend points** (`Call` of a `may_suspend` op, `Wait`,
  `Event` wait, `Fork` join, `Select`).
- **Cross-component interaction is only through endpoints and claimed resources.**
  Within one time step, the order in which ready processes run is unspecified; the rules
  above make that unobservable for latency-insensitive components.
- **Determinism class** is derived, not declared: a component using only blocking
  channel ops and no `Select` is **Kahn** (output streams independent of scheduling and
  latency). `try_*`, `Select`, and `Wait` make it **latency-sensitive**. The class decides
  what a cross-representation check compares (§6).
- **Time** is cycles of a clock domain. Absolute time exists only in P6.
- **Unspecified within a step ≠ undefined.** A back end may pick any order; a
  conformance test may not depend on one.

SV's scheduler and Python's asyncio both satisfy this model; a model that relies on
either one's specific ordering is rejected by the front end (shared state across
components) rather than translated wrongly.

---

## 5. What a binding plugin provides

| Piece | fw-hdl (SV) | zuspec-dataclasses (Python) |
|---|---|---|
| Front end | `python/fw/hdl/fe` (pyslang) | `DataModelFactory` |
| Back end (same level) | **NEW**: IR → idiomatic fw-hdl classes | IR → `@zdc` classes |
| Runtime | `fw_hdl_pkg`, `fw_std_pkg`, protocol kits | `zuspec.dataclasses` runtime |
| Profiles read / written | P0–P3, P5, P6 (subset) | P0–P6 |
| Idiom hints | `fw.*` | `py.*` |

Shared, owned by zuspec: the kernel, the lowerings (`zuspec.synth`), the RTL back end
(be-sv), the C back end (be-sw), the profile checker, and the **conformance suite**.

---

## 6. Conformance

- **Semantic tests per primitive**, run on every front-end/back-end pair.
- **Round-trip:** source → IR → same-language source → IR must give identical IR (modulo
  `loc`). Python → IR → SV → IR must give identical IR (modulo `loc` and hints).
- **Differential execution:** run the Python and SV renderings of the same IR under the
  same stimulus; compare channel traces per channel, in order (Kahn components), or
  against the legal set (latency-sensitive). This generalizes `fw_view_diff`.
- **Generated IR fuzzing** within a profile, à la XLS's fuzzer.
- **Presentation-strip invariant** (§1 rule 6).

---

## 7. Example — one producer/consumer, three renderings

Kernel IR (pseudo-text):

```
interface Put<T> { op put(t: T) may_suspend }

component producer {
  /// Emits four words.
  port out: Put<Bits32>
  process run timing=explicit {
    for i in 0..4 {
      call out.put(0xdead_0000 + zext32(i))
    }
  }
}
component consumer {
  export in: Put<Bits32>   hints {fw.idiom: FW_PUT_IMP}
  field received: List<Bits32>          // P6
  impl in.put(t) { received.push(t) }
}
component pc_top {
  inst prod: producer
  inst cons: consumer
  bind prod.out -> cons.in
}
```

fw-hdl back end (matches `tests/intf_pc`):

```systemverilog
// Emits four words.
class producer extends fw_component implements fw_runnable;
    fw_port #(fw_put_if #(bit[31:0])) out;
    ...
    virtual task run();
        for (int i = 0; i < 4; i++)
            out.t.put(32'hdead_0000 + i);
    endtask
endclass
```

Python back end:

```python
@zdc.dataclass
class producer(zdc.Component):
    """Emits four words."""
    out: zdc.PutIF[zdc.u32] = zdc.port()

    @zdc.proc
    async def run(self):
        for i in range(4):
            await self.out.put(0xdead_0000 + i)
```

The `consumer.received` list is P6, so this pair cannot lower to RTL as is. The profile
checker reports it. Replace it with a `Channel` and it can.

---

## 8. Consolidation path from today's IR

| Today | Becomes |
|---|---|
| `DataTypeChannel`, `GetIF`/`PutIF`, `QueueType`, `QueueField` | `Channel[T](depth)` standard interface + `Endpoint` |
| `IfProtocolType` + `IfProtocolProperties` | user `Interface` + endpoint `Attribute`s (latency, outstanding, in-order, II) |
| `FieldKind.Port/Export/CallablePort/ProtocolPort/…` | `Endpoint(role)` + `Interface` |
| 4 process lists, `Process` | `Process` (P2) or `Sync`/`Comb`/`Assign` (P4) |
| `SpawnStmt`, `SelectStmt`, `CompletionSetStmt`, `QueuePutStmt` | `Fork`, `Select`, `Call` on standard interfaces |
| `ScCoroutine` and `Sc*` | pass IR (activity lowering), not interchange |
| `pipeline.py`, `pipeline_async.py` | `Process(timing=static)` + attributes; existing forms become scheduler pass IR |
| `Field.clock`, `metadata['clock']`, `clock_domain`, pragmas | `ClockDomain` attribute |
| `Function.comment`, `Field.pragmas` (from comments) | `Base.doc`; pragmas become `hints` or attributes |
| `ExprRefPy`, `DataTypePyObj`, `py_type`, Python lambdas | resolved by the Python front end; never in interchange IR |
| `ModuleInstance(module: str)` | reference to `Extern`/`ComponentType` |

Do it with an adapter, not a rewrite: a normalization pass maps today's IR onto the
kernel so the existing front ends and back ends keep working while the kernel settles.

---

## 9. Open questions

| # | Question |
|---|---|
| Q1 | Is the interface-method `Call` the primitive and `Channel` a standard interface (proposed), or the reverse? fw-hdl's general APIs argue for `Call` as primitive. |
| Q2 | Should `Process.timing=static` be allowed on latency-sensitive processes, or only on Kahn ones? |
| Q3 | Where does the interchange/pass boundary live physically — a separate `zuspec.ir.kernel` package, or a profile inside `zuspec-ir-core`? |
| Q4 | How much of SV class semantics (polymorphism, `virtual` methods, factories/views) belongs in P1 vs stays binding-specific? Views look like they belong in the kernel. |
| Q5 | Is `Event` needed at all once `Select` and `Channel(depth=0)` exist, or is it only the SV runtime's implementation detail? |
| Q6 | Serialization format and versioning: is the existing JSON serializer the contract, and what is the compatibility promise? |
| Q7 | What is the minimum `Policy` vocabulary for P3? |
