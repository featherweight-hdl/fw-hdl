# Legacy split: inventory

Step 1 of [legacy-split.md](legacy-split.md) §5 (see §2.3). Every tracked
(`git ls-files`) entry one level deep under `tests/`, `examples/`, `docs/`
(and one level into `docs/reference`, `docs/methodology`), `tools/`, `skills/`,
plus the repo-root files, marked:

- **legacy**: goes to branch `legacy`.
- **keep**: canonical, stays on `main` (sometimes with an edit, noted).
- **port**: wanted on `main` but depends on old code. Per §2.3 it goes to
  `legacy` with the rest plus a to-do, unless it is rewritten before the cut.

`src/` and `python/` are legacy wholesale (§2.2) and aren't listed.

**What counts as canonical.** The dfm packages `fw-hdl-spec` (`sv-api`,
`std-src`, ...), `fw.hdl.rt.sv`, `fw.hdl.fe.sv` (`Elaborate`, `Scan`, `GenKit`,
`GenAcc`, `EmitSV`); the Python namespaces `fw.hdl.fe.sv`, `fw.hdl.gen` (fe-sv)
and `fw.hdl.rt.sv` (rt-sv); SV packages `fw_hdl_pkg` / `fw_hdl_std_pkg` taken
from `packages/fw-hdl-spec` / `fw-hdl-rt-sv`. `fw-hdl-dv` has no code yet.
Old markers: the `hdl.sv-src` / `hdl.rv-src` tasks (the `src/flow.yaml`
fragment), `fw_std_pkg`, `fw_rv_pkg`, `fw_order_pkg`, `fw_root*`,
`fw_runnable`, `uses: fw.hdl.(api|xls|spl|report|knobs|...)`, and any
`fw.hdl.*` import outside the canonical namespaces.

## Repo root

| Path | Class | Evidence |
|---|---|---|
| `.envrc` | keep | sources `packages/packages.envrc` only |
| `.gitignore` | keep | edit: drop the `!python/fw/hdl/lib/` and `!tests/xls/lib/` exceptions |
| `AGENTS.md` | keep | edit per §2.4 (replace the "old front end" paragraph) |
| `LICENSE` | keep | |
| `fw-hdl.code-workspace` | keep | one folder, `.` |
| `ivpm.yaml` | keep | canonical deps (spec, fe-sv, rt-sv, dv) stay; prune deps that only the old tree uses: `zuspec-be-xls`, `zuspec-synth`, `pyslang`, `xlsynth`, `dv-flow-libsynth`, `dv-flow-libproject` (`tests/xls/compose`), probably `dv-flow-libformal` (`tests/formal`) |
| `flow.yaml` | port | entire content is the old regression: `tests` task + fragments `src/flow.yaml`, `tests/**/flow.yaml`. Rewrite as an umbrella flow over `examples/` |
| `pyproject.toml` | port | `fw-hdl = "fw.hdl.cli:main"`, `dv_flow.mgr` → `fw.hdl.dfm_ext`, `zuspec.lowering`, `where = ["python"]`, `testpaths = ["tests/python"]`. Cut down per §6.1 |
| `.github/workflows/ci.yml` | port | `pip install -e .` (old package) then `dfm run -j 64 tests`. Repoint at the new root flow / examples' pytest |
| `.forgejo/workflows/ci.yml` | keep | internal-identifier grep and packaging-metadata static check; no old-code dependency |
| `.forgejo/workflows/docs.yml` | legacy | builds the Sphinx site in `docs/`, which goes (see docs below). Ambiguous, see summary |

## tests/

