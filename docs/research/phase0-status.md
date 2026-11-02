# Phase 0 status

This tracks [phase0-plan.md](phase0-plan.md). A fresh session can resume from this file alone.

## Rules
- **All changes stay inside this packet.** Dependency repos are edited only in
  `packages/<repo>`, on branch `wpk/results-ir`. The out-of-packet checkouts
  (`~/projects/zuspec/*`, `~/projects/dv-flow/*`, `~/projects/featherweight-hdl/*`) are
  read-only.
- **Run everything through the packet environment:** `direnv exec . <command>`, from the
  packet root.
- **Build and test output goes to log files** under `build/` (git-ignored).

## Environment recipe (E1–E3)
1. Run `ivpm update`. This populates `packages/` and needs network. `xlsynth` was added to
   `ivpm.yaml` as the edapack `xlsynth-bin` release, v0.59.0.1 at the time of writing.
2. Run `direnv allow .`.
3. Branch `wpk/results-ir` in each of these `packages/` repos (bases are the `main` HEADs
   at clone time):

   | Repo | Base commit | Note |
   |---|---|---|
   | zuspec-ir-core | `c439187` | Release 0.3.0 |
   | zuspec-be-xls | `a55c6d6` | |
   | zuspec-synth | `19bb9c2` | includes `proc/` and `archsched/` |
   | dv-flow-libsynth | `3f96fcf` | includes `xls/lower.py` |
   | zuspec-dataclasses | `abd40d4` | |

4. Checks:
   - `direnv exec . python -c "import zuspec.synth.proc"` resolves to `packages/`.
   - `which codegen_main` resolves to `packages/xlsynth/bin`.
   - **fw-hdl itself must be installed editable** so that dv-flow finds the `fw.hdl.*`
     packages (entry point `dv_flow.mgr` in `python/pyproject.toml`). ivpm does not do
     this:
     `uv pip install --offline --no-deps --no-build-isolation --python packages/python/bin/python -e python`
     Without it, every dfm-driven test fails with "failed to resolve task-uses fw.hdl.…".

**E4 needs no change.** `tests/xls/test_compose.py` looks for `packages/python/bin/dfm`,
which now exists inside the packet.

