# Protocol-kit follow-ups

Loose ends left after the protocol-kit plan (K0–K11, layer 2), which was
committed and pushed on 2026-11-18 (`mballance/core-layer1` in the
packages and `mballance/sync-design-stye` in the root). The step outcomes
are in the runner's plan:
`.work-packet/runs/74895649-…/state/protocol-kit-plan.md` §8.

## User benefit

- A green root test suite (no "known failures" to look past), so a real
  regression shows up.
- fe-sv answers the same protocol questions as rt-sv
  (`abstractor_for`, `xtors`, cfg values seen by sinks), so a design
  behaves the same under static elaboration and in simulation.
- The protocol IR carries everything the spec says (API methods, the
  endpoint's imp, bundle protocol), so back ends and tools can read it
  instead of re-deriving it from source.
- Formal (SBY/yosys) and Verilog-2005 flows take generated RTL directly,
  with no hand rewriting of type parameters.

## 0. Status

| Item | Status | Notes |
|---|---|---|
| F1 Root tests: install root `fw-hdl` | **done** (uncommitted): the 2 named tests and 34 more pass; 16 XLS-path failures remain, see F13 (`build/f1-rerun.log`) | §1 |
| F13 16 XLS-engine test failures | **done**: libsynth `main` fast-forwarded to `aaceb9a` and pushed; the 7 files now 43/43 pass (`build/f13-rerun.log`) | §2 |
| F2 Full root suite | **done**: final run 831 passed, 0 failed, 3 skipped, 1 xfailed, 46 min (`build/full-root-2.log`); first run: 52 failed / 779 passed / 3 skipped / 1 xfailed, 48 min; all 52 checked so far are F1 | §2 |
| F3 Protocol IR fields (gap 4) | **done** (uncommitted, §8) | §3 |
| F4 cfg binding and on-change listeners in the IR (gap 3) | **done** (uncommitted, §8); netlist listeners deferred | §3 |
| F5 Ctor-returning queries in fe-sv (gap 1) | **done** (uncommitted, §8) | §3 |
| F6 Width-param lowering as an IR transform (gap 7) | **done** (uncommitted, §12) | §3 |
| F7 be-sv `!==`, struct default-zero (G7, G4) | **done** (uncommitted, §10) | §3 |
| F8 Attributes, 4-state, AXI core (gap 6) | Q9 and F8a **done** (§13); F8b **next**: attributes/`fw_opt`, struct-valued params, class-local typedefs, emit order | §3 |
| F9 Complete protocol-package guide | **done** (uncommitted): 6 pages + `docs/examples/sbus/`; sphinx -W, dfm tests, Verilator example pass | §5 |
| F10 gen_tb/gen_bind with nested bundles | **done** (uncommitted, §9); design §7 (found by F9) | §6, §7 |
| F11 GenKit silent drops → diagnostics | **done** (uncommitted, §10) | §6 |
| F12 Spec/tool mismatches (`FW-E-PROTO-XTOR`, role check, stale semantics text) | **done** except the role check (Q9) (uncommitted, §10) |
| F14 zuspec-be-sv: 14 failures that predate this work | **done** (uncommitted): 14/14 pass (`zuspec-be-sv/build/f14-fix.log`) | §6 |
| ivpm.yaml duplicate `uses:` | not started | §1 |

Already closed (checked 2026-11-18): bundle `protocol`/`role` netlist
members (`fw-hdl-fe-sv netlist.py:188-194`), `SVMapper.get_types()`
(`zuspec-fe-sv mapper.py:84-87`).

## 1. Root test failures (F1)

`test_knobs.py::test_dfm_resolve` and
`test_extern.py::test_through_dfm_tasks` fail with "Import file
fw.hdl.spl not found". Cause: the root project is not installed in
`packages/python`, so the `dv_flow.mgr` entry point `fw-hdl =
fw.hdl.dfm_ext` (pyproject.toml:49-50) is missing for the `dfm`
subprocess. The tests themselves import `fw.hdl` only through conftest
`sys.path` edits.

Fix: `pip install --no-deps -e .` at the root. Risk: `python/fw/__init__.py`
and `python/fw/hdl/__init__.py` are regular packages, and fe-sv/rt-sv
install `fw.hdl` as a namespace. If installing hides `fw.hdl.fe.sv` or
`fw.hdl.rt.*`, change those two inits to `pkgutil.extend_path`. Find out
why IVPM did not install the root project (pyproject.toml:53-54 expects
it to).

Also: `ivpm.yaml:15-17` gives the `default` dep-set two `uses:` keys;
the second (`dev`) wins silently.

## 2. Full root suite (F2)

First full run (2026-11-18): 52 failed, 779 passed, 3 skipped,
1 xfailed, 48 min (`build/full-root.log`). Almost all failures, nearly all
in `tests/xls`, are `dfm` reporting "Import file fw.hdl.{spl,knobs,report,check}
not found": the F1 cause.

F1 fix: installing the root (`uv pip install --python
packages/python/bin/python --no-deps -e .`; the venv has no pip) hid
`fw.hdl.rt`. Root's `fw` and `fw.hdl` were regular packages, and rt-sv's
editable finder only resolves `fw.hdl.rt` under a namespace `fw.hdl`.
fe-sv got through because its finder maps `fw.hdl.fe.sv` by its full
name. Fix: delete `python/fw/__init__.py` and `python/fw/hdl/__init__.py`,
so both are namespace packages as they already are in fe-sv/rt-sv
(pyproject `packages.find` defaults to `namespaces = true`). Lost: the
`fw.hdl` docstring (pipeline overview) and `__version__` (unused). Open:
why IVPM did not install the root project.

Rerun after F1 (the 20 failing files + `tests/python/unit`): 16 failed,
486 passed. The remaining failures are all on the XLS engine path (F13):
`ImportError: CODEGEN_DEFAULTS` from `dv_flow.libsynth.xls.codegen`
(test_engine_path ×4), Verilator MODMISSING `xls_fifo_wrapper` (test_sp_mem),
and codegen/latency assertions (block_codegen, latency_contract,
latency_report, multi_proc, resp_tracker). F13 triage: all 16 fail deterministically, for one reason.
`packages/dv-flow-libsynth` is on `main` (3f96fcf), but the root repo and
`zuspec-be-xls` need three commits that exist only on
`origin/wpk/results-ir`:
- `0a300a1` adds `CODEGEN_DEFAULTS` and `codegen_argv`;
- `822e27e` adds per-module codegen options (`xlsCodegenOptions`);
- `aaceb9a` joins repeated `--io_constraints`.

Without `822e27e`, the knob and storage options are dropped: every block gets
one stage, and `--fifo_module=fw_xls_fifo_wrapper` is lost (hence the
missing `xls_fifo_wrapper`). With the branch first on `PYTHONPATH`, all 16
pass (`build/xls-triage-rir.log`).

Fix: fast-forward libsynth `main` to `wpk/results-ir` and push it.
`ivpm.yaml:64-65` fetches from GitHub `dv-flow/dv-flow-libsynth` with no
branch, so the mirror needs the commits too.

## 3. Implementation gaps

| # | Gap | Evidence | Size / repo |
|---|---|---|---|
| F3 | fe-sv `ir_map.py:1533-1590` never sets `ApiEndpoint.imp`, `DataTypeClass.bundle_protocol` or API `methods` (API types are empty `DataTypeProtocol`). Hub `cfg_type`/`functions`/`xfer_time`/`mismatch` are unset, and stale: the spec moved timing to channels (`protocols.md:256-260`) and cfg to endpoints (`:226-228`). | ir-core `protocol_hub.py:61-108` | S each; fe-sv + ir-core |
| F4 | fe-sv `cfg_set` stores on the source only (`rt.py:416`); `add_listener` is a no-op (`rt.py:940`); `check_cfg` sets `c.src`, never `cfg` (`rt.py:462-490`). Spec: push when bound and on `set` (`protocols.md:230-236`). | | S–M; fe-sv |
| F5 | `xtors`/`abstractors`/`abstractor_for` → "fe-sv does not implement" (`rt.py:1018,1064`). Plan: a static `__fw_ctor()` in fe-sv's `fw_xtor_utils`/`fw_abstractor_utils` (`share/sv/fw_hdl_macros.svh:62-80`) returning `fw_ctor_of #(fw_component, this_t)::get()`, served by the existing `ctor_get` (`rt.py:815`). No conformance scenario yet; add one. | spec `protocols.md:106,110` | S; fe-sv + spec scenario |
| F6 | No option to lower packed type params to width params; `test_proc_emit.py:224-227` rewrites text by hand for SBY. Do it as a Zuspec IR transform. | | M; zuspec-ir-core |
| F7 | be-sv has no `!==` (X/Z compares equal); no `'{default:0}`. | plan §8.30 | S; zuspec-be-sv |
| F8 | Class/struct-member attributes (`fw_opt`) not mapped (`class_mapper.py:140`); 4-state fields rejected (`:375-380`), losing `fw_mem_if` `logic` defaults; struct-valued params and class-local typedefs (real AXI core); emitter puts functions before tasks (`sv_emit.py:281-287`). | plan §8.25, §8.31 | M–L; zuspec-fe-sv, ir-core |

Unverified: type-param aliases (`scenario::test_put_if::T`) leaking from
`get_types()` (§8.28).

## 4. Owner decisions (2026-11-18)

- **Q1 Stale hub fields:** yes, delete `cfg_type`, `functions`,
  `xfer_time` and `mismatch` from zuspec-ir-core (F3).
- **Q2 cfg in static elaboration:** static elaboration only *connects* a
  change to the action that runs on change. It records the source→sink
  binding and the listener registrations in the IR and netlist. It does not
  run listeners or simulate the push (F4).
- **Q3 `abstractor_for` scope:** the classes the design names. Make the
  spec wording say so (F5).
- **Q4 Width-param lowering:** a Zuspec IR transform (F6).
- **Q5 `fw_opt`:** not opposed, but the application has to be clear first. Today:
  per-instance optional signals selected by a parameter field (AXI
  `AWLOCK`/`QOS`/`USER`…). The struct member is absent when the parameter's
  field is 0, so its input pin is tied to 0 and its output pin dropped. It
  lives only in the root sync `Emit` pin shell (`emit/pins.py`), and the
  generated `_mask` guesses around its absence (`gen/payloads.py:7-8`).
  Parked until there is a concrete user (F8).
- **Q6 4-state:** the IR should model it, but class emission will not use it
  (F8, parked).
- **Q7 fw-proto-axi-new guide:** leave it for now. Make the guide here
  (`fw-hdl-spec/docs/protocol-packages.rst`) complete and comprehensive
  (F9).

## 5. F9 Protocol-package guide

K11.4 (plan §8.59) rewrote the AXI guide's steps 0–7 for the new path and
dropped: the Known-limits table, the attributes (`fw_opt`, `fw_api`, …),
the rules layer, flow tasks and goldens. Check the guide against (a) the source
guide `/packets/featherweight-ip/fw-proto-axi-new/docs/writing-a-protocol-package.md`
(read-only), (b) what GenKit/Scan/rt-sv/fe-sv actually implement, (c)
the `fw-proto-kit` skill. Fill gaps: a worked example end to end, every
generated artifact and how to use it, testing (class-level, formal,
bind), wrap_rtl, a Known-limits table that tracks F3–F8, and error
codes. Check: sphinx -W, examples compile in Verilator.

F9 outcome (2026-11-18): `fw-hdl-spec/docs/protocol-packages.rst` plus
`docs/protocol-packages/{declare,generate,behaviour,testing,reference}.rst`,
built around one example (`docs/examples/sbus/`, a request/response bus: kit,
behaviour, back-to-back test, RTL memory + wrapper + test, `flow.yaml`,
`check.py`). `skills/fw-proto-kit/SKILL.md` points at it. Logs:
`build/f9-{sphinx,dfm,check}.log`. The sbus RTL bench is hand-written
because of F10.

## 6. Found while writing the guide (F10–F12)

- **F10 `gen_tb`/`gen_bind` with a bundle-of-channels port** (fe-sv
  `gen/tb.py`, `gen/bind.py`):
  - it doesn't import a non-parameterized kit's generated package;
  - it leaves payload struct types unqualified;
  - it bridges the target-driven channel (`rsp`) in the wrong direction;
  - `bind=True` emits `mon_<port>.p.connect`, but the monitor's member is
    `pins`.
- **F11 GenKit drops things silently**; each needs a diagnostic or a fix:
  - a parameterized bundle that the source never specializes gets no
    channel APIs or transactors;
  - a payload struct with a `logic` member loses its helpers and per-field
    pins (tied to Q6/F8);
  - a struct declared inside a class comes out as `pkg::bundle::req_t`;
  - `FW-E-GEN-PKG` says "found no package" when a kit registers only std
    APIs.
- **F12 Spec vs tools:**
  - no tool reports `FW-E-PROTO-XTOR` and no scenario covers it;
  - nothing checks that a transactor's two sides agree on its role;
  - `semantics/protocols.md` still describes the old conventions (one
    parameter struct, class-local typedefs, `fw_default`).
- Minor: txn `sprint` uses `%p` (Verilator prints a packed struct as one
  number); the `fw_mem_if` type-param defaults are lost (with F8).

## 7. F10 design (proposed 2026-11-18)

A bundle of channels is a nested bundle: `fw_rv_if` is itself a bundle
with `fw_rv_proto`, so `sbus_bundle` (`fw-hdl-spec
docs/examples/sbus/src/sbus_pkg.sv:41`) is a bundle of bundles. Elaboration
handles nesting (`bundle_nested` scenario); `gen_tb`/`gen_bind` treat a
port as one flat bundle, and have only been tested on single rv channels
(`examples/wrap_rtl`). That is the cause of all four F10 bugs.

Design: one walk over a port's bundle tree, shared by `gen_tb`, `gen_bind`
and the pins generator, in fe-sv's protocol IR helpers (a query over IR,
not code in each generator). The walk carries:
- **direction**: reversed at each `fw_mirror` on the path;
- **member path**: the pin name is the path joined with `_`
  (`s_req_valid`);
