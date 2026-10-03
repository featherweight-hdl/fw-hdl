# Software Object Models — Concept Survey for the Zuspec Kernel

*Status: research survey and proposal, for review. Feeds `zuspec-semantics.md` §4.2.*

**Question:** zuspec wants to map a host language's syntax onto a concept model in the IR.
For "real" software hosts — C, C++, Rust, Python, Java, plus SystemVerilog — what are the
core concept models, how do they differ, and how should the IR represent them so that each
host's concepts have a home?

---

## 0. Summary

1. **Don't adopt one object model. Decompose them.** Every language's object model is a
   choice along a dozen independent **facets**: value vs reference, identity and aliasing,
   lifetime, mutability, polymorphism, dispatch, generics, errors, concurrency, layout,
   modules, metaprogramming. A language is a *point* in facet space, exactly as a hardware
   layer is a point on the restriction axes (`zuspec-semantics.md` §2).
2. **The IR represents facets; front ends map syntax onto them; hosts declare which facet
   values they carry natively.** Qualification, the capability matrix, and the three
   translation rules (`one-model-many-hosts.md` §4) then apply unchanged.
3. **There is strong precedent.** .NET's Common Type System with its **Common Language
   Specification** (an explicit shared subset, marked `CLSCompliant`) is the closest prior
   art to "shared-subset semantics flow everywhere". The JVM shows richer languages
   (Scala, Kotlin) lowering onto a smaller object model. The WebAssembly Component Model
   (WIT) and COM show that *boundaries* between languages work best when thin: values,
   interfaces, and opaque handles.
4. **The kernel draft needs four changes** (§6): add **sum types** (tagged unions), add
   **external implementations** (Rust traits / impl blocks) alongside class inheritance,
   make **aliasing discipline** an optional facet, and represent errors as **`Result`
   values** with exceptions as a lowered facet.
5. **A notable alignment:** the facets that make software hard to translate — shared
   mutable aliasing, unbounded allocation, dynamic creation — are the same ones the
   hardware axes restrict (`M`, `D`, `C`). Rust's ownership discipline sits close to the
   `M1` communication rule. The more restrictive the layer, the more languages represent
   it natively — Rust included.

---

## 1. Why decompose

A single "zuspec object model" would be one more language's choices, and every host would
translate into it lossily. Decomposition instead lets the IR say *exactly* which concept a
construct uses — "a reference type with single inheritance, garbage-collected, virtual
dispatch" versus "a value type with an external trait implementation, statically
dispatched, owned" — so that:

- a front end records what the source *meant*, not an approximation;
- a back end knows precisely what it must represent natively or lower;
- qualification can say "this Python class uses multiple implementation inheritance (facet
  P-MI), which SV cannot represent".

---

## 2. The languages

### 2.1 C
- **Values & layout:** scalars, structs, unions, arrays; layout fixed by the platform ABI.
  Everything is a value; aggregates copy.
- **Identity:** pointers to any storage, including the stack; pointer arithmetic.
- **Lifetime:** manual (`malloc`/`free`), automatic (stack), static.
- **Polymorphism & dispatch:** none built in; hand-built via function pointers and struct
  embedding (the "vtable by hand" pattern).
- **Generics:** none (macros, `void *`, `_Generic` for overload-like selection).
- **Errors:** return codes, `errno`; `setjmp`/`longjmp`.
- **Concurrency:** threads with a defined memory model (C11).
- **Note:** C is the lowering target of last resort — any facet can be lowered to it, at
  the cost of idiom.

### 2.2 C++
- **Values & layout:** classes are value types by default; objects live on the stack, in
  other objects, or on the heap. C-compatible layout for standard-layout types.
- **Identity:** pointers and references; move semantics.
- **Lifetime:** deterministic — constructors and **destructors** (RAII); smart pointers
  (`unique_ptr`, `shared_ptr`, `weak_ptr`) encode ownership in types.
