# Project architecture: repositories and responsibilities

Status: proposal, 2026-11-14. Builds on [architecture.md](architecture.md).

## 1. The problem

`architecture.md` says fw-hdl is a *specification* with many
interpretations: a stock-simulator SV runtime, sv-weave generated
per-component implementations, vendor-native simulator implementations,
synthesis to RTL, formal, and a fast C model. Today the repo holds all of
these at once, and the code does not keep them apart:

- **No spec/impl boundary in SV.** `src/fw_hdl_pkg.sv` `include`s
  everything (kernel, settle scheduler, debug recorder, registers, sync
  nets) into one package. User base classes name implementation classes
  directly. For example, `fw_component` names `fw_sync_bridge`,
  `fw_dbg_domain` and `fw_view_ctx`. `fw_component_root` constructs
  `fw_sync_kernel`, `fw_dbg_console` and `fw_crossing_check`.
  `fw_rv_sp_in`/`out` construct `fw_rv_sig`, and `fw_sync_port` constructs
  `fw_sync_net`. The debug macros call `fw_dbg_track` directly.
- **The factory can only build components.** Ports, holders, nets, the
  kernel and debug domains are built with `new()`, so an implementation
  cannot substitute them. That is exactly the injection point the spec
  needs.
- **The Python package mixes four roles.** It contains a front end
  (SV→Zuspec IR), IR transformations that belong in Zuspec, engine-specific
  back-end code (`lib/xls_ir.py`, `xls_flow`, `spl_flow`, `stage_tlm`,
  `ppa`, `latency`, `formal/smt`, `cosynth/rewrite`, `emit/regblock`), and
  sv-weave plugins for the SV runtime.
- **Libraries sit in the kernel.** `std/`, the rv protocol kit, registers
  and the RTL helpers (`src/rtl`) live beside the kernel, and the rv kit is
  duplicated in `skills/fw-proto-kit/references/example`.

The verification package will have the same shape: a spec, several
implementations, and libraries. So the repo split should be a **pattern**
that each package family follows, not a one-off.

## 2. Organizing principles

1. **Spec, implementation and library are different kinds of repo.**
   - A *spec* repo defines a **language**: its core constructs, its
     standard library, and the normative semantics of both. Here the
     "language" is an SV class library, not new syntax. As with C++,
     Java or SystemC (IEEE 1666), the standard library is part of the
     language definition.
   - An *implementation* repo makes the spec executable or analyzable in
     one way.
   - A *library* repo holds user-level code written against the spec,
     outside the standard: protocol kits and domain libraries. It is
     portable across implementations by construction. These play the role
     of PyPI packages or crates.
2. **Dependencies flow one way:**

   ```
   library  ──►  spec  ◄──  implementation
   ```

   - Nothing depends on an implementation except a distribution, a test
     harness, or the user's own top-level build.
   - Neither the standard library nor any other library names an
     implementation class or depends on an implementation's extension
     points.
   - An implementation may provide native versions of standard-library
     classes, since their semantics are normative (principle 5). It may
     know about a non-standard library only through a separate
     realization package.
3. **Every implementation is a peer.** The SV runtime is the *reference*
   implementation, the one the conformance suite is validated against
   first. It is not privileged in the API. The same holds one level down:
   XLS is one Zuspec engine among several.
4. **Static tools are implementations too.** The Python front end
   elaborates user `build()` code. When it does, it implements the spec's
   runtime interfaces (factory, ports, connect) in Python. It is therefore
   an implementation of the spec, and it must depend only on the spec repo.
   It must not depend on the SV runtime.
5. **Native realizations live with the implementation, not the library.**
   - A library's portable SV is its normative definition. It must
     simulate correctly on any implementation and lower through the static
     front end without help.
   - An implementation may ship an optimized realization of a library
     class: an IR model, a weave hint, or a vendor's native class. Such a
     realization is optional. It must be equivalent to the portable SV,
     checked against the class's contract, and dropping it may only cost
     performance or QoR, never correctness.
   - The realization belongs to the implementation. That is the same
     position as libstdc++ vs. libc++, or a SystemC vendor with a native
     `sc_fifo`. For standard-library classes it lives in the
     implementation repo. For non-standard libraries it lives in the
     implementation repo or in a bridge package `<impl>-<lib>`. The
     library never knows about it.
   - If a class *cannot* be implemented well without implementation
     knowledge, it is not a library class. It is a spec primitive, and it
     belongs in the api (§3.1, "Primitives vs. standard library").