- **transactor level**: the **outermost** level that carries a protocol
  gets that protocol's opposite-role transactor and its monitor (`sbus`
  → `sbus_initiator`/`sbus_monitor`, not two rv xtors). That level's kit
  package is imported and its payload types are qualified;
- **bridges**: every leaf signal gets one `fw_pin_bridge` with its
  computed direction.

**Missing transactor → error** (owner, 2026-11-18: every protocol is
expected to have transactors). If the outermost protocol level has no
opposite-role transactor (or monitor), `gen_tb`/`gen_bind` report an
error naming the protocol, the role and the port. They never fall back to
the inner channels' transactors. Tests: a nested-bundle golden, and
the sbus RTL bench (`docs/examples/sbus/tb/sbus_rtl_tb.sv`, hand-written
today) generated instead.

## 8. F3–F5 outcomes (2026-11-18, uncommitted)

Suites (logs in each package's `build/`): fe-sv 288/13 (was 280/13);
rt-sv conformance 95/0/11 (was 94); rt-sv pytest 19; ir-core 231/3
(was 230); zuspec-fe-sv 144/5; API check PASS; spec sphinx -W,
`dfm run tests` rc 0.

- **F3:**
  - The four hub fields are deleted.
  - fe-sv writes bundles as `DataTypeBundle`, not `DataTypeClass`, so
    `bundle_protocol` was added to `DataTypeBundle`. For a generic bundle
    it is written over the bundle's own parameters.
  - API types come from the zuspec-fe-sv class mapper, with their methods.
    A mapper error becomes warning `FW-W-SCAN-IR`.
  - `set_imp` is recorded in `ApiEndpoint.imp`. An imp with no path
    (one held in a local variable) is written as `[]`.
- **F4:**
  - New IR record `CfgListener` (`DataTypeComponent.cfg_listeners`).
  - Each sink's resolved source is a `CfgConnection(derived=True)`.
  - No values are pushed and no listeners run.
  - Spec `semantics/protocols.md` "Static view" says so.
  - **Deferred:** listeners in the netlist. That needs `netlist.md`, the
    schema, rt-sv output, `cfg_ep_basic/expect.json`, and a way to write a
    listener that has no path.
- **F5:**
  - A static `__fw_ctor()` in fe-sv's xtor/abstractor utils macros.
  - `abstractors()`/`abstractor_for` register every converter the design
    names (`scan.register_named`).
  - `xtors()` is no longer in the spec, so fe-sv's special case is gone.
    rt-sv's README still mentions it.
  - Spec and guide wording now says "classes the design names".
  - New scenario `proto_abs_query` passes in fe-sv and rt-sv.

Found, not fixed:
- zuspec-fe-sv `map_protocol` on a specialization gives
  `scenario::test_put_if::T`, one key per generic, so `#(byte)` and
  `#(test_pkt_t)` collide. This confirms §8.28.
- fe-sv registers uncreated converters only when a query runs; rt-sv
  always does. The netlist `protocols` table can therefore differ.
- A specialization named only inside a function body is missed.

## 9. F10 outcome (2026-11-18, uncommitted)

- **The walk:** `walk_port(port, owner=None) -> PortWalk` in fe-sv
  `fw/hdl/fe/sv/protocols.py`. It walks the elaborated object tree, not
  the IR, because the IR keeps `fw_rv_if` generic (`T` unsubstituted) and
  so has neither concrete leaf types nor the scan's protocol keys.
  - `PortWalk.levels`: the outermost protocol levels, each with the DUT's
    role.
  - `PortWalk.pins`: each pin's path, name and direction (reversed at each
    mirror).