- **Polymorphism:** multiple implementation inheritance, including virtual inheritance;
  abstract classes as interfaces.
- **Dispatch:** static by default; `virtual` through vtables.
- **Generics:** templates — compile-time instantiation (monomorphization), constrained by
  concepts (C++20).
- **Errors:** exceptions; `std::optional`, `std::variant`, `std::expected` (C++23) as values.
- **Concurrency:** threads, atomics, memory model (C++11); coroutines (C++20).
- **Metaprogramming:** templates, `constexpr`, macros.

### 2.3 Rust
- **Values & layout:** structs and **enums with payloads** (algebraic data types); values
  move by default; layout unspecified unless `#[repr(C)]`.
- **Identity & aliasing:** **ownership and borrowing** — at any time, either one mutable
  reference or any number of shared references. Lifetimes are part of types.
- **Lifetime:** deterministic (`Drop`); `Box`, `Rc`, `Arc`; interior mutability via
  `Cell`/`RefCell`/`Mutex`.
- **Polymorphism:** **no implementation inheritance.** Traits implemented *outside* the type
  (`impl Trait for Type`), subject to coherence (the orphan rule); supertraits.
- **Dispatch:** static (generics, monomorphized) or dynamic (`dyn Trait`, vtable in a fat
  pointer).
- **Generics:** monomorphized, bounded by traits.
- **Errors:** `Result`/`Option` as values; `panic` for unrecoverable errors.
- **Concurrency:** threads with `Send`/`Sync` marker traits; `async`/`await` over poll-based
  futures, runtime supplied by a library.
- **Metaprogramming:** declarative and procedural macros.

### 2.4 Python
- **Values & layout:** everything is an object; reference semantics throughout; no layout.
- **Identity:** every name is a reference; identity via `is`.
- **Lifetime:** garbage-collected (CPython: reference counting plus a cycle collector).
- **Polymorphism:** classes with **multiple inheritance** (C3 method-resolution order);
  **duck typing**; `typing.Protocol` for structural typing (checked by tools, not the
  runtime); ABCs.
- **Dispatch:** dynamic attribute lookup; descriptors; `__getattr__`.
- **Generics:** type hints only; erased at run time.
- **Errors:** exceptions.
- **Concurrency:** threads (historically under the GIL; a free-threaded build is optional
  since 3.13), `asyncio` coroutines, generators.
- **Metaprogramming:** decorators, metaclasses, `dataclasses`, runtime reflection,
  `exec`.

### 2.5 Java
- **Values & layout:** primitives are values; everything else is a heap object reached by
  reference. (Value classes are in progress under Project Valhalla.)
- **Identity:** references; `==` is identity.
- **Lifetime:** garbage-collected; no destructors (try-with-resources for scoped release).
- **Polymorphism:** single class inheritance; multiple interfaces with default methods;
  **records**; **sealed** hierarchies (closed sum types).
- **Dispatch:** virtual by default.
- **Generics:** **erasure** — one runtime implementation, bounded type parameters.
- **Errors:** checked and unchecked exceptions.
- **Concurrency:** threads with the Java Memory Model; virtual threads (Java 21).
- **Metaprogramming:** annotations, reflection, annotation processors.
- **Pattern matching:** `switch` over sealed types and records.

### 2.6 SystemVerilog (classes)
- **Values & layout:** packed and unpacked structs and unions are value types with defined
  bit layout (packed); classes are reference types.
- **Identity:** class handles; no pointers to non-class storage (`ref` arguments only).
- **Lifetime:** automatic memory management (garbage-collected).
- **Polymorphism:** single inheritance; **interface classes** (multiple `implements`).
- **Dispatch:** `virtual` methods.
- **Generics:** parameterized classes, specialized at elaboration (monomorphized).
- **Errors:** no exceptions; `$error`/`$fatal`.
- **Concurrency:** processes (`fork`/`join`), events, mailboxes, semaphores; a
  time-and-event scheduler.
