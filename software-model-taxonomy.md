# Taxonomy of Software Models for the Zuspec IR

*Status: proposal for review.*

**Companions:** `software-object-models.md` (per-language object-model facets — this
taxonomy's §2 summarizes it), `zuspec-semantics.md` (layers, axes, qualification),
`one-model-many-hosts.md` (hosts and translation rules),
`../fw-wb-dma/docs/wb_dma_operation_model.md` (a worked operation model).

---

## 0. How to read this

**Scope.** The IR is not meant to represent all software. It must represent the software
that **models, drives, verifies, or runs alongside hardware**: reference models, operation
models and drivers, firmware, test scenarios, testbench infrastructure, architecture
models, and datapath algorithms. General-purpose application software is out of scope
except where it appears inside those (for example, testbench file I/O).

**The taxonomy has two parts:**
- **Part A — concept models** (§1–§11): the kinds of semantics the IR must be able to
  express, grouped into families.
- **Part B — software artifacts** (§12): the kinds of software users actually write,
  mapped onto Part A. Part B is the coverage check for Part A.

**Columns used in the tables:**

| Column | Values |
|---|---|
| **IR treatment** | **Kernel** — a primitive with normative semantics · **Facet** — an optional property on a kernel construct (`software-object-models.md` §5) · **Library** — built from kernel constructs, shipped as a standard library · **FE** — resolved by the front end, never reaches the IR · **Lowered** — accepted from hosts that have it, represented by an equivalent kernel form · **Out** — outside the IR |
| **Layer** | lowest layer where it is legal: `sw` software · `el` elaborated software · `SPL` · `HLS` · `CAG` · `RTL` · `all` |
| **Pri** | **P1** needed for the operation-model beachhead · **P2** firmware and design expansion · **P3** later · **—** not planned |
| **IR today** | existing `zuspec-ir-core` classes, where they exist |

---

## Part A — Concept models

### 1. Data models

| Concept | Variants | IR treatment | Layer | Pri | IR today |
|---|---|---|---|---|---|
| 1.1 Fixed-width integers, booleans | signed/unsigned `bits[w]`, `bool` | Kernel | all | P1 | `DataTypeInt` |
| 1.2 Unbounded integers | Python `int`, bignums | Kernel | sw | P2 | — |
| 1.3 Floating point | IEEE 754 binary32/64; fixed-point | Kernel (float), Library (fixed-point) | sw → HLS | P2 | — |
| 1.4 Characters, strings | byte strings, Unicode text | Kernel | sw | P1 | `DataTypeString` |
| 1.5 Enumerations | plain enums with a base width | Kernel | all | P1 | `DataTypeEnum` |
| 1.6 Records | structs, records, dataclasses | Kernel | all | P1 | `DataTypeStruct` |
| 1.7 Packed layout | bitfields, packed structs, explicit bit layout | Kernel (facet on records) | all | P1 | partial |
| 1.8 Endianness | byte order of multi-byte fields in memory | Facet on layout | el | P1 | — |
| 1.9 Tuples | anonymous products | Kernel | all | P2 | `DataTypeTuple` |
| 1.10 Fixed arrays | `T[N]` | Kernel | all | P1 | `DataTypeArray` |
| 1.11 Tagged unions | Rust enums, sealed hierarchies, `std::variant` | Kernel (`Variant` + `Match`) | all | P2 | — |
| 1.12 Untagged unions | C unions, type punning | Out, except packed reinterpretation of bits | — | — | — |
| 1.13 Option / Result | nullable values, error-carrying values | Kernel | all | P1 | — |
| 1.14 Growable collections | list, map, set, deque, string builder | Kernel | sw | P1 | `DataTypeList/Map/Set` |
| 1.15 Bounded collections | fixed-capacity queues, ring buffers, bounded maps | Library | SPL | P1 | `QueueType` |
| 1.16 Object handles | references to class instances | Kernel | el | P1 | `DataTypeRef`, handles |
| 1.17 Target addresses | addresses in a modeled address space (MMIO, DMA buffers) | Kernel | SPL | **P1** | `DataTypeAddressSpace`, `DataTypeAddrHandle`, `DataTypeMemory` |
| 1.18 Host pointers | raw pointers, pointer arithmetic over host memory | Out (C hosts lower handles to pointers; not the reverse) | — | — | `DataTypeUptr` |
| 1.19 Function values | function references, closures, lambdas | Kernel (references); Lowered (closures → objects in SV/C) | sw | P2 | `ExprLambda` (Python-only today) |

### 2. Object models

Summarized from `software-object-models.md`; the facet tables there are the detail.

| Concept | Variants | IR treatment | Layer | Pri |
|---|---|---|---|---|
| 2.1 Value vs reference types | value structs; reference classes | Kernel | all / el | P1 |
| 2.2 Identity | identity equality on handles | Kernel | el | P1 |
| 2.3 Lifetime | garbage-collected (default), owned, scoped (RAII / `with`) | Facet | sw | P1 (GC), P2 (owned, scoped) |
| 2.4 Aliasing discipline | shared, unique, borrow | Facet | sw | P2 |
| 2.5 Mutability | mutable, `const`/`final`, immutable-by-default | Facet | all | P1 |
| 2.6 Single implementation inheritance | classes | Kernel | el | P1 |
| 2.7 Multiple implementation inheritance | C++, Python | Out of shared subset; Lowered where possible | sw | P3 |
| 2.8 Interfaces | interface classes, traits, protocols | Kernel | all | P1 |
| 2.9 External implementations | Rust `impl Trait for Type` | Kernel (`Impl`) | all | P2 |
| 2.10 Structural typing / duck typing | Python protocols, duck typing | FE (resolved to interfaces where possible); else Out | sw | P3 |
| 2.11 Dispatch | static, virtual, dynamic attribute lookup | Kernel (static, virtual); Out (dynamic lookup) | el | P1 |
| 2.12 Generics | monomorphized (elaboration), erased, bounded | Kernel (specialized at elaboration, with bounds) | all | P1 |
| 2.13 Type extension | PSS `extend`, `zdc.extend`, partial classes, monkey-patching | Kernel (declared extension, merged at elaboration); Out (monkey-patching) | el | P2 |

### 3. Control models

| Concept | Variants | IR treatment | Layer | Pri | IR today |
|---|---|---|---|---|---|
| 3.1 Structured sequential control | if, loops, match, break/continue, return | Kernel | all | P1 | `stmt.py` |
| 3.2 Bounded loops | loops with elaboration-time bounds | Kernel (qualification facet) | HLS | P1 | `StmtFor` |
| 3.3 Unstructured control | `goto`, `setjmp`/`longjmp` | FE (restructure) or Out | — | — | — |
| 3.4 Recursion | direct, mutual | Kernel | sw | P2 | — |
| 3.5 Generators / iterators | `yield`, iterator protocols | Lowered (to state objects) | sw | P3 | `StmtYield` |
| 3.6 Coroutines / tasks | `async`/`await`, SV tasks, C++20 coroutines | Kernel (processes, suspend points) | SPL | P1 | `ExprAwait`, `proc_processes` |
| 3.7 Callbacks / continuations | handler registration, completion callbacks | Lowered (to processes + events) | sw | P2 | — |
| 3.8 Explicit state machines | switch-on-state, hierarchical statecharts | Library (lowered to processes) | SPL | P3 | — |
| 3.9 Pattern matching | over variants, records, constants | Kernel | all | P2 | `StmtMatch` |

### 4. Concurrency and communication models

| Concept | Variants | IR treatment | Layer | Pri | IR today |
|---|---|---|---|---|---|
| 4.1 Cooperative processes | coroutines over an event loop / scheduler | Kernel | SPL | P1 | `proc_processes`, `ScCoroutine` |
| 4.2 Fork / join, structured concurrency | `fork…join`, task groups, nurseries | Kernel | SPL | P1 | `SpawnStmt`, `ScPar` |
| 4.3 Futures / promises / completions | `Completion[T]`, futures | Kernel | SPL | P1 | `CompletionType` |
| 4.4 Channels (CSP) | blocking/non-blocking put/get, select | Kernel | SPL | P1 | `DataTypeChannel`, `SelectStmt` |
| 4.5 Dataflow / Kahn networks | latency-insensitive process networks | Kernel (derived determinism class) | SPL / HLS | P2 | — |
| 4.6 Actors / mailboxes | Erlang/Akka actors, SV mailboxes | Library (process + input channel) | SPL | P2 | — |
| 4.7 Events and observers | notify/wait, publish/subscribe, taps | Kernel (`Event`, `Tap`) + Library (pub/sub) | SPL | P1 | `DataTypeEvent` |
| 4.8 Shared-memory threads | threads, mutexes, condition variables, atomics | Kernel | sw (`M2`) | P2 | `DataTypeLock` |
| 4.9 Resource claims | lock/share of declared resources, pools | Kernel | CAG | P1 | `ClaimMode`, `Pool` |
| 4.10 Atomic actions / transactions | Bluespec rules, PSS atomic, STM | Kernel (CAG atomic) | CAG | P2 | `ActivityAtomic` |
| 4.11 Synchronous reactive | Esterel/Lustre, clocked RTL | Kernel (RTL layer) | RTL | P2 | `sync_processes` |
| 4.12 Data parallelism | parallel-for, SIMD vectors, GPU kernels | Library over replicate/fork; P3 for a native form | HLS | P3 | `ActivityReplicate` |
| 4.13 Preemption | interrupts preempting running code, priorities | **Open** (§7.3) | SPL | P1 | — |

### 5. Memory and consistency models

| Concept | Variants | IR treatment | Layer | Pri | IR today |
|---|---|---|---|---|---|
| 5.1 Sequential consistency within a process | program order is effect order | Kernel (default) | all | P1 | — |
| 5.2 Weak memory models | C11/C++11/Java atomics, acquire/release | Kernel at `sw` (atomics with orderings); outside the shared subset below | sw | P3 | — |
| 5.3 Device memory semantics | volatile, side-effecting, non-reorderable, access-width-exact accesses | Kernel (accesses to target addresses carry these semantics) | SPL | **P1** | — |
| 5.4 Address spaces and regions | multiple address spaces, regions, attributes (cacheable, secure) | Kernel | el | P1 | `DataTypeAddressSpace` |
| 5.5 Barriers and coherence | memory barriers, cache maintenance, DMA coherence | Kernel (barrier operations as imports) | SPL | P2 | — |

### 6. Error and fault models

| Concept | Variants | IR treatment | Layer | Pri |
|---|---|---|---|---|
| 6.1 Error values | return codes, `Result`, `Option` | Kernel | all | P1 |
| 6.2 Exceptions | checked/unchecked, try/catch/finally | Lowered (to `Result` propagation) in hosts without them; native in hosts with them | sw | P2 |
| 6.3 Fatal errors | panic, abort, `$fatal` | Kernel | all | P1 |
| 6.4 Timeouts | bounded waits | Kernel (wait with bound → `Result`) | SPL | P1 |
| 6.5 Cancellation | aborting a running operation or process | Kernel (structured cancellation) | SPL | P2 |
| 6.6 Fault injection | injecting errors into another component's operations | Pattern: another component's operation model (`wb_dma_operation_model.md` §5.1) | SPL | P2 |

### 7. Hardware/software interaction models

The family that distinguishes zuspec from general-purpose IRs.

| Concept | Variants | IR treatment | Layer | Pri | IR today |
|---|---|---|---|---|---|
| 7.1 Register access | read, write, read-modify-write, field access, side effects (W1C, RO, …) | Kernel + Library (register model) | SPL | **P1** | `DataTypeRegister`, `DataTypeRegisterGroup` |
| 7.2 Memory access primitives | `read8/16/32/64`, `write…`, `read_struct`, `write_struct` | Kernel (the requirement contract an operation model imports) | SPL | **P1** | — |
| 7.3 Interrupts | ISR, deferred handler, wait-for-interrupt, masking, priorities | **Open.** Cooperative processes cannot express preemption exactly. Candidate: interrupt = event source; handler = process at a priority with declared atomicity points | SPL | **P1** | — |
| 7.4 Completion realization | polling vs interrupt-driven completion of the same operation | Kernel (one blocking operation; realization chosen per host/platform) | SPL | **P1** | — |
| 7.5 Shared buffers | buffers handed between hardware and software (descriptors, DMA) | Kernel: ownership transfer (aliasing facet `unique`, §2.4) + target addresses | SPL | P2 | — |
| 7.6 Doorbells, queues, mailboxes | the HW/SW patterns catalog | Library (`hw-sw-interaction-patterns.md`) | SPL | P2 | — |
| 7.7 OS / RTOS primitives | tasks, queues, semaphores, mutexes, timers | Library (over processes, channels, claims) | SPL | P2 | — |
| 7.8 Host I/O | files, console, sockets, environment | Kernel at `sw` only | sw | P1 (console, files) | — |
| 7.9 Foreign calls | DPI, `ctypes`, JNI, `extern "C"` | Kernel (`Extern` / `Native` with per-host implementations) | sw | P1 | `DataTypeExtern`, `Function.is_import` |

### 8. Time models

| Concept | Variants | IR treatment | Layer | Pri |
|---|---|---|---|---|
| 8.1 Untimed | order only | Kernel | all | P1 |
| 8.2 Cycles on clock domains | `Wait(n, domain)` | Kernel | SPL | P1 |
| 8.3 Simulated absolute time | `#10ns`, simulated delays | Kernel | sw | P2 |
| 8.4 Approximately timed | annotated latencies for performance models | Library (delays as attributes) | sw | P2 |
| 8.5 Wall-clock time | real time, host timers | Kernel at `sw` only; testbench use | sw | P3 |
| 8.6 Scheduler-chosen time | HLS static schedules | Kernel (selection attribute) | HLS | P2 |

### 9. Specification and verification models

| Concept | Variants | IR treatment | Layer | Pri | IR today |
|---|---|---|---|---|---|
| 9.1 Assertions | immediate assertions, assumptions | Kernel | all | P1 | `StmtAssert`, `StmtAssume` |
| 9.2 Contracts | pre/postconditions, invariants | Kernel (desugars to assertions at boundaries) | all | P2 | `Function.is_invariant` |
| 9.3 Constraints and randomization | SV `rand`, PSS constraints, Hypothesis strategies | Kernel | CAG / sw | P1 | `constraint.py`, `RandKind` |
| 9.4 Nondeterministic choice | choice points, policies | Kernel | CAG | P1 | — |
| 9.5 Coverage | covergroups, PSS coverage, derived coverage | Kernel | all | P1 | `coverage.py` |
| 9.6 Property-based tests | quickcheck, Hypothesis | Library over 9.3 + 9.1 | sw | P2 | — |
| 9.7 Temporal properties | SVA, LTL over cycles; sequences of operations | Kernel (RTL); P3 for operation-level temporal properties | RTL | P2 | — |
| 9.8 Trace / structured events | `fw_dbg` sites, `trace_fmt!` | Kernel (`TraceSite`) | all | P1 | — |
| 9.9 Scoreboards, reference comparison | in-order / out-of-order matching | Library | sw | P1 | — |

### 10. Structure and composition models

| Concept | Variants | IR treatment | Layer | Pri | IR today |
|---|---|---|---|---|---|
| 10.1 Modules, packages, visibility | namespaces, packages, public/private | Kernel | all | P1 | — |
| 10.2 Components, ports, exports | fw-hdl, zdc, SystemC, UVM | Kernel | el | P1 | `DataTypeComponent`, `Bind` |
| 10.3 Factories, views, overrides | UVM factory, fw-hdl views | Kernel (view selection at elaboration) | el | P2 | — |
| 10.4 Configuration | config databases, parameter objects, negotiated attributes | Kernel (parameters + attributes) | el | P1 | — |
| 10.5 Dependency injection | constructor injection, service lookup | FE (resolved to bindings) | el | P3 | — |
| 10.6 Separate compilation, linking, ABI | object files, shared libraries | Out (back-end concern) | — | — | — |

### 11. Staging and metaprogramming

| Concept | Variants | IR treatment | Layer | Pri |
|---|---|---|---|---|
| 11.1 Compile-time evaluation | `constexpr`, SV parameters, constant folding | Kernel (elaboration-time evaluation) | el | P1 |
| 11.2 Elaboration-time generators | build-phase code, Chisel/Python generators | Kernel (software-layer IR run by be-bc) | el | P1 |
| 11.3 Macros, templates, decorators, metaclasses | text and syntax transformation | FE (expanded before the IR) | — | P1 |
| 11.4 Elaboration-time introspection | walking the component tree, querying types | Kernel | el | P1 |
| 11.5 Run-time reflection | `getattr`, Java reflection, dynamic invocation | Out (except elaboration-time, 11.4) | — | — |

---

## Part B — Software artifacts

### 12. Artifact kinds mapped to concept models

| Artifact | What it is | Concept families used | Target layer | Pri |
|---|---|---|---|---|
| **12.1 Operation model** | the programming contract of an IP: blocking operations over registers and memory | 1 (incl. 1.17), 2, 3.6, 5.3, 6.1/6.4, **7.1–7.4**, 9.1 | SPL | **P1** |
| **12.2 Test scenario** | composed operations with constraints and coverage | 4.9, 4.10, 9.3–9.5, CAG activities | CAG | **P1** |
| **12.3 Testbench infrastructure** | monitors, scoreboards, checkers, stimulus plumbing | 2, 4.4, 4.7, 7.8, 9.8, 9.9 | sw / el | **P1** |
| **12.4 Reference model** | executable golden behaviour of a block | 1, 2, 3, 4.1–4.4 | sw → SPL | **P1** |
| 12.5 Bare-metal firmware / driver core | operations plus interrupt handling and buffer management on a real CPU | 12.1 + 7.3, 7.5, 5.5 | SPL (C host) | P2 |
| 12.6 RTOS application | tasks and queues around drivers | 7.7, 4.1, 4.6, 8.2/8.3 | SPL (C host) | P2 |
| 12.7 Architecture / performance model | approximately timed model for sizing and what-if | 4, 8.4, 1.14 | sw | P2 |
| 12.8 Datapath algorithm | pure computation destined for hardware | 1.1–1.3, 1.10, 3.1–3.2, pure functions | HLS | P2 |
| 12.9 Linux-style device driver | callbacks, locking, DMA mapping inside an OS framework | 3.7, 4.8, 5.5, 7.5 | sw | P3 (generate the core operations; the framework glue stays hand-written) |
| 12.10 Host tooling | compilers, scripts, GUIs | — | — | — (out of scope) |

### 13. Coverage check

Every P1 artifact in §12 is expressible with P1 concepts in Part A, with **two
exceptions that block the beachhead** and need design work first:

1. **Interrupts (7.3, 4.13).** Operation models already treat them as unresolved
   (`wb_dma_operation_model.md` §3.1). The blocking-operation style hides them inside
   operations, which is enough for the operation model itself — but firmware (12.5) needs
   an explicit preemption model.
2. **Device memory semantics (5.3).** Accesses to target addresses must be side-effecting,
   width-exact and non-reorderable in every host. This is a short normative section, but
   it must exist before generating C or SV that talks to registers.

---

## 14. Explicitly out of scope

| Concept | Why |
|---|---|
| Raw host pointers and pointer arithmetic (1.18) | not portable across hosts; target addresses (1.17) cover the hardware need |
| Untagged unions / type punning (1.12) | undefined or host-specific behaviour; packed bit reinterpretation covers the hardware need |
| Unstructured control (3.3) | front ends restructure or reject |
| Run-time reflection (11.5) | not representable in SV or C; elaboration-time introspection covers the modeling need |
| Separate compilation and ABI (10.6) | a back-end concern |
| Monkey-patching, dynamic attribute lookup (2.13, 2.11) | breaks static structure; declared extension covers the need |
| General-purpose application software (12.10) | not the product |

---

## 15. Open questions for review

| # | Question |
|---|---|
| T1 | Is the scope statement in §0 right — software that models, drives, verifies or runs alongside hardware? |
| T2 | Interrupt and preemption model (7.3, 4.13): event + prioritized handler process with atomicity points, or something else? |
| T3 | Floating point (1.3): P2 is driven by datapath algorithms and performance models. Is it needed earlier for reference models? |
| T4 | Should explicit hierarchical state machines (3.8) be a library or a kernel construct, given how common they are in firmware? |
| T5 | Shared-memory threads (4.8) and weak memory models (5.2): are multi-core firmware models in scope for P2, or later? |
| T6 | Exceptions (6.2): lowered to `Result` in SV/C/Rust hosts, as proposed — acceptable idiom for DV teams? |
| T7 | Is the P1 set (operation model, scenario, testbench infrastructure, reference model) the right beachhead? |