6. **Conformance is part of the spec.**
   - The spec repo ships a conformance suite. These are fw-hdl designs whose
     expected behavior is stated as *minimum-bar* semantics. For example,
     "comb runs at least once after each input change". No test may assert
     an exact evaluation count.
   - Each implementation supplies a runner that executes the suite.
   - An implementation "supports API x.y" when it passes conformance x.y.
7. **fw-hdl is a front end; Zuspec does the work** (AGENTS.md).
   - The fw-hdl family owns *recognizing* fw-hdl semantics and producing
     Zuspec IR.
   - Lowering, scheduling, back ends and engines belong in the Zuspec org.
   - Engine-specific code in this repo is debt to move out, never a pattern
     to copy.

## 3. The repositories

### 3.1 HDL family

```
                         ┌──────────────────────┐
                         │ fw-hdl  (distribution│
                         │ docs, examples,      │
                         │ skills, integration) │
                         └──────────┬───────────┘
                       ┌────────────┼─────────────┬─────────────────┐
                       ▼            ▼             ▼                 ▼
                 ┌────────────┐ ┌─────────────┐ ┌──────────────┐ ┌───────────┐
                 │fw-proto-axi│ │ fw-hdl-rt-sv│ │ fw-hdl-fe-sv │ │ vendor    │
                 │fw-proto-...│ │ (reference  │ │ (static impl │ │ native    │
                 │ (libraries)│ │  SV runtime)│ │  → Zuspec IR)│ │ impls     │
                 └─────┬──────┘ └──────┬──────┘ └──────┬───────┘ └─────┬─────┘
                       │               │               │ │             │
                       └───────┬───────┴───────────────┘ │             │
                               ▼                          │             │
                        ┌────────────────┐                 ▼             │
                        │  fw-hdl-spec   │◄─────────┐  zuspec-ir-core,   │
                        │  (language:    │          │  zuspec-fe-sv,     │
                        │  core + std +  │◄─────────┼──zuspec-synth,     │
                        │  conformance)  │          │  be-sv/xls/sw/...  │
                        └────────────────┘          │                    │
                                ▲                   │  (Zuspec org)      │
                                └───────────────────┴────────────────────┘
```

#### `fw-hdl-spec`: the language (spec)
`fw-hdl-spec` defines a language: the core constructs, the primitives, and
the standard library, together with their normative semantics. The
semantics are language-neutral, and each surface language is a
*binding* (decision D1). The repo layout:

```
fw-hdl-spec/
  semantics/       normative docs, std contracts (*.yaml),
                   conformance scenarios and expected behavior
  bindings/sv/     SV packages: core, primitives, std; SV conformance tests
  bindings/py/     later: Python package fw.hdl.api (§3.4); Python conformance tests
```

Each binding ships separately: the SV binding as a dfm/FuseSoC fileset,
the Python binding as the PyPI distribution `fw-hdl-spec`.

Every binding has three layers. Each layer may depend only on the layers
before it. In SV each layer is a separate package:

| Layer | Package(s) | Holds | Implementations must |
|---|---|---|---|
| Core | `fw_hdl_pkg`, `fw_hdl_reg_pkg`, `fw_hdl_dbg_pkg` | Interface classes, base classes, macros, standard port APIs, the injection mechanism | implement it |
| Primitives | in `fw_hdl_pkg` | Channel kinds and memories: structures every implementation must *understand* | realize them |
| Standard library | `fw_std_pkg` | Portable components built from core and primitives | run the portable SV, or substitute a native version that meets the class contract |

