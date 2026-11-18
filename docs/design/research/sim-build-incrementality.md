# Incremental builds for compiled fw-hdl simulation

Research note, 2026-11-18. Question: when fw-hdl is lowered to optimized
C/C++, how do we get good incremental builds, and a dial between "optimize
this subsystem as a whole" and "compile each component once and reuse it"?
What does the shape of fw-hdl code give us for free, and what should we
commit to (e.g. no hierarchical references)?

§6 covers saving parameterized class IR so the front end and codegen don't
redo per-class work. Sources are listed in §7. Items marked **[unverified]** came from memory or
could not be checked against a primary source.

## User benefit

1. **Edit one component and rebuild one component.** Changing a leaf's body
   recompiles that class only. Its parents relink, and recompile only if the
   leaf's boundary summary (§4.2) changed.
2. **Library IP compiles once per parameterization and is cached.** This
   holds across tests, across users (shared cache) and across designs.
3. **Speed is a build setting, not a source edit.** The same design source
   builds "fast to compile" for the edit loop and "fast to run" for
   regressions. The tool picks per-component defaults, and overrides go in
   the flow, not in the design.
4. **Elaboration time follows the code you wrote, not the instance count.**
   Library classes are loaded from saved, parameterized IR and stand in for
   their instances without running their `build()` (§6).
5. **Ordinary fw-hdl code already meets the reuse rules.** The things other
   tools must ban or pre-declare at a boundary (XMRs, `defparam`, `bind`,
   late construction) are already illegal in fw-hdl.

## 1. What others do

### 1.1 Every reuse boundary has the same contract

