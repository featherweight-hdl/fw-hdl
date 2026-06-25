# fw-hdl: Implementation, Test & Docs Plan

Companion to `DESIGN.md`. The keystone risk (§9.1) is **settled**: `spl2rtl`
builds `zuspec.ir.core` RTL IR directly and the **unmodified `be-sv` emitter**
renders Verilator-lint-clean RTL (spike validated end-to-end on a blinky FSM).
This plan turns the design into an ordered, testable build with Sphinx docs.

Status legend: ☐ todo · ◐ partial · ✅ done. Everything below is ☐.

---

## 0. Ground truth from the spike (the IR contract)

The lowering target is fixed by what `be-sv` consumes (verified, not assumed):

| concept | `zuspec.ir.core` construction |
|---|---|
| input pin | `FieldInOut(name, datatype=DataTypeInt(bits,signed=False), is_out=False)` |
| output pin (registered) | `FieldInOut(..., is_out=True)` |
| internal register | `Field(name, datatype, is_reg=True)` — **not** `FieldInOut` |
| clocked process | `Function(name, body=[...], metadata={'clock':ExprRefField(self,i),'reset':ExprRefField(self,j)})` in `DataTypeComponent.sync_processes` |
| signal ref | `ExprRefField(base=TypeExprRefSelf(), index=field_index)` |
| literal | `ExprConstant(value=int)` |
| `a == b`, `<`, … | `ExprCompare(left, ops=[CmpOp.Eq], comparators=[rhs])` — **not** `ExprBin(BinOp.Eq)` |
| `a + b`, `&`, `^` | `ExprBin(lhs, op=BinOp.Add, rhs)` |
| `~a` / `!a` | `ExprUnary(op=UnaryOp.Invert/Not, operand)` |
| `if/else` | `StmtIf(test, body=[...], orelse=[...])` |
| assignment | `StmtAssign(targets=[ExprRefField...], value=Expr)` |
| container | `Context(type_m={name: DataTypeComponent})` |

These constraints are encoded once in `fw/hdl/ir_build.py` (helper constructors)
so the rest of the code can't reintroduce the `FieldInOut`-as-reg or
`ExprBin(Eq)` mistakes the spike caught.

---

## 1. Implementation plan

> **Progress (P0–P3 ✅ — full SV→RTL flow works; generated blinky passes the real
> testbench).** `fw-hdl synth tests/blinky/*.sv --top blinky --top-module
> blinky_top` emits Verilator-lint-clean RTL (FSM: put→`led<=v`, tick→7-bit
> counter to 99, toggle), and that RTL **passes the unmodified
> `tests/blinky/blinky_tb.sv`** under Verilator: `[blinky] PASS (5 blinks
> observed)`. **59/59 unit tests green** (incl. a checked-in golden). The lowering
> (`lower/spl2rtl.py`) builds RTL-level `zuspec.ir.core` IR directly (path b) and
> `emit/be_sv.py` renders it via the **unmodified** be-sv. Bug the real-TB sim
> caught (the spike never ran the TB): **fw-hdl std reset is active-high** (`if
> (reset)`, per `fw_clock_xtor_if`), not the spike's `if (!reset)`; default
> `reset_style` is now `async_high` (be-sv emits sync sensitivity — async
> `posedge reset` is a future be-sv enhancement). P2 recap: the bound SPL IR
> carries the pin boundary via `Field.pragmas`, read structurally from
> `blinky_bind.connect()` + `fw_root`/`u_led` connections (only the
> bridge→protocol meaning is the Option-B table). pyslang-11 AST quirks that shaped
> the mappers (recorded in the `pyslang11-ast-notes` memory): namespaced API
> (`pyslang.syntax`/`pyslang.ast`); a body is a `StatementList` (`.list`), a
> `Block` (`.body`), OR a bare single statement — must normalize; `expr.constant
> is None` is the only reliable "not constant" signal (`ConstantValue.empty()`
> lies, and a wrapping `Conversion` doesn't always fold — use the
> `IntegerLiteral.value`); `x += y` pre-expands to `x = LValueReference + y`
> (resolve the `LValueReference` to the target); task calls (`SubroutineKind.Task`)
> are awaited beats. Verified zero-error blinky lib set:
> `src/{fw_clock_xtor_if,fw_hdl_pkg,fw_root}.sv` +
> `src/std/{fw_put_xtor_if,fw_std_pkg}.sv` (incdirs `src/`+`src/std/`); the
> `fw_root` macro emits a `blinky_bind` class (the P2 binding source).