## Progress
| Item | State | Note |
|---|---|---|
| E1 packages/ via ivpm | done | xlsynth dependency added to `ivpm.yaml` (uncommitted) |
| E2 branches | done | `wpk/results-ir` in 5 repos |
| E3 self-contained env | done | |
| E4 dfm path | done (no change) | |
| E5 baseline | done | logs in `build/phase0-baseline/`; examples in `build/prereq/examples/`, `build/phase0-d5/`. Note: `test_c4_aes128_ctr` baseline failure is Verilator signal 9 (killed), not WIDTHTRUNC |
| Prereq: XlsBinding vs Verilator 5.052 | done | queues/result maps moved from the transactor interface into a `<api>_xtor_state_pkg` class (`python/fw/hdl/fn_api.py`, `comp_api.py`); full example rerun in `build/prereq/examples/`: adler32, lfsr, lfsr_proc, gcd, prefix_sum, fir_dot, idct_chen, sha256, rle, rle_loop pass `<ex>.test` (all views). aes: model/rtl/gates sims pass; its ice40/ecp5 Yosys synth ran >75 min (ABC on `encrypt`) and was stopped — pre-existing runtime, not a binding issue. crc32 `crc32.test` and aes_ctr model/rtl/gates rerun in `build/phase0-d5/`: pass |
| A1 anchor grammar ADR | accepted, amended (P1+P2) | `packages/zuspec-ir-core/docs/anchors.md`; P1 synthesized nodes (`x:<reason>`, `mark_synthesized`), P2 named locals (`v:<name>`, `v:<name>+K`), annotations unanchored; table format v2. Proposal + results: `anchor-adr-proposals.md`. Tests `test_anchor_named.py` |
| P1/P2 front ends | done | fw-hdl `static_mapper.py` marks retvar/return/cast/literal-type/index/incr/forever (user casts unmarked); zdc marks literal casts. A6 rerun: (a)=0, (b) 58/588 (10%, was 41%) |
| A2–A5 anchors | done | `Base.anchor`, `Loc.key()`, `zuspec/ir/core/anchor.py`; tests `test_anchor.py`, `test_anchor_locality.py` |
| B1–B6 facts/overlays/store/bundle, signature v2 | done | `zuspec/ir/core/results/`; `docs/results.md`; tests `test_results.py`, `test_signature_file.py`. JSON Schema files not written (formats documented in `results.md` §5) |
| ir-core suite | 155 passed, 3 skipped | was 107 passed |
| A6 churn tool | done | `tools/anchor_churn.py` → `build/anchor_churn/churn.md`. (a)=0 on all 15 pairs (gate passes). (b) 254/623 re-keyed: head-of-block inserts re-key ~all later siblings (gcd 50/82, 43/46; rle loop 153/154); tail edits 0/154, expr edit 4/69. Real history (5 pairs) never edited a mapped top's IR, so synthetic edits carry the signal; fw-aes-demo history is TLM-only, not used. Named-locals decision: see report to user |
| C1 lowering oracle | done | as a test: pre-opt every node maps `exact` (`be-xls tests/unit/test_overlay.py`); no separate lowering map needed |
| C2 source names on nodes | already existed | `BodyLowerer.name_node` names variable-defining nodes |
| C3 IR reader | reused | `zuspec.be.xls.testing.parser.parse_package` already reads opt/sched IR with `pos`; block IR registers read by regex in `overlay.py` |
| C4 schedule reader | done | `be-xls read_schedule.py` (timed nodes, delays, periods) |
| C5 signature flop kind | done | `signature_from_codegen` reads `flop_kind` (and `stage` if XLS ever emits it; v0.59 does not — stage is derived from the schedule) |
| C6 overlay writer | done | `be-xls overlay.py`; doc `docs/overlay-xls.md`; real data: gcd_binary8 100%/100%, rle_enc8 62.5%/44.4% |
| C7 libsynth outputs | done | `synth.xls.Codegen` also writes `.block.ir` (`xlsBlockIR`) and `.line_map.textproto` (`xlsVerilogLineMap`) |
| Coverage gate | done | `tests/xls/test_xls_overlay.py` + `tests/xls/golden/mapping_coverage.json` |
| D1 engine interface | done (moved) | in **zuspec-ir-core** `engine.py`, not zuspec-synth: be-xls depends only on ir-core, and zuspec-synth would pull in zdc/pysat/dv-flow. Doc `docs/engine.md`; fake-engine tests `test_engine.py` |
| D2 XlsEngine | done | be-xls `engine.py`, entry point `zuspec.engines: xls` (be-xls reinstalled editable to register it). Uses libsynth `codegen_argv` + `fix_source_comments` (factored out of `synth.xls.Codegen`; imported lazily) |
| D3 flow integration | in progress | instead of a parallel `fw.hdl.Synth` path: `fw.hdl.xls.IR` writes `<module>.anchors.json` (`zuspecAnchorTable`), new task `zuspec.xls.Overlay` (be-xls) writes `<module>.zir/` bundles from Codegen's outputs. Verilog keeps coming from `synth.xls.Codegen`; XlsEngine byte-identity is tested separately (`tests/xls/test_engine_path.py`) |
| D4 StageTLM via overlay | done | `stage_tlm.schedule_from_bundle` (ResultStore over `<module>.zir/`); `XlsStageTLM` prefers `zuspecIRBundle`, falls back to `xlsSchedule` (fw-aes-demo still passes schedules). New be-xls fact `xls.node_stage` `{node, stage}`. Test `test_schedule_from_bundle_matches_the_textproto` |
| D5 front-end hook | done | `XlsIR` assigns anchors before lowering, writes `<module>.anchors.json` (`zuspecAnchorTable`); `zir` task (`zuspec.xls.Overlay`, needs [ir, rtl]) in gcd/rle/aes/lfsr flows; documented in `python/fw/hdl/xls.dv`. `dfm run -f xls_examples.<ex>.zir` passes for gcd/lfsr/rle/aes (exit 3). Coverage: all aes/gcd/lfsr functions 100% exact; rle procs 71–75% ops (rest unmapped → block anchor). Engine byte-identity `tests/xls/test_engine_path.py`: 4/4 pass (exit 2); overlay `iface.block` = XLS signature + schedule-filled channel stages |
| D4 StageTLM reader | done | `stage_tlm.parse_schedules` wraps be-xls `read_schedule` (identical on all 30 example schedules; empty stages kept); test `tests/xls/test_stage_tlm_schedule.py` |
| F1 canary spike | done | `docs/research/canary-gaps.md`: zdc GCD reaches an overlay only with hand IR fixes; `iface.block` identical; anchors differ across front ends (SV adds a return variable, zdc a `pass`, casts differ) |
| F3 be-xls div guard | done | `_implies_nonzero` follows `not` (and `or` under negation); test in `test_d1_division_must_be_guarded`; be-xls 68 pass |
| F2 zdc fixes | done (uncommitted, zdc `wpk/results-ir`) | `data_model_factory.py`: gap 1/7 arg+return widths via `get_type_hints(include_extras=True)` + `_resolve_field_type` (`Arg.annotation=None` once `datatype` set); gap 2 `StmtAnnAssign.ir_type` (`_local_decl_type`); gap 3 minimal `_cast_int_literals` (int literal vs sized operand in arith/bitwise/compare -> `ExprCast`, provenance `zdc.cast_int_literals`; shifts and non-constant mixed widths untouched); gap 4 `loc` on `Function`/`Arg`/every expression (`_convert_ast_expr` wrapper), 1-based columns everywhere (also field locs, `activity_parser`; `ir_checker` converts back to 0-based), dedent added back for nested classes, module-level inlined fns located in their own file; gap 5 only methods from classes below `Component` in the MRO. Tests `tests/unit/test_fn_ir_widths_loc.py` (9). Suites: zdc no new failures (`test_zdc_builtins` is flaky before and after); synth, be-sv/sw/py, fw-hdl xls + be-xls unchanged. Canary `zdc_lower.py raw`: Gcd 93/93 exact, GcdNe 73/73 exact, GcdSub 111/111 exact, `iface.block` latency 3 II 1 |
| F4 canary test | done, all green (no xfail) | `tests/xls/test_canary_gcd.py` + `tests/xls/canary/{gcd_canary_pkg.sv,gcd_zdc.py}` (in fw-hdl, not be-xls: the SV half needs fw-hdl). (a) user anchors identical (37); (b) iface.block equal; (c) sched.stage equal on every anchor; (d) all facts validate. Both 93/93 ops exact |

