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
| F5 Ctor-returning queries in fe-sv (gap 1) | **done** (uncommitted, §8); superseded: the queries were dropped as test-only (§14) | §3 |
| F6 Width-param lowering as an IR transform (gap 7) | **done** (uncommitted, §12) | §3 |
| F7 be-sv `!==`, struct default-zero (G7, G4) | **done** (uncommitted, §10) | §3 |
| F15 `four_state` in block signature; cfg listeners in netlist | **done** (uncommitted, §16); Q16-Q18 decided, Q16 done (§16) |
| F16 Transactor role base classes | **done** (uncommitted, §14); FW-E-PROTO-XTOR static-only; test-only protocol queries dropped |
| F17 No reliance on `$typename` except debug | **done** (uncommitted, §15, §17): no string/type-text lookups, no `%p`; acc introspection in `fw_hdl_pkg` |
| F8 Attributes, 4-state, AXI core (gap 6) | Q9 and F8a **done** (§13); F8b **done** (uncommitted, §18): the real AXI core round-trips (packages in the IR, class typedefs over `P`, attributes, method order); `fw_opt` meaning stays parked (Q5) | §3 |
| F9 Complete protocol-package guide | **done** (uncommitted): 6 pages + `docs/examples/sbus/`; sphinx -W, dfm tests, Verilator example pass | §5 |
| F10 gen_tb/gen_bind with nested bundles | **done** (uncommitted, §9); design §7 (found by F9) | §6, §7 |
| F11 GenKit silent drops → diagnostics | **done** (uncommitted, §10) | §6 |
| F12 Spec/tool mismatches (`FW-E-PROTO-XTOR`, role check, stale semantics text) | **done** (uncommitted, §10); the role check is moot: roles come from the base class (F16), and FW-E-PROTO-XTOR is static-only |
| F14 zuspec-be-sv: 14 failures that predate this work | **done** (uncommitted): 14/14 pass (`zuspec-be-sv/build/f14-fix.log`) | §6 |
| ivpm.yaml duplicate `uses:` | **done** (uncommitted): the dead `uses: use` removed; `default` still uses `dev`, as YAML already resolved it | §1 |
| be-sv excluded sim tests (F14 leftovers) | **done** (uncommitted, §11): `test_sim.py` sets `runner.builder`, back in the suite (2/2); `test_xtor_smoke.py` gets the same fix but stays excluded for API drift; be-sv 250/4/3 deselected | §11 |
| fe-sv lint for `add_listener` in `run()` | **not doing**: fe-sv never runs `run()`, and FW-E-CONN-PHASE for `add_listener` is defined as run-time; a static lint needs a new spec diagnostic first | §16 |
| Root suite after F15-F17 | **done**: 831 passed, 0 failed, 3 skipped, 1 xfailed, 48 min (`build/full-root-f17.log`); the run overlapped the 8b.1-8b.3 edits | §2 |

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

Follow-up (2026-11-20, uncommitted): `tests/unit/test_sim.py` and the
sim cases of `test_xtor_smoke.py` had the same missing `runner.builder`.
Both set it now. `test_sim.py` passes (2/2) and is no longer excluded;
`test_xtor_smoke.py` stays excluded because its other failures are API
drift (`SVGenerator._collect_local_vars()` signature, stale expected
text). The `pytest.ini` comment no longer blames a missing simulator.
be-sv: 250 passed, 4 skipped, 3 deselected.

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

Owner decisions (2026-11-18): add `four_state` to the block signature;
cfg listeners must be in the netlist; both in progress (F15).

## 14. F16 Transactor role base classes (agreed 2026-11-18; probe passed)

The owner agreed: a transactor names the bundle type it supports, which
is more natural as a base-class parameter than as a further macro
argument.
- **Classes:** `fw_xtor_initiator`, `fw_xtor_target`, `fw_xtor_monitor`,
  each `#(type B)`. Each holds `pins` (`fw_bundle`/`fw_mirror`/`fw_monitor
  #(B)`) created in its `build()`, a static `role()`, and a static
  `protocol()` = `B::__fw_bundle_protocol()`.
- **Registration:** `fw_xtor_utils(C)` / `fw_xtor_param_utils(C)` lose the
  `PROTO` argument.
- **Method side:** stays in the subclass (Q9).
- **Replaces:** rt-sv's instance-scanning `xtor_role` (a converter that is
  never created falls back to initiator), fe-sv's "first pin member" role
  rule, and `xtor_pins` guessing `pins` vs `p`.
- **To migrate:** std rv initiator, target and monitor (`p` becomes
  `pins`), the GenKit transactor generator, the sbus example, the guide,
  the spec bindings and macros, rt-sv and fe-sv.
- **Probe:** `docs/design/probes/xtor-base/` (README, `run.sh`,
  `expected.txt`). Verilator 5.055 passes: static role and protocol on
  classes never created, distinct specializations, registration in a
  static initializer, `pins` from the base, and `$typename(this_t)` keys
  that stay distinct.

### F16 on the F17 basis (owner, 2026-11-19)

No run-time lookup by type text, and no lookup at all where the type
system already knows the answer (see §15 "Lookups"):
- **Role and protocol** are static functions of the base class. Nothing
  scans instances (`xtor_role` goes) or guesses the pin member (`pins`
  always; `xtor_pins` goes).
- **Instance identity:** the base class's `build()` body (rt-sv) records
  the instance as a transactor of `protocol()` with `role()`, from
  static information. No `conv_by_type`.
- **Class registration** (for `fw_protocol::xtors(p)` and the netlist's
  converter table): the macro's static initializer registers the class
  under its protocol handle, the type-factory instance. The family name
  for FW-E-PROTO-XTOR's path is the macro's stringified `C`.
