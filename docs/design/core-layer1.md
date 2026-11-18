# Core layer 1: component, signal, port, bundle, extern

This is the first abstraction layer of the rebuilt fw-hdl core. It covers
structure only: components, signals, signal ports, bundles, and externs
(wrapped RTL). With this layer a user can:

1. wrap existing RTL modules as fw-hdl components,
2. assemble them into a hierarchy with typed, direction-checked connections,
3. generate Verilog that simulates on a stock simulator (Verilator first).

The layer follows the repository architecture in
[project-architecture.md](project-architecture.md): the API and its
semantics go in `fw-hdl-spec`, and two implementations are built against
it. `fw-hdl-rt-sv` elaborates dynamically in a simulator. `fw-hdl-fe-sv`
elaborates statically and produces Zuspec IR, from which `zuspec-be-sv`
emits the Verilog.

The existing code (`src/`, `python/fw/hdl/`, `tests/`) stays in the repo
as **reference only**. It is not compiled, installed or tested. New code
goes in new places (§2) and reuses old code only by porting it, never by
importing or including it. Each later layer (domains, glue logic,
processes, transaction-level ports, the standard library) is designed the
same way, and draws on the reference code for its own area.

---

## User benefit

What a user of fw-hdl gets from layer 1:

1. **Existing RTL becomes a typed component without touching the RTL.**
   A wrapper class declares ports and bundles, and a short map ties them
   to the module's pins by rule (prefix, rename), with ties and open pins
   stated explicitly. The module header is checked against the map, so a
   wrong pin name, width or direction is an elaboration error, not a
   silent mis-wire.
2. **Interfaces connect as one object.** A ready/valid or AXI-Stream link
   is one `connect` between bundles, with roles (initiator, mirror,
   monitor) that fix the directions. Mismatched types, multiple drivers,
   undriven nets and open inputs are reported with stable IDs and full
   paths.
3. **Parameterized assemblies stay parameterized.** A class with
   parameters, loops and conditionals emits as one parameterized Verilog
   module with generate blocks, not a module per configuration, so the
   output is reviewable and reusable as RTL.
4. **The output is plain, lint-clean Verilog.** Wrapped modules are
   instantiated directly, packed struct and enum types keep their names,
   and `verilator -Wall` is clean with no pragmas. Nothing from fw-hdl is
   needed to simulate or synthesize it.
5. **Two implementations agree.** The same design elaborates in a
   simulator (rt-sv) and statically (fe-sv) to the same netlist, checked
   by conformance scenarios, so behavior is defined by the spec rather
   than by one tool.
6. **It runs through dfm.** `Elaborate` and `EmitSV` tasks take the
   design and the RTL and produce the Verilog and a file list.

---

## 0. Status

The plan is in §9. Update this table as each step finishes, so a fresh
session can pick up from this file.

| Step | Status | Notes |
|---|---|---|
| M0 Scaffolding | done, one item deferred | All three repos laid out with `ivpm.yaml`/`flow.yaml`/`pyproject.toml`; rt-sv and fe-sv installed editable in this repo's venv (`uv pip install --python packages/python/bin/python -e ... --no-deps`; the venv has no pip). The old `python/` was already not installed. Dependency lint: `tools/layer1_dep_lint.py` (0 findings). Deferred: taking the old `src/` filesets off the root `flow.yaml`, because the in-flight sync work on this branch still uses them. |
| M1 Spec API (SV) and semantics docs | done | `semantics/*.md` and `netlist.schema.json`; 37 conformance scenarios, all compiling against the default bodies (`dfm run conformance-compile`); API check and spec lint in `tools/fw_api_check.py`. Additions to confirm: `FW-E-NAME-BAD`; `FW-E-EXT-PIN` also for a pin mapped twice; `FW-E-EXT-PORT` also for `pin()` on a non-port; `**` matches zero or more segments, registered globs match strict descendants only. Added `fw_extern_map::unused(o)` (decided 2026-11-15): an input port or bundle with no pin; scenarios `extern_unused`, `extern_unused_bad`; both implementations pass them; the smoke `valid_mon` is a monitor of `fw_rv_if` again with `p.data` unused. Extern parameters are typed (decided 2026-11-15): `param(name, fw_param_arg)` with `fw_value #(T)::of(v)` / `fw_type #(T)::get()`; netlist `{"type", "value"}`; `FW-E-EXT-PARAM` header check; scenarios `extern_params`, `extern_param_bad`. Open: mixins on a commercial simulator (deferred, §10 Q2). The `logic` emission of `bit` type parameters was closed by M8(b). |
| M2 rt-sv elaboration runtime | done | `dfm run tests` in fw-hdl-rt-sv: api-check PASS, conformance 29 passed / 4 static-only skipped, smoke through `fw_elab`. Verilator 5.055 V3Param internal error worked around (runner elaborates through a non-parameterized wrapper). |
| M3 fe-sv static elaboration to netlist | done | All 33 scenarios pass on fe-sv, the 4 static-only ones included (`fw-hdl-fe-sv/tests/conformance`); rt-sv passes the same expectations, so the two netlists agree. Z4: generic interpreter `zuspec.fe.sv.interp` (zuspec-fe-sv moved to pyslang 12). fe-sv: `api.py` (own `fw_hdl_pkg`, stub bodies from the spec), `rt.py` (intrinsics, phases, params), `resolve.py` (nets, checks, extern header checks), `netlist.py`. Spec fix: `shape_param` used `port_c::` (illegal without `#()`, IEEE 1800-2017 §8.25.1; Verilator accepted it). |
| M4 Zuspec IR and Verilog emission | done | Z1/Z2 in zuspec-ir-core (§6.3 "IR shapes"); IR serializer fixed to round-trip enums and shared subtrees (it cut every repeated object). Z3: `zuspec.synth.passes.struct_flatten` + be-sv `structural.py`. fe-sv `ir_map.py`, `emit.py`. The spec's `soc` (pass-through hierarchy, monitor, ties, overrides) emits lint-clean under `verilator -Wall` (warnings only in the wrapped RTL). The open-pin pragma and plain-vector struct/enum ports noted here were closed by M8(b). |
| M5 Extern end to end | done | `fw-hdl-fe-sv/examples/wrap_rtl`: `fw_rv_fifo` + `axis_reg` (AXI pin names, active-low reset, tie and open) wrapped with `fw_rv_if` bundles, assembled in `chain`; emitted `chain.sv` is lint-clean and matches the hand-wired `chain_ref` cycle for cycle over 2000 random cycles (`tests/e2e/test_wrap_rtl.py`; the testbench fails on a mutated reference). |
| M6 Parameterized emission | done | Symbolic tracing in `zuspec.fe.sv.interp` (`trace.py`: `Sym` values carry an IR expression; parameter loops/branches reported, else tainted). Z5 in ir-core (`GenerateFor`/`GenerateIf`, `DataTypeComponent.generates`, `Field.inst_params`/`index_var`, generic bundles). `struct_flatten` handles the Z5 form; be-sv renders parameters, array nets, generate blocks. fe-sv `ir_map` maps each class generally or falls back per specialization (`FW-I-EMIT-SPEC`; `require_param` makes it `FW-E-EMIT-SPEC`; dfm `Elaborate` has `parameterize`/`require_param`). `smoke_pkg::fifo_chain` emits as one module, lint-clean, and matches a hand-wired reference at n=1,2,3 (`tests/e2e/test_param_emit.py`). Open: value/struct class parameters always specialize; no conditional children or port arrays inside generate loops; unused params fields give Verilator `UNUSEDPARAM`. |
| M7 dfm tasks and user docs | done | dfm package `fw.hdl.fe.sv` (`python/fw/hdl/fe/sv/flow.dv`, entry point `dv_flow.mgr`): `Elaborate` (inputs: `fwHdlSource` design + extern RTL; outputs `zuspecIR` = `design.json` + `design.zir`, `fwHdlNetlist`, and the RTL forwarded) and `EmitSV` (Verilog in dependency order + `files.f`). `examples/wrap_rtl`: `dfm run sim` passes through dfm alone; its README walks through wrapping. User guide: `fw-hdl-spec/docs/wrapping.rst` (builds with `-W`). fe-sv `dfm run tests`: 35 pass. |
| M8 Layer-1 close-out | done, two items deferred | Started 2026-11-15. (a) M6 gaps against §6.6: done. Value and shape class parameters become module parameters (`S_data_w`); `if` on parameters becomes generate `if` (both arms, the other arm elaborated separately and merged); port and bundle arrays in loops become unpacked array ports with per-index connections. Also fixed: a value class parameter setting a port width, or a `mk_params` default computed from one, was silently baked in. Tests: `fw-hdl-fe-sv/tests/e2e/test_param_gaps.py` (35; designs in `examples/param_gaps/`). fe-sv 85 passed, zuspec-fe-sv 105/5 skipped, be-sv 199, ir-core 220, flatten 14, wrap_rtl sim pass. Remaining limits in §6.6 (case/while on parameters, conditionals inside loops, zero-iteration loops, module parameter defaults are the elaborated values). (b) Emission details: done. Packed struct and enum ports keep their types: one generated `<top>_types_pkg`, full `pkg::name` references, and the RTL's own declaration reused when the extern RTL declares the same type (a different declaration of the same name is the new `FW-E-EXT-TYPE`). `DataTypeInt.four_state` (None = not stated) makes `bit` type parameters emit as `bit`; ports and nets stay `logic`, except a port typed by a 2-state type parameter. Unread outputs and `open` extern pins connect to `<inst>_<pin>_unused` nets, so `-Wall` is clean with no pragma (an extern given without its RTL still gets an empty `.pin()`). Also fixed: a class's declared type-parameter default is now used (it was the first specialization). Tests: `examples/packed_types`, `tests/e2e/test_packed_types.py` (8). fe-sv 93 passed, zuspec-fe-sv 107/5 skipped, be-sv 203, ir-core 221, flatten 17, wrap_rtl sim pass. Limits: packed array and union members emit as vectors; no `struct packed signed`. M0's deferred `src/` item still waits on the sync work. Commercial-simulator checks (§10 Q2) deferred: Verilator only for now (decided 2026-11-15). |

---

## 1. Scope

### In scope