## Baseline (E5)

Measured 2026-11-01, after the fw-hdl editable install. "Nothing regressed" means: no new
failures relative to this table.

| Suite | Command (via `direnv exec .`) | Result | Known failures (pre-existing, not Phase 0 scope) |
|---|---|---|---|
| fw-hdl XLS + be-xls | `pytest tests/xls packages/zuspec-be-xls/tests` | 171 passed, 4 failed | `test_compose::test_t1_through_dv_flow[chain-rtl, chain-rtl-recipe]` (dfm: `project.spl.utils.xls-rtl` not resolved); `test_corpus::test_c4_aes128_ctr` and `test_formal_svunit::test_flow_prove_and_replay` (Verilator 5.052 lint: WIDTHTRUNC on `randomize`) |
| zuspec-ir-core | `pytest` in package | 107 passed, 3 skipped | none |
| zuspec-be-xls | included above | | |
| zuspec-synth | `pytest --ignore=tests/test_synth_command.py` | 1115 passed, 53 failed, 96 errors, 36 skipped | `test_synth_command.py` imports a missing `zuspec.cli`; the others are example modules not on `sys.path` (`rotate`, `fetch`, `blink`, `dma`, …) and `pyslang.Compilation` API drift |
| dv-flow-libsynth | `pytest` in package | 51 passed, 1 failed, 6 skipped | `test_yosys_frontend_reports_the_read_error_at_its_line` |
| zuspec-dataclasses | `pytest tests --ignore=tests/performance` | 2014 passed, 99 failed, 24 skipped | perf tests need `uvloop`; `examples/spi` needs `spi_model` on path |
| fw-hdl python | `pytest tests/python` | 89 passed, 42 failed | all in mmio / regblock / regmap / structural_top (`mmio_multi_pkg.sv` include errors; "register block has no registers") |
| examples/xls | `dfm run tests` | 10 pass, 1 error, 14 not run | `adler32.rtl`: Verilator 5.052 "Unsupported: virtual interface trigger on `bit[7:0]$[$]`" in generated `adler32_pkg_api_xls.sv:15` blocks the rest; per-example run below |