### 1.0 Packaging & layout
- ✅ `python/pyproject.toml` — package `fw-hdl`, console script
  `fw-hdl = "fw.hdl.cli:main"`, deps `pyslang`/`zuspec-ir-core`/`zuspec-be-sv`,
  `[test]` extra (`pytest`, `pytest-dfm`, `dv-flow-mgr`, `dv-flow-libhdlsim`),
  `[dev]` extra (`zuspec-synth`, reference only). `python/fw/...` layout.
  *(dv_flow entry-point deferred to P4 with §1.6.)*
- ✅ `python/fw/__init__.py`, `python/fw/hdl/__init__.py`, `python/README.md`.

### 1.1 Shared core (`fw/hdl/`)
- ✅ `errors.py` — `Diagnostic` + `ErrorReporter` + `FwHdlError` (strict
  unsupported-construct raiser via `reporter.fail(...)`).
- ✅ `config.py` — `FlowConfig` (`incdirs`, `defines`, `top`, `top_module`,
  `reset_style`, `output`, `dump_ir`; `predefine_strings()` for slang).
- ✅ `ir_build.py` — the §0 helper constructors + `validate_rtl_component()`
  (rejects internal-reg `FieldInOut` and `ExprBin` comparisons). Smoke-emits the
  spike's blinky FSM byte-for-byte.

### 1.2 Front end — `sv2ir` (`fw/hdl/fe/`)  *(all SV→IR lives here)*
- ✅ `parser.py` — pyslang-11 wrapper (`pyslang.syntax`/`pyslang.ast`); auto-adds
  the fw-hdl library + incdirs; `+incdir+`/`+define+` via `PreprocessorOptions`;
  diagnostics → `ErrorReporter`. `astdump.py` lists user (non-library) classes.
- ✅ `astdump.py` (`collect_user_classes`) — visits `getRoot()`, gathers user
  component classes (skips `zsp_*`/`fw_*` lib + template specializations). The
  `*_top.sv` `fw_root` binding collection is folded into P2 `bind/`.
- ✅ `type_mapper.py` — SV integral → `DataTypeInt(bits,signed)`; 1-bit `logic`
  carve-out allowed (LED pin); wider 4-state → hard error.
- ✅ `expr_mapper.py` — binary/unary/literal/named/member/call; **`ExprCompare`
  for relational** (regression-guarded); constant folding (`const_to_int` /
  `parse_int_token`); `LValueReference` resolution for compound assigns.
- ✅ `stmt_mapper.py` — `forever`→`StmtWhile(True)`; `if`/assign/compound/`++`/
  begin-end with 3-way body normalization; task call→`ExprAwait` beat;
  unsupported kinds → `FwHdlError`.
- ✅ `func_mapper.py` + `class_mapper.py` + `context.py` — `run`→async `Function`
  in `proc_processes`; own `ClassProperty` fields (port placeholder for `out`);
  run-locals hoisted to state fields with initial values; assembled into
  `ir.Context`. `ir_text.py` gives the `--dump-ir` view.
