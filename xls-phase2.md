# XLS phase X2: from SPL sources to an integrated RTL top

Status: **plan**, 2026-10-03. Follows `xls-phase0.md` (X0 done; X1-1 to X1-6 done early,
X1-0 open). The design discussion that led here is summarized in §2.

## 1. Goal

A user who has an fw-hdl SPL design gets synthesizable RTL for it, with XLS
implementing the parts they choose, through a pipeline they can see and customize
with dv-flow.

X2 is the **first vertical slice**, kept narrow:

- **The partition is explicit.** The user names the component classes that XLS
  implements; nothing is inferred.
- **The partition boundary is a component.** No function-level offload and no
  regions inside a component.
- **The integration is structural.** A generated top instantiates the blocks and wires
  their channels.
- **The output is Verilog text from XLS.** It is not fed back into zuspec IR, but
  the design keeps that path open (§3.3).

**First target (T1):** a top component that chains two corpus blocks, `rle_enc` →
`crc32_stream`, through a framer block and two channels (ST-3). One testbench runs against the class model (SPL
view) and the generated top (RTL view), and the output streams must match.

## 2. Where things live

| Layer | Contents | Kind |
|---|---|---|
| **fw-hdl** | SV front end (static subset, component structure); the partition step; the integration step; the RTL-view protocol transactors | front end + integration |
| **zuspec-ir-core** | `BlockSignature` and its file form | shared types |
| **zuspec-be-xls** | zuspec IR → XLS IR; the task `zuspec.xls.IR`, which picks a front end by fileset type | primitive |
| **dv-flow-libsynth** | `synth.xls.Codegen` (`opt_main` + `codegen_main`), `synth.xls.DslxToIR`; outputs are XLS-native; maps XLS errors back to source through `pos=` | tool wrappers |
| **dv-flow-libproject** | the default A → B×N → C wiring as a compound; the `engine` knob | wiring and defaults only |
| **edapack xlsynth** | XLS binaries on PATH via ivpm (X1-0) | tools |

Each layer depends only on the layers below it. libsynth knows nothing about zuspec,
and libproject holds no logic: anything a recipe would compute is a task in fw-hdl or
be-xls.

## 3. The pipeline

```
src-spl ──► A. Partition ──► manifest + shell
                │
                ├──► B. per XLS class (fans out):  zuspec.xls.IR ──► synth.xls.Codegen
                │                                   └─► block = { signature, module ref }
                ▼
            C. Integrate ──► top.sv (+ native-path modules, channel FIFOs)
```

### 3.1 Steps and their artifacts