| Path | Class | Evidence |
|---|---|---|
| `tests/blinky` | legacy | `needs: [hdl.sv-src]`; `import fw_std_pkg` |
| `tests/clock_domain` | legacy | `needs: [hdl.sv-src]` |
| `tests/conftest.py` | legacy | puts `tests/` on `sys.path` for `fw_tools`; only old suites use it |
| `tests/crossing` | legacy | `needs: [hdl.sv-src]` |
| `tests/dbg_filter` | legacy | `needs: [hdl.sv-src]` |
| `tests/dbg_listener` | legacy | `needs: [hdl.sv-src]` |
| `tests/dbg_op` | legacy | `needs: [hdl.sv-src]` |
| `tests/dbg_reg` | legacy | `needs: [hdl.sv-src]` |
| `tests/dbg_sched` | legacy | `needs: [hdl.sv-src]` |
| `tests/dbg_smoke` | legacy | `needs: [hdl.sv-src]` |
| `tests/dbg_struct` | legacy | `needs: [hdl.sv-src]` |
| `tests/edges` | legacy | TB driven by `tests/python/system/test_edges_sim.py` (`from fw.hdl.fe.parser import FW_LIB_FILES`) |
| `tests/fifo` | legacy | `needs: [hdl.sv-src]`; `import fw_std_pkg` |
| `tests/flow.yaml` | legacy | `smoke-img` `needs: [hdl.sv-src, smoke-tb]` |
| `tests/formal` | legacy | hand-written RTL (`fw_fifo`, `fw_initiator`, `fw_target`) proved with `formal.sby.BMC`; no fw-hdl dependency, but it is the formal twin of the old `rv_proto` and only the old regression runs it. Ambiguous |
| `tests/fw_smoke_tb.sv` | legacy | `import fw_std_pkg` |
| `tests/fw_tools.py` | legacy | generic tool finder (dfm, verilator, sby); used only by old suites (`rv_proto`, `stdlib`, `xls`, `python`) |
| `tests/intf_pc` | legacy | `needs: [hdl.sv-src]`; `import fw_std_pkg` |
| `tests/mmio` | legacy | driven by `test_mmio_sim.py` (`from fw.hdl.mmio_synth import ...`) |
| `tests/mmio_gated` | legacy | driven by `test_mmio_gated_sim.py` (old `fw.hdl.*`) |
| `tests/mmio_multi` | legacy | driven by `test_mmio_multi_sim.py` (old `fw.hdl.*`) |
| `tests/order` | legacy | FileSet `base: ../../src/std/order` (`fw_order_pkg`) |
| `tests/put_proto` | legacy | `needs: [hdl.sv-src]`; `import fw_std_pkg` |
| `tests/python` (all but the row below) | legacy | `conftest.py` puts `python/` on `sys.path`; `from fw.hdl.errors` (38), `fw.hdl.config` (37), `fw.hdl.fe.parser` (16), `fw.hdl.emit.regblock` (11) |
| `tests/python/system/test_wb_xtor.py` | keep (move) | only `fw.hdl.fe.sv` + `packages/fw-hdl-spec`, `fw-hdl-rt-sv`; no fixtures from the old conftest. Move to `examples/wb_xtor/tests/` and fix `_EX` (`parents[3]`) |
| `tests/reg_bus` | legacy | `needs: [hdl.sv-src]` |
| `tests/reg_core` | legacy | `needs: [hdl.sv-src]` |
| `tests/reg_dma` | legacy | `needs: [hdl.sv-src]` |
| `tests/reg_hooks` | legacy | `needs: [hdl.sv-src]` |
| `tests/reg_smoke` | legacy | `needs: [hdl.sv-src]` |
| `tests/reset_domain` | legacy | `needs: [hdl.sv-src]` |
| `tests/root_param` | legacy | `needs: [hdl.sv-src]` |
| `tests/root_restart` | legacy | `needs: [hdl.sv-src]` |
| `tests/rv_proto` | legacy | `needs: [hdl.sv-src, hdl.rv-src]`; `import fw_rv_pkg` |
| `tests/socket` | legacy | `needs: [hdl.sv-src]` |
| `tests/stdlib` | legacy | `needs: [hdl.sv-src]`; `../../src/rtl/fw_rv_fifo.sv`; `fw_order_pkg` |
| `tests/sync` | legacy | FileSet `base: ../../src/std` (`fw_std_pkg.sv`); tests `src/sync/`; weavers `fw.hdl.weave.*` |
| `tests/xing` | legacy | driven by `test_xing_sim.py` (`from fw.hdl.fe.parser import ...`) |
| `tests/xls` | legacy | `from fw.hdl.spl_flow` (50), `fw.hdl.xls_flow` (30); `uses: fw.hdl.spl.Partition` |