- **Unique:** constraint randomization and covergroups are *class features*.

---

## 3. The facet matrix

| Facet | C | C++ | Rust | Python | Java | SV |
|---|---|---|---|---|---|---|
| **F1 value vs reference** | values | both (value default) | values (move) | references | primitives / refs | structs values, classes refs |
| **F2 aliasing** | unrestricted | unrestricted | **XOR mut/shared** | unrestricted | unrestricted | unrestricted |
| **F3 lifetime** | manual | RAII + smart ptrs | owned + `Drop` | GC | GC | GC |
| **F4 mutability default** | mutable (`const`) | mutable (`const`) | **immutable** (`mut`) | mutable | mutable (`final`) | mutable (`const`) |
| **F5a implementation inheritance** | — | multiple | — | multiple | single | single |
| **F5b interfaces** | — | abstract classes | traits | Protocol / ABC | interfaces | interface classes |
| **F5c external impl** | — | — | **trait impls** | monkey-patching | — | — |
| **F5d sum types** | tagged unions by hand | `variant` | **enums** | `match` over classes | sealed + records | tagged unions (limited) |
| **F6 dispatch** | fn pointers | static / vtable | static / `dyn` | dynamic lookup | virtual | virtual / static |
| **F7 generics** | — | templates (mono) | mono, trait-bounded | hints only | erasure | params (mono, elaboration) |
| **F8 errors** | codes | exceptions / `expected` | `Result` / panic | exceptions | checked/unchecked exc. | `$fatal` |
| **F9 concurrency** | threads | threads, coroutines | threads, async | threads, asyncio | threads, virtual threads | processes, events |
| **F10 layout control** | ABI | ABI | `repr(C)` | — | — | packed bits |
| **F11 modules** | files/headers | namespaces/modules | crates/modules | modules | packages/modules | packages |
| **F12 metaprogramming** | macros | templates, constexpr | macros | decorators, metaclasses | annotations | macros, params |

---

## 4. Prior art: multi-language object models

| System | Approach | Lesson for zuspec |
|---|---|---|
| **.NET CTS / CLS** (ECMA-335) | One rich type system (CTS); an explicit **shared subset** (CLS) that every language must support for interop, marked by `CLSCompliant` | The direct precedent for "shared-subset semantics flow everywhere". Make the subset explicit and checkable. |
| **JVM** (Kotlin, Scala, Clojure) | Languages with richer models (Scala traits with state, Kotlin coroutines, extension functions) **lower** onto Java's object model | "The greater-capability side lowers to the lesser" works if the target has a few general primitives (classes, interfaces, closures). |
| **GraalVM Truffle interop** | A dynamic, message-based protocol (read member, invoke, array element, is executable…) between language runtimes | Runtime interop between arbitrary object models is possible, but loose: precision and performance cost. We translate source, so we can be stricter. |
| **WebAssembly Component Model** (WIT) | Boundaries carry **values** (records, variants, enums, flags, lists, options, results) and **resources** behind `own` / `borrow` handles; no shared object graph | Thin boundaries are robust. WIT's value vocabulary is a good model for the cross-host shared subset — and for hardware. |
| **COM / IDL** | Interfaces only, `QueryInterface`, reference counting; no implementation inheritance across the boundary | Interface-only boundaries survive decades; implementation inheritance does not cross languages well. |
| **pybind11, UniFFI, SWIG** | Generated bindings over one language's object model | Bindings are a back end's job; the concept model must exist first. |

The pattern across all of them: **values, interfaces, and opaque handles cross well;
shared mutable object graphs, implementation inheritance, and deterministic destruction
cross badly.**

---

## 5. Proposed IR representation, by facet