| Step | Task (package) | In | Out |
|---|---|---|---|
| A | `fw-hdl.spl.Partition` | `src-spl` fileset; `top`; `xls: [class, ...]` | `splPartition`: the manifest (each XLS class and specialization, its instances) and the shell (component tree, channels, binds). Static-subset errors for the listed classes, at SV lines. |
| B1 | `zuspec.xls.IR` (be-xls) | `src-spl` + one class | `xlsIR` (with its file table) + the predicted `blockSignature` |
| B2 | `synth.xls.Codegen` (libsynth) | `xlsIR`; stages or clock period; naming flags | `systemVerilogSource` (one module); `xlsModuleSignature` (XLS's textproto); optimized IR; schedule report |
| B3 | `zuspec.xls.Signature` (be-xls) | `xlsModuleSignature` + the predicted signature | `blockSignature` (the actual one), after checking it against the prediction |
| C | `fw-hdl.spl.Integrate` | `splPartition`; every `blockSignature` | `systemVerilogSource`: the top, plus any native-path modules and FIFOs |

**Rule 1: step C depends only on signatures.** It never reads XLS's Verilog. A block is
`{signature, module ref}`, and the module ref is a module name plus a fileset.

**Rule 2: every block arrives the same way.** An XLS block, a hand-written module with a
signature file, and later a native-engine block all look the same to C. Customization
follows from that:
- replace B for one class with your own RTL;
- set codegen options per block;
- choose an engine per block.

### 3.2 What the user sees

```yaml
- override: src-spl
  needs: [model]

- name: chain-rtl
  uses: spl.rtl                  # libproject compound: A → B×N → C
  needs: [src-spl]
  with:
    top: chain_top
    xls: [rle_enc8_t, crc32_stream]
    codegen: {pipeline_stages: 1}

- override: src-rtl
  needs: [chain-rtl]
```

`dfm run tests --views spl,rtl` then runs the same cases on both views.

**Documentation is part of the deliverable.** The pipeline is explained where it is
defined, so the generated reference (sphinx-dv-flow, as libproject already does) is
the user-facing description:
- every task carries `desc:` and `doc:`, and the doc names its input and output fileset
  types;
- the compound's `doc:` shows the A → B×N → C structure, which artifacts flow between
  steps, and which node to override for each customization in §3.1;
- the fileset types (`splPartition`, `xlsIR`, `xlsModuleSignature`, `blockSignature`)
  are documented once, in the package that defines them.

The libproject docs coverage gate then holds every new task to this.

### 3.3 The long-term path this keeps open

Later, `codegen_main --output_block_ir_path` gives XLS's block IR. A translator into
zuspec RTL IR would let the module ref become an in-IR component, so be-sv emits the
whole design. That gives one naming scheme and one style, and zuspec passes such as
the debug domain apply to XLS logic too.

Under Rule 1, that swap happens inside B; A, C and the user's flow are unchanged.

## 4. Semantics of composition

**Composition is a Kahn process network.**
- The static subset has only blocking `get` and `put`: no peek, no try-get, no select.
- A network of such processes connected by FIFO channels is determinate: each
  channel's stream doesn't depend on timing or channel depth, as long as the network
  doesn't deadlock.
- So the conformance check stays a comparison of streams for compositions too, and
  the RTL may choose depths, pipeline stages and backpressure freely.

**What depth does affect:** throughput, and whether the network deadlocks. Deadlock is
reported, not hidden: a run that stops making progress with inputs left is a failure
in both views.

**The channel object.** A put port can't connect to a get port; fw-hdl connects port
→ export, and both XLS blocks have ports. The library needs a channel component:

```systemverilog
fw_channel #(.T(pkt_t), .DEPTH(2)) ch;   // exports put_ex and get_ex
rle.out.connect(ch.put_ex);
crc.in.connect(ch.get_ex);
```

| Channel | SPL view | RTL |
|---|---|---|
| `DEPTH == 0` | rendezvous (put completes when the matching get does) | a direct ready/valid wire |
| `DEPTH ≥ 1` | FIFO of `DEPTH` | a ready/valid FIFO of `DEPTH` |
| one end at the top boundary | the testbench binds it | ready/valid pins named from the signature |

## 5. Work items

### 5.1 Structure (ST)
- ☑ **ST-1** `fw_channel #(T, DEPTH)` in `src/std`, with `put_ex`/`get_ex`. Verilator
  tests for depth 0, 1 and N, including a put that blocks.
  → `src/std/fw_channel.svh`, included by `fw_std_pkg`. The two ends are top-level
  parameterized classes (an export that is its own imp, as `fw_put_xtor_bridge` is), not
  `FW_*_IMP` nested classes, because the channel itself is parameterized.
  `tests/xls/test_channel.py` checks order and the exact time each put returns at depths
  0, 1 and 3.
- ☑ **ST-2** Front end: extract a component's structure as zuspec IR.
  - from `build()`: child components and channels, with their specializations and
    `DEPTH`;
  - from `connect()`: port → export binds into `DataTypeComponent.bind_map`.
  - It reuses the `connect()` walking in `fe/bind/elaborate.py`.
  - Anything else in `build()`/`connect()` (loops, conditionals, computed names) is
    rejected with an SV location for now.

  → `fe/structure.py`, `StructureMapper.map_structure`, via `xls_flow.sv_to_structure`.
  It needed no new IR:
  - a child is `Field(DataTypeRef(<spelling>))`;
  - a channel is the existing `DataTypeChannel(element_type, depth)` (the PSS channel
    type; depth 0 = rendezvous);
  - binds are `Bind(lhs=<child port>, rhs=<own port | channel end>)`.

  Rules, each rejected at its SV line (8 cases in `test_compose.py`):
  - a structural class has no `run()`, and only ports, children and channels;
  - `build()` constructs each field exactly once, as `new("<field>", this)`, since the
    name becomes the RTL instance name;
  - every child port and channel end is connected exactly once, with no child-to-child
    links;
  - a parameterized child needs a typedef, which names its generated block.

  Direction and payload mismatches are already SV type errors, so slang reports them.
- ☑ **ST-3** The T1 composition `chain_top` runs on Verilator (SPL view).
  → `tests/xls/compose/chain_pkg.sv`. T1 grew a third block: `rle_enc` puts a 16-bit
  `{sym, cnt}` packet and `crc32_stream` gets a 9-bit `{last, byte}`, so `pkt_framer`
  sits between them. It sends each packet as two beats, with a predicated get, and
  ends a frame every fourth packet. Channels: `c0` is a rendezvous (depth 0) and `c1`
  has depth 2. On 400 random bytes the CRC stream matches a Python model
  (`zlib.crc32`).

### 5.2 Signatures (SIG)
- ☑ **SIG-1** A file form for `BlockSignature` (JSON) in ir-core, with a round trip.
  - Payloads as types: bits now, with the SV type name kept for the transactors.
  - Includes the module name and the module ref's fileset.

  → `signature_to_json`/`signature_from_json`/`save_signature`/`load_signature`. The
  format carries `"format": "zuspec.block-signature"` and `"version": 1`, and other
  formats and versions are rejected. New fields: `ChannelSignature.payload_sv_type` and
  `BlockSignature.sources`. Payloads are `int` only for now.
- ☑ **SIG-2** `zuspec.xls.Signature`: XLS textproto → `BlockSignature`, checked
  against the prediction. The code exists (`signature_from_codegen`,
  `signature_mismatches`); this item makes it a task.
  → Done. The function is `be-xls signature.actual_signature(predicted, codegen,
  sources)`: it raises `SignatureMismatch` on any difference, and copies the SV type
  names (which XLS doesn't know) from the prediction. The task is `zuspec.xls.Signature`,
  in the dv-flow package `zuspec.xls` that be-xls now registers (`zuspec/be/xls/dfm/`,
  entry point `dv_flow.mgr`).

### 5.3 Partition (PART)
- ☑ **PART-1** `fw-hdl.spl.Partition`: elaborate `top` (ST-2), resolve each `xls:` class,
  run the static-subset check on each, and write the manifest and the shell.
  → `spl_flow.partition(files, top, xls)`, and the task `fw.hdl.spl.Partition`
  (`fw/hdl/dfm_tasks.py`). The task writes:
  - `splPartition`: the shell as `partition.json`, `spl_flow.Shell`, format
    `fw-hdl.spl-partition` v1;
  - per class: `xlsIR` and `blockSignaturePrediction`.

  Because the task also emits each class's IR, B1 runs inside A for now (see BLK-1).
- ◐ **PART-2** Diagnostics:
  - a listed class that isn't instantiated;
  - a class outside the subset (the existing per-construct errors);
  - a channel between an XLS block and a native block (not supported in X2, §6).

  → The first two are done and tested. A child not listed in `xls` is an error at its
  declaration, since X2 has no other engine, so the third can't occur yet.

### 5.4 Blocks (BLK)
- ☐ **BLK-1** `zuspec.xls.IR` in be-xls: front ends register by fileset type (entry
  point); fw-hdl registers `systemVerilogSource`.
  → Deferred. Partition emits each class's `xlsIR` itself, so the pipeline doesn't
  need it. A front-end-neutral task still matters for a single component without a
  structural top, and for zuspec-dataclasses. It is now possible, since fw-hdl's Python
  is installed and registers an entry point.
- ☑ **BLK-2** `synth.xls.Codegen` in libsynth, plus `xls` fileset types. It also maps
  XLS errors to source through `pos=` and the file table (+1 for XLS's 0-based lines).
  → `dv-flow-libsynth` (cloned into `packages/`, added to `ivpm.yaml`, not committed):
  - package `synth.xls` with `Codegen` and `DslxToIR`;
  - file types `xlsIR`, `xlsOptIR`, `xlsModuleSignature`, `xlsSchedule` and
    `dslxSource`, documented in the package;
  - XLS tools are found on PATH or in `$XLS_BIN`;
  - source annotations are on by default.

  Tests run through pytest-dfm: DSLX → Verilog, and an XLS type error reported as a
  marker at `bad.src:7:11`, the node's `pos=` plus 1.
- ◐ **BLK-4** Diagnostics: map every kind of XLS message back to the source. XLS has
  no warnings channel. Its errors cite the IR, never the source, in three ways (see
  `diag.py`'s docstring):
  - an IR line:col (parse/verify);
  - bare node names (optimizer checks);
  - nothing at all (an unmet clock period).

  Positions are best-effort through `opt_main`.
  → Done:
  - **be-xls** writes absolute `file_number` paths (`lower_fn.src_path`). Before, it
    wrote paths relative to the directory `dfm` ran in, and libsynth joined them to
    the IR's directory: wrong for every real run. State elements, `state_read` and
    `next_value` now carry `pos=` (the declaration, and the last assignment), and
    assert messages carry absolute paths.
  - **libsynth `xls/diag.py`**:
    - indexes the IR (nodes, operands, users, every `pos` tuple);
    - maps an IR line:col to the node on that line;
    - matches node names, skipping English words (`a`, `is`) unless set off;
    - falls back to the nearest positioned operand, then user;
    - drops the `; Running pass` chain, demotes glog `E` progress lines to notes, and
      ignores `<Generated ...>` pseudo-files.
  - **An unmet clock period** reruns codegen at XLS's suggested period, and reports
    the critical path: an error on its last source line, a note on each.
  - **Source comments** in the Verilog are rewritten to 1-based, absolute
    `// file:line:col`. XLS prints its 0-based positions raw in all three annotation
    strategies, even for DSLX. `--output_verilog_line_map_path` is no substitute:
    v0.59 maps every `assign` to the same Verilog line. `diag.verilog_source(v, line)`
    maps a Verilog line back to the source.

  Tests: `test_diag.py` (no XLS needed) plus flow tests for each error kind.
  Open:
  - wire `verilog_source` into the Verilator lint/sim steps, so their messages on
    generated modules land on SV lines;
  - report the 0-based annotation bug upstream.
- ☑ **BLK-3** Module names: one module per class specialization, named
  deterministically (sanitized specialization name). The instance count comes from the
  shell.
  → `spl_flow.module_name`: `pkg::cls` → `pkg__cls`, and other non-identifier
  characters → `_`. With a typedef required for specializations (ST-2), T1's modules are
  `rle_enc8_t`, `pkt_framer` and `crc32_stream`.

### 5.5 Integration (INT)
- ☑ **INT-1** `fw-hdl.spl.Integrate`: build the top `DataTypeComponent` with
  `module_instances`, through be-sv. It follows `emit/structural.py`, the MMIO
  precedent.
  → `spl_flow.integrate(shell, signatures)` and `spl_to_rtl` (A → B×N → C in one
  call). The task is `fw.hdl.spl.Integrate`, with `passthrough: none`, so its output is
  exactly the compile list: FIFO, blocks, top, plus the top's `blockSignature`.
  - It reads only signatures (Rule 1).
  - It also returns **the top's own signature**, so a composed top is itself a block.
  - It needed `ModuleInstance.parameters` in ir-core, emitted by be-sv as `#(.K(V))`
    (`test_module_instance.py`).
- ☑ **INT-2** A ready/valid FIFO module (`fw_rv_fifo`, parameterized width and depth,
  `DEPTH == 0` = a wire) in fw-hdl's RTL library, verified on its own.
  → `src/rtl/fw_rv_fifo.sv`, a new directory for synthesizable library RTL.
  `test_rv_fifo.py` runs depths 0, 1, 2 and 5. With the output stalled it accepts exactly
  DEPTH values, and under random traffic on both sides the stream is unchanged.
- ☑ **INT-3** Top-level pins: each boundary channel becomes `<chan>`, `<chan>_vld`,
  `<chan>_rdy`, plus one clock and reset fanned out to every block.

- ☐ **INT-4** XLS multi-proc as a test oracle for C. For an all-XLS composition, lower it
  into one XLS package:
  - each class → a proc;
  - each `fw_channel` → a channel declared in the parent (`fifo_depth = DEPTH`);
  - the parent → `proc_instantiation`s.

  Then `codegen_main --multi_proc`. XLS's top, our signature-built top and the SPL view
  must give the same streams.

  Checked with v0.59.0 on a two-proc chain: the converter emits the parent's channel and
  the `proc_instantiation`s, and codegen emits per-proc modules plus a top. That top
  instantiates `xls_fifo_wrapper` **without defining it**, so the FIFO module has to be
  supplied (shared with INT-2?). Whether `fifo_depth=0` is accepted is unchecked.

### 5.6 Views and recipe (VIEW)
- ☐ **VIEW-1** Ready/valid pin transactors as a library protocol (promote
  `tests/rv_proto`), so the RTL view binds the same component ports to pins.
- ☐ **VIEW-2** The `spl` and `rtl` DUT views for T1 under `tests`, with one testbench.
- ◐ **VIEW-3** The libproject compound `spl.rtl` and the `engine` knob, documented per
  §3.2.
  → The compound is `project.spl.utils.xls-rtl` in dv-flow-libproject (cloned into
  `packages/`, not committed), and `dfm show task` prints its pipeline doc. The
  `engine` knob waits for a second engine. All four new dv-flow packages pass the
  libproject docs gate (`dvflow-doc coverage --internal --strict`).
- ◐ **VIEW-4** `fw-hdl/tests/xls` moves onto the same tasks where it can, so the
  conformance suite exercises the user-facing path.
  → `test_compose.py::test_t1_through_dv_flow` runs `dfm` on both the explicit
  four-task flow and the recipe (`tests/xls/compose/flow.yaml`). It simulates using only
  the files the last task outputs, and checks against the Python model. The X0 suites
  still call the Python API directly.

## 6. Out of scope for X2

- **Channels between XLS and native blocks.** The native SPL contract has no `get`,
  and its `put` is an unhandshaked `pin <= v`. Ready/valid get/put on the native path
  is the next step (SPL contract "future", C5).
- **MMIO-configured XLS blocks.** They need the item above plus register-to-channel
  adapters.
- **Automatic partitioning**, function-level offload, and translating XLS block IR
  into zuspec IR (§3.3).
- **XLS multi-proc as a product path.** For all-XLS regions it could replace step C, but X2
  keeps one integration path, because only C mixes XLS, native and hand-written blocks.
  In X2 it is used only as a test oracle (INT-4); revisit for QoR.

## 7. Risks

1. **Elaborating structure statically (ST-2).** `build()`/`connect()` are procedural
   SV. The X2 subset is straight-line code only; richer forms need a real elaborator.
2. **Deadlock with small depths.** Determinacy (§4) holds only if the network doesn't
   deadlock. A depth that deadlocks in RTL but not in the SPL view would be a mismatch
   of depths, not of semantics, so both views must use the same `DEPTH`.
3. **Verilator holes** (`xls-phase0.md` risk 5). Two specializations in one build already
   misbehaved once, and T1 needs two classes in one build. Check that first.
4. **Naming stability.** Module and port names come from class specializations and
   codegen flags, and downstream lint baselines and constraints will depend on them.
   Fix the scheme in BLK-3 and INT-3 and keep it.

## 8. Decisions

| # | Question | Recommendation |
|---|---|---|
| X2-D1 | Where does the XLS class list live? | Flow parameter (`xls:`) now. An SV attribute on the class later, with the flow parameter overriding it. |
| X2-D2 | Default `engine` | `xls` for listed classes. Nothing is implicitly assigned. |
| X2-D3 | `src-spl` vs a separate slot for the static subset | Keep `src-spl`. The subset is checked per listed class in A, not per project. |
| X2-D4 | Default channel depth | No default: `DEPTH` is required, because it is a design decision that changes throughput. |

## 9. Order of work

1. ST-1, ST-2, ST-3: can the structure be recovered? This is risk 1, so it goes first.
2. SIG-1, INT-2: the two leaf pieces, independent of each other.
3. PART-1, INT-1, INT-3: T1 end to end from Python, before any dv-flow task.
4. BLK-1, BLK-2, BLK-3, SIG-2: the dv-flow tasks (needs X1-0 for the tools on PATH).
5. VIEW-1 to VIEW-4, with the docs.

## 10. Log

| Date | Item | Note |
|---|---|---|
| 2026-10-03 | — | Plan written after the pipeline discussion. Found while planning: the library has no channel component (two ports can't connect), hence ST-1; ir-core already has `bind_map` and `module_instances`; libproject generates its reference from task `desc:`/`doc:`, which §3.2 relies on. |
| 2026-10-03 | ST-1..3 | Channel, structure mapper and T1 SPL view done. ir-core already had `DataTypeChannel(element_type, depth)` for PSS channels, so channels need no new IR. The types forced T1 to grow a framer (16-bit packets vs 9-bit beats). |
| 2026-10-03 | SIG-1, INT-1..3, PART-1, BLK-3 | **T1 works end to end in the RTL view.** `spl_to_rtl(files, "chain_top", [rle_enc8_t, pkt_framer, crc32_stream])` produces three XLS modules plus a be-sv structural top with two `fw_rv_fifo`s (`c0` is a wire, `c1` has depth 2). Behind randomly throttled ready/valid, at 1 and 2 pipeline stages, it gives the same CRC stream as the SPL view and the Python model (`test_compose.py::test_t1_*`). What's left for X2 is the dv-flow side: tasks, the libproject recipe, views and docs. |
| 2026-10-03 | (env) | **Why `dfm` won't start here:** the editable `yosys_bin` install still registers the `dv_flow.mgr` entry point `libyosys`, but its source directory (`~/.ivpm/cache/yosys/vyosys-0.9.26713680176_linux_x86_64`) is gone from the ivpm cache. dv-flow-mgr imports every extension at startup, so one stale entry stops all runs (`ModuleNotFoundError: dv_flow.libyosys`). The likely fix is `ivpm update`. A more robust fix in dv-flow-mgr: warn and skip an extension that fails to import. This blocks the dv-flow half of X2 (BLK-1/2, SIG-2's task, VIEW-*). |
| 2026-10-03 | (env), CH-6 | `ivpm update` fixed `dfm`. The whole `dfm run tests` regression passes with `fw_channel` in `fw_std_pkg`. **CH-6 had never really run:** under `dfm` (no `opt_main` on PATH) it reported 67 skipped. The be-xls `conftest.py` tested `"xls" in item.keywords`, and pytest keywords include path segments, so every test under `tests/xls/` looked `xls`-marked. Both conftests now use `get_closest_marker`. CH-6 now runs 104 tests (12 skip without XLS), with `uptodate: false` so it is never cached. |
| 2026-10-03 | BLK-2, SIG-2, PART-1, INT-1, VIEW-3 | **The pipeline runs as dv-flow tasks.** `fw.hdl.spl.Partition` → `synth.xls.Codegen` → `zuspec.xls.Signature` → `fw.hdl.spl.Integrate`, step by step or as the recipe `project.spl.utils.xls-rtl`. Simulating T1 from the output files alone matches the model. Findings: (1) a pytask's module path, and `${{ srcdir }}` in `run:`, resolve against the *using* task's directory, or the package root when reached from another package, not the defining fragment's. (2) So fw-hdl's tasks moved out of the project flow into a dv-flow package, `fw.hdl.spl` (`python/fw/hdl/spl.dv`), registered by fw-hdl's Python package (`dv_flow.mgr` entry point), as PLAN.md §1.6 intended. fw-hdl's Python is now installed editable in `packages/python`, and it lists `zuspec-be-xls` as a dependency. (3) Without that move, libproject could not find the fw-hdl tasks at all; the docs gate caught it. |
| 2026-10-03 | BLK-4 | **XLS diagnostics.** Probing v0.59 with hand-built bad IR showed three message kinds (IR line:col, bare node names, nothing for scheduling) and a latent bug: be-xls wrote cwd-relative source paths, and libsynth resolved them against the IR's directory, so every marker from a real run pointed at a missing file. It passed its test only because `bad.src` sat next to `bad.ir`. Fixed at both ends (absolute paths in the IR; libsynth tries the IR's directory, then the cwd). Also found: XLS annotations are 0-based (an upstream bug), its line map is too coarse to use, and `--use_system_verilog=false` drops asserts silently (Codegen now warns). |