## examples/

| Path | Class | Evidence |
|---|---|---|
| `examples/cag-risc` | legacy | one sketch file, `cag_risc_c extends fw_component` with `fw_action`, `state_c`, `resource_pool_c` (none canonical) |
| `examples/counter.sv` | legacy | `import fw_std_pkg` |
| `examples/counter_tb.sv` | legacy | plain Verilog TB for `counter.sv`; goes with it |
| `examples/flow.yaml` | legacy | `fw-src` FileSet `base: ${{ rootdir }}/../src` (`fw_hdl_pkg.sv`, `std/fw_std_pkg.sv`) |
| `examples/log` | legacy | scratch notes ("TODO: Create root") |
| `examples/resp_tracker` | legacy | `uses: fw.hdl.spl.Partition`, `fw.hdl.spl.Integrate`, `fw.hdl.report.Ppa` |
| `examples/rr_merge` | legacy | `from fw.hdl.emit.sync`; `../../src` |
| `examples/rr_merge_pipe` | legacy | `from fw.hdl.emit.sync`, `fw.hdl.spikes.pipeline`, `fw.hdl.spikes.dataflow` |
| `examples/wb_initiator` | legacy | `scripts/gen_rtl.py`: `from fw.hdl.emit.sync import emit_sync`, `PYTHONPATH=../../python`; `run_sim.sh`: `$root/src/fw_root.sv`, `src/std/fw_std_pkg.sv`; `src/wb_init_pkg.sv`: `import fw_std_pkg`. `wb_xtor/README.md` item 6 calls it "the old, `src/`-based version". **Contradicts §2.2**, which lists it as canonical |
| `examples/wb_xtor` | keep | only `fw.hdl.fe.sv` (`elaborate`, `emit_sv`, `emit_xtor`), `uses: fw.hdl.fe.sv.Scan`; README: "Nothing comes from this repo's `src/` or `python/fw/hdl`" |
| `examples/xls` | legacy | `uses: fw.hdl.api.XlsBinding` (14), `fw.hdl.xls.IR` (13), `fw.hdl.api.ModelBinding` (13) |

## docs/

`docs/design/` stays whole (§2.2). The rest of `docs/` is a Sphinx site whose
every content page documents the old API; §6.3 removes `docs/reference`.