Contents:
- **SV packages (core).**
  - Interface classes, such as the elaboratable, runnable, combinational,
    domain, register, debug-listener and awaitable interfaces.
  - The *minimal* user base classes: `fw_component`, `fw_component_root`,
    ports, exports, sockets, sync ports/signals, `fw_reg_base`.
  - The register shape (decision D3): the register interfaces and base
    classes that the front end recognizes, like a RAL. The concrete types
    are in the standard library.
  - Ready/valid as a built-in protocol (decision D4): the `fw_rv_sp_*`
    signal ports and the rv initiator/target/monitor role interfaces.
  - Macros, and the standard transaction-level interface types: put, get,
    get_nb, reqrsp, mem, level and valid_put. These are the types that let
    libraries interoperate.
  - **Structural primitives** whose meaning every implementation must
    understand: channel kinds and memories. See "Primitives vs. standard
    library" below and decision D6.
  - It is split into small packages (`fw_hdl_api_pkg`, `fw_hdl_reg_pkg`,
    `fw_hdl_dbg_pkg`) so users import only what they use.
- **The injection mechanism.** This is the one piece of concrete code in
  the spec:
  - `fw_factory`, `fw_view_ctx` and a services interface, `fw_rt_if`.
  - `fw_rt_if` creates port/holder/net implementations, the kernel, debug
    domains and the crossing checker.
  - Base classes reach their implementation *only* through
    `fw_rt::get()` or the view context. The view context keeps per-instance
    and per-subtree overrides.
  - An implementation package registers itself at time 0. If no
    implementation is registered, elaboration fails with a fatal error that
    names the problem.
- **The `fw_root` module contract.** This is the port shape and pin
  bridging semantics, as a spec document plus a conformance test. Each
  implementation supplies the module body.
- **Normative semantics docs.** These grow out of today's `docs/reference`
  pages: settle, rv, clocking, contracts, facts, registers.
- **Conformance suite.** It includes a dfm package that takes the
  implementation as a parameter: the runner task and the implementation's
  filesets.

Deliberately excluded: kernels, schedulers, recorders, sinks, register
state-machine *runtimes*, transactors other than the standard rv ones, and
any implementation Python. (A Python language binding is a separate
question; see D1.)

#### `fw-hdl-rt-sv`: reference SystemVerilog runtime (implementation)
This is the "Plain SV" tool: fw-hdl on any stock SV simulator.
Contents:
- The `fw_rt_if` implementation: the sync kernel, settle scheduler, nets,
  holders, `fw_sp_comb`, domains, quantum keeper, crossing check, the debug
  recorder/track/console/sinks, and the register state machine.
- The `fw_root.sv` module, clock/reset xtors and pin modules
  (`fw_rv_pin_in`/`out`).