- ✅ `bind/elaborate.py` — `elaborate_binding()` reads the module pins, the
  `fw_root` clock/reset connections, and the `<top>_bind.connect()` bindings
  (`port.connect(bridge)` + the bridge's `new()` xtor instance), tracing the
  xtor's data port to the real pin → `BoundDesign(clock_pin, reset_pin,
  [PortBinding(class_port, protocol, pin, width, …)])`. `apply_binding()` injects
  the pin `FieldInOut`s (appended, indices preserved) + tags via `pragmas`.
- ✅ `bind/protocols.py` — **Option B table** (`fw_put_xtor_bridge` → registered
  `put` beat). Header restates the §3 caveat + migration trigger.
- ✅ `context.py` — `build_spl_context()` parses, maps each runnable component,
  elaborates+applies its binding → bound **SPL** `ir.Context`.
- (`FwHdlError` in `errors.py` serves as the strict unsupported-construct raiser;
  a separate `diagnostics.py` proved unnecessary.)

### 1.3 Lowering — `spl2rtl` (`fw/hdl/lower/`)  *(the novelty)* ✅
- ✅ `spl2rtl.py` — `_parse_loop` splits the `forever` body into beats
  (put/tick) + comb segments; allocates a `state` reg (omitted if 1 beat) and a
  `count` reg sized to the max tick; builds one `sync_processes` `Function`:
  `StmtIf(reset, reset-init, <state-chain>)`, put→`pin<=value`+advance,
  `tick(N)`→`count==N-1 ? wrap-comb+advance : count++`. SPL field refs are
  rewritten to fresh RTL field refs **by name**; the abstract `out` port is
  dropped. `validate_rtl_component` (in `ir_build`) is the §0-contract check
  (no separate `validate.py` needed).

### 1.4 Emit — `rtl2v` (`fw/hdl/emit/`) ✅
- ✅ `be_sv.py` — thin `SVGenerator(out_dir).generate(ctxt)` wrapper + optional
  module-name override. No emitter logic; **no be-sv changes were needed** for
  blinky.

### 1.5 CLI & flow (`fw/hdl/`) ✅
- ✅ `cli.py` — all four sub-commands wired: `sv2ir` (SPL IR / `--dump-ast`),
  `spl2rtl` (RTL IR dump), `rtl2v`/`synth` (emit SV, `synth` adds a report on
  stderr). Plusargs + `-I`/`-D`. *(IR-artifact JSON round-trip still TODO — verbs
  currently run from source; a later nicety.)*
- ✅ `flow.py` — `synth` orchestrator (`sv2ir → spl2rtl → rtl2v`) + `_report`
  (inputs/outputs/registers/clocked-process count).
- ✅ `__main__.py` — delegates to `cli.main()`.

### 1.6 DFM task (`fw/hdl/dfm.py` + `flow.dv` + `__ext__.py`)
*The vehicle for the `pytest_dfm` system tests (§2.3); promoted from P5 → P4.*
- ☐ `fw/hdl/dfm.py` — a **`fw.hdl.Synth`** task modeled on `zuspec.synth.dfm`
  (`TaskRunCtxt`/`TaskDataResult`/`FileSet`, memento up-to-date check). Consumes a
  `systemVerilogSource` FileSet (fw-hdl sources) + params (`top`, `top_module`,
  `reset_style`), runs the `synth` flow, and emits a generated-RTL
  `systemVerilogSource` FileSet for downstream `hdlsim.*` tasks.
- ☐ `fw/hdl/flow.dv` + `fw/hdl/__ext__.py` — register the `fw.hdl` package so
  `uses: fw.hdl.Synth` resolves (mirrors `zuspec.synth` `__ext__` + the pyproject
  `dv_flow` entry-point in §1.0).

### Build order (gated, each ends green)
1. ✅ **P0** 1.0–1.1 + `parser` + `cli sv2ir` dumping AST. *(18/18 unit tests green)*
2. ✅ **P1** 1.2 mappers → SPL `ir.Context` for blinky (class only, no binding). *(38/38 green)*
3. ✅ **P2** `bind/` → clock/reset/led pins injected + put port tagged. *(46/46 green)*
4. ✅ **P3** 1.3 `spl2rtl` + 1.4 `rtl2v` → `synth` emits lint-clean RTL that passes
   the real `blinky_tb` (`[blinky] PASS`). *(59/59 green + golden)*
5. **P4** 1.6 `fw.hdl.Synth` dfm task + the `pytest_dfm` system test (§2.3): generated
   RTL compiles and passes the existing `blinky_tb` under Verilator.
6. **P5** generalize: `counter` example, begin Option A.

---

## 2. Test plan

Tests live in **`tests/python/`** (repo root), split by whether they need a
simulator. Flow/simulation tests use **`pytest_dfm`** — the in-tree convention
(see `packages/dv-flow-libhdlsim/tests`): the `dvflow` fixture
(`pytest_dfm/__init__.py:6`, `runFlow`/`mkTask`/`runTask`) drives `dfm` task
graphs, and `hdlsim_available_sims()` (`dv_flow.libhdlsim.pytest`) parametrizes
over installed simulators (Verilator here) so the same test runs on any available
sim and **auto-skips when none is present**. Pure-Python IR tests stay plain
pytest (no sim, always run).

```
tests/python/
  unit/                         # plain pytest — pure Python, no simulator
    __init__.py
    test_ir_build.py            # §0 helpers produce contracted nodes (+ negative tests)
    test_parser.py              # pyslang load, +incdir/+define, lib files, diagnostics
    test_collect.py             # finds blinky class + fw_root bindings; skips lib classes
    test_type_mapper.py         # integral widths; 4-state diagnostic; led_t carve-out
    test_expr_mapper.py         # relational -> ExprCompare (regression on the spike trap)
    test_stmt_mapper.py         # forever->StmtWhile(True); if/assign; unsupported->error
    test_bind.py                # ✅ put-bridge -> led pin + tags; clock/reset pins
    test_spl2rtl.py             # beats->states; tick->counter; FieldInOut never a reg
    test_emit_be_sv.py          # RTL IR -> SV text assertions (ports/always/==/~)
    test_synth_golden.py        # full Python flow -> emitted SV == golden/blinky.rtl.sv
    golden/blinky.rtl.sv        # checked-in golden (the spike output)
  system/                       # pytest_dfm — builds & runs sims through dfm
    __init__.py
    conftest.py                 # exposes dvflow + hdlsim_available_sims (per libhdlsim)
    test_blinky_synth.py        # flow: fw.hdl.Synth -> SimImage -> SimRun ; assert PASS
    data/
      blinky/                   # fw-hdl sources (from tests/blinky)
      flow.dv                   # package wiring fw.hdl.Synth + hdlsim.<sim>.Sim*