| Path | Class | Evidence |
|---|---|---|
| `docs/design/` | keep | §2.2: stays whole (107 files, incl. `probes/`, `research/`); old-tree docs get the one-line `legacy` header |
| `docs/conf.py` | legacy | Sphinx config for the old site; nothing left to build once the pages go. Ambiguous |
| `docs/index.md` | legacy | old API (`fw_runnable`, `fw_port #(fw_put_if)`, "compiles, through XLS, to RTL") |
| `docs/README.md` | legacy | site build notes; old example (`fw_root_begin`) |
| `docs/requirements.txt` | legacy | docs-build deps for the old site (`.forgejo/workflows/docs.yml`). Ambiguous |
| `docs/_static/`, `docs/_templates/` | legacy | `.gitkeep` only; go with the site |
| `docs/examples/` | legacy | `xls/*.md` (13): write-ups of `examples/xls` |
| `docs/methodology/components.md` | legacy | `fw_std_pkg`, `fw_step_ctx`, `fw_get_nb_if`, `fw_root` |
| `docs/methodology/flows.md` | legacy | `fw.hdl.lower.Lower`, `fw.hdl.xls.IR`, `fw.hdl.spl.Partition` |
| `docs/methodology/index.md` | legacy | toctree of this directory |
| `docs/methodology/ip-reuse.md` | legacy | `fw_extern_impl`, `fw_runnable`, `fw_rv_fifo` |
| `docs/methodology/islands.md` | legacy | `src/rtl/fw_xls_fifo_wrapper.sv`, `fw.hdl.spl.Integrate` |
| `docs/methodology/knobs.md` | legacy | `fw.hdl.knobs.Resolve`, `fw.hdl.verif.canon` |
| `docs/methodology/overview.md` | legacy | `fw_root_begin`, `fw_runnable`, `fw_std_pkg` |
| `docs/methodology/storage.md` | legacy | `fw_channel`, `fw_sram_fifo`, `fw_xls_fifo_wrapper` |
| `docs/methodology/sync-logic.md` | port | step/comb/run model is the canonical one (`fw_step_if`, `fw_comb_if`), but written against `fw_steppable`, `fw_sync_kernel`, `fw_root`. Rewrite in fw-hdl-spec docs |
| `docs/methodology/synthesis.md` | legacy | `fw.hdl.xls.IR`, `fw.hdl.spl.*`, `fw.hdl.lower` |
| `docs/methodology/testing.md` | legacy | `fw.hdl.api.XlsBinding`, `ModelBinding`, `Functions`, `Components` |
| `docs/methodology/timing.md` | legacy | `fw_resource`, `fw_timed`, `fw_ii`, `fw_guard`, `fw_storage` |
| `docs/reference/clocking.md` | port | domains/clock/reset concepts match canonical `fw_domain`, `fw_clock_kind`, `fw_reset_kind`, but written against `fw_root`, `fw_reset_xtor_bridge`, `fw_crossings`. Rewrite in fw-hdl-spec docs |
| `docs/reference/components.md` | legacy | `fw_steppable`, `fw_runnable`, `fw_step_undo` |
| `docs/reference/contracts.md` | legacy | `src/std/order/fw_order_pkg.sv`, `fw.hdl.verif.canon` |
| `docs/reference/debug.md` | legacy | 12-line stub over old `fw_hdl_pkg` observability |
| `docs/reference/diagnostics.md` | legacy | `fw.hdl.lower` diagnostics |
| `docs/reference/extern.md` | legacy | `src/fw_extern.svh`, `fw.hdl.rtl_header.read_header` |
| `docs/reference/facts.md` | legacy | `src/fw_facts.svh` |
| `docs/reference/index.md` | legacy | toctree of this directory |
| `docs/reference/knobs.md` | legacy | `python/fw/hdl`, `fw.hdl.knobs.Resolve` |
| `docs/reference/lib.md` | legacy | `src/std/fw_resource.svh`, `fw_channel.svh`, `fw.hdl.verif.cosim` |
| `docs/reference/macros.md` | legacy | autodoc of old `fw_hdl_macros`, `fw_std_macros` |
| `docs/reference/registers.md` | legacy | `fw_reg_component`, `fw_event_set` |
| `docs/reference/registry.md` | legacy | `fw.hdl.lib.registry` |
| `docs/reference/reports.md` | legacy | `fw.hdl.report.Latency`, `Ppa`, `fw.hdl.check.Contracts` |
| `docs/reference/rtl.md` | legacy | `fw.hdl.spl.Integrate` |
| `docs/reference/rv.md` | port | protocol section already points at fw-hdl-spec `std/fw_rv_proto.svh` + `GenKit`; the rest is `fw_rv_pkg` autodoc and `fw_root_bind_port`. Rewrite in fw-hdl-spec docs |
| `docs/reference/settle.md` | legacy | `fw.hdl.weave.settle`, `fw.hdl.weave.binding` |
| `docs/reference/spl-ir-contract.md` | legacy | contract for `zuspec.synth.spl`, fed by the old SPL flow (`fw_role`, `fw_pin`) |
| `docs/reference/std.md` | legacy | `fw_std_pkg` (21), `fw_valid_channel`, `fw_reg_level` |
| `docs/reference/struct-ports.md` | legacy | `fw.hdl.weave.sp_comb`, `fw.hdl.sync.Emit` |
| `docs/reference/tasks.md` | legacy | `python/fw/hdl/*.dv` tasks (`fw.hdl.xls`, `fw.hdl.spl`, `fw.hdl.report`) |

## tools/