- **Transactor choice:** `gen_tb` and `gen_bind` share `_xtor_of`.
  - New errors `FW-E-TB-XTOR` and `FW-E-TB-MON` name the protocol, role and
    port.
  - The connect line uses `xtor_pins(cls)`, the transactor's real pin
    member: `pins` when generated, `p` for std's rv monitor.
- **Helpers added:** `qual_type_name` and `package_of` (`types.py`),
  `xtor_class` (`scan.py`).
- **The pins generator does not use the walk:** it works per kit, on
  generic channels.
- **Tests:**
  - `unit/test_walk_port.py` and `unit/src/deep_bundle_pkg.sv`: mirrors at
    three levels, pin names and directions checked against the emitted
    ports, both errors.
  - `e2e/test_gen_tb_sbus.py`: the generated sbus bench passes in
    Verilator, and a planted RTL bug makes it fail.
- **sbus example:** `tb/sbus_rtl_tb.sv` is now just the test, a subclass
  of the generated class. `check.py` generates the bench and the bind
  module.
- **Guide:** `testing.rst`, `reference.rst`, `protocols.rst` (a paragraph
  on nested bundles).
- **Suites:** fe-sv 295/13 (was 288), conformance 95/0/11, sphinx -W rc 0,
  sbus check PASS.