| Facet | IR concept | Native in | Lowered in |
|---|---|---|---|
| **F1** | `ValueType` (struct, union, tuple, packed) and `ClassType` (reference) | all have both, except Python (refs only: values via immutable dataclasses) and Java (until value classes) | Python/Java: value types as immutable objects with copy-on-assign |
| **F2** | optional **aliasing annotation** on handles and parameters: `shared` (default), `unique`, `borrow`, `borrow_mut` | Rust (enforced), C++ (`unique_ptr`, by convention) | others: annotation kept as a hint and checked by the validator, not by the host |
| **F3** | **lifetime class** per type: `gc` (default), `owned`, `scoped` (deterministic release) | GC: Python, Java, SV; owned: Rust, C++; scoped: C++, Rust | GC in C/Rust via runtime (be-sw's GC seam; `Rc`/`Arc`); scoped in GC hosts via explicit `close`/`with` — **deterministic destruction is outside the shared subset** |
| **F4** | `mut` / `const` on fields, locals, parameters; default **[TBD]** | all, with different defaults | defaults made explicit by front ends |
| **F5a** | single implementation inheritance | C++, Python, Java, SV | Rust: composition + trait delegation (unidiomatic) |
| | multiple implementation inheritance | C++, Python | **outside the shared subset** |
| **F5b** | `Interface` (pure operations) | all except C | C: struct of function pointers |
| **F5c** | `Impl(Interface, Type)` declared separately from the type | Rust | others: merged into the class at generation (requires the type to be in the same model) |
| **F5d** | `Variant` (tagged union with payloads) + `Match` | Rust, Java (sealed+records), C++ (`variant`) | C/SV: tag + union; Python: class per case + `match` |
| **F6** | `static` / `virtual` per method; dynamic lookup only at the software layer (`D2`) | per host | dynamic lookup outside the shared subset |
| **F7** | parameterized types **specialized at elaboration** (monomorphized), with interface bounds | C++, Rust, SV | Java/Python: erased form + checked bounds |
| **F8** | `Result[T, E]` and `Option[T]` as values; `fatal` for unrecoverable errors; **exceptions** as a facet | Result: Rust, C++23, any host as a library; exceptions: C++, Python, Java | exceptions → `Result` propagation in C, Rust, SV |
| **F9** | processes / coroutines, channels, the SPL rules (`zuspec-semantics.md` §6); shared-memory threads at the software layer only | per host | async in C via the be-sw runtime |
| **F10** | layout only on packed value types (bit-exact) and on `repr(C)`-style ABI types | C, C++, Rust, SV | others: layout is not observable |
| **F11** | packages and visibility (`public`, `package`, `private`) | all | mapped per host |
| **F12** | metaprogramming is **expanded by front ends**; generators that run at elaboration are stored as software-layer IR (`zuspec-semantics.md` §3) | — | — |

---

## 6. Changes to the kernel draft (`zuspec-semantics.md` §4.2)

1. **Add sum types** (`Variant` + `Match`). Rust, Java, C++ and Python all have them in some
   form; they are central to modelling transactions and opcodes; and a tagged union is a
   packed, hardware-friendly type.
2. **Add external implementations** (`Impl(Interface, Type)`) as a kernel concept, alongside
   single implementation inheritance. This gives Rust a native mapping and lets interfaces
   be satisfied without class hierarchies.
3. **Make aliasing an optional facet.** Default `shared` keeps GC hosts simple; `unique` and
   `borrow` let Rust and C++ be generated idiomatically, and let the validator check the
   `M1` rule in software terms.
4. **Errors as values first.** `Result`/`Option` are kernel types; exceptions are a facet
   lowered to `Result` propagation for C, Rust and SV. Keep `fatal` for unrecoverable
   errors.
5. **Lifetime class per type,** with GC as the default and deterministic destruction
   explicitly outside the shared subset.

Unchanged: single implementation inheritance plus multiple interfaces as the shared
subset for class hierarchies; multiple implementation inheritance outside it.

---

## 7. The shared subset (zuspec's "CLS")

Across SV, Python, C, C++, Rust and Java, the subset every host represents natively or
through a cheap, idiomatic runtime:

- value types: fixed-width integers, booleans, enums, structs, tuples, fixed arrays,
  **variants**;
- `Option`, `Result`;
- interfaces with operations;
- single implementation inheritance (Rust excepted — see below);
- parameterized types specialized at elaboration;
- handles to objects with GC lifetime (a runtime in C and Rust);
- processes, channels, the SPL concurrency rules.

**Rust is the interesting outlier.** Generating idiomatic Rust from a GC, shared-aliasing
model means `Rc<RefCell<…>>` everywhere — correct but ugly. Generating it from SPL-level
models (`M1`: endpoints only, no shared mutable state) is natural. Rust is a good host
**for the restricted layers** and a poor host for the software layer.

---

## 8. Alignment with the hardware axes

| Software facet | Hardware axis | Correspondence |
|---|---|---|
| F2 aliasing (`shared` → `unique`/`borrow`) | **M** communication (`M2` → `M1`) | no shared mutable state across components |
| F3 lifetime + F1 values | **D** data bounds, **C** creation | static allocation, value semantics |
| F7 monomorphized generics | elaboration | parameters fixed before time zero |
| F5d variants | packed types | tagged unions are bit-exact |
| F8 `Result` values | **N** determinism, observation | errors as data, not control transfer |

One lattice, two vocabularies: restricting a software model toward hardware *is* moving it
along these facets. Qualification (`zuspec-semantics.md` §8) can report software facets
and hardware axes in the same diagnostic.

---

## 9. Front-end mapping

- Each front end maps syntax to facets and **records the facets a scope uses** (for example,
  `{F5a: multiple, F3: gc, F8: exceptions}` for a Python class).
- Qualification compares used facets against each target host's native set, as well as
  against the target layer. Example:
  ```
  class Scoreboard (python) → host SV:
    F5a multiple inheritance (bases A, B) — not representable in SV
    F8  exceptions (raise at line 31) — lowered to Result propagation
  ```
- Metaprogramming (decorators, macros, templates, metaclasses) is expanded by the front end
  before the IR. Generators that must survive as generators run at elaboration and are
  stored as software-layer IR.

---

## 10. Open questions

| # | Question |
|---|---|
| O1 | Default mutability in the IR: mutable (most hosts) or immutable (Rust, and easier analysis)? |
| O2 | Should aliasing annotations ever be *enforced* by the validator outside Rust, or only checked and reported? |
| O3 | Is Java a target host, or a source of lessons only? (Same question for C++ as a source host: its full template language is very hard to lift.) |
| O4 | How far should `Variant` go — full Rust-style enums, or Java-style sealed hierarchies of records? (They are interconvertible; the question is which is canonical.) |
| O5 | Do `with`/try-with-resources and RAII map to one IR "scoped resource" construct? |
| O6 | Is `Impl(Interface, Type)` allowed for types defined in another model (Rust's orphan rule), or only within one model? |

---

## 11. Sources

- ISO/IEC 9899 (C17; C23), ISO/IEC 14882 (C++20; C++23).
- The Rust Reference; *The Rust Programming Language* (ownership, traits, error handling).
- Python Language Reference, "Data model"; PEP 544 (Protocols); PEP 557 (dataclasses);
  PEP 703 (free-threaded CPython).
- The Java Language Specification (records, sealed classes, pattern matching); JEP 444
  (virtual threads); Project Valhalla.
- IEEE 1800-2023 (SystemVerilog), clauses on classes, interface classes, processes,
  randomization.
- ECMA-335, Common Language Infrastructure: Common Type System and Common Language
  Specification.
- WebAssembly Component Model and WIT documentation (component-model.bytecodealliance.org).
- GraalVM Truffle polyglot interoperability (`InteropLibrary`) documentation.
- Microsoft COM specification (IUnknown, IDL).