| Concept | SV binding names |
|---|---|
| Object identity and naming | `fw_object` |
| Component | `fw_component`, `` `fw_component_utils ``, `` `fw_component_params ``, `` `fw_component_params_init `` |
| Creation | the factory: every structural object is created through it (§3.8) |
| Parameters | shape class parameters; a params struct per component, with defaults, creator values, path overrides, and constructor factories set by `init_params` (§3.9) |
| Signal (local) | `fw_signal #(T)` |
| Signal ports | `fw_input #(T)`, `fw_output #(T)`, `fw_inout #(T)` |
| Bundles | `fw_bundle_base`, `fw_bundle #(B)`, `fw_mirror #(B)`, `fw_monitor #(B)` |
| Built-in ready/valid bundle | `fw_rv_if #(T)` (decision D4: rv is built in) |
| Connections | `a.connect(b)`, `connect_all(...)`, `s.tie(v)` |
| Extern | `fw_extern_if`, `fw_extern_map`, `` `fw_extern_utils `` |
| Implementation handle | `fw_impl_if`: an empty interface class; every object holds one for the tool (§4.1) |
| Elaborated netlist | a JSON schema, used as the conformance artifact |

**Acceptance criterion for the layer.** Take existing RTL modules
(`src/rtl/fw_rv_fifo.sv`, `src/rtl/fw_valid_check.sv`, and one module
with foreign pin names and an active-low reset). Wrap them, and assemble
a parameterized chain with bundles, a monitor, ties and a pass-through
hierarchy level. Then:
- generate Verilog with fe-sv, Zuspec and be-sv;
- lint it clean with `verilator -Wall`;
- simulate it with a plain SV testbench, matching a hand-wired reference
  cycle for cycle;
- have rt-sv and fe-sv produce identical elaborated netlists for every
  conformance scenario.

### Out of scope (later layers)

These are deliberately absent. The layer-1 API must not need to change
when they arrive (§3.3, "Reserved").

- Behavior: `comb()`, `step()`, `run()`, and signal read/write timing
  (layer 2, processes).
- Transaction-level ports, exports and sockets (layer 3). In the new core
  "port" means a *signal* port. The transaction-level API will get its
  own names when that layer is designed, and today's `fw_port`/`fw_export`
  stay in the old package until then.
- Clock and reset *domains*, crossing checks and reset supervision. Layer 1
  has no clock or reset classes; RTL clock and reset pins are plain ports
  until the domain layer replaces them (§3.6).
- Registers, debug, the standard library, channels and memories.
- Running class-level behavior alongside RTL in one simulation. In layer 1
  an extern has no class body to run.
- The Python language binding (D1 sub-question).
- **Factory substitution.** Global type overrides and instance type
  overrides. In layer 1 the factory creates exactly the type asked for.
  Choosing an implementation at build time is *in* scope: it is done with
  constructor factories carried in the params value (§3.9). Every object already goes through it, so adding
  substitution later changes no user code (§3.8).

---

## 2. Where the code lives

Each part is its own repo. All three fw-hdl repos are pulled into
`packages/` by the `dev` dep-set of this repo's `ivpm.yaml`. This repo,
`fw-hdl`, is the umbrella, and it holds the old code as reference.

| Part | Repo (checkout) | Depends on |
|---|---|---|
| Spec: semantics, SV binding, conformance scenarios | `fw-hdl-spec` (`packages/fw-hdl-spec/`) | nothing fw-hdl; sv-weave for its own compile check |
| Reference SV runtime (elaboration only, in this layer) | `fw-hdl-rt-sv` (`packages/fw-hdl-rt-sv/`) | `fw-hdl-spec` |
| Static front end | `fw-hdl-fe-sv` (`packages/fw-hdl-fe-sv/`) | `fw-hdl-spec`, pyslang, `zuspec-fe-sv`, `zuspec-ir-core`, `zuspec-be-sv` |
| Zuspec IR additions and passes | `zuspec-ir-core`, `zuspec-fe-sv`, `zuspec-synth` / `zuspec-be-sv` | — |

`fw-hdl-rt-sv` and `fw-hdl-fe-sv` never depend on each other. Each
repo carries its own `ivpm.yaml`, which lists its dependencies so it can
be developed standalone, and its own `flow.yaml`.

Repo layout of `fw-hdl-spec` for this layer:

```
fw-hdl-spec/
  flow.yaml                    dfm package fw-hdl-spec (sv-api fileset; sv-api-compile; tests)
  tools/
    fw_hdl_bodies.py           sv-weave weaver: default bodies for every extern method
    sv-weave.yaml
  semantics/
    elaboration.md  signals.md  bundles.md  connections.md  extern.md
    params.md                  parameters and overrides (§3.9)
    diagnostics.md             stable diagnostic IDs (§3.10)
    netlist.schema.json        the elaborated-netlist format (§3.11)
  conformance/
    <scenario>/top.sv          one directory per scenario
    <scenario>/expect.json     expected netlist, or expected diagnostic IDs
  bindings/sv/                 the API: declarations only, one class per .svh (§4)
    fw_hdl_api.svh             every declaration; included inside a package
    fw_hdl_pkg.sv              package fw_hdl_pkg around fw_hdl_api.svh
    fw_hdl_macros.svh          macro names and declared members; minimal expansions
    fw_impl_if                                     the implementation's handle: empty
    fw_object  fw_component  fw_ctor  fw_ctor_of
    fw_param_edit  fw_param_override
    fw_signal_base  fw_signal  fw_input  fw_output  fw_inout
    fw_bundle_base  fw_bundle  fw_mirror  fw_monitor  fw_rv_if
    fw_pin_rule  fw_extern_map  fw_extern_if
  tests/sv/smoke/              §4.8 example, compiled against the API
```

Repo layouts of the two implementations:

```
fw-hdl-rt-sv/
  ivpm.yaml  flow.yaml         dfm package fw.hdl.rt.sv (filesets, conformance runner)
  sv/
    fw_hdl_pkg.sv              its own fw_hdl_pkg: the spec's fw_hdl_api.svh plus its bodies (§4.1)
    fw_elab.sv                 fw_elab #(type T): elaborate, write the netlist
  python/fw/hdl/rt/sv/         conformance-runner glue (no __init__.py above sv/)
  pyproject.toml               distribution fw-hdl-rt-sv
  tests/

fw-hdl-fe-sv/
  ivpm.yaml  flow.yaml         dfm package fw.hdl.fe.sv (Elaborate, EmitSV tasks)
  python/fw/hdl/fe/sv/         FeRt intrinsics, netlist, IR mapping, extern check
  pyproject.toml               distribution fw-hdl-fe-sv
  tests/
