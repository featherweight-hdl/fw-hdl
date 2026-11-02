# Phase 0 (the spine): implementation, test and documentation plan

*Plan accepted 2026-11-01; see §10 for the decisions.*

This is Phase 0 of [adoption-path-plan.md](adoption-path-plan.md), implementing the design
in [ir-results-overlay.md](ir-results-overlay.md). Code facts were checked against these
checkouts (out-of-packet, read-only; all **changes** go in this packet's `packages/`, see E1):
- the editable installs under `~/projects/featherweight-hdl/fw-hdl/packages/`
- the dev checkouts `~/projects/zuspec/zuspec-synth` (`19bb9c2`) and
  `~/projects/dv-flow/dv-flow-libsynth` (`3f96fcf`)

## 0. Scope

**Goal.** By the end of Phase 0:
- Every IR node that can carry a result has a stable **anchor**.
- Engine results are **facts in overlays**, defined in `zuspec-ir-core`.
- XLS is driven through an **engine interface** that returns RTL plus an overlay.
- The SV source and a zuspec-dataclasses source produce the same anchors and `iface`
  facts for the same design.

**Not in Phase 0:**
- report renderers (Phase 3)
- promotion of facts to intent (Phase 3)
- refinements beyond re-pointing StageTLM (Phase 4)
- a native engine adapter (Track B, which uses this interface later)
- the full constraints model (Phase 2)

**Settled decisions this plan builds on:**
- Results are IR: anchors, facts and overlays live in `zuspec-ir-core`.
- **Lossy engines are acceptable.** Weak source mapping limits analysis but never fails a
  build. The mapping-coverage numbers are informational, and CI only catches regressions
  in *our* lowering.

**Exit criteria:**
1. Every existing XLS test still passes:
   - `pytest tests/xls`
   - `zuspec-be-xls/tests`
   - `dfm run tests` over `examples/xls/*`
2. The new engine-based flow produces **byte-identical Verilog** to today's `fw.hdl.xls.IR`
   → `synth.xls.Codegen` path for gcd, rle, aes and lfsr.
3. Each example's build directory contains `anchors.json` and `overlays/xls-*.json`.
4. `iface` facts round-trip to the same `shell.json` (block signature) as today's
   `signature_from_codegen`.
5. StageTLM generates byte-identical SV when reading the overlay instead of the schedule
   textproto.
6. The neutrality canary (zdc GCD vs SV GCD) is green, or xfail with a written gap list.
   §5 covers why.
7. Mapping coverage is recorded for gcd, rle and AES A0, and gated against regression.
8. The anchor scheme has been measured on real edit history: zero re-keying outside edited
   scopes.
9. Docs listed in §7 are merged. zuspec-ir-core, zuspec-be-xls, zuspec-synth and
   dv-flow-libsynth are released, and fw-hdl is pinned to them.

---

## 1. Workstream 0: Environment and branches (do first)

Problems found:
- This packet has no `packages/` directory, so its `.envrc` sets nothing up.
- The only working venv is `~/projects/featherweight-hdl/fw-hdl/packages/python`.
- That venv's `zuspec-synth` (0.1.0) has no `proc/` or `archsched/`, and its libsynth has
  no `xls/lower.py`.
- `tests/xls/test_compose.py:234` points at a `packages/python/bin/dfm` that doesn't exist
  here.

| # | Task | Effort |
|---|---|---|
| E1 | **All changes stay inside this packet.** Populate the packet's own `packages/` with `ivpm update`. That needs network, so the user runs it. Every zuspec-* and dv-flow-libsynth change is made in `packages/<repo>`, never in `~/projects/zuspec/*`, `~/projects/dv-flow/*` or the featherweight checkout. `.envrc` already sources `packages/packages.envrc` once that directory exists | S |
| E2 | Inside `packages/`, branch `wpk/results-ir` in zuspec-ir-core, zuspec-be-xls, zuspec-synth, dv-flow-libsynth and zuspec-dataclasses (if present; it is needed for canary F, and if ivpm does not bring it, add it to `ivpm.yaml`). Check that `packages/zuspec-synth` has `proc/` and `archsched/` and that `packages/dv-flow-libsynth` has `xls/lower.py`. If they don't, ask before bringing that work in: it exists only in the out-of-packet dev checkouts. fw-hdl stays on `mballance/fw-hdl-xls` | S |
| E3 | Verify the packet is self-contained: the packet venv imports every zuspec module from `packages/` (`python -c "import zuspec.synth.proc; print(zuspec.synth.proc.__file__)"` and similar). Record the recipe in `docs/research/phase0-status.md` | S |
| E4 | Fix the `dfm` path in `test_compose.py` (use `shutil.which("dfm")` or `$DFM`) | S |
| E5 | Baseline: run every suite in exit criterion 1, log to `build/phase0-baseline/*.log`, and record pass/skip counts. This baseline is what "nothing regressed" means | S |

---

## 2. Workstream A: Anchors (`zuspec-ir-core`)

### A1. Grammar (ADR first)

Write `docs/anchors.md` before coding, and review it first; everything else depends on it.
**Drafted:** `packages/zuspec-ir-core/docs/anchors.md`. It supersedes the sketch below:
branches are named by IR field path, so every statement kind is covered without a
per-kind table.

```
anchor    := root ( "." member )* ( "#" stmtpath ( "." expr )? )?
root      := neutral qualified type name (pkg.Type; language spelling kept in source_name)  e.g. rle_pkg.RunLengthEncoder
member    := field | port | channel | function | process name   e.g.  .prev_count  .run
stmtpath  := "s" N ( "." branch "." "s" N )*                 N = 1-based ordinal in its block
branch    := IR field path of the nested list: body | orelse | clauses.K.body | cases.K.body
expr      := "e" N                                            pre-order ordinal among value-producing
                                                              exprs of that statement (1-based)
qualifier := "@" word ( ":" word )*                           derived anchors only, e.g.
                                                              …prev_count@reg:2   …out_c@fifo
```

Examples:
- `rle_pkg.RunLengthEncoder.run#s4.body.s1.e2`
- `gcd_pkg.gcd#s3`

**Rules:**
- **Names win over ordinals.** A named statement-level declaration (a local variable) does
  not get its own named level. That keeps the grammar small; the edit-history measurement
  in A6 decides whether to add one.
- **Ordinals are local to the innermost block.** An edit re-keys only the statements after
  it in the same block, and its own subtree.
- **Overloads:** SV has none at class scope. The Python front end must reject or
  disambiguate them with `~N`.
- **Anchors are ASCII.** The characters `.` `#` `@` `:` are reserved, and source names
  containing them are escaped as `\xx`.

### A2. Storage on the node
- Add `anchor: Optional[str] = dc.field(default=None, compare=False, repr=False)` to
  `Base` (`base.py:75`). This follows the precedent of `annotations`: setting an anchor
  never changes node equality.
- Add `anchor` to `ChannelSignature` and `BlockSignature` for free, since both are `Base`.

### A3. Assignment pass
New module `zuspec/ir/core/anchor.py`:
- `assign_anchors(ctx: Context, roots: Optional[List[str]] = None) -> AnchorTable`
  - walks `Context.type_m` (`context.py:9`): components, then fields, functions and
    processes, then statement blocks, then expressions
  - sets `node.anchor`
  - **idempotent:** rerunning yields identical anchors
- `AnchorTable`:
  - per entry: `anchor → {kind, loc, source_name, scope}`
  - per named scope: `scope_hash`
  - `by_loc` index `(file, line, col) → [anchor]`, used by engine adapters to resolve `pos`
  - `node_of(anchor)`: an in-memory weak map, populated only when built from a live
    Context
- **Scope hash:**
  - SHA-256 (first 16 hex digits) of the scope subtree, serialized with the existing
    `serializer._to_dict`
  - excludes `loc`, `doc`, `doc_trailing`, `anchor`, `annotations` and `provenance`
  - so moving code without changing it, or editing comments, leaves the hash unchanged
- **File form:** `anchors.json`, format `zuspec.anchor-table` v1, with JSON Schema
  `schemas/anchor-table.v1.json`.

### A4. Loc conventions (needed for `by_loc` to work across front ends)
The two front ends disagree on columns:
- fw-hdl `static_mapper.loc()` (`:89`) stores a **1-based** column in `Loc.pos`.
- zuspec-dataclasses stores the **0-based** `col_offset` (`data_model_factory.py:2410`).

The fix:
- **Document** `Loc.pos` as a 1-based column in `base.py`.
- **Fix** zdc to add 1.
- **Add** a helper `Loc.key()` → `(file, line, col)`, normalized to an absolute file path.

### A5. Serialization
- `serializer.py` / `deserializer.py` / `json_converter.py` already walk `dc.fields`, so
  `anchor` round-trips with no change.
- Add tests that pin this behavior, and that confirm an anchored model compares equal to
  an unanchored one.

### A6. Edit-history measurement (`tools/anchor_churn.py`)
For each consecutive commit pair touching `examples/xls/**.sv` in this repo, and the fw-aes
repo's history:
1. Build the IR at both commits.
2. Diff the AnchorTables.
3. Report:
   - **(a)** anchors changed in scopes whose hash is unchanged. **Must be 0.**
   - **(b)** the fraction of anchors re-keyed inside changed scopes. Informational.

Run it once in Phase 0 as the gate before freezing the grammar. It also stays as a
maintained tool.

### Tests (`zuspec-ir-core/tests/`)
| File | Covers |
|---|---|
| `test_anchor_grammar.py` | parse/format round-trip, escaping, qualifiers, reject malformed |
| `test_anchor_assign.py` | hand-built Contexts: component/field/function/stmt/expr anchors as specified; nested if/loop/match paths; idempotence; equality unaffected |
| `test_anchor_locality.py` | change one function: only its scope's anchors and hash change; insert a statement: only later siblings in that block re-key; edit a comment or move a location: no hash change |
| `test_anchor_table_file.py` | JSON round-trip, schema validation, `by_loc` lookup, unknown-version rejection |
| `test_loc_key.py` | column normalization, path normalization |

---

## 3. Workstream B: Facts, overlays and `ResultStore` (`zuspec-ir-core`)

New subpackage `zuspec/ir/core/results/`.

### B1. `fact.py`
```python
@dc.dataclass(frozen=True)
class Fact:
    kind: str            # "sched.stage", "timing.node_delay_ps", "xls.node_name", ...
    anchor: str          # may carry a qualifier: "…prev_count@reg:2"
    value: Any           # JSON-representable; schema per kind
    quality: str         # exact | merged | derived | partial | unmapped
```

### B2. `kinds.py`: the core kind registry
Each kind has a value schema and the anchor kinds it may attach to. Phase 0 core set:

| Kind | Value | Anchored at |
|---|---|---|
| `iface.block` | `BlockSignature` (JSON via `signature_to_json`) | component |
| `iface.channel_stage` | int | channel |
| `iface.channel_flop` | `"none"\|"flop"\|"skid"\|"zero_latency"` | channel |
| `sched.stage` | int | expr, stmt, state, channel op |
| `sched.stage_count` | int | process / function |
| `sched.ii` | `{value:int, reliable:bool}` | process / function |
| `timing.node_delay_ps` | int | expr |
| `timing.path_delay_ps` | int | expr |
| `timing.critical_path` | `{stage:int, anchors:[str], delay_ps:int, slack_ps:int?}` | process / function |
| `timing.clock_period_ps` | int | component |
| `rtl.signal` | `{module:str, name:str}` | expr, state, derived |
| `rtl.register` | `{module:str, name:str, width:int, stage:int}` | derived `@reg:<stage>` |

Rules:
- **Unregistered kinds are allowed if namespaced** (`xls.*`, `native.*`). They are stored
  opaquely and never validated against a schema.
- **Extensibility** goes through an entry-point group `zuspec.fact_kinds`, mirroring
  `registry.py`'s `zuspec.lowering`.
- **`area.*` and `sim.*` are reserved** but not defined until a producer exists.

### B3. `overlay.py`
- **`OverlayHeader`:**
  - `schema_version`, `overlay_id`, `engine`, `engine_version`
  - `delay_model`
  - `constraints` (dict) and `constraints_hash`
  - `command`, `created`
  - `scope_hashes` (a snapshot from the AnchorTable at build time)
  - `coverage` (a dict, defined in C6)
  - `artifacts` (paths of the engine's own files: IR, schedule, block IR, Verilog)
- **`Overlay`:** the header plus facts, stored **columnar per kind**:
  `{kind: {"anchor": [...], "value": [...], "quality": [...]}}`.
- **File form:** `overlays/<engine>-<overlay_id>.json`, format `zuspec.overlay` v1, with
  `schemas/overlay.v1.json`.

### B4. `store.py`: `ResultStore`
- `ResultStore(anchor_table)` with:
  - `add(overlay)` and `load(path)`
  - `overlays()`
  - `facts(anchor_or_node, kind=None, overlay=None) -> List[FactView]`
- **`FactView`** adds a status:
  - `valid`: the scope hash matches the current table
  - `stale`: the scope changed
  - `orphan`: the anchor is gone
- `by_kind(kind, overlay)` returns the columnar view, for bulk consumers.

### B5. `bundle.py`: the IR bundle directory
```
<build>/zir/
  manifest.json          format zuspec.ir-bundle v1; lists the files below
  model.yaml             existing IRSerializer output (optional in Phase 0; written when requested)
  anchors.json
  overlays/xls-<id>.json
```

### B6. `BlockSignature` as `iface`
- Extend `ChannelSignature` with `stage: Optional[int]` and `flop_kind: Optional[str]`.
- Bump `SIGNATURE_VERSION` to 2. **`signature_from_json` still reads v1**, and
  `save_signature` writes v2.
- Fix the gap that `_payload_to_json` handles only `DataTypeInt`: add structs and arrays.
  The rle and AES channels carry structs.
- `iface.block` facts embed the signature JSON, so `shell.json` = `iface.block` value
  written standalone. One source of truth.

### Tests
| File | Covers |
|---|---|
| `test_fact_kinds.py` | schema validation per core kind; namespaced passthrough; bad value rejected; entry-point registration |
| `test_overlay_file.py` | round-trip, schema validation, columnar layout, header fields required |
| `test_result_store.py` | lookups by anchor/node/kind; `valid`/`stale`/`orphan` after modifying a scope; several overlays side by side |
| `test_bundle.py` | manifest consistency; partial bundles (no model.yaml) load |
| `test_signature_file.py` (extend) | v1 files still load; v2 with stage, flop and struct payloads round-trips |
| `test_overlay_scale.py` | 100k facts: write + load under 1 s (guards the columnar choice) |

---

## 4. Workstream C: XLS overlay writer (`zuspec-be-xls`, `dv-flow-libsynth`)

### What already exists
- `lower_fn.py:98` `pos_of()` already emits `pos=(fileno, line-1, col-1)` on every expr and
  statement node (`set_loc`, `:128`), and `printer.py:51,96` prints `pos=` and the file
  table.
- **So `pos` is the primary mapping mechanism and needs no new emission work.** It is
  reversible to `Loc.key()`, then to `AnchorTable.by_loc`.
- Node names, by contrast, exist only for params, state, state reads and channels; other
  nodes print as `op.N` (`xir.py:221`).

### Tasks
| # | Task | Where | Effort |
|---|---|---|---|
| C1 | **Lowering map (oracle).** As `BodyLowerer` creates nodes, record `node_id → anchor` of the IR node being lowered. Write `<top>.lowering.json`. Used by tests to check pos-based resolution on *pre-opt* IR; not required at run time | `lower_fn.py`, `lower_proc.py`, `xir.Package` | S |
| C2 | **Name variable-defining nodes after source names** (local assigns: `count`, `do_send`), uniquified with XLS's own rules. Expression temporaries stay unnamed, which keeps RTL readable without leaking anchors into names. This gives readable `p2_count` registers | `lower_fn.py`, `lower_proc.py` | S–M |
| C3 | **IR text reader** `read_ir.py`: functions, procs and blocks, and per node: name, op, id, operands, `pos` list. One reader for opt, scheduled and block IR (`reg` and instantiation lines for block IR). Replaces the ad-hoc parser at libsynth `xls/lower.py:171` later (Phase 4) | be-xls | M |
| C4 | **Schedule reader** `read_schedule.py`, consolidating fw-hdl `stage_tlm.parse_schedules` (`stage_tlm.py:37`, regex) onto be-xls's existing `parse_textproto` (`signature.py:72`). Reads stages and nodes, `length`, `min_clock_period_ps`, and timed nodes (node, `node_delay_ps`, `path_delay_ps`) | be-xls | S |
| C5 | **Signature reader extension:** `signature_from_codegen` (`signature.py:141`) also reads per-channel `stage` and `flop_kind` from `channel_interfaces` | be-xls | S |
| C6 | **Overlay writer** `overlay.py`: `xls_overlay(anchor_table, *, signature, schedule, opt_ir, block_ir=None, line_map=None, constraints, command) -> Overlay` | be-xls | M |
| C7 | **libsynth codegen outputs:** add `--output_block_ir_path` and `--output_verilog_line_map_path` to `xls/codegen.py`, exposed as task outputs. Today it passes signature, schedule and schedule IR only (`:138`, `:158-159`) | dv-flow-libsynth | S |

### C6 in detail: mapping rules
1. **Resolve each opt/scheduled-IR node** with a non-empty `pos` list to anchors:
   - Each `pos` maps to `by_loc` exact `(file, line, col)` and gives expression anchors.
   - One `pos` resolving to one anchor is `exact`. Several `pos`, or several anchors, is
     `merged`.
   - No exact match but a match on file and line gives the statement anchor on that line,
     as `partial`.
   - Nothing at all is `unmapped`. The fact is still emitted with an anchor of the
     enclosing function or proc, so totals add up.
2. **`sched.stage`** per resolved node.
   - Several nodes on one anchor (one source expression split into several XLS ops) yield
     several facts with the same anchor. Consumers aggregate: min/max stage.
3. **`timing.node_delay_ps` / `path_delay_ps`** come from the schedule's timed nodes.
4. **`timing.critical_path`** per stage:
   - walk the max-`path_delay_ps` chain backwards through operands, using C3 operand lists
   - emit the anchor sequence, collapsing consecutive duplicates
5. **`sched.stage_count`** comes from the schedule `length`. **`sched.ii`** comes from the
   signature, with `reliable=False` for procs (XLS's `value_or(1)`).
6. **`iface.*`** come from the signature (C5), anchored on the component and on channel
   fields matched by name.
7. **`rtl.register`** (when block IR is present):
   - each `reg p<s>_<name>` becomes the derived anchor `<anchor-of-name>@reg:<s>`
   - the name is resolved through C2 names, then node names in the opt IR, then `pos`
   - **`rtl.signal`** comes from the Verilog line map, for named nodes
8. **Coverage** goes in the header:
   - `ops_total`, `ops_by_quality{...}`
   - `pct_ops_attributed` (exact + merged)
   - `pct_crit_delay_attributed`
9. **Engine-specific extras:**
   - `xls.node_name` per resolved node, so the Phase 5 monitors can find RTL names
   - `xls.node_id`

### Tests
| File | Kind | Covers |
|---|---|---|
| `tests/unit/test_read_ir.py` | unit, checked-in fixtures | opt, scheduled and block IR samples; `pos` lists; operands; regs |
| `tests/unit/test_read_schedule.py` | unit | fixture textprotos incl. timed nodes; parity with `stage_tlm.parse_schedules` on the same input |
| `tests/unit/test_signature.py` (extend) | unit | channel stage and flop kind |
| `tests/unit/test_overlay_map.py` | unit | synthetic AnchorTable + IR fixtures covering every mapping-quality case |
| `tests/unit/test_lowering_oracle.py` | unit (no XLS binary) | for every fn and proc in `tests/xls` micro-corpus: pre-opt `pos` resolution == lowering map, for 100% of nodes. This proves our side is lossless before XLS optimizes |
| `tests/integration/test_xls_overlay.py` | needs `$XLS_BIN` (skip otherwise) | gcd, rle, AES A0, lfsr_proc: overlay validates; every scheduled node has `sched.stage`; `stage_count` == signature latency + 1 where applicable; `iface.block` == today's `signature_from_codegen` output; coverage recorded |
| `tests/integration/golden/mapping_coverage.json` | gate | per design `pct_ops_attributed` and `pct_crit_delay_attributed`; fail on a drop > 2 points; **improvements update the golden** |
| libsynth `tests/test_codegen_outputs.py` | needs XLS | block IR and line map files produced and non-empty |

---

## 5. Workstream D: Engine interface (`zuspec-synth`) + XLS adapter

### D1. `zuspec/synth/engine/` in zuspec-synth (dev)
```python
class Engine(Protocol):
    name: str
    def version(self) -> str: ...
    def accepts(self, ctx: Context, top: str) -> Verdict: ...           # ok + reasons (each with anchor)
    def build(self, ctx: Context, top: str, anchors: AnchorTable,
              constraints: Constraints, workdir: Path) -> BuildResult: ...

@dc.dataclass
class BuildResult:
    rtl: List[Path]
    top_module: str
    overlay: Overlay
    artifacts: Dict[str, Path]   # engine-native files, also listed in overlay header
    log: Path
```
- **`Constraints` (Phase 0 subset):** `clock_period_ps`, `pipeline_stages`, `reset`,
  `reset_active_low`, `module_name`, plus `extra: Dict[str, Any]` as an engine-specific
  passthrough. Phase 2 replaces it with the full constraints model.
- **Registry:** the entry-point group `zuspec.engines`, plus `get_engine(name)`.

### D2. `zuspec.be.xls.engine.XlsEngine`
- **`accepts`:** runs be-xls's existing lowerability checks, and turns each failure into a
  reason with an anchor.
- **`build`:** lower → `opt_main` → `codegen_main` (with every output, including C7's)
  → `xls_overlay` → `BuildResult`.
- **Tool invocation reuses libsynth's codegen command builder:**
  - factor it into a plain function `codegen_argv(params) -> List[str]`, callable without
    dv-flow
  - so the two invocation paths can't drift: the dfm task and `XlsEngine` build the same
    argv
- **Tool discovery:** `$XLS_BIN`, then `PATH`, as the tests already do.

### D3. Flow integration
- **New dfm task `zuspec.engine.Build`** (zuspec-synth `flow.dv`):
  - **inputs:** an IR producer (the fw-hdl front end) and an engine name
  - **outputs:** an RTL fileset and the `zir/` bundle
- **New fw-hdl task `fw.hdl.Synth`**: fw-hdl front end → `assign_anchors` → `zuspec.engine.Build`.
- **Keep `fw.hdl.xls.IR` + `synth.xls.Codegen` unchanged** in Phase 0.
- **Add one flow variant per example** (`<ex>.synth`) running the new path, plus a
  comparison task that diffs the Verilog from both paths (exit criterion 2).
- Deprecate the old pair only after Phase 1.

### D4. StageTLM re-pointed (`fw-hdl python/fw/hdl/stage_tlm.py`)
- Read stages from the overlay (`sched.stage`, `sched.stage_count`, and
  `timing.clock_period_ps` / `min_clock_period_ps`) through `ResultStore`, instead of
  `parse_schedules`.
- Keep `parse_schedules` as a thin wrapper over be-xls `read_schedule` for one release,
  then delete it.

### D5. fw-hdl front-end hook
- In `xls_flow.py` (`:63`, `:119`), `spl_flow.py:133` and `dfm_tasks.py:352`, call
  `assign_anchors(ctx)` right after `StaticMapper`, and write `zir/anchors.json` to the
  build directory.
- **One call site per path.** No change inside `fe/` mappers: `static_mapper.py` already
  sets `loc` on every expression, statement, function, field and component.
- **Gap, deferred:** DataTypes (`dtype()`, `:125`) get no `loc`. Struct typedef anchors
  are not needed in Phase 0, so this is logged for Phase 1 (shell types).
- **Proc IR (`fe/elab/translate.py`)** carries `loc` as a `"basename:line"` string with no
  link to ir-core nodes. Thread an `anchor: Optional[str]` alongside `loc` on `P.Assign`,
  `P.If` and `P.Await`, and an anchor in `Var.origin`.
  - **Stretch goal for Phase 0.** Needed by Track B, not by the XLS path.

### Tests
| File | Covers |
|---|---|
| zuspec-synth `tests/engine/test_registry.py` | entry-point discovery; unknown engine error |
| zuspec-synth `tests/engine/test_fake_engine.py` | a fake in-process engine (writes a canned overlay). Proves the interface and the dfm task without XLS, and serves as the template for future adapters |
| be-xls `tests/integration/test_xls_engine.py` | `accepts` reasons carry anchors; `build` on gcd, rle, aes, lfsr; RTL byte-identical to the two-task path |
| libsynth `tests/test_codegen_argv.py` | `codegen_argv` == what the dfm task executes (golden argv) |
| fw-hdl `tests/xls/test_engine_path.py` | `fw.hdl.Synth` on examples; bundle present; Verilog identical to `fw.hdl.xls.IR`→`synth.xls.Codegen` |
| fw-hdl `tests/xls/test_stage_tlm_overlay.py` | StageTLM output byte-identical, textproto vs overlay input, on gcd and aes |

---

## 6. Workstream F: Neutrality canary (zdc GCD vs SV GCD)

**Purpose.** Prove that nothing SV-specific leaked into the neutral layer. It is **not** a
Python product, which stays parked.

| # | Task | Effort |
|---|---|---|
| F1 | **Spike (time-boxed to 2 days):** write `gcd_zdc.py`, a zuspec-dataclasses component equivalent to `examples/xls/gcd/gcd_pkg.sv`, with the same names. Run `DataModelFactory` → `assign_anchors` → be-xls `lower_fn`. Record every failure as a gap | S |
| F2 | **zdc fixes found by the spike**, at minimum: `loc` on expressions and functions (today only fields and statements get one, `data_model_factory.py:1243`, `:2410`), and the 1-based column (A4) | S–M |
| F3 | **be-xls fixes** for IR shapes that only fw-hdl produced so far. Each fix gets a unit test with a hand-built IR, not a zdc dependency in be-xls core tests | S–M |
| F4 | **Canary test** in `zuspec-be-xls/tests/canary/test_gcd_neutral.py` (needs zdc; skip if not installed) | S |

**What F4 asserts:**
- **(a)** The anchor sets of the two sources are equal modulo the root prefix
  (`gcd_pkg.gcd` vs `gcd_zdc.Gcd`). Same names, same statement structure, same anchors:
  that tests the grammar's language neutrality.
- **(b)** The `iface.block` facts are equal (channel names, payload types, latency).
- **(c)** The `sched.stage` facts agree per anchor.
- **(d)** Both overlays validate.

**If the spike shows large gaps:**
- (a) and (b) must still pass.
- (c) is `xfail` with the gap list in `docs/research/phase0-status.md`.
- Exit criterion 6 allows this.

---

## 7. Documentation

| Doc | Repo | Content |
|---|---|---|
| `docs/anchors.md` | ir-core | **ADR + spec:** grammar (A1), stability rules, scope hash, derived-anchor qualifiers, escaping. **Front-end obligations checklist:** set `loc` on decls, statements and expressions; 1-based columns; absolute or normalized paths; call `assign_anchors` |
| `docs/results.md` | ir-core | Intent vs facts vs refinements; fact model; core kinds table (B2) with value schemas; mapping-quality definitions; staleness; the lossy-engine policy |
| `docs/formats.md` + `schemas/*.json` | ir-core | `zuspec.anchor-table` v1, `zuspec.overlay` v1, `zuspec.ir-bundle` v1, `zuspec.block-signature` v2 (v1 still read); versioning policy |
| `docs/overlay-xls.md` | be-xls | How each XLS artifact maps to facts (C6 rules); what XLS loses and why that only limits analysis; coverage numbers for gcd, rle and AES; `xls.*` extras |
| `docs/engine.md` | zuspec-synth | Engine interface; `Constraints` (Phase 0 subset); `zuspec.engine.Build` task; **"writing an engine adapter"** checklist using the fake engine as the worked example |
| `python/fw/hdl/DESIGN.md` + `docs/reference` | fw-hdl | `fw.hdl.Synth` task; build-directory layout (`zir/`); where to find anchors and overlays; StageTLM now reads overlays |
| `docs/research/phase0-status.md` | fw-hdl | Live status per task (§9); environment recipe (E3); baseline counts (E5); canary gap list (F); churn results (A6) |
| Update `ir-results-overlay.md`, `adoption-path-plan.md` | fw-hdl | Point to the specs; mark Phase 0 status |

Every repo gets a CHANGELOG entry and a version bump at release (§8, M5).

---

## 8. Sequence and milestones

```
E1–E5 ──► A1 (grammar ADR, review) ──► A2–A5 ──► A6 churn gate ─┐
                 │                                               │
                 └──► B1–B6 (in parallel with A2–A5) ────────────┤
                                                                  ▼
            C3, C4, C5, C7 (independent of A/B) ──► C1, C2 ──► C6 overlay writer
                                                                  │
                                       D1 (can start with B) ──► D2 ──► D3, D4, D5
                                                                  │
                                       F1 spike (after A3 + C1) ──► F2, F3 ──► F4
                                                                  ▼
                                                      docs finalized ──► releases
```

| Milestone | Contents | Demo / evidence | Rough effort |
|---|---|---|---|
| **M0** | E1–E5 | baseline logs; packet runs self-contained | 2–3 days |
| **M1** | A1 reviewed; A2–A5, B1–B6 | anchors and overlays round-trip; ir-core suite green | ~2 weeks |
| **M2** | C1–C7 | `xls_overlay` on gcd/rle/AES; lowering oracle 100%; coverage golden recorded | ~2 weeks (overlaps M1 for C3–C5, C7) |
| **M3** | D1–D5, A6 | `fw.hdl.Synth` on all examples, Verilog identical; StageTLM via overlay; churn gate passes | ~1.5 weeks |
| **M4** | F1–F4 | canary green (or xfail with gap list) | ~1 week (spike can start at M2) |
| **M5** | docs + releases | ir-core, be-xls, zuspec-synth, libsynth released; fw-hdl pinned; exit criteria 1–9 checked | 2–3 days |

The total is roughly **6–7 person-weeks**. These are estimates, not measurements.

---

## 9. Status

| Task group | State | Note |
|---|---|---|
| E (environment) | not started | |
| A (anchors) | not started | A1 grammar ADR is the first review gate |
| B (facts / overlays) | not started | |
| C (XLS overlay writer) | not started | |
| D (engine interface) | not started | |
| F (canary) | not started | |
| Docs / releases | not started | |

*Mirror detailed progress in `docs/research/phase0-status.md` once work begins.*

---

## 10. Decisions (accepted 2026-11-01)

The recommendations below were accepted as written. For Q5 the default is: keep D5's
proc-IR anchors a stretch goal, and do them only if M3 has slack; otherwise they go to
Track B.

### Original questions

1. **Anchor root:** use the qualified type name (`rle_pkg::RunLengthEncoder`), which is
   SV-flavored, or a neutral `pkg.Type` form with the language separator normalized?
   - **Recommend:** neutral form `rle_pkg.RunLengthEncoder`, with the language spelling
     kept in `source_name`. Canary (a) is easier to state that way too.
2. **Named locals as anchor levels:** add `run#count` for local-variable declarations now,
   or wait for the A6 churn data?
   - **Recommend:** wait for the data.
3. **Overlay encoding:** JSON columnar is easy to inspect and diff. A binary form
   (Parquet/msgpack) would be smaller.
   - **Recommend:** JSON in Phase 0; revisit if `test_overlay_scale` or real designs push
     it.
4. **Who invokes XLS tools:** the plan puts `codegen_argv` in libsynth and has
   `XlsEngine` call it. The alternative is moving tool invocation into be-xls and having
   libsynth depend on it.
   - **Recommend:** the former. libsynth already owns tool knowledge, and be-xls stays
     free of dv-flow.
5. **Proc-IR anchors (D5 stretch):** do them in Phase 0, while the code is fresh, or leave
   them to Track B?