- The sv-weave plugins (today's `python/fw/hdl/weave`). These generate
  per-component SV realizations that bypass the generic kernel paths.
- A dfm package for building simulations, plus the conformance runner.

#### `fw-hdl-fe-sv`: static front end to Zuspec (implementation)
Static interpretation is shared by synthesis, formal and the C model. All
of them consume Zuspec IR, so this one repo is the entry point to all of
them.
Contents:
- Only the fw-hdl-specific front-end layers. The generic SV-subset→IR
  layer comes from `zuspec-fe-sv` (decision D2): pyslang parsing and the
  type, expression, statement and function mappers.
- The elaborator (`fe/elab`), which supplies a Python implementation of
  the spec's runtime interfaces while it runs `build()`/`connect()`.
- Binding (`fe/bind`), register and MMIO recognition, and the extern/wrap
  readers.
- Recognition of spec-level semantics: sync classes, settle and contracts.
- Output is **Zuspec IR only**.
- Thin dfm flow packages compose the front end with Zuspec engines:
  `fw.hdl.synth` (with optional formal-property emission), `fw.hdl.formal`
  and `fw.hdl.swmodel`. Each engine is an optional dep-set, so a user who
  wants only synthesis does not pull in the C toolchain.
- Conformance runners for each static path. For example: synthesize, then
  run under Verilator; or build the C model, then run it.

`fw-hdl-fe-sv` keeps the elaborator, binding, the recognition of fw-hdl
classes and primitives, and the flows. Generic SV mapping goes into
`zuspec-fe-sv`, which other SV-input Zuspec users then share
(decision D2).

#### The standard library (inside `fw-hdl-spec`)
- **Contents.**
  - The portable components: `fw_fifo`, `fw_resource`, credit, arb, table,
    pool, dep, match, order, and reset combiners.
  - The concrete register types (`fw_reg`, `fw_reg_set`, `fw_reg_block`).
    Their shape is declared in core (decision D3).
  - **Ready/valid** (decision D4). The rv components (`fw_rv_slice`,
    `fw_rv_pass`, `fw_put_to_rv_bridge`, `fw_get_from_rv_bridge`, the
    role bridges) and the signal-level rv transactor modules
    (`fw_rv_*_xtor`, with synthesizable `*_xtor_core.sv`). The rv role
    interfaces are in core.
- **Written only against core and primitives.** It contains no Python, no
  implementation entry points, and no generated or engine-specific
  artifacts.
- **Each class's contract is normative.** The contract is the existing
  `*.yaml` file (`fw_channel.yaml`, `fw_credit_tx.yaml`,
  `fw_arbiter.yaml`). It is implementation-neutral: ordering,
  conservation, and the observation points.
  - The portable SV is the reference implementation of that contract.
  - An implementation may substitute a native version, but only if the
    native version meets the contract.
  - Conformance covers the standard library through the contracts. An
    implementation that runs the portable SV conforms automatically.
- **Inclusion criteria.** A class must be general-purpose and stable, and
  it must be useful across domains. Protocol- and domain-specific code
  goes in external libraries (`fw-proto-*`). This keeps the language
  version from being driven by library churn, the "batteries go stale"
  problem Python's stdlib has. Additions are minor-version bumps of
  `fw-hdl-spec`.

**Precedent.** Most language standards include the standard library's
interface and semantics:
- ISO C (clause 7), ISO C++ and the JLS/Java SE all do. Implementations
  are provided per vendor: glibc/musl, libstdc++/libc++/MSVC STL.
- IEEE 1666 (SystemC) defines primitive channels (`sc_signal`, `sc_fifo`,
  `sc_mutex`) and TLM-2.0 in the core standard.
- SystemVerilog defines `mailbox`, `semaphore` and `process` in IEEE 1800.
  UVM is a separate standard (1800.2), which is the analogue of our
  protocol kits and `fw-dv`.
- VHDL started with `std_logic_1164`/`numeric_std` as separate standards
  and folded them into 1076-2008.

Splitting the standard library into its own repo would buy an independent
release cadence. That isn't worth an extra repo and a second version
axis, as long as the inclusion criteria keep the standard library small.

**Primitives vs. standard library.** Can the standard library be pure
portable SV? Yes. Today's `lib/registry.py` shows why. It recognizes
three groups:

| Group | Classes today | What the tools need | Where it goes |
|---|---|---|---|
| Cycle-step components | `fw_credit_tx`, `fw_arbiter`, slices, pool, dep, match | Nothing. They already lower from their body ("has no entry: its step() is mapped like any other component's"). `lib/xls_ir.py` is a leftover that the library no longer uses. | Standard library as is. Delete `xls_ir.py`. |
| Primitives the tools must understand | channels (`ChannelKind`), port APIs (`PortApi`), `fw_sp_mem` (`MemoryKind`), the storage bindings that tables allow | Their *meaning*: buffering and timing freedom, memory ports and read latency, legal storage. Tools pick a structure from that meaning (flops, RAM macro, XLS channel). This is not an optimization, so it is not a realization. | Promote them to **spec primitives** in `fw-hdl-spec`, with normative semantics and conformance. Each implementation realizes them. Recognition code moves to `fw-hdl-fe-sv`, keyed by api class. |
| Register block | `fw_reg_component` → `fw.hdl.native` regblock | Register semantics | Spec sub-API (D3). Recognition lives in `fw-hdl-fe-sv`. |

The test for promotion: **if removing every implementation-specific
recognition of a class would make some implementation wrong or unusable
(not just slower), the class is a primitive.** Memories and channels fail
the test, because a synthesizer that does not know `fw_sp_mem` is a RAM
cannot map it to a macro. A FIFO built *from* a channel or memory primitive
passes, so `fw_fifo` stays in the standard library.

This splits today's `std` across two layers:
- **Primitives.** A small set that every implementation must realize:
  channel kinds, single-port and dual-port memory, and the standard port
  APIs.
- **Standard library.** Components built from those primitives. An
  implementation can run them unchanged.

The primitive set must stay small and change slowly, because each
primitive costs every implementation work. A new structure is first
written from existing primitives. It is promoted only when the test above
forces it.

**Where today's support code goes.**
- `lib/registry.py` → `fw-hdl-fe-sv`, recognizing api primitives.
- Storage binding (`storage.py`) → `fw-hdl-fe-sv` plus `zuspec-synth`.
- `src/rtl` RAM models → the implementations that need them: `fw-hdl-rt-sv`
  for simulation models of the memory primitive.
- `fw_rv_fifo`, `fw_sram_fifo` and `fw_xls_fifo_wrapper` → the Zuspec
  back ends that emit them (`fw_xls_fifo_wrapper` → `zuspec-be-xls`).
- A native or optimized version of a standard-library class goes in the
  implementation repo. It never goes in `fw-hdl-spec`.

#### `fw-proto-<p>`: protocol kits (library), one repo per protocol
Examples: `fw-proto-axi` (it already exists as a branch line), APB,
Wishbone. Ready/valid is not a kit: it is built into the language
(decision D4), and kits build on it.
- Each kit contains role APIs (initiator, target, monitor), bridges,
  signal-level transactors (`*_xtor_core.sv` is synthesizable), a
  back-to-back sim test and an SBY formal component. This is the structure
  `skills/fw-proto-kit` already describes.
- One repo per protocol because protocols version and gain owners
  independently.
- A kit depends only on `fw-hdl-spec`, which includes the standard
  library.
- The duplicate rv kit in `skills/fw-proto-kit/references/example` is
  retired. The skill's reference example becomes a small non-rv protocol,
  or points at `fw-proto-axi`. Its rv material points at the standard
  library.
- **The verification side of a kit lives in the same repo** under a
  separate fileset/package (`dv/`), depending on `fw-dv-spec` (§3.2).
  Protocol knowledge stays in one place, and design-only users don't pull
  in verification.

#### `fw-hdl`: distribution and integration (umbrella)
This is what a user installs: `ivpm` dep-sets select a stack, such as
`sim` (api + sv + std), `synth` (api + fe + std + zuspec synth) or `all`.
It also holds:
- User-facing docs: methodology, tutorials, and the Sphinx site that
  aggregates each repo's reference pages.
- Examples, and the agent skills (`fw-hdl`, `fw-api-kit`, `fw-proto-kit`,
  `fw-design-uarch`).
- **Cross-implementation integration tests.** This is the only place where
  two implementations meet. Tests here include: SV-runtime simulation vs.
  synthesized RTL equivalence; the QoR/XLS benchmark corpus
  (`examples/xls`, `tests/xls`); and the sync-lowering equivalence proofs
  this packet just did.
- Tool-side checking that compares implementations against each other:
  `verif/canon`, `verif/cosim`, `cosynth/equiv` and contract checks. These
  stay here until they generalize; see the note in §3.2.

The name `fw-hdl` moves to the umbrella, because it is what users mean by
"fw-hdl". The current repo becomes this umbrella once the other repos are
extracted, so history is preserved where most of it lives.

### 3.2 Verification family (future)

It follows the same pattern, under the name `fw-dv`.

| Repo | Kind | Depends on | Holds |
|---|---|---|---|
| `fw-dv-spec` | spec (language) | `fw-hdl-spec` | Core: testbench interface classes for sequences/stimulus, scoreboards and comparators, coverage, checkers and assertions, plus minimal base classes. Standard library: reusable scoreboards (today's `verif/canon` reorder-tolerant comparison is a candidate) and stimulus utilities. Conformance suite. |
| `fw-dv-rt-sv` | impl | `fw-dv-spec`, `fw-hdl-spec` | Stock-simulator runtime for the above. Peer of `fw-hdl-rt-sv`. Shares nothing with it except through `fw-hdl-spec`. |
| static/formal support | impl | `fw-dv-spec` | A plugin to `fw-hdl-fe-sv`, not a separate front end. It recognizes `fw-dv` constructs (properties, coverage, constraints) and emits Zuspec IR for the formal engine and solver (`zuspec-solver`). It becomes its own repo, `fw-dv-fe`, only if it outgrows a plugin. |
| `fw-proto-<p>/dv` | library | `fw-dv-spec` | Per-protocol sequences, coverage and protocol checkers, in the kit repo. For ready/valid, which is built in, these go in the `fw-dv-spec` standard library. |

The two families share the spec-level injection mechanism, because
`fw-dv` components are `fw_component`s. That is why `fw_factory`,
`fw_view_ctx` and `fw_rt_if` must be in `fw-hdl-spec` and not in an
implementation.

Two kinds of "verification" need to stay distinct:
- **Verification library (`fw-dv-*`).** What a *user* writes testbenches
  with.
- **Verification tooling.** Equivalence, formal lift, cosim. These prove
  that one *implementation* matches another. They belong in the umbrella's
  integration layer or in the Zuspec/dv-flow orgs (formal lift →
  zuspec-synth/formal, SBY driving → `dv-flow-libformal`), not in `fw-dv`.

### 3.3 What leaves the fw-hdl org

This applies the "Zuspec does the work" and "not XLS-centric" rules.

| Current location | Destination |
|---|---|
| `fe/parser`, `type_mapper`, `expr_mapper`, `stmt_mapper`, `func_mapper` (the generic SV subset) | `zuspec-fe-sv` (D2). Reconcile with its existing mappers there. Don't keep two copies. |
| `lower/spl2rtl.py`, `ir_build.py`, `ir_text.py` | Already thin over `zuspec.synth.spl`. Delete the wrappers. Text dump → `zuspec-ir-core`. |
| `facts.py`, `latency.py`, `storage.py`, `knobs.py` | Interface facts, latency tables and storage binding are IR concerns → `zuspec-synth`. `fw-hdl-fe-sv` only *attaches* facts recognized from SV. |
| `xls_flow`, `spl_flow`, `stage_tlm`, `ppa`, XLS IR regex in `latency`, `formal/smt`, `formal/codegen_equiv` | `zuspec-be-xls` (engine adapter) and `dv-flow-libsynth` (tasks). |
| `cosynth/rewrite.py` (AES-specific pipeline rewrite) | Into `zuspec-be-xls` as a generic pass, or retire it. |
| `emit/regblock.py` (writes SV text) | IR → `zuspec-be-sv`. |
| `fe/elab/translate.py` partial evaluation of blocked threads | The partial-evaluation core is an IR transform → `zuspec-synth.proc`. `fw-hdl-fe-sv` keeps the heap/interpreter glue. |
| `formal/lift`, `prove`, `replay` | Formal SVUnit is a verification-tooling feature. Lifting a test to an IR function → `fw-hdl-fe-sv`. Proving is engine-neutral, through Zuspec. |

### 3.4 Python namespace

`fw` and `fw.hdl` (and `fw.dv`) are **PEP 420 namespace packages**. No
distribution ships `fw/__init__.py` or `fw/hdl/__init__.py`. Each repo
contributes a subpackage:

| Module | Distribution / repo | Holds |
|---|---|---|
| `fw.hdl.api` | `fw-hdl-spec` (`bindings/py`) | The Python binding: what users import to write fw-hdl in Python. Added later (D1). |
| `fw.hdl.fe.sv` | `fw-hdl-fe-sv` | SV front end to Zuspec IR. Owns the dfm packages `fw.hdl.synth`, `fw.hdl.formal`, `fw.hdl.swmodel` and the `zuspec.lowering` registration. |
| `fw.hdl.fe.py` | `fw-hdl-fe-py` (later) | Python front end. `fw.hdl.fe` is itself a namespace. |
| `fw.hdl.rt.sv` | `fw-hdl-rt-sv` | sv-weave plugins and the simulation dfm package for the SV runtime. |
| `fw.hdl.tools` | `fw-hdl` (umbrella) | The `fw-hdl` CLI, cross-implementation integration and checking (`verif/canon`, `cosim`, `cosynth/equiv`). |
| `fw.dv.api`, `fw.dv.rt.sv`, … | `fw-dv-*` | The same shape for verification. |

Notes:
- The user-facing binding is `fw.hdl.api`, not `fw.hdl.spec`. The *repo*
  is the specification. What a user imports is the API that the spec
  defines for Python. This also reads naturally: `from fw.hdl.api import
  Component`.
- No `__init__.py` at a namespace level means no `__version__`, no
  docstring, and no re-exports at `fw.hdl`. Version queries go through
  `importlib.metadata.version("fw-hdl-spec")`, and so on.
- dfm entry points and package data (`*.dv`, `schema/*.json`) move from
  `fw.hdl` to the owning subpackage. That is mostly `fw.hdl.fe.sv`, with
  the sim tasks in `fw.hdl.rt.sv`.
- Today's tree breaks the rule: `python/fw/__init__.py` and
  `python/fw/hdl/__init__.py` both exist. Removing them is part of
  migration step 1, together with moving the current modules under
  `fw.hdl.fe.sv` / `fw.hdl.rt.sv` / `fw.hdl.tools`.

## 4. Versioning and compatibility

- **`fw-hdl-spec` uses semver.** The spec version is the contract.
  Implementations declare the range they support (e.g. `api >=0.3,<0.4`),
  and so do libraries.
- **Conformance tags match api tags.** Each implementation's CI runs
  `fw-hdl-spec@<tag>` conformance through its own runner.
- **Library compatibility is by construction.** A library that passes its
  own tests on the reference runtime *and* the static front end is
  considered portable. Its CI runs at least those two implementations.
  This catches code that only works dynamically (e.g. unbounded runtime
  allocation in synthesizable components).
- **Realizations are versioned with their implementation.** They declare
  the library range they cover, and they are re-checked against the
  library's contracts.
- **Only the umbrella pins exact versions.** It is the one repo that pins
  a full known-good set.

## 5. Migration plan

Split *logically in place first*, then extract physically. The spec will
churn for a while, and cross-repo PRs for every API change would be
expensive. This order gets the dependency discipline without that cost.

1. **Reshape in this repo.**
   - Create top-level directories that mirror the target repos:
     `spec/semantics/`, `spec/bindings/sv/{core,std}/`, `rt-sv/`,
     `fe-sv/`, `umbrella/`.
   - Each gets its own `flow.yaml` filesets and, for Python, its own
     subpackage under the `fw.hdl` namespace (§3.4). Delete
     `python/fw/__init__.py` and `python/fw/hdl/__init__.py`.
   - Add a lint check, run in CI, that enforces dependency direction:
     files under `spec/` may not name a class defined outside `spec/`;
     `core/` may not name `std/`; and so on.
   - At first the check fails. That gives an explicit work list.
2. **Introduce `fw_rt_if` and widen the factory.**
   - Make the factory create more than components: services and port
     implementations.
   - Move `fw_component`/`fw_component_root`/ports onto `fw_rt::get()`.
   - Split the files the survey marked as mixed: `fw_component` (807
     lines), `fw_component_root[_param]`, `fw_steppable`, `fw_extern`,
     `fw_reg_base`, `fw_event_set`, and the sync ports.
   - Move kernel, debug, registers and `sync/` out of `fw_hdl_pkg`.
   - Delete the orphan `fw_type*.svh` files.
3. **Make the Python elaborator implement `fw_rt_if` semantics** directly,
   rather than special-casing implementation class names, so it depends
   only on the spec.
4. **Write the conformance suite.** Seed it from the existing
   `tests/sync`, rv and domain tests, rewritten to minimum-bar
   assertions. Add runners for `rt-sv` and for `fe`+synth+Verilator.
5. **Move engine code and generic SV mapping to Zuspec** (§3.3). This proceeds alongside the
   other steps and is tracked as XLS/back-end debt.
6. **Extract repos** with `git filter-repo`, which keeps history per
   directory. Do it in this order: `fw-hdl-spec` → `fw-hdl-rt-sv` →
   `fw-hdl-fe-sv`. `fw-proto-axi` is assembled from its branch, on top of
   the extracted `fw-hdl-spec`. What remains becomes the
   `fw-hdl` umbrella. Extract a component only once its lint column is
   clean.
7. **Start `fw-dv-spec` as a new repo** on the finished pattern. Don't
   start it in this repo.

## 6. Decisions (D6 deferred, D5 open)

- **D1 Names, and language bindings.** *Decided.*
  - **One spec repo with per-language bindings inside it:** `fw-hdl-spec`.
    - fw-hdl captures hardware *semantics*. SV and Python are two surface
      syntaxes for the same semantics, as with protobuf/OpenAPI or
      Accellera PSS (a DSL input and a C++ input in one standard).
    - Bindings share one repo so that a semantic change lands in every
      binding at once.
  - **Implementation repos are qualified by binding:** `fw-hdl-rt-sv`,
    `fw-hdl-fe-sv`, and later `fw-hdl-fe-py`. Protocol kits are
    `fw-proto-<p>`, and the umbrella is `fw-hdl`. The verification family
    mirrors this: `fw-dv-spec`, `fw-dv-rt-sv`.
  - **The Python namespace** is in §3.4. `fw.hdl` is a namespace package,
    so the Python binding lives at `fw.hdl.api`.
  - **Still open: the Python binding vs. `zuspec-dataclasses`.** A Python
    binding sits very close to zdc, which already captures
    `@sync`/`@comb` components in Python. Before starting
    `bindings/py/`, decide among three options:
    - define `fw.hdl.api` on top of zdc;
    - make zdc *be* the Python binding;
    - keep the two deliberately distinct: `fw.hdl.api` as the user-facing
      class-library API, zdc as the Zuspec modeling layer.
- **D2 Front end vs. `zuspec-fe-sv`.** *Decided.* Build out the generic
  SV-subset layer in `zuspec-fe-sv`, and layer `fw-hdl-fe-sv` on it. The
  migration is in §3.3.
- **D3 Registers.** *Decided.*
  - The register shape (interfaces and base classes) is declared in
    `fw-hdl-spec` core.
  - The concrete register types are in its standard library.
  - Recognition is in `fw-hdl-fe-sv`, and the register state-machine runtime
    is in `fw-hdl-rt-sv`.
- **D4 Ready/valid.** *Decided: rv is built into the language*, not a
  protocol kit. The standard library is expected to build on rv.
  - **Core:** the `fw_rv_sp_*` signal ports and the rv
    initiator/target/monitor role interfaces.
  - **Standard library:** the rv components and bridges, and the
    signal-level rv transactor modules.
  - **Runtime:** the `fw_root` pin bridging (`fw_rv_pin_in`/`out`)
    remains in `fw-hdl-rt-sv`.
  - **Verification:** rv verification (sequences, coverage, checker) goes
    in the `fw-dv-spec` standard library.
  - Precedent: Chisel ships `Decoupled` in `chisel3.util`, and XLS
    channels are ready/valid natively.
  - `fw-proto-*` kits start with AXI and build on the built-in rv.
- **D6 The primitive set.** *Deferred.* Proposed primitives: channel
  kinds, memory (single-port and dual-port), and the standard port APIs.
  Tables and pools stay library classes, with their storage choice made
  through the memory primitive. Revisit before conformance work on the
  standard library (migration step 4).
- **D5 Timing of the split.** The proposal is in-place reshaping until
  `fw-hdl-spec` reaches 0.1 with a passing conformance suite on two
  implementations. The alternative is to extract immediately and accept
  cross-repo churn.