| System | Unit | Boundary rules |
|---|---|---|
| Verilator `--hierarchical` / `hier_block` | Module, one library per unique parameter set | No dotted refs into the block except the parent's port refs. No modports on the boundary. Generated clocks "may not work". No `defparam`. Type params only recently supported. |
| VCS precompiled IP / partition compile | Module, package, program | XMRs only with `-allxmr`. `defparam`, `bind`, timescale or `` `ifdef `` changes, and package edits force recompile. |
| Questa PDU (`vopt -pdu`, `qrun -makepdu`) | Preoptimized design unit | Optimizes inside the unit, not across it. Hierarchical refs and `+acc` reduce inlining. |
| Xcelium MSIE | Primary / incremental snapshot | Anything the incremental part reaches inside the primary (XMR targets, probes) must be declared when the primary is built. |
| Bluespec `(* synthesize *)` | Module, compiled to a `.ba` file | Concrete interface (no polymorphic or function params **[unverified]**). The scheduler sees only per-method ordering annotations. |
| Switchboard (Zero ASIC) | Whole separately built simulator | Latency-insensitive queues only. Total reuse, no cycle-exact coupling. |

The common pattern:
- no cross-references through the boundary;
- parameters fixed per compiled artifact;
- no elaboration-time back-doors such as `defparam` or `bind`;
- clocks handled explicitly;
- a **summary** at the boundary that lets an outer scheduler order calls into
  the unit without seeing its contents.

### 1.2 Boundaries cost runtime. Nobody publishes how much.

- Verilator docs: hierarchical mode is "likely not as fast as flat
  Verilation, in which all modules are globally scheduled".
- Siemens: a PDU "does not improve simulation run-time compared to the
  standard vopt flow".
- Verilator #2562: per-block thread pools made runtime **11x worse** before
  blocks were forced to one thread. The cost was in scheduling at the
  boundary, not the code.
- Verilator #6748: a 30M-signal design with dozens of hier blocks, on 256
  cores, ran at 52–100 cycles/s. Estimating per-block cost for the scheduler
  gave +28%.
- I found no controlled study of flat vs hierarchical runtime on the same
  design.

### 1.3 Build-time gains are real and come from deduplication

- snax_cluster PR #672 marked two leaf modules as hier blocks (1,024 and
  3,584 instances). Cold build went from ~1000–1200 s to ~330–360 s, and warm
  rebuild from 295 s to 191 s, on 24 cores. Simulation output was identical.
- The gain comes from **translating a module once instead of once per
  instance**. Flat Verilator emits code per instance. Its `dedup` pass only
  merges trivial blocks; the ASPLOS'24 paper measured almost no effect from
  `-fno-dedup`.
- Verilator's other build options: `--output-split` (better C++ parallelism
  and ccache hits), `--inline-mult` (inlining vs compile time), and a fixed
  `--protect-key` (otherwise ccache thrashes).

### 1.4 The fastest simulators flatten

ESSENT, Arcilator ("hierarchy is purely cosmetic"), GSIM (7.3x Verilator on
XiangShan, 19.9x on Rocket), RepCut (27x on 24 threads, 3.8% duplicated
logic), Khronos and Parendi all build one global graph, then partition and
schedule it. Their speed comes from global scheduling and activity gating,
both of which require seeing everything.

### 1.5 Wang, Nijssen, Beamer, ASPLOS'24 ("Don't Repeat Yourself")

This is the best-documented middle ground.

**Mechanism:**
1. Pick the repeated module with the largest instances × size.
2. Partition one instance and apply the same partitioning to every copy.
3. Partitions on each copy's **I/O edge** would create cycles in the global
   graph. Dissolve them and re-partition them with the parent.
4. **Interior** partitions become one shared function over a per-instance
   state struct.
5. Schedule all copies of a partition back to back so the shared code stays
   hot in the instruction cache.

**Cost:** a "dedup tax" of +12.4% instructions from indirection, which
blocks constant-address optimization.

**Result:**
- Dual-core designs ran at 0.85–0.89x: the tax outweighs the benefit.
- At 4–8 cores it reaches up to 1.95x, and 2.09x throughput for parallel
  runs. MegaBoom-8C, which Verilator fails to compile, works.
- Partitioning time drops to 17.6% of ESSENT's.

The point: large full-cycle models are bound by the instruction cache and
last-level cache, so code sharing pays off once there is enough repetition.

### 1.6 Software analogies that carry over

- **ThinLTO.** Compile each module with a small summary. Run a fast serial
  whole-program pass over the summaries only. Import a few functions across
  modules for inlining. The result builds like non-LTO and runs close to
  full LTO. This is the model for us: per-class object code plus a summary,
  a global scheduler that reads only summaries, and selective inlining as
  the dial.
- **Monomorphization vs `dyn`.** One copy per specialization is fast to run
  but costs code size and compile time. One generic copy over indirection is
  small but pays on every access. The "dedup tax" is the hardware form of
  this trade-off.
- **Swift resilience (`@inlinable` / `@frozen`).** A boundary is opaque
  unless the author opts in to exposing internals. Opting in makes those
  internals part of the contract, so dependents recompile when they change.
  This is the right semantics for an "inlinable" component. In fw-hdl the
  build config should make that choice, not the source.

## 2. What fw-hdl's shape gives us

From `packages/fw-hdl-spec/semantics/*.md`, `core-layer1.md` and
`core-domains.md`.

**[SPEC]** means a normative rule today; **[IMPL]** means current tool
behaviour only; **[NONE]** means it does not exist yet.

### 2.1 Guaranteed by construction [SPEC]

| Property | Where | What it buys a C lowering |
|---|---|---|
| Connections are own-scope plus direct children's ports only (`FW-E-CONN-SCOPE`). There is no XMR netlist. | `semantics/connections.md:3-13` | The netlist half of the "no hierarchical references" boundary rule already holds everywhere. |
| Structure is frozen after elaboration (`FW-E-ELAB-LATE`). All construction goes through the factory (`FW-E-ELAB-NEW`). | `semantics/elaboration.md:29-68` | Fixed per-instance state layout. No dynamic instances. Instance count is known at build time, which is the input to the dedup decision. |
| Signals are packed types with a single writer (`FW-E-WRITE-MULTI`). Register vs wire is decided per signal. | `semantics/signals.md:3-5`, `processes.md:51-72` | A per-class state struct, and a per-signal decision on what crosses the boundary as registered vs combinational. |
| Process bodies are functions; they never wait. | `processes.md:35-49` | Every unit is a set of plain C functions. No coroutines at any boundary. |
| A comb may run extra times (minimum semantics). | `architecture.md:24-27` | Static scheduling is legal. So is conservative scheduling across an opaque boundary. |
| Step order within a domain is unobservable. | `processes.md:98-117` | Steps of separately compiled units can run in any order, batched by class (the Wang'24 cache trick) or in parallel. |
| Module ports, including domain ports, are a function of the class. | `core-domains.md:411-427` | The boundary is per class, so one artifact serves every instance with the same parameters. |
| One parameterized module per class. | `core-layer1.md:1366-1400`, `examples/rr_merge/LOWERING.md` | The emitted structure already matches the unit we want to compile and cache. |
| TLM ports bind statically to exactly one export. | `protocols.md:160-200` | Calls can be devirtualized when inlined, or made one indirect call when opaque. |
| Config sinks are single-writer, read-only copies. | `protocols.md:224-253` | Treated as constant inputs to a unit, and a candidate for specialization. |

### 2.2 Gaps: rules we should commit to

The user's instinct, "commit to no hierarchical references", is correct, but
the gap is **not** in connections. Those are already local. The gap is in
**process bodies**.

1. **Process locality [unspecified today].** Nothing in the spec stops a
   parent's `comb()` from reading `u0.out.valid` on a child or grandchild.
   - The implementation lets it through: `_path()` in `proc_mapper.py:94-107`
     accepts any member chain, and it only works if a flat net of that name
     happens to exist (`struct_flatten.py:708-735`).
   - **Recommendation:** make this a spec rule, not an opt-in. A process may
     read and write only its own ports, bundles, local signals and state, and
     may read its direct children's ports in the same way a `connect()` could
     name them.
   - It costs users almost nothing, because monitoring is already done by
     connection (`core-layer1.md:312-331`). It is what makes every class a
     legal compilation unit, and it should get a new `FW-E-` code.
2. **No mutable static or global state, and no DPI, in lowered processes
   [unspecified].** These are hidden cross-unit edges. Ban them in
   `comb()`/`step()`, or require them to go through a declared
   capability/port.
3. **Param closure.** Path-glob overrides from farther ancestors force
   specialization (`core-layer1.md:1395-1414`), which breaks
   one-artifact-per-parameterization.
   - `require_param: true` is a per-task switch for this today.
   - Library IP needs the property per class, so it can be checked when the
     library is published, not when a user builds.
   - This is the one place where a per-class marker is justified. It
     restricts the *users* of a class, so the class author has to declare it.
4. **Constructor-factory realization.** Each factory choice is a separate
   specialization. That is fine, but the choice must be part of the cache
   key (§4.3).

Everything else in the boundary contract (no `defparam`, no `bind`, no late
construction, explicit domains) fw-hdl already has.

### 2.3 Gaps: things to build [NONE]

- **Read sets per `ProcBlock`.** `proc_block.py:50-65` records `writes` but
  not `reads`.
- **A per-class boundary summary** in Zuspec IR, specified in §4.2. The old
  core's `fw_settle_table` (`docs/reference/settle.md:11-34`) is the
  precedent: per-class read/write sets and per-field comb dependences, cut
  at port boundaries, with SCC scheduling over them.
- **Sample-window and guard annotations** (`protocol-sample-windows.md`,
  not started). These feed activity gating within and between units.
- **A `ProcBlock` path into `zuspec-be-sw`.** Its RTL-to-C pipeline today
  takes one zuspec-dataclasses component at a time
  (`zuspec-be-sw/.../passes/rtl/comb_order.py`).

Per AGENTS.md, the summary, locality checks and C lowering all belong in
Zuspec IR passes, not fw-hdl-specific code.

## 3. Properties that unlock more than the minimum

Beyond "no hierarchical references", these are the properties that pay off.
Most can be **derived**; none needs user annotation.

| Property (derived per class) | What it enables |
|---|---|
| **No comb path from input to output.** Every output is registered or depends only on state ("Moore boundary"). | An outer schedule calls the unit once per phase, with no settle exchange. It can be fully opaque at almost no runtime cost, and steps can run in parallel threads. |
| **No comb path from output back into this unit.** No input has a comb dependency on any of its outputs. | No cross-boundary SCC. A static schedule is possible without inlining. |
| **Latency-insensitive ports only** (ready/valid with registered handshakes, from protocol kits). | Switchboard-style decoupling: a separate thread, process or machine, and time-skipping per unit. |
| **Quiescence predicate** (from guards and sample windows). | Skip the whole unit when it is idle. This is the activity-gating win from the previous discussion, applied at unit granularity. |
| **Width classes, not exact widths.** | Specialize on how a width is represented (≤8, ≤16, ≤32, ≤64, wide) and pass the exact width and `DEPTH` at runtime. One artifact then covers `rr_fifo#(T=bit[12], DEPTH=4)` and `#(bit[13], 8)`. This is the `dyn` end of the trade-off, chosen per parameter. |

The comb-path facts are what the Verilator #2562/#6748 problems lacked.
There, the scheduler had to treat each block as an opaque comb-and-seq pair
of calls with guessed costs.

## 4. Proposed design

### 4.1 The dial: four unit modes per class instance group

| Mode | What is emitted | Build | Run | Use when |
|---|---|---|---|---|
| **M0 Inline** | Folded into the parent's global schedule (ESSENT/Verilator flat) | Recompile with parent | Fastest; full cross-boundary optimization and activity gating | Small, few instances, comb paths through it, or a regression build |
| **M1 Shared interior** | One function per interior partition over a per-instance state struct; I/O-edge logic inlined into the parent (Wang'24) | Interior compiled once per artifact key; edges with parent | Near flat, minus the dedup tax; wins on instruction cache with many instances | Many instances × large body |
| **M2 Opaque** | Separately compiled unit with an `eval_comb`/`step` ABI, scheduled from its summary | Compiled once per artifact key and cached; parent only relinks if the summary is unchanged | Boundary cost low for Moore-boundary units, higher for comb-through units | Stable library IP, and the edit loop |
| **M3 Decoupled** | M2 plus latency-insensitive coupling, its own thread or process, time-skipping | As M2 | Parallel, can fast-forward when idle; cycle-exact only at LI channels | LI-only ports; large SoC partitions |

**Defaults are derived** (see the minimal-user-spec feedback). Inputs to the
choice: the summary's comb facts, instances × size, whether the class comes
from an installed library (stable) or the working tree (changing), and the
build profile (`edit` vs `regress`).

**Overrides go in the flow configuration (dfm), never in design source.**
The class author declares only semantic commitments (§2.2 item 3), not build
choices.

### 4.2 The boundary summary (ThinLTO-style)

The summary is emitted per class per artifact key, and is the only thing
the parent's scheduler reads:

- port list with width classes and domains;
- per output: registered, or a comb function of {inputs}. This is the
  port-to-port dependence matrix;
- step domains and which ports each samples;
- cost estimate per `eval_comb`/`step` (static, and later from profiles,
  which gave +28% in #6748);
- optional quiescence predicate over ports and state;
- TLM exports and imports.

**Invalidation rule:**
- A body change that leaves the summary unchanged recompiles the unit only.
  Parents relink.
- A summary change reschedules parents. Only M0 and M1 parents recompile.

This is the property that makes incremental builds scale.

### 4.3 The cache key

Hash of:
- normalized Zuspec IR for the class (not source text, so comment and
  formatting edits are free);
- specialized parameters (width classes and type params; runtime params are
  excluded);
- factory realizations;
- lowering options;
- emitter and compiler versions.

This makes a shared, team-wide cache safe (ccache-like, but at IR level).
Verilator's `--protect-key` problem shows that every input must be
deterministic.

## 5. Recommended next steps

1. **Spec rule: process locality**, plus a `FW-E-` diagnostic in the
   front-end; also the no-static/DPI rule (§2.2 items 1–2). This is cheap,
   and every later step depends on it.
2. **Read sets in `ProcBlock`**, then a **per-class boundary-summary pass**
   in Zuspec IR. This is the Zuspec IR form of the old core's settle table.
   It also serves the settle weaver (`core-layer2.md:413-418`), which needs
   the same data, so it is not throw-away work.
3. **Zero-code baseline probe.** Build today's emitted SV for `rr_merge` and
   `two_uart` under Verilator, flat vs `--hierarchical` with each class as a
   `hier_block`. Record build time (cold and warm), runtime and code size.
   This shows what M2 costs with an off-the-shelf scheduler, using the
   one-module-per-class output we already produce. Put it under
   `docs/design/probes/`.
4. **M2 emitter first, M0 second, M1 later.**
   - M2 is the simplest C emission (one unit per class) and gives the
     incremental-build story immediately.
   - M0 is an inlining pass over the same units.
   - M1 only pays off with many instances, so defer it until a design needs
     it.
5. **Param closure as a class-level check for library publication.** This
   extends `require_param` (§2.2 item 3).

**Open questions:**
- Do width classes give up too much (masking on every op) compared with
  exact-width specialization? Measure in step 3's successor.
- Should M3's latency-insensitive coupling reuse protocol-kit transactor
  metadata directly? That would tie it to fw-proto.

## 6. Saving the IR of parameterized components

The other half of incremental builds is the front end: do not re-derive a
class's IR when nothing about the class changed. fw-hdl is unusually well
placed for this, because it already lowers one parameterized IR type per
class (`core-layer1.md` §6.6). A saved class IR is therefore reusable at
any parameter value, not only at the values one design happened to use.

### 6.1 Where front-end time goes today (measured)

Probe: `docs/design/probes/ir-cache/`.
- `gen.py N K W` writes a design of N lanes. Each lane is a `src#(T)` plus K
  `stage#(T)` (comb + step), using W distinct widths of `T`.
- `timeit.py` times each phase.
- Run: `direnv exec . python timeit.py top.sv` from that directory, after
  `python gen.py ...`.

| Lanes × stages (widths) | Components | pyslang compile | Interpreted elaborate | `to_ir` | YAML serialize | `emit_sv` | `.zir` size | IR types |
|---|---|---|---|---|---|---|---|---|
| 1 × 2 (1) | ~5 | 4 ms | 8 ms | 1 ms | 20 ms | 1 ms | 44 KB | 7 |
| 16 × 4 (4) | ~85 | 4 ms | 48 ms | 18 ms | 33 ms | 2 ms | 71 KB | 7 |
| 64 × 4 (4) | ~325 | 4 ms | 190 ms | 71 ms | 64 ms | 3 ms | 140 KB | 7 |
| 256 × 8 (4) | ~2,300 | 5 ms | 1,255 ms | 506 ms | 239 ms | 20 ms | 428 KB | 7 |

Python import adds a constant ~0.25 s.

Observations:

1. **Cost scales with instances; the output scales with classes.**
   - Elaboration is ~0.55 ms per component instance, and `to_ir` ~0.2 ms.
   - 2,300 instances collapse to the same 7 IR types as 5 instances.
   - Extrapolated, a 100k-instance SoC spends over a minute in the front end
     before any codegen.
2. **`to_ir` does class-level work once per instance.**
   - `_component` (`ir_map.py:738`) calls `_general(c)` for every instance.
     This builds the full parameterized type, including `explore()`
     (`rt.py:748`), which **re-elaborates the instance's class on its own**
     to find parameter-dependent branches.
   - `_intern` then hash-conses identical results.
   - In the profile, `_procs` ran 5,124 times (about twice per instance) to
     produce 7 types.
   - This is the Chisel-elaborate-then-FIRRTL-Dedup pattern. It is the main
     in-run waste, and can be fixed now, independent of any cache: memoize
     `_general` by (class, realization, specialization reason).
3. **pyslang compile is negligible.** Parsing is not the problem; running
   `build()` per instance is.
4. **The saved `.zir` is write-only today.** `IRDeserializer` fails on the
   root:
   `Unknown _type tag 'Context' ... register the class with IRDeserialize`.
   The Elaborate task writes `design.zir` (`dfm.py` `Elaborate`), but nothing
   can load it back. The file also grows with instances, because it carries
   the instance tree with the class types.
5. **`emit_sv` is cheap.** Downstream cost will be in the passes, the C/XLS
   back ends and the C++ compiler, all of which work per class. That is where
   a class-keyed cache pays back most.

### 6.2 Prior art for saving IR

From memory; not re-verified in this pass.

| System | What is saved | What it buys |
|---|---|---|
| Rust `.rlib` metadata | Type-checked MIR of generic and `#[inline]` functions | Downstream crates monomorphize without re-parsing or re-checking the upstream source. `-Zshare-generics` reuses upstream instantiations. |
| Swift `.swiftmodule` | Interface, plus SIL bodies of `@inlinable` functions | Separate compilation with opt-in cross-module specialization (§1.6). |
| C++20 modules (BMI); `extern template` | Parsed and checked interface; explicit instantiations | Removes re-parsing; `extern template` stops every translation unit from instantiating the same specialization. |
| Bluespec `.bo` | Type-checked package, including polymorphic modules | Importers skip re-checking; instantiation happens in the user's compile. |
| Chisel `Definition` / `Instance`, `ImportDefinition` **[unverified details]** | One elaborated module definition, instantiated many times, importable from a separate elaboration | Added because elaborating every instance and then running FIRRTL Dedup was too slow for large designs. This is the closest precedent to the fw-hdl problem. |
| Surelog / UHDM **[unverified details]** | Precompiled packages (e.g. UVM) and a serialized UHDM database | Parse and elaborate stable packages once. |
| VCS `vlogan` / Questa `vlog` work libraries; Questa `vopt` PDU; Xcelium primary snapshots | Analyzed design units, optimized units, elaborated snapshots | The vendor version of "save at each layer" (§1.1). |
| CIRCT / MLIR bytecode | Versioned binary IR with lazy loading of function bodies | Load a summary first, and bodies only when needed. |
| Bazel / Shake | Content-addressed outputs with early cutoff | An input change whose output is identical stops propagating. |

The recurring idea: **save the generic definition, after checking but before
specialization, and let consumers instantiate it.** fw-hdl's parameterized
class IR is that artifact.

### 6.3 What to save: three layers

| Layer | Content | Key | Depends on |
|---|---|---|---|
| **L-class** | Parameterized `DataTypeComponent`: `template_params`, fields, binds, generates, `proc_blocks`, domains, protocols, plus the boundary summary (§4.2) | Hash of the class's resolved source closure, its factory realization, spec/API version and front-end version | Only the class and what it references, never its users |
| **L-spec** | One specialized type, for each forced specialization (`FW-I-EMIT-SPEC`) | L-class key plus the reason's inputs (concrete params, override set) | The user's context |
| **L-design** | Instance tree, parameter values, overrides, top-level netlist | Per design | Everything; this layer is small |

Back-end artifacts (C, SV, XLS IR, objects) are keyed by L-class or L-spec
key plus back-end options. They are never keyed by the design, so the same
`fifo` IR feeds every design and every back end.

This fits the XLS constraint in `CLAUDE.md`. The saved artifact is Zuspec IR;
each engine adapter, including XLS, consumes it.

### 6.4 The big win: elaborate a cached class as a stub

Caching the per-class IR after a full elaboration only saves `to_ir` and
later steps. The large cost (6.1 item 1) is *interpreting `build()` for every
instance*. To remove it, the elaborator must be able to **stand a cached
class in for its instances without running the class's code**.

The spec already makes this nearly possible:

- **Connections are own scope plus direct children's ports**
  (`FW-E-CONN-SCOPE`). A parent's `connect()` needs only a child's port list
  and types, which are in the L-class summary, not its internals.
- **Structure is frozen and created only through the factory.** The stub's
  structure is fully described by its L-class IR, evaluated at the
  instance's parameter values. That includes generates, which is how per-
  instance netlist detail (signal names, port-array sizes) is recovered when
  a back end or a waveform needs it.
- **Process locality** (§2.2 item 1, still to be specified) ensures no parent
  process reaches inside the stub.

What blocks treating a class as a stub (it is then elaborated normally):

- **Ancestor path-glob overrides that land inside the class.** The override
  set becomes part of an L-spec key, or the class is elaborated.
- **A parameter-dependent structure that `explore()` can't express**
  (`NotParam`). This is already detected, and it produces an L-spec entry.
- **Constructor-factory overrides that change a realization inside the
  class.** These are part of the key.
- **Anything that reads elaboration-time values out of a child** (config
  reads back up the tree, `get_*` queries in the parent's `build()`/
  `connect()`). This needs an audit. If such reads exist, the summary must
  export those values.

So the same commitments that make a class a reusable *compilation* unit (§2.2)
make it a reusable *elaboration* unit. "Param closure" now pays twice.

Elaboration cost then becomes proportional to the **user-written,
non-cached** part of the design, plus a cheap stub instantiation per cached
instance. That is the Chisel `Definition`/`Instance` result, reached through
a spec rule rather than a separate user-facing API. Per the minimal-user-spec
feedback, the user writes `fifo#(T)::create(...)` as before, and the tool
decides whether to stub it.

### 6.5 Format and invalidation

- **Split per class.** One file per L-class / L-spec entry, named by key,
  plus a small L-design file. Do not use one monolithic `design.zir`.
  - This matches how invalidation works, and lets a library ship its
    L-class files.
  - Per the strategy memory, a library would ship its L-class files
    alongside its plain SV, so users of the IP do not need its source in
    the fw-hdl front end.
- **Round-trip first.** Fix the deserializer (6.1 item 4) and add a
  serialize → load → emit equality test before any caching depends on it.
- **YAML for debugging, binary for the cache.** YAML serialization of 428 KB
  took 0.24 s, which is comparable to the `to_ir` work it would replace at
  small scale. A binary or compact JSON form with lazy body loading (load the
  summary for stubs; load bodies only for classes a back end must regenerate)
  follows the MLIR bytecode model.
- **Early cutoff at two points:**
  1. Source edit, but the class IR hash is unchanged (comments, formatting,
     or a different class in the same package): nothing downstream rebuilds.
     This matters because SV packages put many classes in one file, so
     file-level invalidation over-invalidates.
  2. Class IR changed but the boundary summary is unchanged: only that
     class's artifacts rebuild; parents relink (§4.2).
- **Source closure for the L-class key.** The key covers the class text,
  its base classes, the packed types and protocols it references, the
  included macros it expands, and the API/spec version. pyslang's symbol
  references give this closure. Since pyslang compile is cheap (6.1 item 3),
  re-parsing everything to compute keys is affordable. Only interpretation
  and later steps need skipping.

### 6.6 Steps

1. **Memoize `_general` per (class, realization)** within a run, so `explore()`
   and `_procs` run once per class instead of once or twice per instance.
   This needs no cache, can be done now, and should take the 2,300-instance
   `to_ir` from ~0.5 s to near-constant.
2. **Fix `.zir` round-trip** and add the equality test.
3. **Split IR output** per class (L-class / L-spec / L-design), with
   content-hash keys and source-closure hashing.
4. **Audit elaboration-time reads from children** (6.4, last bullet), then
   add **stub elaboration** for classes with an L-class hit. This is the step
   that removes per-instance interpretation.
5. **Key back-end artifacts by L-class key** (C units from §4, emitted SV
   modules, XLS IR), and add a shared cache directory.

Re-run `docs/design/probes/ir-cache/` after steps 1 and 4 to measure the
gain.

## 7. Sources

- Verilator hierarchical verilation: https://verilator.org/guide/latest/verilating.html ; options: https://verilator.org/guide/latest/exe_verilator.html
- Antmicro, Verilator hierarchical mode (2025): https://antmicro.com/blog/2025/05/improving-verilator-hierarchical-mode
- Verilator issues #2562, #6748, #8558: https://github.com/verilator/verilator/issues/2562 , https://github.com/verilator/verilator/issues/6748 , https://github.com/verilator/verilator/issues/8558
- snax_cluster PR #672: https://github.com/KULeuven-MICAS/snax_cluster/pull/672
- VCS precompiled IP (EDN): https://www.edn.com/speed-compile-verification-under-synopsys-vcs/
- Questa qrun/PDU: https://blogs.sw.siemens.com/verificationhorizons/2021/07/07/qrun-ing-optimized-build-flows-in-questasim/
- Xcelium MSIE: https://blog.asfigo.com/2024/08/cadence-xcelium-multi-snapshot.html (Cadence app note not retrievable)
- Wang, Nijssen, Beamer, ASPLOS'24: https://scottbeamer.net/pubs/wang-asplos24.pdf
- ESSENT: https://scottbeamer.net/pubs/beamer-dac2020.pdf
- GSIM: https://arxiv.org/abs/2508.02236 ; RepCut: https://dl.acm.org/doi/10.1145/3582016.3582034 ; Khronos: https://dl.acm.org/doi/10.1145/3613424.3614301
- Arcilator: https://llvm.org/devmtg/2023-10/slides/techtalks/Erhart-Arcilator-FastAndCycleAccurateHardwareSimulationInCIRCT.pdf
- Parendi: https://arxiv.org/html/2403.04714v1 ; Cuttlesim: https://people.csail.mit.edu/stellal/papers/cuttlesim-ASPLOS21.pdf
- Bluespec user guide: https://csg.csail.mit.edu/6.375/6_375_2016_www/resources/bsv-user-guide.pdf
- Switchboard: https://arxiv.org/pdf/2407.20537
- ThinLTO: https://research.google/pubs/thinlto-scalable-and-incremental-lto/ ; Swift library evolution: https://www.swift.org/blog/library-evolution/