- **Channel APIs:** GenKit emits their registration in the protocol's
  `declare()`, so FW-E-PROTO-XTOR doesn't match `<p>_req_if` by name.
- **Conformance:** a transactor with no bundle port (`bad_p_xtor`) or a
  bundle of another protocol (`nobundle_xtor`) can no longer be written.
  Both `proto_xtor_bad` cases are retired; the base class makes them
  impossible.

### F16 migration sites (survey 2026-11-19, about 94)

- **fw-hdl-spec:** `bindings/sv/fw_hdl_macros.svh:129-152` (macros and
  docs), `fw_protocol.svh:17`; `std/fw_rv_xtor.svh:16,70,177` (monitor
  `p` → `pins`); conformance `proto_xtor`, `proto_xtor_param`,
  `proto_xtor_bad` (2 cases retired), `cfg_explicit:28-29`, two
  `meta.json`, `README.md:105-107`; `semantics/protocols.md:49-51,
  69-101`; docs `protocols.rst:195-229`, `protocol-packages/{behaviour
  .rst:106-114, declare.rst:150-162, generate.rst:172-195,
  reference.rst:64-69}`, `api/macros.rst:18-19`;
  `tools/fw_api_check.py:52-53`.
- **fw-hdl-rt-sv:** `sv/fw_hdl_macros.svh:73-99`; `sv/fw_rt_proto.svh`
  `add_conv` :124, `xtor_role` :219-237, its uses :305, :363; std monitor
  `.p` users `tests/sv/rv_b2b.sv:66,102`, `tests/sv/pin_bridge_rv.sv:16,45`.
- **fw-hdl-fe-sv:** `python/fw/hdl/fe/sv/share/sv/fw_hdl_macros.svh:65-75`;
  `protocols.py:50-75` (`_PIN_ROLE`, `xtor_pins`, `xtor_role`), :300-316
  (`register_converter`), :358-372 (`_conv_members`); `scan.py:9,280,
  302-311`; `channels.py:55`; `gen/tb.py:37-122,215,225`;
  `gen/bind.py:44`; `gen/xtor.py:111-118` (macros), :149-309 (`pins`
  declared and created, `extends fw_component`; needs the base and
  `super.build()`), :295 (monitor `.p`); tests `e2e/sv/rv_mon_mixed.sv:16,45`,
  `e2e/test_gen_bind.py:77`, `e2e/test_proc_emit.py:157`,
  `e2e/test_gen_tb_sbus.py:59-60`, `unit/gen/test_gen_xtor.py:94-95,
  166-172`.
- **Root:** design notes only; the probe `docs/design/probes/xtor-base/`.

Status: **in progress** (2026-11-19, uncommitted):
- **Spec:** `bindings/sv/fw_xtor_{initiator,target,monitor}.svh` (real
  bodies; `fw_api_check.py` `BODY_OK`), one-argument
  `fw_xtor[_param]_utils(C)`, std rv transactors on the bases (monitor
  `p` → `pins`), conformance `proto_xtor`, `proto_xtor_param`,
  `cfg_explicit`, `proto_xtor_bad` (`nobundle_xtor` retired; `bad_p_xtor`
  now has no API endpoint), `semantics/protocols.md`, `protocols.rst`,
  the guide pages, `api/protocols.rst`. API check, lint, sphinx -W and
  `dfm run tests` pass.
- **rt-sv:** the class's `__fw_conv` record (static initializer, keyed
  under its protocol handle) is given to each instance by `create`
  (`begin_comp`); `conv_by_type` and `xtor_role` are gone; role from
  the record; FW-E-PROTO-XTOR path from the macro's class name.
  Conformance 97/0/11, pytest 19 (`build/f16-*.log`).
- **fe-sv:** macros (`__fw_xtor_protocol` returns `protocol()`),
  `protocols.xtor_role`/`xtor_pins` from the base class, `gen/xtor.py`
  emits the bases and `super.build()`, `gen/tb.py`; tests for the std
  monitor's `pins`. Suite: running.
- **FW-E-PROTO-XTOR is static-only** (owner, 2026-11-19): it is a check
  on the class declaration, so a static front end makes it; rt-sv's
  `check_convs`/`sides`/`ep_apis` (the last name-parsing lookup) are
  removed, `proto_xtor_bad` is `static-only`, and `protocols.md`,
  `diagnostics.md`, `protocols.rst`, `reference.rst` and rt-sv's README
  say so. rt-sv conformance 96/0/12, pytest 19, API PASS, sphinx -W
  and the sbus check pass (`build/f16b-*.log`). (The protocol's
  `declare()` is hand-written and the channel
  APIs generated later, so it could not have registered them anyway.)