- **Q8, owner decision 2026-11-18: error.** A port is one protocol. If a
  collection of protocol ports is needed, that is a different construct
  from a bundle port. Done (uncommitted):
  - `gen_tb`/`gen_bind` report `FW-E-TB-NOPROTO` for a port whose bundle
    has no protocol but holds bundles that do;
  - the fixture top `deep_pkg::dut_q`;
  - test `test_port_without_protocol`;
  - guide `reference.rst` and `protocols.rst`.

Open:
- Arrays of bundle ports have not been tried.

## 10. F7, F11, F12 outcomes (2026-11-18, uncommitted)

- **F7:**
  - ir-core `expr.py` gets case-equality ops; `ExprStructLiteral` gets a
    `default` field.
  - zuspec-fe-sv maps `===`/`!==`; `==?`/`!=?` are still rejected.
  - be-sv emits `===`/`!==` and `'{a: v, default: 0}`.
  - fe-sv `gen/irb.py` gets `ne()` and `zero()`, and the payload and txn
    compare helpers use `!==`. Four goldens were regenerated.
- **F11:** `gen_kit(diags=...)`, and the GenKit dfm task reports the
  diagnostics as markers. New codes:
  - `FW-W-GEN-UNSPEC`: a parameterized bundle that is never specialized.
  - `FW-W-GEN-4STATE`: a `logic` member. This also fixes the channel API
    declaring such a payload as `int`.
  - `FW-E-GEN-SCOPE`: a payload typedef inside a class.
  - `FW-E-GEN-PKG`: now accurate. The protocol's package counts; a
    std-only kit no longer comes out as `fw_hdl_std_pkg_gen_pkg`.

  The guide lists all four.