```

### 2.1 Unit (fast, no external tools) — plain pytest
- ✅ `test_ir_build` — helpers yield contracted types; negative tests
  (`binop(Eq)` rejected, validator flags `ExprBin` compares, `reg()` is `Field`)
  + a be-sv emit smoke. *(`tests/python/unit/test_ir_build.py`, green)*
- ✅ `test_parser` — clean blinky parse, class discovery, library filtering,
  syntax-error reporting, `+define+` preprocessing. *(green)*
- ✅ `test_type_mapper` / `test_expr_mapper` / `test_stmt_mapper` — via
  self-contained snippets (no library): widths + 4-state carve-out;
  `ExprCompare` regression guard, constant folding, unary; forever/if/compound/
  `++`/await-beat/unsupported-error. *(green)*
  (`test_eq_is_exprcompare` is the explicit guard for the spike's `(state ? 0)` bug.)
- ✅ `test_spl2rtl` — beats→states, `tick`→7-bit counter, abstract `out` dropped,
  internal regs are plain `Field` (not `FieldInOut`), contract clean. *(green)*
- ✅ `test_emit_be_sv` — `input/output logic` pins, sized internal regs (not
  ports), `always @(posedge clock)`, `if (reset)`, `state == 0`, `led <= v`,
  `v <= ~v`. *(green)*
- ✅ `test_synth_golden` — full `flow.synth()` text == `golden/blinky.rtl.sv`;
  `FW_UPDATE_GOLDEN=1` rewrites it. *(green)*

### 2.2 sv2ir shape check — plain pytest
- ✅ `test_blinky_sv2ir` — `build_spl_context` on the blinky files; asserts the
  DESIGN §5 SPL shape: `out` port + `v` reg(init 0), `proc_processes=[run]`,
  `body[0]` is `StmtWhile(True)`, two awaited beats (`put`+`tick`),
  `v=~v` Invert, `tick(100)` folded. *(green)*

### 2.3 System / behavioral (the real proof — automated) ✅
- ✅ `system/test_blinky_sim.py` — generates blinky RTL, **lints it**
  (`verilator --lint-only -Wall`) and **runs it against the unmodified
  `tests/blinky/blinky_tb.sv`** under Verilator, asserting `"[blinky] PASS"`.
  Done for **both** front ends (`test_fwhdl_…` and `test_zdc_…`) → the
  behavioral multi-language proof. Auto-skips when Verilator is absent.
  *(Direct-Verilator form; the richer `pytest_dfm` + `fw.hdl.Synth` dfm-task
  version, §1.6, is a later upgrade — needs the dfm task built.)*
- ✅ `unit/test_lower_robustness.py` — error paths (`SplLowerError`: no run / no
  clock / no beats / unsupported beat) + a **multi-state FSM** (two ticks 5,3
  sharing one down-counter → 1-bit state, per-state reloads), which blinky/@zdc
  don't exercise.
- ✅ `unit/test_multilang_lowering.py`, `test_nomagic_firewall.py`,
  `test_every_cycle.py` — @zdc front end via the shared lowering; the no-magic
  import firewall; the `cycles(1)` every-cycle idiom.

### 2.4 Running / CI
- ✅ `pytest tests/python/unit` — 73 tests, no tools required (CI default).
- ✅ `pytest tests/python/system` — 2 behavioral tests; **auto-skips** when
  Verilator is absent (`shutil.which` guard). Full suite: **75 green**.

---

## 3. Sphinx docs plan (`docs/`)

`docs/` is currently empty. Stand up a project-level Sphinx site mirroring the
in-tree convention (`packages/zuspec-synth/docs`: `sphinx.ext.autodoc` +
`napoleon` + `viewcode` + `intersphinx`, `alabaster` theme).

```
docs/
  conf.py            # project "fw-hdl"; autodoc fw.hdl.*; intersphinx -> zuspec, python
  Makefile           # standard sphinx-build
  index.rst          # overview + toctrees (mirrors zuspec-synth/index.rst)
  quickstart.rst     # install + `fw-hdl synth tests/blinky/*.sv --top blinky ...`
  concepts.rst       # the SV->SPL IR->RTL IR->Verilog pipeline (condensed DESIGN §1-5)
  cli.rst            # sub-commands + plusarg options (the §6 table)
  blinky_walkthrough.rst  # the worked example end-to-end, incl. the emitted RTL
  binding.rst        # the class->module boundary + Option B debt + migration trigger
  ir_contract.rst    # the §0 table — how IR maps to be-sv output (for contributors)
  api.rst            # automodule:: fw.hdl.fe / lower / emit / cli
  _static/  _templates/