- **Family records by handle** (owner, 2026-11-19): the protocol macros
  declare `__fw_family()` returning `__fw_rt_family_of #(C)::get()`; `C`
  is the bare class name, i.e. the default specialization, so all
  specializations share one record (Verilator probe: `rv_proto#(8)`,
  `#(16)`, `#(32)` share it; different families don't). `fams[fname]`
  is gone.
- **Dropped** (owner, 2026-11-19; test-only): `fw_protocol_type::api`,
  `::apis`, `fw_api_type::protocols` and the `fw_api_type_q`/
  `fw_protocol_type_q` typedefs; spec, rt-sv, fe-sv, `protocols.md`, and
  fe-sv `e2e/part_a` (its IR side now asserts the APIs directly).
- **Suites after all of the above:** rt-sv conformance 96/0/12, pytest
  19; fe-sv 308/13; API PASS, sphinx -W, `dfm run tests`, sbus check
  (`build/q-*.log` in each package).
- **All protocol queries dropped** (owner, 2026-11-19; all test-only):
  `fw_protocol_type::name/family/params/bundles/abstractors`,
  `fw_protocol_family::name/prefix`, `fw_api_type::name/family`,
  `fw_protocol::of/role_of/abstractor_for`, and the `fw_string_q`/
  `fw_component_ctor_q` typedefs. The handle classes stay (empty), with
  `fw_protocol_type_of::get`, `fw_api_type_of::get`, `fw_protocol::declare`
  and `fw_protocol_decl`. rt-sv: the bodies and `__fw_rt_proto::of/
  role_of/abstractors/abstractor_for/family_of` gone (its diagnostic uses
  `api_names` directly). fe-sv: the query intrinsics, `register_named`
  (it served only the constructor queries) and the macros' `__fw_ctor`
  gone. Spec: `protocols.md` "Queries" says there are none; the
  "Completeness" bullet and the guide pages no longer name queries.
  Retired: conformance `proto_abs_query`, fe-sv
  `test_abstractors_named_specializations`; fe-sv `e2e/part_a` keeps its
  protocol facts as IR asserts. Suites: rt-sv conformance 95/0/12,
  pytest 19; fe-sv 305/13 (3 fewer: the retired test and two
  `proto_abs_query` parametrizations); API PASS, lint PASS, sphinx -W,
  `dfm run tests`, sbus check (`build/dq-*.log`).

## 15. F17 `$typename` only for debug (owner, 2026-11-18; settled 2026-11-19)

**Rule (owner).** `$typename` output is informative text, available only
at run time. By definition it cannot feed the netlist or the IR. The IR
comes only from the static front end (fe-sv `ir_map.py`). rt-sv's netlist
is read only by its own conformance runner
(`fw-hdl-rt-sv/python/fw/hdl/rt/sv/conformance.py`).

The first survey (below) read the rule as "netlist type spellings are
debug-only" and asked Q12–Q15 on that basis. That was a misreading. The
spellings in fe-sv's netlist stay normative (`netlist.md:40`). Q12–Q15 are
replaced by the decisions below.

### Decisions (2026-11-19)

- **Type names reported at run time are not part of the conformance
  check.** Conformance compares rt-sv on objects, paths, roles, nets,
  ties, listeners and diagnostics, and masks type text. (Old Q12, Q13.)
- **The same holds for all other run-time value text** (owner,
  2026-11-19): protocol `params` and the param, domain, attribute and
  extern values are informative and masked in conformance. (Old Q14.)
- **Avoid `%p`, even for debug** (owner, 2026-11-19): Verilator is known
  to crash on it. Being informative is not enough; a debug path that can
  crash the simulation is not acceptable. No `%p` on any path that runs
  by default (netlist write, messages, `sprint`). Values are formatted
  from what is known statically:
  - integral values: `$sformatf` with `'h`/`%0d`, by `$bits`;
  - structs and enums: a formatter fe-sv generates beside the name table
    (`fw_type_fmt #(T)`, field by field; fe-sv knows the layout), and
    GenKit's generated `sprint` formats field by field the same way
    (today `gen/txn.py:72-73` uses `%p`, see §6);
  - with no formatter: the raw bits in hex, never `%p`;
  - class handles: the object's path or `type_name()`, never printed
    handles.
- **FW-E-CONN-TYPE** follows the spec (`signals.md:16`, 6.22.2
  equivalence): width, sign and 2/4-state for integral types, a handle
  for class, struct and enum types. Today's string compare is a bug
  (`bit[7:0]` vs `bit[8:1]` fails). (Old Q15: a fix, not a question.)
- **Proper names at run time come from fe-sv, not `$typename`.** fe-sv
  already resolves every specialization to its canonical spelling. It
  writes a name table, one static registration per specialization:

  ```systemverilog
  package top_fw_names;   // generated by fe-sv from the elaborated design
    bit __r0 = fw_type_name #(foo #(8, bit[7:0]))::set("foo#(8,bit[7:0])");
    bit __r1 = fw_type_name #(pkt_t)::set("pkt_t");
  endpackage
  ```

  `type_name()` (in the macros) and port, signal and protocol reporting
  look up `fw_type_name #(T)::get()`. With no entry they fall back to the
  macro's `"T"`, then `$typename`. A missing or stale table only makes
  debug text worse.
  - A table, not a derived class that overrides `type_name()`: `create`
    is a plain `T obj = new()` (`fw_hdl_macros.svh:26-32`), so a derived
    class would need factory substitution, would miss a `new()` the user
    writes, and can't name types that aren't classes.
  - The F16 probe already covers what it relies on (distinct statics per
    specialization, registration in a static initializer, Verilator
    5.055).
  - Limits: a type declared in a module or `$unit` can't be named from
    the table and falls back; only specializations fe-sv elaborated get
    names; one more flow step (fe-sv elaborate → name table → simulator
    compile), as a dfm task beside GenKit and gen_tb.

### F17 work items

1. **Behaviour off `$typename`** (no output change): converter lookup and
   `xtor_role` on the `fw_ctor_of` handle; protocol match on the
   `fw_protocol_type` handle; API-to-endpoint match on
   `fw_api_type_of #(A)::get()`; override `ptype` on `__fw_rt_tid #(P)`;
   domain kinds from the macro's `"T"`; FW-E-CONN-TYPE by 6.22.2; the
   ctor registry on handles, not `%p`.
2. **Remove `%p`** from rt-sv and generated code: the params, attr,
   domain and extern JSON (`__fw_rt_shape` and friends), the ctor
   registry, GenKit `sprint`. Add a check (grep in CI) that no `%p`
   remains in `fw-hdl-rt-sv/sv`, the spec bindings, std and generator
   templates.
3. **Spec:** `netlist.md` (and `diagnostics.md:77`) say type and value
   text from a run-time implementation is informative; add
   `fw_type_name #(T)` to the SV bindings.
4. **Conformance:** rt-sv's compare masks type and value text.
5. **Name table and formatters:** fe-sv generator (`fw_type_name`,
   `fw_type_fmt`) and dfm task; macros and rt-sv reporting use them.

Status: **in progress** (2026-11-19). Progress:

- **Lookups (owner, 2026-11-19):** no lookups by string, and no
  run-time lookup at all where the type system knows the answer. In order
  of preference: (1) the compiler, through typed signatures (typed
  `connect()` is already checked); (2) `$cast` inside a parameterized
  class, for untyped entry points such as `connect_all`; (3) static or
  virtual members that macros or base classes generate (role, protocol,
  converter information); (4) per-specialization static lists. A
  registry keyed on a type-factory handle only where the API itself asks
  by type (`fw_protocol::xtors(p)`).
- A first cut (per-type id handles compared at run time) was reverted.
- **Item 1, connections and overrides** (uncommitted, rt-sv): the typed
  create bodies attach a `__fw_rt_tchk_t #(C)` whose `same()` is a
  `$cast` to `fw_signal #(T)` or `B`; `connect` checks both sides.
  Overrides check FW-E-PARAM-LATE against `__fw_rt_params #(P)::comps`,
  the components with params of type `P`. `ptype` is gone.
- **Finding:** a 2-state simulator can't tell 2- from 4-state at run
  time (`$isunknown(T'('x))` is 0 under Verilator). rt-sv's check is
  therefore matching types (typedefs transparent), as before: stricter
  than 6.22.2 only for a packed struct or union against a vector of the
  same width. fe-sv applies 6.22.2 fully.
- **Item 1, converters, `xtor_role`, FW-E-PROTO-XTOR:** done as part of
  F16 (§14), which rewrites the same macros.

### F17 items 2-5: design (owner chose (B), 2026-11-19)

Masking value text would drop conformance's check of rt-sv's param
resolution (`params`, `param_src` in ~140 scenarios' objects), so:
**type text is masked for a run-time implementation; value text stays
normative, formatted from static type information, never `%p`.**

- **Type text** (masked in rt-sv's compare): object `type`, `top`,
  object `protocol`, the `protocols` table's keys and `family`, `params`,
  `apis[].type`, `bundles`, converter `type`/`from`/`to`; domain kind
  names (`assoc` keys, extern `domain_pins[].kind`); extern param `type`.
- **Value text** (compared): `params`, `param_src`, domain `params`,
  `attr`, `provides`, extern param values, ties. A factory value is the
  realization's name and a domain handle its path.
- **Formatting without `%p`:**
  - integral values (incl. packed struct, enum) generically in rt-sv:
    unsigned decimal up to 64 bits, `'h` hex above (fe-sv
    `netlist.params_value`'s rules);
  - unpacked structs and arrays: a formatter fe-sv generates per type
    (field by field, mirroring `params_value`), registered in a
    per-type static (`__fw_rt_tinfo #(T)`); `param_src` comes from
    diffing the fields it yields;
  - class handles: a domain (an fw object) by its path; a factory by
    its realization's name, from a handle-keyed registration made in
    `fw_ctor_of #(B,D)::get()` (no `%p` of a handle);
  - with no formatter for a type: no value (rt-sv writes `null`), never
    `%p`.
- **Names:** the same generated package registers each specialization's
  canonical spelling (`__fw_rt_tinfo #(T)::name`); without it rt-sv
  falls back to the macro's `"T"`, then `$typename`.
- **Where it runs:** fe-sv elaborates the scenario's top and writes
  `<top>_fw_rtinfo.sv` (dfm task beside GenKit and gen_tb); rt-sv's
  conformance runner generates it per scenario and compiles it in.
  With it, rt-sv's type text is canonical too, so the runner can
  compare everything; without it (`--no-rtinfo`) type text is masked.

Stages:
1. Spec note (`netlist.md`: run-time type text informative, value text
   normative) and the type-text mask in rt-sv's runner. rt-sv still
   uses `%p` for values here.
2. fe-sv generator (`fw.hdl.gen.rtinfo`) + dfm task: names and
   formatters per type; rt-sv's `__fw_rt_tinfo #(T)`; runner wiring.
3. rt-sv off `%p`/`$typename`: values through formatters, factory
   names through `fw_ctor_of` registration, `__fw_rt_pj`,
   `__fw_rt_shape`, `pval`, `tn` removed; GenKit `sprint` field by
   field; a CI grep for `%p`.
4. Full suites; conformance with and without rt-info.

Status (2026-11-19, uncommitted): **stages 1-4 done.**
- **rt-sv:** `__fw_rt_tinfo #(T)` (name + `__fw_rt_fmt #(T)`),
  `__fw_rt_name_of #(T)` (names read when written: protocol, API and
  converter names registered in static initializers are refreshed before
  the netlist is written), `__fw_rt_txt::path`, `__fw_rt_ctors #(B)`
  (factory handle -> realization name, registered in `fw_ctor_of::get`).
  Params, domain params/attr/provides and extern values go through the
  formatters; with none, `null`. Removed: `__fw_rt_pj`, `__fw_rt_shape`,
  `pval`, the `%p` ctor registry, `val_json`/`attr_json`/`dfields`.
  `tn` stays only as the display fallback.
- **Behaviour that read `%p` text, now typed:** FW-W-DOM-STYLE and a
  reset driver's `active_low` from `fw_reset_kind::pin_attr_t`;
  FW-E-DOM-DERIV by `==` on the kind's `params_t`
  (`__fw_rt_held::same`; Verilator compares unpacked structs with handle
  queues correctly, probed).
- **fe-sv:** `fw.hdl.gen.rtinfo.gen_rtinfo(rt, pkg)` and dfm task
  `GenRtInfo`; the package's `register()` is called explicitly before
  elaboration (not a static initializer: Verilator may drop an
  unreferenced package's initializers, and the call fixes the order).
  GenKit's `sprint`/`compare` print a kit payload struct through its
  `<n>_sprint` and anything else as `0x%0h` (goldens regenerated).
  `tests/unit/test_no_percent_p.py` fails on `%p` in rt-sv, the spec's
  bindings and std, and the golden generator output.
- **Runner:** generates the package per scenario (fe-sv elaborates
  `scenario::top`) and compares unmasked; falls back to the masked
  compare, noting why, when fe-sv cannot; `--no-rtinfo` masks type text.
- **Suites:** rt-sv conformance 95/0/12 unmasked (all 95 with rt-info);
  `--no-rtinfo` 80/15/12 (the 15 are value text: params, param_src,
  domain params, extern values, now `null` without formatters, as
  designed); rt-sv pytest 23 (19 + 4 `test_rtinfo`); fe-sv 417/13
  (305 + 108 `%p` checks + 4 `test_rtinfo`); API, lint, sphinx -W,
  `dfm run tests`, sbus pass (`build/s4-*.log`).
- **Limits:** a class handle in a value that is neither an fw object
  nor a factory is `null` (fe-sv writes its class name); a type declared
  in a module or `$unit` gets no name or formatter.

### F17 survey (2026-11-18, superseded framing)
**Where the uses are.** About 50 uses, all in rt-sv; none in spec
bindings, std or fe-sv's `share/sv`. `gen/txn.py:72-73` uses `%p` only in
transaction text, which is debug and can stay.

**The core of it.** `__fw_rt_str::tn` (`fw_rt_util.svh:81-200`) rewrites
Verilator's `$typename` text into the netlist's canonical spelling. That
spelling is both written to the netlist and used as a string key. The
conformance runner compares the whole netlist, type strings included:
43 of the 108 `expect.json` files have `objects`, 34 have `#(` spellings
and 19 have `protocols`.

**Uses that drive behaviour, and their replacements:**
- component `tname`, used to look up converters: a per-class singleton
  handle, with the name `"T"` from the macro;
- converter `ty` (`conv_by_type`, `xtor_role`): key on the
  `fw_ctor_of #(fw_component,C)::get()` handle;
- signal and port `tname` for **FW-E-CONN-TYPE** (string equality at
  `fw_rt.svh:635`): compare `$bits`, sign and 2/4-state for integral
  types, and a handle for class, struct and enum types. Today's check is
  stricter than the spec's 6.22.2 (`bit[7:0]` vs `bit[8:1]` fails);
- protocol `aproto` (a string compare): the `fw_protocol_type` handle;
- matching APIs to endpoints (`ep_apis` parses type names): endpoints
  record `fw_api_type_of #(A)::get()` handles;
- override `ptype`: a `__fw_rt_tid #(P)::get()` handle (S, low risk);
- domain kinds: the macro passes `"T"` (kinds have no parameters, so it
  is exact);
- the ctor registry (`%p` of a struct holding a handle): this depends on
  how Verilator prints handles (L).

**No portable replacement exists for:**
- spelling a type parameter's value or a typedef name as text;
- splitting a packed struct into members (`__fw_rt_shape`);
- the params, attr, domain and extern JSON parsed out of `%p`.

**Spec clauses involved:**
- netlist.md:40, canonical type spelling;
- params.md:44, a factory is written as its realization's spelling;
- domains.md:20, a kind's spelling (fine with `"T"`);
- diagnostics.md:77, class paths are spellings;
- signals.md:16, 6.22.2 equivalence (fine without `$typename`);
- protocols.md:32, `p.params()` is for reporting.

**Order:**
1. Identity (no change to output).
2. Bare names from the macros.
3. Decide what the netlist's type fields mean.
4. Params, attr and ctor JSON.

## 17. Introspection: acc (owner direction 2026-11-19)

F17 stages 2-3 first built run-time introspection (per-type names and
field-by-field value formatters, generated by fe-sv) inside rt-sv, for
rt-sv's netlist. Owner direction, which replaced it:

- **Purpose:** visibility for testing, debug and reporting. acc may later
  allow manipulating objects, but it is always an **optional** facility.
- **Elaboration never needs it.** Elaboration stores typed values only
  (the params value after each source: defaults, creator, each override,
  init; domain params, pin attributes, `provides`, extern parameter
  values; each type's name holder). Reporting (the netlist writer, debug
  printing, tests) asks acc to turn them into text; `param_src` is found
  then, by comparing the stored values' fields. A null answer means no
  text (`null` in the netlist), never a different elaboration.
- **Bright line:** generated accessor objects are separate from the
  user's description. Nothing in a design, the modeling classes or their
  macros refers to acc. Static uses of introspection may be powerful
  later; not mixed in now.
- **Name:** acc ("access"). `fw_acc` is a handle factory. Not "view"
  (reserved for RTL vs TLM views).
- **Structure (owner, 2026-11-19): acc is declared in `fw_hdl_pkg`**, not
  in separate packages. SV's package structure makes splits costly
  (imports are not transitive, every compile line and API check grows),
  so fewer packages is better. Optionality is registration, not a
  package boundary: with no generated accessors registered, every lookup
  returns null and the text is null. (A split into fw_acc_pkg /
  fw_acc_hdl_pkg, then fw_hdl_acc_pkg / fw_hdl_rt_pkg, was drafted and
  dropped.)

Built (uncommitted, 2026-11-19):
- **Spec:** `bindings/sv/fw_acc.svh`, included by `fw_hdl_api.svh`:
  - plain SV, the same in every tool (in `fw_api_check.py`'s `BODY_OK`):
    `fw_acc` (registry: `add_type`, `types()`, `add_component`,
    `component(fw_component)` = the most derived registered class whose
    `$cast` test accepts it, else null; `jstr`), `fw_acc_field` (name,
    text), `fw_acc_type` (`name()`), `fw_acc_value_of #(T)` (defaults for
    `text`, `fields`, `literal`), `fw_acc_component` /
    `fw_acc_component_of #(C)` (`register(name, depth)`, `name`,
    `accepts`, `make`), `fw_acc_ctor_names #(B)` (a factory handle's
    realization name, keyed by handle);
  - extern (tool): `fw_acc::path(fw_object)`, `fw_acc_value_of::get/set`
    (the tool links an accessor to the values it holds),
    `fw_acc_component_of::params/param_src` (the tool's snapshots).
  - Domains and fw_value need no classes of their own: their values go
    through `fw_acc_value_of` of their types (a kind's `params_t` and
    `pin_attr_t`, an extern parameter's `T`).
  - `semantics/acc.md`; docs `api/acc.rst`. `tools/fw_hdl_bodies.py` now
    keeps a `ref` argument's direction in the default bodies.
- **rt-sv** (one package): elaboration keeps `__fw_rt_held #(T)` values
  and `__fw_rt_name_of #(T)` name holders (display text only) and never
  calls acc. `fw_rt_acc.svh` holds the acc bodies and the bridges
  (`__fw_rt_acc`: each registered accessor matches the core's holders of
  its type by `$cast`). `fw_rt_netlist.svh` (`__fw_rt_netlist`) is the
  netlist writer and the only caller of acc; `__fw_rt::main` calls it. The
  internal object-to-record accessor `__fw_rt_acc` is renamed
  `__fw_rt_impl_of`. Removed: `__fw_rt_tinfo`, `__fw_rt_fmt`,
  `__fw_rt_ctors`, `__fw_rt_txt`, the factory registration in
  `fw_ctor_of::get`. `tests/test_acc.py` checks that acc is used only in
  `fw_rt_acc.svh` and `fw_rt_netlist.svh`, and that a run with no
  accessors elaborates the same (structure and diagnostics).
- **fe-sv:** `fw.hdl.gen.acc` (was `gen.rtinfo`): `gen_acc_package(comp,
  pkg)` writes `<pkg>_acc` (names for its non-parameterized classes,
  `fw_acc_component_of::register` for its components, value accessors
  for its typedefs and class-local typedefs; a domain kind's types write
  fw objects as paths); `gen_acc_design(rt, name, packages)` writes the
  optional per-design package (specializations, built-in types,
  factories, types of packages with none generated) whose `init()` runs
  the per-package ones. Generated code uses only `fw_hdl_pkg` and the
  design's packages. Each package registers by static initialization and
  has an idempotent `init()`. dfm task `GenAcc` (was `GenRtInfo`).
- **Conformance:** rt-sv's runner generates `fw_hdl_pkg_acc`,
  `fw_hdl_std_pkg_acc`, `scenario_acc` and the per-design
  `scenario_top_acc`, calls its `init()`, and compares unmasked;
  `--no-acc` masks type text (value text is then null).
- **Suites:** rt-sv conformance 95/0/12 (unmasked, with acc), `--no-acc`
  80/15/12 (the 15 compare value text, null without accessors: as
  designed); rt-sv pytest 25; fe-sv 420/13 (incl. the `%p` guard over
  rt-sv, bindings, std and goldens); API check, spec lint, sphinx -W,
  `dfm run tests`, sbus check pass (`build/acc-*.log`).

## 16. F15 outcome (2026-11-18, uncommitted)

- **`four_state` in the block signature** (ir-core `signature.py`):
  - written only when true, so 2-state output is unchanged; absent reads
    as `None` (unstated), which keeps be-sv's `bit`/`logic` choice as it
    was;
  - schema `block-signature.v3.json` gains `$defs/payload` (int, array and
    struct forms); no version bump, per `docs/formats.md` (additive
    optional field).
- **Listeners in the netlist:**
  - top-level `listeners`, written only when non-empty: `{sink, order,
    scope, listener}`, sorted by sink, then order;
  - `order` is the order `changed()` runs in; `scope` is the component
    whose phase made the call;
  - `listener` is the object's path if it is an fw object, else `null`.
    SV can't give a plain object's dynamic class name or its holding
    member.
  - Spec: `netlist.md`, `protocols.md`, `netlist.schema.json`, conformance
    README.
  - Both runners write it. New scenario `cfg_listeners` covers a
    component, a member object, a local object, and a sibling registered
    by the parent. `cfg_ep_basic` was updated.
- **Suites:** fe-sv 308/13, conformance 97/0/11, rt-sv 19, ir-core 241/3,
  zuspec-fe-sv 148/5, be-sv 248/4, be-xls signature 6, API PASS, sphinx
  and dfm rc 0, sbus PASS, root check set 355/2.

Owner decisions (2026-11-19):
- **Q16:** a run-time `add_listener` (outside a phase method) is
  `FW-E-CONN-PHASE`, like a run-time connect, and is not attached:
  listeners are structural, so simulation and the IR agree. Done
  (uncommitted): rt-sv `__fw_rt_cfg_t::listen`, `diagnostics.md`,
  `protocols.md`, `fw_cfg_sink.svh`; rt-sv test `cfg_ep_runtime` covers
  it. Suites: rt-sv conformance 95/0/12, pytest 19, API PASS,
  sphinx -W and `dfm run tests` pass (`build/q16-*.log`). fe-sv interprets only phase code, so it never records one; it
  does not lint `add_listener` calls in `run()` (possible follow-up).
- **Q17:** (a) accepted: a plain listener is known by sink, order and
  scope at run time; its class is a static fact in fe-sv's IR. No common
  listener base class.
- **Q18:** no version bump; `four_state` stays an additive optional
  field of signature v3 (`formats.md` policy).

Original questions:
- **Q16:** only phase-time `add_listener` calls are recorded. Is that
  acceptable?
- **Q17:** `null` listeners can't be told apart without a common listener
  base class.
- **Q18:** bump the signature version for `four_state`? A v3 reader that
  ignores the field treats a 4-state port as unstated.

## 18. F8b: the real AXI core round trip (probe 2026-11-20)

Target: `fw-proto-axi-new/src/core` (`fw_proto_axi4_defs_pkg.sv`,
`fw_proto_axi4_core_pkg.sv` with `axi4_types.svh`, `axi4_bundle.svh`
and the three `axi4_*_if.svh`) through zuspec-fe-sv → IR → be-sv →
`verilator --lint-only`, the way `test_sv_round_trip.py` handles the
2-state copy. Scratch run: `fw_proto_pkg` stubbed down to `fw_rv_ch #(T)`,
one package per file (three packages in one file trip `DECLFILENAME`).

Result: mapping reports nothing, but Verilator gives 18 syntax errors,
all from class-local typedefs emitted as `axi4_types::aw_t` at package
scope. Re-parsing fails too, so neither the equal-IR check nor the
fixed-point check can run. With the names patched by hand, lint
passes, but much of the content has been dropped without a message.

Findings, in order:

1. **No message, nothing mapped:** `AXI4_PARAM_DEFAULT` (a localparam),
   the 16 package functions (`w1`, `max2`, `axi4_*`), package imports,
   and class attributes (`fw_api`, `fw_proto_bundle`, `fw_roles`,
   `fw_defs_pkg`). The visitor in `zuspec-fe-sv mapper.py:68-79` collects
   classes, generic classes and typedefs only.
2. **Interface classes lose `#(P)`:** `class_mapper.py:451-463` keeps
   only the protocol. `map_generic_api` (`:502`) exists, but `SVMapper`
   never calls it (`mapper.py:87-91`).
3. **Struct-valued default is emitted as a string:**
   `P = "320'd1591…"`, the evaluated value cut to text
   (`class_mapper.py:496-499`, `_const` at `:585`).
4. **Class-local typedefs are hoisted and frozen:** they go to package
   scope, are named `axi4_types::aw_t`, and keep the default-`P` widths
   (`type_mapper.py:64-84`, `core_to_sv.py:544-561`). Struct members
   never get `width_expr`, and `module_header._xlate` (`:311-349`)
   handles neither member access (`P.ADDR_W`) nor calls to user
   functions (`w1(...)`).
5. **`typedef axi4_types #(P) t;` in the bundle is dropped:** fields
   become `fw_rv_ch #(axi4_types::aw_t)`.
6. `fw_opt` on struct members is dropped (parked, Q5). `fw_fwd`/`fw_rev`
   survive.
7. Minor: struct typedefs come out in first-use order, and
   `int unsigned` becomes `bit [31:0]`.
8. **Functions before tasks** (`sv_emit.py:281-287`, split at
   `core_to_sv.py:327-332`) breaks nothing in SV. It costs fidelity: the
   round-trip test has to sort methods by name
   (`test_sv_round_trip.py:31-41`).

4-state `logic` (F8a) round-trips, including a `logic`-based enum.

The real blocker is not in the F8b list: **the IR has no package
container.** ir-core's `Context` is just `type_m: Dict[str, DataType]`.
There is nowhere to keep package localparams, package functions or
imports, and the core's widths call `w1`/`max2` from the defs package.
That makes the work L, not M–L, and it is an IR design change (Q19).

### Plan

| Step | What | Size | Needs |
|---|---|---|---|
| 8b.1 | Parameterized interface classes go through `map_generic_api` and keep `#(P)` | S | — |
| 8b.2 | Struct-valued default: keep the expression (`ExprRefUnresolved("AXI4_PARAM_DEFAULT")` or a literal), not the evaluated text | S–M | — |
| 8b.3 | Methods kept in source order (one ordered list in the be-sv SV IR); round-trip test stops sorting | S | — |
| 8b.4 | IR package container: localparams, functions, imports, types in source order; fe-sv maps it, be-sv emits it | L | Q19 |
| 8b.5 | Class-local typedefs: a typedef list on the class, `width_expr` on struct members, `_xlate` member access and function calls, typedefs in class bodies, `cls #(P)::t` type references | L | 8b.4, Q20 |
| 8b.6 | Class and interface attributes (`sv_annotations` in `_map_plain_class` and `map_protocol`) | S | — |
| 8b.7 | Round-trip test on the real core (one file per package, `fw_proto_pkg` stubbed or filtered) | S | all of the above |

### Questions

- **Q19 package container in ir-core.** Proposal: add a `Package`
  (name, imports, constants/params, functions, types, in source order),
  with `Context.packages`. Package functions reuse `Function`. The
  Python front end would map a module the same way later. The
  alternative is to keep packages in fe-sv metadata only; that goes
  against "represent it in Zuspec".
- **Q20 class-local typedefs.** Proposal: a `typedefs` list on
  `DataTypeClass`, with names scoped to the class. A
  `DataTypeSpecialized` member reference (`axi4_types #(P)::aw_t`) is a
  new type-reference form. The alternative is hoisting with a mangled
  name plus extra template parameters, which loses fidelity.

### Decisions (owner, 2026-11-20)

- **Q19:** yes. An ir-core `Package` (name, imports, constants,
  functions, types in source order) in `Context.packages`, plus an
  expression reference to a package member. The package references the
  types in `type_m` rather than owning them.
- **Q20:** yes, parametric. `DataTypeClass.typedefs`, member widths as
  expressions over the class parameters, a member-type reference
  (`axi4_types #(P)::aw_t`). Per-specialization copies, if a back end
  wants them, are a later IR transform.
- Struct-member attributes are recorded in the IR now. What `fw_opt`
  means stays parked (Q5).

### Status (2026-11-20, uncommitted)

- **8b.1 done:** `SVMapper` maps a parameterized interface class with
  `map_generic_api`. It keeps its parameters
  (`get_api_templates()`), and the protocol body stays in
  `get_protocols()`. New `get_decls()` gives every declaration once.
- **8b.2 done:** a struct-valued default that names a constant becomes
  `ExprRefUnresolved` (`P = DEF`); any other struct value (defaults and
  specialization arguments) becomes an `ExprStructLiteral`, member by
  member and nested. The value is read as hex, since decimal printing
  is abbreviated for wide structs. This replaces K5's "struct-valued =
  packed int"; `test_class_mapper_param.py` was updated. Nothing
  downstream read the packed form.
- **8b.3 done:** be-sv `SVTaskDecl`/`SVFunctionDecl.pos`.
  `_split_methods` sets it, and `emit_class`/`emit_interface_class`
  interleave by it; with no positions, the order is functions then
  tasks as before. The round-trip test no longer sorts methods.
- Tests: new `zuspec-fe-sv tests/unit/test_struct_param_api.py`.
  zuspec-fe-sv 155 passed / 5 skipped, be-sv 250 / 4 / 3 deselected,
  fw-hdl-fe-sv 420 / 13.
- Known: the emitted `P = DEF` does not lint until the localparam
  is emitted too (`Can't find definition of variable: 'DEF'`). That
  is 8b.4. The old text (`P = "320'd…"`) did not lint either.
- 8b.4 and 8b.5 wait for Q19/Q20; 8b.6 (attributes) is not started.

**Update (2026-11-20, later; uncommitted): 8b.4–8b.7 done. The real AXI
core round-trips.** `zuspec-fe-sv tests/unit/test_sv_round_trip_axi4_core.py`
uses a copy of `fw-proto-axi-new/src/core` at `2e2cf3f`
(`tests/unit/axi4_core/`, with `fw_proto_pkg` stubbed to `fw_rv_ch`). Its
three packages map without diagnostics. The output lints with Verilator
(`-Wall`, as the source does), re-maps to an equal IR (types,
declarations, packages) and re-emits unchanged. The constructs the
source writes over `P` all survive, checked by count against the
source: 20 `P.`, 13 `fw_opt`, 24 typedefs, 16 functions, 12 casts,
class attributes.

- **ir-core (8b.4, 8b.5):**
  - `Package` (`items` in source order: `PackageImport`, `PackageConst`,
    `Function`, `PackageType`) and `Context.packages`;
  - `ExprRefPackage`;
  - `TypeDef` in `DataTypeClass.typedefs`/`DataTypeProtocol.typedefs`;
  - `DataTypeMemberRef`.
  - New `tests/test_package_ir.py`; CHANGELOG entry.
- **zuspec-fe-sv:**
  - `SVMapper.get_packages()`.
  - Class-scope typedefs stay in their class (`TypeMapper.class_local`
    hook); a reference from another class is a `DataTypeMemberRef`.
  - In a template body, `cls #(P)` and `x::member` are mapped from type
    syntax, so `P` is kept. Every parameter gets an argument; an omitted
    one takes its resolved value.
  - `_xlate` translates `P.X` (a `ScopedName` with `.`), `pkg::X`,
    package parameters and package function calls, nested
    (`w1(max2(..))`). It skips the comma tokens in separated lists, a
    bug that hid every argument list with more than one item.
  - Struct members get `width_expr` from syntax.
  - Attributes: string values are decoded (slang holds a struct
    member's as an integer), and class attributes are read from the
    declaration syntax (slang keeps none for a class).
  - Statements and expressions:
    - comparisons are `ExprCompare` (were `ExprBin` with a `CmpOp`, which
      be-sv could not emit);
    - local declarations are `StmtAnnAssign`;
    - `inside` is `ExprIn`;
    - written casts are `ExprCast`.
- **be-sv:**
  - `translate_ir_package`;
  - class typedefs, `DataTypeMemberRef`, `ExprRefPackage`;
  - class, interface and struct-member attributes;
  - function `lifetime`.
  - Members of the package or of a `*`-imported one are written
    unqualified (`LOCAL_PACKAGES`, also set by `emit_package`).
  - A width over parameters wins over the 1-bit shortcut.
  - **Correctness fix:** a nested `&&`/`||` is now parenthesized. Before,
    `a && (b || c)` came out as `a && b || c`.
  - New `tests/unit/test_ir_package.py`.
- **fw-hdl-fe-sv:** the `FW-E-GEN-SCOPE` message names a class-scope
  payload (`ls_bundle::req_t`) from the `DataTypeMemberRef`.
- **Suites:**

  | Suite | Result |
  |---|---|
  | ir-core | 243 passed / 3 skipped |
  | zuspec-fe-sv | 160 / 5 |
  | be-sv | 254 / 4 / 3 deselected |
  | fw-hdl-fe-sv | 420 / 13 |
  | root | 831 passed / 3 skipped / 1 xfailed, 47 min (`build/full-root-f8b.log`) |

- **Left:**
  - `int unsigned` is emitted as `bit [31:0]`; the type is the same.
  - The meaning of `fw_opt` is still parked (Q5); the attribute itself
    is kept.
  - `implements` keeps only interface names, not their arguments.