- **F12:**
  - `FW-E-PROTO-XTOR` is checked in fe-sv (at registration) and rt-sv
    (after connect). New scenario `proto_xtor_bad`.
  - Two exemptions: a monitor needs no API endpoint, and the derived
    `<p>_req_if`/`<p>_rsp_if` count as the API side.
  - `diagnostics.md` now has rt-sv checking this too.
  - Stale convention text in `protocols.md` is rewritten, and the rt-sv
    README no longer mentions `xtors(role)`.
- **Suites:**

  | Suite | Now | Before |
  |---|---|---|
  | fe-sv | 304/13 | 295 |
  | conformance | 96/0/11 | 95 |
  | rt-sv pytest | 19 | 19 |
  | ir-core | 231/3 | 231/3 |
  | zuspec-fe-sv | 146/5 | 144 |
  | zuspec-be-sv | 230 passed, 14 failed | 228 passed, the same 14 failed (F14) |

  API check, sphinx -W, `dfm run tests` and sbus check pass.

Owner decisions (2026-11-18):
- **Q9, role from the pin side only.** A converter's role is its pin-side
  mixin (`fw_bundle` = initiator, `fw_mirror` = target, `fw_monitor` =
  monitor). The method side has no role rule and there is no
  method-vs-pin check: two initiator-pin ports with different method
  interfaces don't happen. Spec `protocols.md` "Roles are derived" to be
  rewritten.