```

- ☐ `conf.py` — copy `zuspec-synth/docs/conf.py`; set project/release; `autodoc`
  `bysource`; `intersphinx_mapping` to zuspec + python; add `python/` to
  `sys.path` so autodoc imports `fw.hdl`.
- ☐ `index.rst` — overview paragraph + "Quick Links" + User Guide / Reference
  toctrees (same structure as `zuspec-synth`).
- ☐ Docstrings are the source of truth: write **NumPy-style** docstrings on every
  public class/function (napoleon is NumPy-configured upstream) so `api.rst`
  autodoc stays populated — no hand-maintained API prose.
- ☐ `blinky_walkthrough.rst` embeds the actual emitted `blinky.sv` via a
  `literalinclude` of the golden file (doc stays truthful to tests).
- ☐ `quickstart.rst` commands are copy-runnable and covered by a docs smoke check.
- ☐ Build: `make -C docs html`; add a `docs-build` check (warnings-as-errors,
  `-W`) to catch broken autodoc/refs. Optional follow-on: a `flow.yaml` docs task.

### Docs ↔ code sync rules
- The `ir_contract.rst` table and `fw/hdl/ir_build.py` must agree; a test
  (`test_docs_contract`) can assert the helper set matches the documented rows.
- `cli.rst` option table generated from / checked against `argparse` help.

---

## 4. Deliverables checklist (review-gate per phase)

| phase | code | tests green | docs |
|---|---|---|---|
| P0 | ✅ pkg, errors, config, ir_build, parser, cli(sv2ir) | ✅ unit: ir_build, parser | conf.py + index + quickstart stub |
| P1 | ✅ fe mappers → SPL IR | ✅ unit mappers + sv2ir shape | concepts.rst |
| P2 | ✅ bind/ | ✅ test_bind | binding.rst |
| P3 | ✅ spl2rtl, emit, flow, cli(all) | ✅ unit spl2rtl/emit + **synth golden** | cli.rst, ir_contract.rst, walkthrough |
| P4 | `fw.hdl.Synth` dfm task + flow.dv | **pytest_dfm equivalence vs blinky_tb** | walkthrough finalized w/ literalinclude |
| P5 | counter, Option A start | counter parity tests | examples page |

---

## 5. Open items / explicit non-goals for v1

- **Non-goals:** multiple concurrent processes, sub-component hierarchy, derived
  clock domains, non-`put` protocols, 4-state synthesis semantics. Structure
  supports them (DESIGN §7.5) but they are out of v1 scope.
- **Known debt:** Option B transactor table (DESIGN §3) — first non-`put`/
  user-defined transactor triggers the Option A migration.
- **Resolved (review):** tests live in **`tests/python/`**; sim/flow tests use
  **`pytest_dfm`** (per `packages/dv-flow-libhdlsim`), parametrized over
  `hdlsim_available_sims()`. Package/console-script named `fw-hdl` (`fw.hdl.cli:main`).