## Final rerun against the baseline (2026-11-01)

Logs are in `build/phase0-final/`.

| Suite | Baseline | Now | Verdict |
|---|---|---|---|
| fw-hdl `tests/xls` + be-xls | 171 passed, 4 failed | 189 passed, 3 failed | No regressions. Still failing: `test_compose` ×2 (`project.spl.utils`) and `test_c4_aes128_ctr` (Verilator signal 9). `test_formal_svunit` now passes. |
| zuspec-ir-core | 107 passed | 173 passed, 3 skipped | New tests only |
| zuspec-synth | 1115 passed, 53 failed, 96 errors | same | Unchanged |
| dv-flow-libsynth | 51 passed, 1 failed | same | Unchanged |
| zuspec-dataclasses | 2014 passed, 99 failed | 2020 passed, 102 failed | The only extra failures are in `test_zdc_builtins`, which fails a random 16–19 tests every run. No other differences. |
| fw-hdl python | 89 passed, 42 failed | same | Unchanged |
| examples (`<ex>.test`) | — | all pass | aes's FPGA synthesis (ice40/ECP5) was not run (>75 min); aes_ctr ran model/rtl/gates only. |

## Exit criteria (phase0-plan.md)

| # | Criterion | State |
|---|---|---|
| 1 | Existing XLS tests pass | Met. No regressions. The full `dfm run tests` sweep was not run end to end because aes's FPGA synthesis takes too long; every `<ex>.test` was run instead. |
| 2 | Engine Verilog byte-identical | Met. `test_engine_path.py` passes 4/4 (gcd, aes, lfsr, rle). |
| 3 | `anchors.json` + `overlays/xls-*.json` per example | Met. `xls_examples.<ex>.zir/<module>.zir/` for gcd, lfsr, rle, aes; rebuilt with the final overlay code, and all 44 files validate against the schemas (`build/phase0-final/schema-real.log`). |
| 4 | `iface` round-trips to `signature_from_codegen` | Met. Identical except for the schedule-filled channel `stage` (asserted in `test_engine_path.py`). |
| 5 | StageTLM byte-identical from the overlay | Met. The `Schedule` built from the bundle equals the one from the textproto (`test_schedule_from_bundle_matches_the_textproto`), and `stage_tlm_sv` is a pure function of it. |
| 6 | Canary green | Met, all four checks with no xfail (`test_canary_gcd.py`). |
| 7 | Mapping coverage recorded and gated | Met. `tests/xls/golden/mapping_coverage.json`; examples are 100% exact (functions) and 71–75% (rle procs). |
| 8 | Zero re-keying outside edited scopes | Met. A6 (a) = 0. |
| 9 | Releases | Prepared, not done: CHANGELOG "Unreleased" entries in ir-core, be-xls, zdc, libsynth. Version bumps and publishing wait for the user. |

## Left / follow-ups

- **Final `pytest tests/xls packages/zuspec-be-xls/tests` rerun (2026-11-02): 189 passed, 3 failed.** The three failures are the pre-existing baseline ones: `test_compose` ×2 and `test_c4_aes128_ctr`. Log: `build/phase0-final/pytest-xls.log`.

- **M5 release:** version bumps, tags, publishing, and pinning fw-hdl. These need the user's go-ahead.
- **Nothing is committed** in any repo (fw-hdl branch `mballance/fw-hdl-xls`; packages on `wpk/results-ir`).
- **Plan deviations:**
  - The engine interface lives in ir-core.
  - There is no `fw.hdl.Synth` task: the front end writes anchors, and `zuspec.xls.Overlay` builds the bundles.
  - The F4 canary is in fw-hdl.
  - New fact `xls.node_stage`.