- **Q10, accepted:** both exemptions and the run-time check. The owner
  also allows marking a transactor explicitly with a dedicated base class
  (e.g. to tell it from a channel), where that makes classification
  cleaner than inferring it.
- **Q11:** no filter; model 4-state in the IR (F8), which removes the
  warnings at the source.

Earlier questions, now answered above:
- **Q9:** the transactor role rule. The spec says "outbound req or inbound
  rsp = initiator", but `fw_rv_initiator` takes its requests in through an
  export, so the rule would make std's own initiator fail. Proposed
  wording: "an initiator transactor takes requests in and sends responses
  out at its endpoints; a target the reverse; a monitor has no method-side
  role; disagreement is `FW-E-PROTO-XTOR`."
- **Q10:** accept the two `FW-E-PROTO-XTOR` exemptions and the run-time
  check?
- **Q11:** GenKit now reports `FW-W-SCAN-IR` warnings that used to be
  dropped (e.g. `test_put_if #(logic[W-1:0])`). Filter them?

## 11. F14 outcome (2026-11-18, uncommitted)

The 14 failing be-sv tests are all Verilator perf tests in
`tests/performance/` (`test_sim_perf.py`, `test_scaling_analysis.py`,
`test_backend_comparison.py`). dv-flow-libhdlsim 74cd85f (Jul 2026) made
SimRun call `ctxt.mkDataItem`, which needs `TaskSetRunner.builder`
(dv-flow-mgr `task_runner.py:385`). These tests never set it. Fix: one
`runner.builder = builder` per file. They failed on committed HEAD too.