```

Python packages are namespace portions: there is no `__init__.py` at the
`fw`, `fw.hdl`, `fw.hdl.rt` or `fw.hdl.fe` levels.

**Old code is reference, not implementation:**
- **Off the compile.**
  - The root `flow.yaml` stops exporting the `src/` filesets.
  - The root `pyproject.toml` stops installing `python/`.
  - Pytest stops collecting the old `tests/`. Keep them in a
    `testpaths` exclusion, not deleted.
  - Nothing built from this repo includes or imports old code.
- **SV package name.** Because the old package is never compiled, the new
  core package takes the final name, `fw_hdl_pkg`, as the architecture doc
  already has it. There are no name clashes to manage. In particular,
  `fw_mirror` is free for the bundle mirror (as `signals.md` proposed, and
  as zuspec-dataclasses names it).
- **Python packages.** With `python/` no longer installed, its
  `fw/__init__.py` and `fw/hdl/__init__.py` no longer hide anything. The new
  packages (`fw.hdl.fe.sv`, `fw.hdl.rt.sv`) are namespace portions from the
  start: they have no `__init__.py` at the `fw`, `fw.hdl` or `fw.hdl.fe`
  levels.
- **Porting, not importing.** Useful old code is copied into its new home
  and cleaned up there, keeping a note of where it came from.
  - The generic pieces go to Zuspec (D2): the class interpreter
    (`python/fw/hdl/fe/elab/interp.py`, 1351 lines) moves to
    `zuspec-fe-sv`, which today has a parser and mappers but no
    interpreter.
  - fw-hdl-specific pieces, such as the extern header check, go to
    `fw-hdl-fe-sv`.
- **Dependency rules (lint check, M0).**
  - Nothing in `packages/fw-hdl-spec` names anything outside it.
  - `fw-hdl-rt-sv` and `fw-hdl-fe-sv` name nothing in this repo's
    `src/` or `python/`, and nothing in each other.

---

## 3. Semantics

This section is the normative content. It becomes `semantics/*.md` in the
spec repo. It is written binding-neutral; the SV spelling is in §4.

### 3.1 Objects and names

- Every structural object (component, signal, port, bundle) has a
  **name** and a **parent**. Only the top component has no parent.
- The **full name** is the parent's full name, `.`, then the name.
  Bundle members are named through their bundle: `top.u0.out.valid`.
- Names must be unique among the children of a parent. A name must be a
  legal SV identifier, or an identifier with one or more `[index]`
  suffixes for array elements.
- A **scope** is the component that owns an object: for a signal or port,
  its parent component; for a bundle member, the component that owns the
  outermost bundle.

### 3.2 Elaboration

Elaboration builds the object tree, records connections, then resolves and
checks them. Its phases, in order:

1. **Construct the top.** The implementation creates the top component
   through the factory (§3.8). Its parameters are resolved like any
   other component's (§3.9).
2. **Build, top-down.** `build()` runs on a component before it runs on
   the component's children, and children are built in creation order.
   - Children, signals, ports and bundles are created in `build()`, or
     in the constructor. Every one is created through the factory.
   - Parameter overrides are registered in `build()` or in the
     constructor, before the components they target are created.
   - Creating any structural object after the build phase is an error
     (`FW-E-ELAB-LATE`).
3. **Connect, top-down.** `connect()` runs on every component.
   - Connections and ties may be made only here (`FW-E-CONN-PHASE`
     otherwise). This guarantees every port of every child exists.
4. **Resolve.**
   - The implementation forms nets from the recorded connections
     (§3.5).
   - It checks every net, every extern map, and every unconnected
     input, reporting *all* errors, not only the first.
   - If any error was reported, elaboration fails.
5. **Frozen.** After resolution the structure is immutable.

Every implementation must produce the same tree, the same nets and the same
diagnostics for the same input. The conformance suite checks this through
the netlist (§3.11). How an implementation walks the phases is its own
business: the reference runtime executes the code, and the static front
end interprets it.

### 3.3 Signals and ports

- A **signal** carries a value of a packed type `T`: `bit`/`logic`
  vectors, packed structs, packed unions or enums. The default is `bit`.
  Width is `$bits(T)`. Unpacked and class types are not signals.
- A **local signal** (`fw_signal`) belongs to a component and is not
  visible outside it. In emitted RTL it is a `logic` net inside the
  module.
- A **port** is a signal on the component boundary, with a declared
  direction: `in`, `out` or `inout`. In emitted RTL it is a module port.
- A port declared inside a bundle has a *declared* direction relative to
  the bundle's initiator. Its *effective* direction is the declared one,
  flipped once for every mirror on the path from the scope (§3.4).
- **Arrays.** A signal or port may be declared as an array of `N`
  elements with the same type, named `p[0]`..`p[N-1]`. When `N` comes from
  a component parameter, emitted RTL keeps it as an array port (§6.6).

**Layer 2.** Signal values (`read()`, `write(v)`) and their timing come
with processes in layer 2. Reading will be legal on every direction, and
writing an effective input illegal. A tool keeps value storage and update
scheduling behind the object's `fw_impl_if` handle (§4.1), in the style of
SystemC's request-update, so adding them adds methods but changes no
layer-1 declaration.

### 3.4 Bundles

A **bundle type** is a named, ordered group of ports and nested bundles.
Directions are written from the **initiator's** point of view. A bundle
type cannot be used directly; every use names a **role**:

| Role | Meaning | Effective direction of a member declared `out` |
|---|---|---|
| bundle (initiator) | this side drives what the initiator drives | out |
| mirror (target) | directions flipped | in |
| monitor | observes only; drives nothing | in (every member is an input) |

- Bundles nest. A member may itself be a bundle or a mirror of another
  bundle type, so AXI is five channel bundles, with `r` and `b` mirrored.
- Effective direction is computed along the path: each mirror flips it.
  A monitor anywhere on the path makes every member below it an input.
- An `inout` member stays `inout` in every role.
- A bundle may appear as an array, like a port.
- Bundles are a structural grouping. Emitted RTL flattens a bundle to one
  port per member, named by joining the path with `_`: `out_valid`,
  `axi_aw_addr` (§6.3). A name that collides after flattening is an
  error (`FW-E-NAME-FLAT`).

### 3.5 Connections

**Locality.** A component may connect only objects in its own scope:
- its own ports and local signals, and
- the ports and bundles of its *direct* children.

Reaching deeper into the hierarchy is an error (`FW-E-CONN-SCOPE`). This
keeps every connection inside one module of the emitted RTL.

**Endpoints.** Seen from the connecting component, each endpoint is a
source, a sink, or both:

| Endpoint | Role in the scope |
|---|---|
| own `in` port | source |
| own `out` port | sink |
| own local signal | neither; it is the net |
| child's `out` port | source |
| child's `in` port | sink |
| any `inout` | both |
| child monitor member | sink |

**Nets.**
- Connections are symmetric and transitive: connected endpoints form one
  net (union-find).
- A net must have **exactly one source** if it has any sink, unless it is
  tied (`FW-E-NET-UNDRIVEN`, `FW-E-NET-MULTI`).
- A tie is a source.
- Nets made only of `inout` endpoints are exempt from the driver check.
- All endpoints of a net must have equivalent types (SV type equivalence,
  IEEE 1800-2017 §6.22.2). Equal width is not enough (`FW-E-CONN-TYPE`).
  There is no implicit extension or truncation; slices come with a later
  layer, or with an extern pin map (§3.7).
- An own `in` port connected straight to an own `out` port is legal.
  It becomes an `assign` in emitted RTL.

**Bundle connections** connect member-wise, by member name, and are legal
only if every member pair is legal. The common cases:

| Connect | Where | Typical use |
|---|---|---|
| child bundle ↔ child mirror | siblings | initiator to target |
| own bundle ↔ child bundle | pass-through | re-export a child's initiator side |
| own mirror ↔ child mirror | pass-through | re-export a child's target side |
| child monitor ↔ any bundle or mirror of the same type | anywhere | tap a link; the monitor's members are sinks |

Both sides must have the same bundle type (`FW-E-CONN-TYPE`).

**Unconnected endpoints.**
- An unconnected effective input is an error (`FW-E-IN-OPEN`) unless it
  is tied.
- An unconnected output is legal.
- An unconnected `inout` is legal.

**Ties.** `s.tie(v)` drives a sink with a constant. A tied endpoint may
not also be driven.

### 3.6 Clock and reset

Layer 1 has **no clock or reset classes**. A clock or reset pin of wrapped
RTL is an ordinary `fw_input #(bit)` port, connected explicitly like any
other signal. This is a deliberate stopgap: the domain layer, which comes
next, replaces it.

The domain layer is designed in `core-domains.md`. What it means for
layer 1 (revised 2026-11-15):
- **Domains are a capability layer.** Association, query and pin mapping
  are static functions of `fw_domain #(K)` that take core objects, for
  example `fw_clock_domain::set(child, dom)` and
  `fw_clock_domain::pin(m, "clk")`.
  - Nothing is added to `fw_component`, the port and bundle classes, or
    `fw_extern_map`.
  - The `clock`, `reset`, `clock_out` and `reset_out` method names that
    were reserved on `fw_extern_map` are no longer reserved (decided
    2026-11-15).
- **Domain association.** A component resolves a domain of each kind by
  lookup, inherited from its parent unless it is set. Nothing on the
  component's boundary carries them.
- **Emission.** Each generated module's clock and reset ports are derived
  from the domains its subtree realizes.

Consequences for layer 1:
- A layer-1 wrapper's `clk`/`rst` ports disappear when domains land. The
  change is local: delete the two ports, add two `fw_domain #(K)::pin`
  lines to the map, and delete the matching connections in the parent's
  `connect()`.
- There is no implicit clock or reset connection rule. It would exist only
  to hide clock and reset wiring, and domains do that properly.

### 3.7 Extern

An **extern** is a component realized by an existing RTL module. It
declares ports and bundles like any component and supplies a **pin map**.
It has no children and no behavior.

The pin map, as data:
- The module name. File paths are deliberately not in the class: the
  build system supplies sources through filesets, and the module is found
  by name.
- Parameter values, as typed objects: `fw_value #(T)::of(v)` for a value
  of any type (integral, string, enum, packed struct), `fw_type #(T)::get()`
  for a `parameter type`. Each may be computed from the component's own
  parameters. The value carries its type, so a tool writes it as the
  module needs (an enum by its label, a type by its name) and checks it
  against the module's parameter (`FW-E-EXT-PARAM`). Decided 2026-11-15:
  one typed form rather than `param_int`/`param_str`/..., because typed
  methods cannot express enums or type parameters.
- For every module pin, exactly one of:
  - a port or bundle member of the extern, optionally a bit slice of a
    wider pin, or a slot `k` of a packed pin shared by several ports;
  - a tie to a constant (an input pin);
  - open (an output pin);
  - not mentioned, in which case the default rule applies.
- **Unused ports.** `unused(o)` marks an input port, or every port of a
  bundle, as having no pin: the module does not use it. A monitor of
  `fw_rv_if` wrapping a checker with no data pin marks `p.data` unused.
  An unused port is still an input of the component (it must be connected,
  `FW-E-IN-OPEN`); it just reaches no pin. Only inputs may be unused: an
  output with no pin would leave its net undriven in the emitted RTL.
- **Default rule.** An unmapped port or bundle member maps to the pin
  with its flattened name. For example, `in.data` maps to pin `in_data`.
- **Prefix rules.** A bundle can be mapped with a rule: a prefix, an
  optional suffix, per-member renames, and optional upper-casing. For
  example, `prefix(in, "in_").rename("valid", "vld")` maps `in.valid` to
  `in_vld`. This replaces today's per-protocol `rv`/`valid`/`level` kinds:
  a bundle's members are known from its type, so one rule covers every
  protocol.

**Checks.** These need the module header, so a static implementation does
them. The reference runtime records the map but cannot check it.
- Every module pin is accounted for exactly once (`FW-E-EXT-PIN`).
- Every port that is not unused maps to a pin (`FW-E-EXT-PORT`).
- Directions agree, and widths agree after the parameter values are
  applied (`FW-E-EXT-DIR`, `FW-E-EXT-WIDTH`).
- Every parameter set exists in the module and fits it: a value for a value
  parameter, a type for a `parameter type`, a string only for a `string`
  parameter, an enum only for the same enum type (`FW-E-EXT-PARAM`).

**Abstract realization.** An extern may extend an abstract component
that declares only ports and params. The creator chooses the realization,
RTL or (in a later layer) a model, through a constructor factory in its
params (§3.9). Factory type overrides will be a second route, later. This
is why "extern" is an interface the class implements rather than a base
class (§4.7).

### 3.8 Creation

**Every structural object is created through the factory:** components,
signals, ports and bundles. Constructing one any other way is an error
(`FW-E-ELAB-NEW`).
- The creation call names the type, the instance name, the parent and,
  for a component, optionally a parameter value. It is one call: there is
  no separate step to set parameters.
- The factory supplies the name, parent and parameters to the new object
  before its constructor body runs, so constructors take no arguments.
  Most user classes need no constructor at all and create their members
  in `build()`.
- The netlist records each object's created type.

In layer 1 the factory always creates exactly the type requested. A
realization is chosen at build time by a constructor factory in the
creator's params (§3.9), not by the factory itself.

The factory is the single point where later layers attach substitution:
global type overrides, instance type overrides and per-instance
implementation injection. Because no user code calls `new` on a
structural class, adding them changes no user code.

### 3.9 Parameters

There are two ways to parameterize a component. The split is deliberate:
it keeps class (template) parameters to a minimum.

| Kind | Set by | Used for |
|---|---|---|
| **Class parameters**: scalar or struct value parameters, plus type parameters where a payload type is generic | the type name, at compile time | **physical type shape** only: anything that reaches a signal's or bundle's type, such as data and address widths |
| **Params value**: a struct per component, passed at construction | the creator, procedurally, and overrides | **everything dynamic**: number of channels, depths, modes, child parameters, extern parameters, conditional structure |

**Rule.** A value that reaches a signal's type must be a class parameter,
because SV signal types are fixed at compile time. Every other value goes
in the params value.

**Guidance.**
- Keep class parameters few.
- Group a component's or bundle's widths into one struct-valued class
  parameter (a *shape*) rather than a list of scalars, for example
  `class axi_port #(axi_shape_t S = AXI_DFLT)` with
  `fw_input #(bit [S.data_w-1:0])`.
- Use type parameters only where a payload type is truly generic, such as
  `fw_rv_if #(T)`.
- Struct-valued class parameters, packed or unpacked with member defaults,
  were checked in Verilator 5.055 and slang, including member references
  in widths.

**The params value.**
- A component that has params declares the type inside the class as
  `params_t`, an unpacked struct, and a **params function**, `mk_params`,
  with one defaulted argument per field. The function is the one source
  of defaults; the struct members have none. Both are declared in the
  class so they can refer to the class parameters, which constructor
  factories need (below).
- The params function is what makes creation one call when only some
  fields change: `mk_params(.depth(7))` is every default except `depth`.
  An SV struct literal cannot do this, because it must name every member
  and ignores member defaults.
- Every component has params: one without params of its own inherits the
  empty `params_t` and `mk_params()` of `fw_component`.
- A subclass inherits its parent's `params_t` and `mk_params` and
  redeclares neither.
  So every realization of an abstract component takes the same params,
  and a creator's code does not depend on which realization it gets.
- The resolved value is available, read-only, from the start of the
  component's constructor. Writing it is an error; the static front end
  reports it as `FW-E-PARAM-WRITE`.

**Constructor factories.** When a component's *implementation* is chosen
at build time, the params value carries a constructor factory: a typed
handle, `fw_ctor #(B)`, that creates some subclass of `B`.
- The creator gets it from `fw_ctor_of #(B, D)::get()`, where `D` is
  the realization.
- The component calls `params.fifo_h.create(name, this, p)` instead of
  naming a class.
- A handle's default argument in `mk_params` must be a constant, so it
  is `null`.
- The component supplies a **params-initialization function**,
  `init_params`, which runs last in resolution. It sees `fifo_h == null`
  and sets the default realization. It may also fill any other default
  that is not a constant.
- Because handles are ordinary params fields, everything that sets params
  can choose an implementation: the creator, an override from an
  ancestor, or a global override from the test bench. Global factory type
  overrides are still deferred (§1), but they are not needed for this.
- Typed constructor factories, a `create` that takes `B::params_t`, and a
  class-scoped params struct that names `T` in a handle type all compile
  in Verilator 5.055 and slang. A non-null *default* for a handle field
  does not compile, which is why `init_params` sets defaults.
- Named, defaulted arguments to a class-scoped static function
  (`fifo #(T)::mk_params(.depth(7))`) also compile and run in both.

**Resolution.** A component's params value is computed when it is created,
from these sources, lowest precedence first:
1. the defaults of `mk_params`;
2. the value the creator passed, computed procedurally in the creator's
   `build()` from its own params, loop indices and so on;
3. **overrides** registered by ancestors, applied from the nearest
   ancestor to the farthest. The outermost ancestor has the last word,
   so the integrator overrides the block designer;
4. **global overrides**, registered by the test bench or tool before the
   top is created;
5. the component's `init_params`, which fills in defaults that cannot be
   constant, such as null constructor factories. By rule it
   changes only fields that are still null or another sentinel, and it
   never overrides a value set by sources 2–4.

Within one registering component, a later registration wins over an
earlier one. A constructor factory still null after step 5, when the
component then uses it, is an error (`FW-E-PARAM-NULL`).

**Overrides.** An override is registered by a component and applies to its
own subtree. It has three parts:
- **Target.** A path glob, relative to the registering component. `*`
  matches within one path segment, and `**` matches any number of
  segments. For example: `u[*]`, `chain.u[0]`, `**`.
- **Params type.** The override applies only to components whose params
  type is the override's type. This keeps it type-safe, and lets `**` mean
  "every FIFO below here".
- **Action.** Either a *set*, which replaces the whole value, or an
  *edit*, a function from value to value that changes some fields and
  keeps the rest. Edits compose in precedence order: each sees the result
  of the sources below it.

An override must be registered before its target is created. One that
matches a component already created is an error (`FW-E-PARAM-LATE`), not
silently ignored. An override that matches nothing by the end of build
is a warning (`FW-W-PARAM-UNUSED`).

The netlist records each component's resolved params value, and for each
field the source that set it (§3.11).

### 3.10 Diagnostics

Each error has a stable ID (`FW-E-<AREA>-<WHAT>`), a message and the full
name of the object. Conformance compares the IDs, not the message text.
The initial list:

| ID | Condition |
|---|---|
| `FW-E-ELAB-LATE` | object created after build |
| `FW-E-ELAB-NEW` | structural object constructed without the factory |
| `FW-E-PARAM-LATE` | override registered after its target was created |
| `FW-E-PARAM-WRITE` | component writes its params value (static front end) |
| `FW-W-PARAM-UNUSED` | override matched nothing (warning) |
| `FW-E-PARAM-NULL` | a null constructor factory is used |
| `FW-E-PARAM-CTOR` | a constructor factory's type is not a subclass of the expected base |
| `FW-E-NAME-DUP` | duplicate name under one parent |
| `FW-E-NAME-FLAT` | flattened-name collision |
| `FW-E-CONN-PHASE` | connect or tie outside `connect()` |
| `FW-E-CONN-SCOPE` | endpoint outside the connecting component's scope |
| `FW-E-CONN-TYPE` | non-equivalent types, or different bundle types |
| `FW-E-NET-MULTI` | more than one source on a net |
| `FW-E-NET-UNDRIVEN` | a net with sinks but no source |
| `FW-E-IN-OPEN` | unconnected, untied input |
| `FW-E-EXT-PIN` | module pin unmapped or mapped twice |
| `FW-E-EXT-PORT` | extern port mapped to no pin |
| `FW-E-EXT-DIR` / `FW-E-EXT-WIDTH` | pin and port disagree |
| `FW-E-RT-NONE` | no implementation registered |

### 3.11 Elaborated netlist

The netlist is a normalized JSON form of an elaborated design, defined by
`semantics/netlist.schema.json`. It is the conformance artifact: every
implementation's conformance runner produces it, and the suite compares it
with `expect.json`. It is a specification artifact, not a tool format;
emitted RTL does not depend on it.

```json
{
  "top": "fifo_chain",
  "objects": [
    {"path": "top", "kind": "component", "type": "fifo_chain#(bit[7:0])",
     "params": {"n": 2, "depth": 2, "deep_tail": 0, "fifo_h": "rv_fifo#(bit[7:0])"},
     "param_src": {"fifo_h": "init"}},
    {"path": "top.in", "kind": "mirror", "type": "fw_rv_if#(bit[7:0])"},
    {"path": "top.in.valid", "kind": "port", "dir": "in",  "width": 1},
    {"path": "top.u[0]", "kind": "component", "type": "rv_fifo#(bit[7:0])",
     "params": {"depth": 2}, "param_src": {"depth": "creator"},
     "extern": {"module": "fw_rv_fifo", "params": {"WIDTH": 8, "DEPTH": 2},
                "pins": {"in_vld": "in.valid", "clk": "clk"}, "ties": {}, "open": []}}
  ],
  "nets": [
    {"scope": "top", "source": "top.in.valid", "sinks": ["top.u[0].in.valid"]}
  ],
  "diagnostics": []
}
```

Normalization: objects are sorted by path, sinks are sorted, and each net
is listed in the scope where it is formed. A net that crosses a hierarchy
level appears once in each scope.

---

## 4. SV binding

The spec defines the API; every tool implements it. The source in
`fw-hdl-spec/bindings/sv/` is normative for exact declarations; this
section shows the shape and the rules.

### 4.1 Declarations in the spec, bodies in each tool

The API is **declarations only**: classes whose methods are `extern`
prototypes (or `pure virtual`), typedefs, and doc comments. There are no
method bodies in the spec, except in `fw_rv_if`, which is a bundle type
written *with* the API like a user's.

| File | Contents |
|---|---|
| `fw_hdl_api.svh` | Every declaration, one class per included `.svh`. Included inside a package. |
| `fw_hdl_pkg.sv` | `package fw_hdl_pkg; `include "fw_hdl_api.svh" endpackage`, plus an sv-weave include hook (`SV_WEAVE_INCLUDE_fw_hdl_pkg`) used only by the spec's own compile check. |
| `fw_hdl_macros.svh` | The macros' names, arguments and declared members are API; each tool supplies its own expansions. The spec's are the minimum that compiles. |

A tool provides its own package. It includes the spec's declarations
unchanged and supplies an out-of-block body for every `extern` method:

```systemverilog
package fw_hdl_pkg;
    `include "fw_hdl_api.svh"              // the spec's, unchanged
    `include "rt_sv_bodies.svh"            // the tool's: function fw_signal::tie(T value); ... endfunction
endpackage
```

The tool consumes the spec; the spec never names anything of a tool's.

Rules for a tool:
- **Add nothing to API classes.** A tool's state for an object hangs off
  one handle: `fw_object` holds `protected fw_impl_if __fw_impl`, and
  `fw_impl_if` is an empty interface class with no API. The tool stores
  an object of its own class there and downcasts to it. Typed state, such
  as layer 2's value storage, is a parameterized tool class in the same
  slot: the bodies of `fw_signal #(T)` know `T`.
- **`__fw_` names are reserved** for the API and its macros; a macro
  expansion may declare only the members the API lists (§4.6) plus
  `__fw_` names.
- Methods that return a type built from class parameters return a class
  typedef (`this_t`, `base_t`, `ctor_t`), so out-of-block bodies can name
  it: `function fw_mirror::this_t fw_mirror::create(...)`.

What keeps the tools honest is mechanical:
- the spec compiles against **generated default bodies** (each returns
  a default value or does nothing), which is how scenarios and the smoke
  test are compile-checked without any tool. An sv-weave weaver
  (`tools/fw_hdl_bodies.py`) reads the declarations in sv-weave's syntax
  pre-pass and adds the bodies inside `fw_hdl_pkg` as a package include;
  the dfm task `sv-api-compile` outputs the API plus the bodies. Nothing
  generated is checked in;
- an **API check** extracts the declarations a tool compiles and requires
  them to equal the spec's;
- the **conformance scenarios** (§7) check behavior.

The API has only what layer 1 uses. Queries such as names, parents,
children, lookup, directions, widths, kinds and type names are not API:
a tool keeps that information behind `__fw_impl`. They are added when
user code needs them.

### 4.2 The recipe

- **Declare** fields and handles with the API classes: `fw_input #(T)`,
  `fw_mirror #(B)`, `fifo #(T)`.
- **Create** anything with `T::create`. Built-in classes declare it;
  user components get it from `` `fw_component_utils(T) ``.

```systemverilog
fw_input  #(bit)            clk;
fw_mirror #(fw_rv_if #(T))  in;
fifo      #(T)              u;

clk = fw_input  #(bit)::create("clk", this);
in  = fw_mirror #(fw_rv_if #(T))::create("in", this);
u   = fifo #(T)::create("u", this, fifo #(T)::mk_params(.depth(4)));
```

Exceptions, none of them structural objects: the extern map and pin rules
are created by the tool and handed to `extern_map()`; constructor
factories come from `fw_ctor_of #(B, D)::get()`; edit objects
(`fw_param_edit`) use `new()`.

### 4.3 Objects, components and constructor factories

```systemverilog
interface class fw_impl_if; endclass                 // empty: the tool's handle

virtual class fw_object;
    protected fw_impl_if __fw_impl;
endclass

virtual class fw_component extends fw_object;
    typedef struct { bit unused; } params_t;         // empty; a subclass with params declares its own
    extern static function params_t mk_params();
    extern virtual function void build();            // phase hooks; empty by default
    extern virtual function void connect();
    extern function void connect_all(fw_pair_t pairs[]);   // bulk (§4.5)
endclass

interface class fw_ctor #(type B = fw_component);   // constructor factory
    pure virtual function B create(string name, fw_component parent, B::params_t p);
endclass
class fw_ctor_of #(type B = fw_component, type D = B) implements fw_ctor #(B);
    typedef B            base_t;
    typedef fw_ctor #(B) ctor_t;
    extern static  function ctor_t get();            // one instance per (B, D)
    extern virtual function base_t create(string name, fw_component parent, B::params_t p);  // D::create
endclass
```

Constructors take no arguments. `T::create` supplies the name, parent and
params; how is the tool's business, and the netlist must show the result.
A structural object constructed with `new()` is `FW-E-ELAB-NEW`.
`fw_ctor` is an interface class because it is a value in a params struct
that any realization's constructor factory must fit.

### 4.4 Signals, ports and bundles

```systemverilog
virtual class fw_signal_base extends fw_object; endclass   // what an extern map's pin() takes

class fw_signal #(type T = bit) extends fw_signal_base;
    typedef fw_signal #(T) this_t;
    extern static function this_t create(string name, fw_object parent);
    extern function void connect(fw_signal #(T) other);    // compile-time type check
    extern function void tie(T value);
endclass
class fw_input  #(type T = bit) extends fw_signal #(T);    // likewise fw_output, fw_inout
    typedef fw_input #(T) this_t;
    extern static function this_t create(string name, fw_object parent);
endclass

virtual class fw_bundle_base extends fw_object;
    extern virtual function void build();                  // the bundle type creates its members
endclass
class fw_bundle  #(type B = fw_bundle_base) extends B;     // role = INITIATOR
    typedef fw_bundle #(B) this_t;
    extern static function this_t create(string name, fw_object parent);   // then calls build()
    extern function void connect(fw_mirror #(B) other);    // siblings
    extern function void connect_up(fw_bundle #(B) outer); // pass-through: child side calls it
endclass
class fw_mirror  #(type B = fw_bundle_base) extends B; ... endclass  // TARGET; connect(fw_bundle #(B)), connect_up(fw_mirror #(B))
class fw_monitor #(type B = fw_bundle_base) extends B; ... endclass  // MONITOR; connect(B)

virtual class fw_rv_if #(type T = bit) extends fw_bundle_base;      // built-in bundle type
    fw_output #(bit) valid;
    fw_input  #(bit) ready;
    fw_output #(T)   data;
    virtual function void build();
        valid = fw_output #(bit)::create("valid", this);
        ready = fw_input  #(bit)::create("ready", this);
        data  = fw_output #(T)  ::create("data",  this);
    endfunction
endclass
```

`connect` takes `fw_signal #(T)`, so the compiler rejects mismatched value
types at the call site. Directions are checked at resolution, because the
same handle is an input in one scope and a source in another. Arrays of
signals, ports and bundles are made by calling `create` in a loop with
names `name[i]`.

A bundle type is a `virtual class` that extends `fw_bundle_base`, so it
cannot be instantiated without a role, and it creates its members in
`build()`. The roles are mixins: each extends its type parameter, so
`fw_mirror #(fw_rv_if #(bit[7:0])) in;` *is* an `fw_rv_if`, and its
members are reached directly as `in.valid`. The role is part of the static
type: connecting bundles of different types, an initiator straight to an
initiator, or an initiator to a monitor fails to compile. Nested bundles
are members declared with a role: `fw_mirror #(axi_r_if #(...)) r;`.

Class-extends-type-parameter is legal SV (IEEE 1800-2017 §8.26.3, mixins),
and out-of-block bodies of mixin methods work. Both have been checked with
Verilator 5.055 and slang. Before M1 closes, check them on a commercial
simulator. If one rejects mixins, the fallback is a member handle
(`in.b.valid`) with the same semantics.

### 4.5 Bulk connections

`signals.md` asked for connections written as data. `connect_all` is a
method of `fw_component`, valid only in `connect()`:

```systemverilog
typedef fw_object fw_pair_t[2];

function void connect();
    connect_all('{ '{u[0].out, u[1].in},
                   '{u[1].out, out},
                   '{in,       u[0].in} });
endfunction
```

The literal form `'{'{a, b}, ...}` passed as a dynamic array of
`fw_object[2]` was checked in Verilator 5.055 and slang. It loses the
compile-time type check; resolution applies the same checks, with the same
diagnostic IDs.

### 4.6 Creation, parameters and overrides

```systemverilog
class fifo_chain #(type T = bit[7:0]) extends fw_component;
    typedef struct {
        int                      n;
        int                      depth;
        fw_ctor #(fifo_api #(T)) fifo_h;          // null: init_params picks the default
    } params_t;
    static function params_t mk_params(int n = 2, int depth = 2,
                                       fw_ctor #(fifo_api #(T)) fifo_h = null);
        ...                                       // the one source of defaults
    endfunction
    `fw_component_params_init(init_params)       // declares `params`
    `fw_component_utils(fifo_chain #(T))         // declares create()

    static function void init_params(ref params_t p);
        if (p.fifo_h == null) p.fifo_h = fw_ctor_of #(fifo_api #(T), rv_fifo #(T))::get();
    endfunction
    ...
endclass

u = fifo_chain #(T)::create("u", this);                                  // defaults
u = fifo_chain #(T)::create("u", this, fifo_chain #(T)::mk_params(.n(4)));

// Overrides, registered in build() before the targets are created:
fw_param_override #(fifo_chain #(T)::params_t)::set (this, "chain", p);       // replace
fw_param_override #(fifo_api #(T)::params_t)::edit(this, "**", d);           // modify
fw_param_override #(fifo_chain #(T)::params_t)::set (null, "top.**", p);      // global

class deepen extends fw_param_edit #(fifo_api #(bit[7:0])::params_t);
    virtual function params_t apply(params_t p);
        p.depth = 2 * p.depth;
        return p;
    endfunction
endclass
```

The macros (`fw_hdl_macros.svh`) are API by name, arguments and what they
declare; each tool supplies the expansions. They are orthogonal: one pair
is about params, the other about creation.

| Macro | Used in | Declares |
|---|---|---|
| `` `fw_component_utils(T) `` | every concrete component | `static function T create(string name, fw_component parent, params_t p = mk_params())` |
| `` `fw_extern_utils(T, "module") `` | every concrete extern | the same, plus `extern_module()` |
| `` `fw_component_params `` | the class that declares `params_t` | `params_t params`: the resolved value, available from the start of the declaring class's constructor, read-only |
| `` `fw_component_params_init(FN) `` | the same, when it has an init function | as above; `FN(ref params_t)` runs last in resolution |

So an abstract component with params (`fifo_api`) uses only a params
macro, its realizations (`rv_fifo`) use only a creation macro and inherit
the rest, and a concrete component with params (`fifo_chain`) uses both.
Naming the init function in the macro is what lets resolution call it
only when the class has one.

An override applies only to components whose params type is the
override's `P` (§3.9). In layer 1 `create` makes exactly the type asked
for. Type overrides attach inside `create` later, without changing user
code.

### 4.7 Extern

```systemverilog
interface class fw_extern_if;
    pure virtual function string extern_module();             // from `fw_extern_utils
    pure virtual function void   extern_map(fw_extern_map m);
endclass

class fw_extern_map;                                          // created by the tool
    extern function void        param(string name, fw_param_arg value);  // fw_value #(T)::of(v), fw_type #(T)::get()
    extern function void        pin(string name, fw_signal_base s);
    extern function fw_pin_rule prefix(fw_object b, string pre);   // b: a bundle in a role
    extern function void        tie(string name, logic [1023:0] value);
    extern function void        open(string name);
    extern function void        unused(fw_object o);          // an input port or a bundle: no pin
endclass
class fw_pin_rule;
    extern function fw_pin_rule rename(string member, string pin_part);
endclass
```

The map takes object handles for the class side and strings for the
module side. Compared with today's `fw_extern_map`:
- `rv`/`valid`/`level` collapse into `prefix` plus the default rule;
- `fileset` is removed (§3.7);
- slices, packed-pin slots, suffixes and upper-casing are left out until
  a wrapped module needs them;
- clock and reset pins are ordinary `pin()` mappings, or the default
  rule, in layer 1. The domain layer maps them through its own classes,
  not through new map methods (§3.6).

### 4.8 Worked example

The extern wraps `src/rtl/fw_rv_fifo.sv`, whose pins are `clk`, `rst`,
`in_data`, `in_vld`, `in_rdy`, `out_data`, `out_vld` and `out_rdy`. The
full source, with `valid_mon` and the edit, is
`fw-hdl-spec/tests/sv/smoke/smoke_pkg.sv`.

```systemverilog
// The abstract FIFO: ports and params only. Realizations extend it.
virtual class fifo_api #(type T = bit[7:0]) extends fw_component;
    typedef struct { int depth; } params_t;
    static function params_t mk_params(int depth = 2);
        params_t p;
        p.depth = depth;
        return p;
    endfunction
    `fw_component_params

    fw_input  #(bit)            clk, rst;
    fw_mirror #(fw_rv_if #(T))  in;
    fw_bundle #(fw_rv_if #(T))  out;

    virtual function void build();
        clk = fw_input  #(bit)::create("clk", this);
        rst = fw_input  #(bit)::create("rst", this);
        in  = fw_mirror #(fw_rv_if #(T))::create("in",  this);
        out = fw_bundle #(fw_rv_if #(T))::create("out", this);
    endfunction
endclass

// The RTL realization: wraps fw_rv_fifo. It inherits ports and params.
class rv_fifo #(type T = bit[7:0]) extends fifo_api #(T) implements fw_extern_if;
    `fw_extern_utils(rv_fifo #(T), "fw_rv_fifo")

    virtual function void extern_map(fw_extern_map m);
        m.param("WIDTH", fw_value #(int)::of($bits(T)));
        m.param("DEPTH", fw_value #(int)::of(params.depth));
        void'(m.prefix(in,  "in_").rename("valid", "vld").rename("ready", "rdy"));
        void'(m.prefix(out, "out_").rename("valid", "vld").rename("ready", "rdy"));
        // clk, rst, in_data, out_data: default rule
    endfunction
endclass

class fifo_chain #(type T = bit[7:0]) extends fw_component;
    typedef struct {
        int                      n;
        int                      depth;
        bit                      deep_tail;
        fw_ctor #(fifo_api #(T)) fifo_h;               // null: init_params picks rv_fifo
    } params_t;
    static function params_t mk_params(int n = 2, int depth = 2, bit deep_tail = 0,
                                       fw_ctor #(fifo_api #(T)) fifo_h = null);
        params_t p;
        p.n = n; p.depth = depth; p.deep_tail = deep_tail; p.fifo_h = fifo_h;
        return p;
    endfunction
    `fw_component_params_init(init_params)
    `fw_component_utils(fifo_chain #(T))

    static function void init_params(ref params_t p);
        if (p.fifo_h == null) p.fifo_h = fw_ctor_of #(fifo_api #(T), rv_fifo #(T))::get();
    endfunction

    fw_input  #(bit)            clk, rst;
    fw_mirror #(fw_rv_if #(T))  in;
    fw_bundle #(fw_rv_if #(T))  out;
    fifo_api  #(T)              u[];
    valid_mon #(T)              mon;   // wraps fw_valid_check; port p: fw_monitor #(fw_rv_if #(T)),
                                       // p.data unused (the module has no data pin)

    virtual function void build();
        clk = fw_input  #(bit)::create("clk", this);
        rst = fw_input  #(bit)::create("rst", this);
        in  = fw_mirror #(fw_rv_if #(T))::create("in",  this);
        out = fw_bundle #(fw_rv_if #(T))::create("out", this);
        u = new[params.n];
        foreach (u[i])
            u[i] = params.fifo_h.create($sformatf("u[%0d]", i), this,
                fifo_api #(T)::mk_params(.depth(
                    (params.deep_tail && i == params.n - 1) ? 2 * params.depth
                                                            : params.depth)));
        mon = valid_mon #(T)::create("mon", this);
    endfunction

    virtual function void connect();
        u[0].in.connect_up(in);   // pass-through: child mirror to own mirror
        for (int i = 0; i + 1 < params.n; i++) u[i].out.connect(u[i+1].in);
        u[params.n-1].out.connect_up(out);
        mon.p.connect(u[0].out);
        foreach (u[i]) begin u[i].clk.connect(clk); u[i].rst.connect(rst); end
        mon.clk.connect(clk); mon.rst.connect(rst);
        // the domain layer removes the clk/rst lines (§3.6)
    endfunction
endclass

// An integrator overriding one FIFO deep inside the chain:
class soc extends fw_component;
    `fw_component_utils(soc)
    fifo_chain #(bit[31:0]) chain;
    virtual function void build();
        fw_param_override #(fifo_api #(bit[31:0])::params_t)::set(
            this, "chain.u[0]", fifo_api #(bit[31:0])::mk_params(.depth(16)));
        chain = fifo_chain #(bit[31:0])::create("chain", this);
        // ports and connections omitted
    endfunction
endclass
```

Expected emitted Verilog for `fifo_chain` (§6.6). The params fields
become module parameters, and the creator's procedural computation
becomes a parameter expression:

```systemverilog
module fifo_chain #(parameter type T = logic [7:0],
                    parameter int n = 2, parameter int depth = 2, parameter bit deep_tail = 0) (
    input  logic clk, input logic rst,
    input  T     in_data,  input  logic in_valid,  output logic in_ready,
    output T     out_data, output logic out_valid, input  logic out_ready);
    T     c_data [n+1]; logic c_valid [n+1]; logic c_ready [n+1];
    assign c_data[0] = in_data; assign c_valid[0] = in_valid; assign in_ready = c_ready[0];
    for (genvar i = 0; i < n; i++) begin : u
        fw_rv_fifo #(.WIDTH($bits(T)),
                     .DEPTH((deep_tail && i == n - 1) ? 2 * depth : depth)) u (
            .clk(clk), .rst(rst),
            .in_data(c_data[i]),    .in_vld(c_valid[i]),    .in_rdy(c_ready[i]),
            .out_data(c_data[i+1]), .out_vld(c_valid[i+1]), .out_rdy(c_ready[i+1]));
    end
    // mon: fw_valid_check on c_valid[1]/c_ready[1]; outputs: out_* from c_*[n]
endmodule
```

Three points about this example:
- `fifo_h` is not a module parameter. `init_params` chose `rv_fifo`, so
  each `u` instance is the module `fw_rv_fifo` itself, because an extern
  is replaced by its module.
- A creator that set `fifo_h` to another realization would get a separate
  specialization of `fifo_chain` (§6.6).
- In `soc`, the override on `chain.u[0]` cannot be written in terms of
  `fifo_chain`'s own parameters, so `soc` also instantiates a
  specialization of `fifo_chain` (§6.6, specialization rule).

The exact net naming belongs to be-sv. The shape is what M6 must deliver:
one module, a generate loop, array nets, and parameter expressions.

---

## 5. `rt-sv`: reference runtime (elaboration only)

In this layer the reference runtime elaborates in a stock simulator and
produces the netlist. That is enough to:
- prove the injection architecture on a real implementation from day one;
- give SV users elaboration errors in their own simulator;
- act as the second implementation for conformance.

Contents:
- **Its own `fw_hdl_pkg`** (§4.1): the API's declarations, with bodies,
  and its own classes behind `fw_impl_if`.
  - The bodies record objects, connections, ties and overrides, and
    track the phase.
  - A phase walker: build top-down, then connect, then resolve.
  - Net resolution by union-find over `fw_signal_base`, plus bundle
    expansion into member connections.
  - Every check in §3.5 and §3.6 that does not need a module header.
  - A netlist writer (§3.11), triggered by `+fw_netlist=<path>`.
- **`fw_elab #(type T)` module.**
  - Creates `T` with `T::create("top", null)`, runs elaboration
    and writes the netlist.
  - It ends with a non-zero exit status if there were errors.
- **`flow.yaml`.** Its `fw_hdl_pkg` fileset, which a user compiles in
  place of the spec's `sv-api`, plus an API-check task and a conformance-runner task that
  builds `fw_elab #(top)` per scenario under Verilator.

Not here yet: kernels, settle, `fw_root`, pin bridges. They come with
layer 2. Today's `src/fw_root.sv` and `src/sync/*` are the source material
for that layer.

---

## 6. `fe-sv`: static elaboration to Zuspec IR

### 6.1 Pipeline

```
user SV + fw_hdl_pkg sources
   │ pyslang (via zuspec-fe-sv)
   ▼
interpret construct/build/connect      ← the API's methods as Python intrinsics
   ▼
elaborated object graph (Python)  ──►  netlist JSON (conformance runner)
   ▼
Zuspec IR (ir-core): DataTypeComponent per class, DataTypeExtern per extern
   ▼  Zuspec passes: bundle flatten, net resolution (Z1–Z3)
zuspec-be-sv  ──►  Verilog + filelist (generated modules + extern RTL filesets)
```

fe-sv stops at Zuspec IR, following the project rule. Flattening and
emission are Zuspec passes, so other Zuspec front ends reuse them.

### 6.2 Interpreting with intrinsics

fe-sv uses the class interpreter, which is ported from
`python/fw/hdl/fe/elab/interp.py` into `zuspec-fe-sv` (§2), to run
constructors, `build()`, `connect()` and `extern_map()` on the real
`fw_hdl_pkg` declarations from the spec. The API's methods are the
intrinsics: when the interpreted code calls one, the interpreter
dispatches to Python objects (`FeRt`) that do what rt-sv's bodies do, in
Python. fe-sv's copy of the package is the spec's, so it passes the API
check trivially.

The front end therefore needs no special cases on base-class internals:
the base classes are executed, not pattern-matched. This is migration
step 3 of project-architecture.md, done from the start.

fe-sv implements the spec's `domains` and `protocols` features
(protocol registry and queries, API endpoints and sockets, configuration
publishers and consumers) with the reference runtime's checks, including
domain crossings over API and configuration bindings
(`domains.check_binds`). On top of those, fe-sv checks extern maps
against module headers (§3.7). It gets module headers from the RTL
filesets passed to the task. The pin-check logic of today's
`python/fw/hdl/extern.py` (`check`, `header`) is ported, not imported,
because its record format changes.

### 6.3 IR mapping

| fw-hdl | Zuspec IR |
|---|---|
| component class (or specialization) | `DataTypeComponent`, with `template_params` from the class parameters and the flattened params fields (§6.6) |
| a child's resolved params value | instance parameter overrides: values, or expressions over the parent's parameters and genvars |
| port | `FieldInOut` (`is_out`, `is_inout`), `datatype` from `T` |
| local signal | `Field` |
| bundle / mirror / monitor field | bundle-typed field with a role (Z1) |
| child | instance field of the child's type |
| connection | `Bind` in the scope's `bind_map` |
| tie | `Bind` to a constant expression |
| extern | `DataTypeExtern`, with `extern_name` = module and a pin map (Z2) |
| packed struct or enum `T` | a packed `DataTypeStruct` or a `DataTypeEnum` in `type_m`, referred to by `DataTypeRef`; declared once in the generated types package, or, when the extern RTL declares it, referred to by its own name (§6.5) |

**IR shapes, as built (zuspec-ir-core).** fe-sv produces *structural* IR;
Z3 lowers it to a *flat* form that be-sv emits.

Structural (fe-sv output):
- A component specialization is a `DataTypeComponent` named by its
  created type (`fifo_chain#(bit[7:0])`; one per distinct params value
  until M6). Its fields, in creation order:
  - a port is a `FieldInOut`, a local signal a `Field`; `datatype` is a
    `DataTypeInt` or a `DataTypeRef` to a packed struct or enum (below);
  - a bundle in a role is a `Field` whose `datatype` is a
    `DataTypeRef` to a `DataTypeBundle` and whose `role` is a
    `BundleRole` (`INITIATOR`, `MIRROR`, `MONITOR`);
  - a child is a `Field` whose `datatype` is a `DataTypeRef` to the
    child's component or extern type.
- Array elements are fields named `u[0]`, `p[1]`.
- A `DataTypeBundle` holds its members as fields: `FieldInOut` with the
  initiator's direction, or nested bundle fields with a role.
- A connection is a `Bind` in `bind_map`. Each side is an
  `ExprHierarchical` path of field names from the scope
  (`u[0].out`, `in.valid`). The order of the sides carries no meaning,
  and bundle-level binds are kept as written. A tie is a `Bind` whose
  `rhs` is an `ExprConstant` with its width.
- An extern is a `DataTypeExtern` with ports and bundles as fields,
  `extern_name` (the module), `extern_params` (`{name: Expr}`), and
  `pins`: one `ExternPin` per module pin, in module order. Each pin has
  exactly one of `path` (field names from the extern), `tie` or `open`.
  An open pin has `datatype`, from the module header: a `DataTypeInt` as
  wide as the pin (a `width_expr` over the extern's parameters when the
  width follows them), or the value of the module type parameter that
  types it; None without RTL to read.
- Types (M8):
  - A `DataTypeInt` has `four_state`: False for `bit`, True for `logic`,
    as written; None (unstated) from producers that do not say.
  - A packed struct is a `DataTypeStruct` with `packed` set and its
    members as `Field`s, in declaration order (first member most
    significant). An enum is a `DataTypeEnum`: `items` (label -> value),
    `width`, and `base_type` (the encoding `DataTypeInt`). A packed array
    or packed union member is a `DataTypeInt` of its width.
  - Each is in `type_m` once, keyed by its package-qualified name
    (`pt_pkg::tag_t`); an anonymous one, or a second, different type of
    the same name, gets a key of its own. Ports, nets, members, type
    parameter values and `inst_params` refer to it with a `DataTypeRef`.
  - `extern_name` is set on one the extern RTL also declares: a typedef in
    a package of the RTL filesets, with the same structure (an enum's
    labels and values, a struct's members, widths and states). A back end
    refers to it by that name and does not declare it. The same name
    declared differently is `FW-E-EXT-TYPE`.

Flat (Z3 output, be-sv input):
- Every generated component has only `FieldInOut` ports and `Field` nets
  of flattened names (`out_valid`, `u_0_out_valid`).
- Children are `module_instances`: `ModuleInstance(module, name,
  parameters, connections)`. A `PortConnection.signal` is a net name, an
  `ExprConstant` tie, or `None` for an open extern pin whose type is not
  known (no RTL was read).
- An output nothing reads (a child's unconnected output, an extern pin
  mapped `open`) is connected to a net of its own, of the pin's type,
  named `<instance>_<pin>_unused` (`slice_m_axis_tlast_unused`; `_1`, ...
  if taken). An instance array's is an array net, indexed per instance.
- Port, net and type parameter types are unchanged: packed struct and enum
  `DataTypeRef`s stay as they are, and `$bits(T)` of one folds to its
  width.
- A port driven straight from a port or a constant is a `NetAssign` in
  `net_assigns`.
- `bind_map` is empty.
- `DataTypeExtern` and `DataTypeBundle` types are never emitted.

Parameterized (Z5, §6.6), in both forms:
- A component, extern or bundle type mapped generally has
  `template_params`: `TemplateParamType` for an integral type parameter,
  `TemplateParamValue` for a value class parameter, for each field of a
  struct-valued one (a shape, flattened: `S_data_w`) and for each params
  field. Inside the type a value parameter is `ExprRefParam(name)`, a type
  parameter `DataTypeRef(name)`.
- A port's type written over parameters is a `DataTypeInt` whose
  `width_expr` is an expression of them (`bits` is its value here).
- A child or bundle field gives its type's parameters in `inst_params`:
  expressions over the enclosing type's parameters and genvars (an
  `ExprRefLocal`), or `DataType`s for type parameters.
- An array of children, ports or bundles made in a loop over parameters
  is one field whose `datatype` is a `DataTypeArray` with `size_expr`; a
  child array has `index_var`, the genvar its `inst_params` use. A port
  or bundle array is a `FieldInOut` or a bundle `Field` (with `role`) of a
  `DataTypeArray`.
- A path element may have a `subscript`: the element of an own array
  (`in[i].valid`), of a child array (`u[i+1].in`), or of a child's port
  or bundle array (`x.in[i]`, one level below the child).

Structural only:
- `generates` holds `GenerateFor` (connections made in a loop) and
  `GenerateIf` (`cond`, `items`, `orelse`) blocks of `Bind`s and nested
  blocks. A `GenerateIf` arm may also hold child `Field`s (single or
  arrays): children that exist only in that arm. The same name may be
  declared in both arms of one `GenerateIf` (a different type in each).
  Connections to such a child are made in its arm or one inside it.

Flat only:
- Ports of a port or bundle array are unpacked arrays (`input T in_data
  [n]`); nets of a child array or of a child's array ports are array nets.
- `generates` holds the instance arrays (a `GenerateFor` labelled with the
  field's name around one `ModuleInstance`) and the blocks of `NetAssign`s.
  A child declared in a `GenerateIf` arm has its nets (`Field`s) and its
  instance in that arm's block, before the arm's assigns.

### 6.4 Zuspec work items

These belong in Zuspec, not fe-sv (AGENTS.md: prefer representing and
manipulating in Zuspec):

| ID | Item | Where |
|---|---|---|
| Z1 | A bundle type and a role (initiator, mirror, monitor) on fields, matching the `bundle`/`mirror`/`monitor` field kinds zuspec-dataclasses already has | ir-core |
| Z2 | Extern pin map on `DataTypeExtern`: pin → field path or slice or slot, ties, opens, parameter expressions | ir-core |
| Z3 | Structural passes: flatten bundles to member ports (with `_` names); resolve `bind_map` into nets, `assign`s and instance connections. First check what `zuspec-be-sv` already does with `bind_map` (generator.py:171, :198) and `module_instances` (:1007). | zuspec-synth or be-sv |
| Z4 | A generic SV class-subset interpreter, ported from `python/fw/hdl/fe/elab/interp.py` (D2) | zuspec-fe-sv |
| Z5 | Instance arrays and generate loops for parameterized structure (§6.6) | ir-core, be-sv |

### 6.5 Output

- **Verilog.** One file per generated module, plus a types package if
  one is needed.
- **Types package.** The packed structs and enums the generated modules
  use (ports, nets, type parameters, through struct members too), each
  declared once, dependencies first, in `<top>_types_pkg`
  (`<top>_types_pkg.sv`), `<top>` the emitted top module's name. A type
  keeps its own name there (`tag_t`); two of the same name are told apart
  by their scope (`q_pkg__tag_t`). Generated code refers to a type as
  `<top>_types_pkg::tag_t`, never by importing the package. A type the
  extern RTL declares (§6.3: same package-qualified name, same structure)
  is not declared again: generated code refers to the RTL's declaration
  (`prm_pkg::cfg_t`), since a copy is a different type, and connecting it
  to an RTL port of the original is a type mismatch in strict tools. A
  struct of the package may hold an RTL type as a member. With no extern
  RTL, every type is declared in the package.
- **Two- and four-state.** Ports and nets of an integral type are
  `logic`, whatever the class wrote: signals between modules carry X and Z
  in simulation, and the hardware is the same. A type the user wrote is
  passed as written: a type parameter's default and override
  (`.data_t(bit [11:0])`, `parameter type T = bit [7:0]`), a value
  parameter's type (`parameter bit [3:0] K`), a member of a generated
  struct, an enum's base type. A port typed by a type parameter or a
  struct therefore has the user's type, two-state if the user's is: the
  type can reach an extern's type parameter, which must get exactly what
  was written.
- **Open pins.** An output nothing reads is connected to an `_unused` net
  of its type (§6.3), not left empty. Every pin of every instance is then
  connected, the intent is in the name, and lint tools need no waiver:
  Verilator's default `--unused-regexp` (`*unused*`) exempts such nets
  from `UNUSEDSIGNAL`, so `verilator -Wall` is clean without a pragma.
  Only an open pin of an extern whose RTL was not read (type unknown) is
  an empty `.pin()`, which `-Wall` reports as `PINCONNECTEMPTY`.
- **Filelist.** The extern RTL filesets passed in, then the types package,
  then the generated modules, each after the modules it instantiates. This
  is what "simulating Verilog" means here: a user's testbench instantiates
  the top module and compiles the filelist.

`fw-hdl-fe-sv/examples/packed_types` shows all of this: fw-hdl's own
`pri_e` and `tag_t` (holding the RTL's `op_e`) through a generic `pass`,
the RTL's `cmd_t` on the wrapped `pt_acc`'s port, and its open debug pin,
whose width follows `W` (`logic [($clog2(W)+1)-1:0] a_nops_unused`).
Emitted, it is lint-clean under `verilator -Wall` and matches a model in
simulation at W = 5, 8, 12 (`tests/e2e/test_packed_types.py`).

### 6.6 Parameterized emission

Following the existing rule for sync lowering, generated RTL keeps the
classes' parameters: **one module per class**, not one per
specialization.
- A value or type class parameter that reaches structure becomes a
  module parameter. A struct-valued class parameter (a shape) is
  flattened like the params value: `S.data_w` becomes `S_data_w`, and
  port widths are written over it, e.g. `logic [S_data_w-1:0]`.
- Each field of the params struct becomes a scalar module parameter,
  named after the field, with nested struct fields joined by `_`. Its
  default is the struct member's default. Flattening is used because
  struct-typed module parameters are unevenly supported by tools.
- The value a creator computes for a child, from its own params and loop
  indices, becomes a parameter expression on the child instance.
- **Constructor-factory fields are not module parameters.** They choose
  which module is instantiated, and Verilog cannot parameterize that.
  - The module emitted under the class's own name uses the realizations
    `init_params` picks by default.
  - Each other combination of realizations gets its own specialization.
  - Netlists and diagnostics name a handle by the type it creates.
  - Emitting `generate case` over the realizations a design actually
    uses is a possible later refinement.
- Child arrays created in a loop bounded by a parameter become a generate
  loop.
- `if` on parameters becomes a generate `if`.
- Extern parameter values computed from class parameters become parameter
  expressions.

The **structural subset** that can be emitted in this form is:
- loops bounded by parameter expressions;
- conditions on parameters;
- constant functions of parameters;
- no data-dependent structure.

**Specialization rule.** A module is emitted per specialization when
either of these holds:
- its `build()`/`connect()` leaves the structural subset;
- a child's resolved params cannot be written as an expression over the
  module's own parameters and genvars. This typically happens with an
  override registered by a farther ancestor, such as `soc` overriding
  `chain.u[0]`.

A specialized module is emitted with an informational diagnostic naming
the construct that forced it. Passing such values down as extra
parameters is a possible later refinement. A task option (`require_param: true`) turns that
into an error.

M4 and M5 emit per specialization, to bring the pipeline up. M6 delivers
parameterized emission and closes the layer. The analysis is the
interpreter run symbolically over parameters, as `fe/elab/sync_param.py`
already does for leaf classes. `sync_param.py`'s composite path ("nested
composites are not lowered yet", `sync_param.py:891`) is the gap this
closes.

**As built.** The tracing lives in zuspec-fe-sv
(`zuspec.fe.sv.interp.trace`); fe-sv supplies the leaves and the policy.
- Class parameters are traced through the `symbolic_param` intrinsic: the
  running component's (or, while its `build()` runs, bundle's) value
  parameters are `Sym`s over their leaves, a shape's members read as
  `ExprAttribute`s of its leaf, which fe-sv resolves to the flattened
  field (`S.data_w` -> `S_data_w`). A base class's parameters are what
  its `extends` clause passes; another class's, in a static call that
  names it (`wfifo #(W)::mk_params()`, a `mk_params` default computed from
  `W`), what that call passes; a `localparam` is traced through its
  initializer.
- Types are traced as written, since the compiler folds class parameters
  away: `SynTracer` reads the class arguments at the creation site
  (`fw_input #(bit [W-1:0])::create`, `wfifo #(S.data_w)::create`, a
  typedef by its own declaration).
- A type parameter's module default is the class's declared default
  (`pass #(type T = bit [7:0])` gives `parameter type T = bit [7:0]`), so
  `pass #(tag_t)` and `pass #(pri_e)` are one module. (Until M8(b) the
  lookup failed silently and the default was the first specialization's
  type, so such classes were split into `pass`, `pass__1`, ....)
- Branch arms: the run at the elaborated values takes one arm of each
  `if` on parameters. When the other arm has effects (a call, `new`, or an
  assignment), the component's class is elaborated again on its own with
  the same params value, assuming the condition has its other value
  (every `if` on that condition, or its negation, takes the other arm,
  through the `ctl_force` intrinsic). The runs are merged by construct;
  anything outside the arms must be the same in every run. An arm that
  cannot be elaborated at the values seen (an index out of range, an input
  left open) makes the component a specialization, with the diagnostic
  naming the branch.
- Still outside the subset (specialized, `FW-I-EMIT-SPEC` naming why): a
  `case`, `while` or irregular loop on parameters; a child, port or bundle
  under an `if` in a loop, or a port under an `if`; a loop over parameters
  that runs no iteration at the elaborated values; arrays of arrays; a
  connection to a conditional child from a loop; a child created through a
  constructor factory whose value class parameters depend on ours; a
  struct-valued class argument built from parameters (`'{data_w: W, ...}`);
  a child's class parameter left to a default computed from the others it
  is passed (`c #(int A, int B = A*2)` created as `c #(W)`); an extern
  whose open pin's width follows its parameters in a form the header
  reader does not translate (it reads literals, parameter names,
  `+ - * / % << >> **`, unary minus and `$clog2`, in `[hi:0]` ranges).

### 6.7 dfm tasks (`fw.hdl.fe.sv`)

| Task | In | Out |
|---|---|---|
| `Elaborate` | SV sources (directly or passed on by `Scan`, with its `fwHdlScan`), top class and parameters, extern RTL filesets | Zuspec IR bundle (`.zir`), netlist JSON |
| `EmitSV` | `.zir` | Verilog and filelist, by composing the Zuspec be-sv task (or adding one there if it doesn't exist) |
| `Scan` *(added 2026-11-15, built 2026-11-16)* | SV sources | `scan.json` (the netlist-form `protocols` table) and a Zuspec IR bundle (`scan.zir`: each protocol's API classes and the types they use), as a `fwHdlScan` FileSet; the sources are passed on; no netlist |
| `GenKit` *(built 2026-11-16)* | a protocol kit's SV sources | `<core pkg>_gen_pkg.sv` (the classes derived from the kit's APIs, `fw.hdl.gen.gen_kit`) as `systemVerilogSource`; the sources are passed on; re-runs when the generators change (`GEN_VERSION`) |

**Two modes.** fe-sv does two jobs. Layer 1 needed, and built, only the
second:
- **Scan:** parse a collection of SV, map its types to IR, and find the
  fw-hdl types in it.
- **Elaborate:** elaborate a given specification from a top class.

`Scan` was added by
[core-protocol-kit-prep.md](core-protocol-kit-prep.md) (§7, Q-A). Its kit
stage reads a protocol kit's sources and generates the derived classes
from the types it finds. How `Scan` works:
- **Type mapping** uses zuspec-fe-sv's `SVMapper`, which maps classes,
  structs and methods from parsed source without elaborating them.
- **fw-hdl types** are found by their registration macros:
  - components and extern wrappers (`` `fw_component_utils ``,
    `` `fw_extern_utils ``);
  - domain kinds (`` `fw_domain_kind_utils ``);
  - bundles;
  - protocols and their parts (`` `fw_protocol_utils ``,
    `` `fw_bundle_protocol ``, `` `fw_xtor_utils ``).
- **Registrations** are evaluated by the interpreter as intrinsics (§6.2),
  as `build()` is, but no component is constructed.
- **`Elaborate` takes an optional input:** the `fwHdlScan` FileSet of a
  `Scan` upstream, with the sources it passes on, plus a choice of top.
  The sources are still compiled again (a scan holds no elaboration
  state); the scan is checked against the elaborated `protocols` table,
  and a protocol whose declaration, bundles or converters differ is
  `FW-E-SCAN-STALE`. Scan then Elaborate gives the same netlist and IR as
  Elaborate alone.
- **Not in the scan yet:** hubs' `cfg_t`, `xfer_time` and `mismatch`, and
  their IR; hubs exist only after elaboration.

---

## 7. Conformance and tests

| Level | What | Runs against |
|---|---|---|
| Conformance | `fw-hdl-spec/conformance/<scenario>`. Each scenario is `top.sv` plus the expected netlist or expected diagnostic IDs. | rt-sv (Verilator) and fe-sv. Both must pass every scenario. |
| fe-sv unit | IR mapping, header checks, symbolic parameters | pytest |
| End to end | the §1 acceptance design: generate, `verilator -Wall`, simulate against a hand-wired reference, yosys read | pytest + dfm |

Initial scenarios, about 25. Each one names its diagnostic where it has
one:
- naming;
- late creation;
- each connection-table row, legal and illegal;
- bundle roles, nesting, and a mirror inside a mirror;
- monitor taps;
- multi-driver and undriven nets;
- open inputs and ties;
- type mismatch;
- arrays;
- the extern default rule, prefix, rename, slot, tie and open;
- creation without the factory;
- a struct-valued shape class parameter driving port widths;
- params defaults, creator values, and each override form and precedence
  level;
- late and unused overrides;
- constructor factories: the `init_params` default, a creator's choice,
  an override's choice, a null-use error, and a base-type mismatch.

Extern header checks run only on fe-sv. The scenario metadata marks them
`static-only`.

---

## 8. Relationship to existing code

| Existing | Becomes | When |
|---|---|---|
| `src/fw_component.svh` (hierarchy and naming parts) | `fw_object`, `fw_component` (data only) | L1 |
| `src/fw_component.svh` (phases, reset supervision, bind-map dump) | rt-sv's `fw_hdl_pkg` bodies (phases, netlist); the rest in later layers | L1, L2 |
| `src/fw_factory.svh`, `fw_view_ctx.svh` | reference for factory substitution (new `fw_factory` written for L1) | substitution layer |
| `src/fw_component_param.svh`, `` `fw_component_obj_param_utils `` | params value as a struct, with overrides | L1 |
| `src/sync/fw_sig*.svh`, `fw_sync_net.svh` | `fw_signal` (API); storage and nets in rt-sv | L2 |
| `src/sync/fw_rv_sp_in/out`, `fw_rv_sig` | `fw_mirror`/`fw_bundle #(fw_rv_if #(T))` | L1 (structure), L2 (behavior) |
| fw_proto `fw_sp_base`, `fw_rv_ch` | protocol kits declare bundle types | when `fw-proto-axi` moves |
| `src/fw_extern.svh` | `fw_extern_if`, `fw_extern_map` (handles, default rule, no fileset) | L1 |
| `python/fw/hdl/extern.py` | fe-sv extern check (ported) | L1 |
| `python/fw/hdl/fe/elab/hier.py` | fe-sv `FeRt` (rewritten against the API's methods, §4.1) | L1 |
| `fe/parser.py`, `fe/elab/interp.py` | ported to `zuspec-fe-sv` (Z4) | L1 |
| `src/fw_domain_port.svh`, `fw_clock_domain*.svh`, `fw_reset_*.svh`, `fw_domains.svh` | reference for the domain layer (domain association, slots, sources) | domains |
| `emit/pins.py` (text pin shells) | not needed: bundles are flattened by Z3 | retire after L1 |
| `src/fw_root.sv`, `fw_rv_pin_*`, `src/sync/*` kernel | rt-sv simulation runtime | L2 |
| `src/fw_port.svh`, `fw_export.svh`, `fw_socket.svh` | transaction-level layer | L3 |

Old tests are reference too and are not run. A test is ported when the
layer that covers it lands. The `tests/xls/test_extern.py` designs, minus
their XLS child, are good seeds for the layer-1 end-to-end tests.

---

## 9. Work plan

Each step ends with its exit criterion met. Update §0 as steps finish.

- **M0. Scaffolding.**
  - Lay out the three repos (§2), each with its `ivpm.yaml` and
    `flow.yaml`, plus `pyproject.toml` for the two implementations.
    Install the Python packages editable in this repo's environment.
  - Take the old code off the compile: the root `flow.yaml`,
    `pyproject.toml` and pytest configuration (§2).
  - Add the dependency lint (§2).
  - *Exit:* an empty `fw_hdl_pkg` compiles under Verilator from the spec
    repo's own fileset; `import fw.hdl.fe.sv` and `import fw.hdl.rt.sv`
    both work; nothing from `src/`
    or `python/` is on any fileset or `sys.path`; the lint runs.
- **M1. Spec API and semantics.**
  - The §4 declarations, with trivial bodies; the spec lint (trivial
    bodies only) and the API check (a tool's declarations equal the
    spec's, §4.1).
  - `semantics/*.md` from §3, and `netlist.schema.json`.
  - About 25 conformance scenarios with expected outputs, written by hand.
  - Mixins and bulk literals checked on one commercial simulator, if one
    is available.
  - *Exit:* every scenario's `top.sv` compiles against `fw_hdl_pkg`.
- **M2. rt-sv.**
  - rt-sv's `fw_hdl_pkg` bodies, `fw_elab`, the netlist writer and the conformance runner.
  - *Exit:* every non-`static-only` scenario passes under Verilator.
- **M3. fe-sv to netlist.**
  - Z4 (the interpreter port), `FeRt` intrinsics, the netlist writer, and the
    extern header check.
  - *Exit:* every scenario passes on fe-sv, and the netlists match rt-sv's
    byte for byte after normalization.
- **M4. IR and emission (per specialization).**
  - The §6.3 mapping and Zuspec Z1 and Z3.
  - *Exit:* externs aside, the acceptance design's hierarchy of
    pass-throughs, bundles and ties emits Verilog that passes
    `verilator -Wall`.
- **M5. Extern end to end.**
  - Z2, extern emission and the filelist.
  - *Exit:* the acceptance design simulates against the hand-wired
    reference.
- **M6. Parameterized emission.**
  - Z5, symbolic build analysis, and `require_param`.
  - *Exit:* `fifo_chain` emits as one parameterized module, and
    simulates at two values of `N`.
- **M7. dfm tasks and user docs.**
  - The `fw.hdl.fe.sv` tasks, plus a user guide page for wrapping and
    assembling.
  - *Exit:* the acceptance test runs through dfm alone.

---

## 10. Open questions

Each has a recommendation. None blocks M0.

1. **Hierarchical connections (§3.5).**
   *Recommendation:* keep them forbidden. They break one-module-per-class
   emission. Pass-throughs cover the need.
2. **Mixin portability (§4.4).** The design depends on class-extends-type-
   parameter. It is confirmed on Verilator and slang. A commercial
   simulator still needs checking, and the member-handle fallback is
   documented.
   Partial finding before the check was deferred (2026-11-15): Vivado
   xsim 2024.1 rejects `B::params_t` (type parameter on the left of `::`)
   as an argument type in `fw_ctor::create`/`fw_ctor_of::create`
   (VRFC 10-2989); a class-local `typedef B::params_t` works around it.
   DSim's compile-only `dvlcom` accepts the pattern.
3. **Bundle emission.** Flattened ports are the only form in layer 1,
   because they work with every tool and every existing RTL.
   *Recommendation:* add SV `interface` or struct-port emission later, as
   a be-sv option.
4. **Signal value storage (layer 2).** The SystemC-style request-update
   outline in §3.3 is a placeholder. Confirm it when layer 2 is designed;
   layer 1 only commits to the API.