| Path | Class | Evidence |
|---|---|---|
| `tools/anchor_churn.py` | legacy | measures Zuspec IR anchor stability across edits; `from fw.hdl.config`, `fw.hdl.spl_flow`, `fw.hdl.xls_flow`; corpus `examples/xls`, `src` |
| `tools/layer1_dep_lint.py` | keep | lints the layer-1 package repos for references back into `src/`/`python/` (complements the planned `check-no-legacy.sh`). Note: its `from fw\.hdl\.(?!fe\.sv\|rt\.sv)` rule would also flag fe-sv's own `from fw.hdl.gen`; add `gen` to the allow-list |

## skills/

| Path | Class | Evidence |
|---|---|---|
| `skills/fw-api-kit` | legacy | defines APIs via `` `FW_<PROTO>_IMP `` provider macros, a pattern defined only in old `src/fw_hdl_macros.svh` / `src/std/fw_std_macros.svh`; canonical APIs come from `fw-proto-kit` + `GenKit`. Ambiguous |
| `skills/fw-design-uarch` | legacy | `SKILL.md` is empty (0 bytes); delete |
| `skills/fw-hdl` | port | teaches `src/fw_root`, `src/fw_hdl_macros`, `src/std/fw_put_xtor_*`. Per §6.2, rewrite around modeling in `fw-hdl-spec/skills/` |
| `skills/fw-proto-kit` | keep | all paths into `packages/fw-hdl-spec` (`docs/examples/sbus/src/...`, `std/fw_rv_*`) and fe-sv (`GenKit`, `examples/wrap_rtl`) |

## Summary

| Area | Rows | keep | port | legacy |
|---|---|---|---|---|
| repo root | 11 | 7 | 3 | 1 |
| tests/ | 39 | 1 | 0 | 38 |
| examples/ | 11 | 1 | 0 | 10 |
| docs/ | 41 | 1 | 3 | 37 |
| tools/ | 2 | 1 | 0 | 1 |
| skills/ | 4 | 1 | 1 | 2 |
| **total** | **108** | **12** | **7** | **89** |

**Port candidates**

- `flow.yaml`, `pyproject.toml`, `.github/workflows/ci.yml`: stay as files,
  contents rewritten (umbrella flow over `examples/`; §6.1 minimal package;
  CI that runs it). These must be done in the cut commit, not deferred.
- `skills/fw-hdl`: rewrite in fw-hdl-spec (§6.2).
- `docs/methodology/sync-logic.md`, `docs/reference/clocking.md`,
  `docs/reference/rv.md`: the concepts are canonical (sync step/comb,
  domains, the rv protocol), only the code and autodoc are old. Worth a
  rewrite in the fw-hdl-spec docs; until then they go to `legacy` with a to-do.

**Relocation (keep):** `tests/python/system/test_wb_xtor.py` is the only
canonical test in `tests/`; move it under `examples/wb_xtor/` before `tests/`
goes, and point pytest `testpaths` at the examples (§6.1).

**Owner review**

1. `examples/wb_initiator`: §2.2 lists it as canonical, but it builds on
   `src/` and `fw.hdl.emit.sync`; `examples/wb_xtor` supersedes it. Classified
   legacy. Fix §2.2's "what stays" line.
2. The Sphinx scaffold (`docs/conf.py`, `requirements.txt`, `_static`,
   `_templates`, `index.md`, `README.md`) and `.forgejo/workflows/docs.yml`:
   with every page gone there is nothing to build. Legacy unless fw-hdl
   should keep an umbrella docs site.
3. `tests/formal`: standalone RTL, no fw-hdl dependency, but tests nothing on
   `main`. Legacy unless wanted as a seed for canonical formal tests.
4. `tests/fw_tools.py`: generic tool finder; legacy, but reusable if the
   moved `test_wb_xtor.py` or future example tests need it.
5. `skills/fw-api-kit`: superseded by `fw-proto-kit` + `GenKit`, or still
   wanted as a "pure API, no fw-hdl" skill (cf. `wb_xtor/src/wb_api_pkg.sv`)?
   If wanted, it's a port.
6. `ivpm.yaml` pruning: confirm which deps examples still need (e.g.
   `dv-flow-libformal`, `nextpnr`, `yosys` for `wb_initiator`'s equivalence).
7. `docs/examples/` isn't named in §2.2; it is legacy (XLS write-ups).