Not done:
- `pytest.ini` blames sim failures on "no simulator on PATH", which is
  wrong.
- `tests/unit/test_sim.py` (excluded) and part of `test_xtor_smoke.py`
  build the runner the same way, so they probably have the same bug.

## 12. F6 outcome (2026-11-18, uncommitted)

- **The transform:** zuspec-ir-core `xf/width_params.py`,
  `lower_type_params_to_widths(ctxt, components=None, *, suffix="_W")` (or
  `TypeParamWidthPass`). It changes the IR in place and returns a report
  of what it lowered and what it kept.
- **What it does:** `parameter type T` becomes `parameter int T_W`.
  Every use becomes `T_W` bits wide; `$bits(T)` becomes `T_W`; overrides
  are renamed wherever the component is instantiated (child fields, module
  instances, generate blocks).
- **What qualifies:** a generated component whose type parameter has a
  packed integer vector default, every override packed and of the same
  signedness, and no other use of the parameter.
- **What is kept and reported:** struct- or enum-typed parameters, no
  default, a mixed override, a name clash, and extern components.
- **Hook-up:** fe-sv `emit_sv(..., width_params=False)` and the EmitSV dfm
  task option `width_params`; a parameter that is kept becomes a Warning
  marker. `test_proc_emit.py::test_rv_formal` now uses the transform in
  place of the hand rewrite, and the SBY bmc and cover tasks pass.
- **Tests:** ir-core `tests/xf/test_width_params.py` (6); be-sv
  `tests/unit/test_width_params_emit.py` (3): Verilator lint and yosys
  `read -formal`. Without the pass, yosys fails.
- **Suites:** ir-core 237/3, fe-sv 304/13, be-sv 247/4/0 failed (with F14).

Open:
- Struct-typed parameters are not flattened.
- `emit_sv`/EmitSV don't pass the `components` filter through yet.
- The width name is always `<T>_W`, so harnesses override `.T_W(...)`.

## 13. Q9 and F8a outcomes (2026-11-18)

- **Q9:**
  - Spec `protocols.md` "Roles are derived" now says the role comes from
    the pin side only, with no method-side rule and no comparison.
    `diagnostics.md`, `protocols.rst`, the guide's `behaviour.rst`, the
    `fw_socket.svh` and `fw_hdl_macros.svh` comments say the same.
  - A socket has no role against a protocol.
  - fe-sv and rt-sv already derived the role from the pin mixin only.
- **F8a:**
  - ir-core already had `DataTypeInt.four_state`, with a round-trip test.
  - zuspec-fe-sv maps `logic`/`reg`/`integer` as 4-state instead of
    rejecting them, so `fw_mem_if` keeps its defaults.
  - Specializations map with their actual argument types, which fixes the
    `#(byte)`/`#(test_pkt_t)` collision.
  - be-sv `sync_param` no longer turns a 4-state signed 32-bit type into
    `int`.
  - GenKit still skips helpers for a struct with a `logic` member
    (`FW-W-GEN-4STATE`).
  - `FW-W-SCAN-IR` warnings: 19 before, 0 now.
  - The guide's `generate.rst` (`compare` uses `!==`) and the Known-limits
    F6 row are updated.
- **Suites:** fe-sv 305/13, conformance 96/0/11, rt-sv 19, ir-core 237/3,
  zuspec-fe-sv 148/5, be-sv 248/4/0, API PASS, sphinx -W and `dfm run
  tests` rc 0, sbus PASS, root check set 355/2 skipped.

Open:
- **Transactor base class:** would let rt-sv know a converter's role at
  registration. Today a converter nobody creates falls back to
  "initiator" in the netlist. It would also settle fe-sv's role for a
  class with several bundle members.
- Should the block-signature JSON carry `four_state` (a schema change)?
- Listeners in the netlist (F4, deferred).
