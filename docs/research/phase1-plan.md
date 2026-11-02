# Phase 1 ("It's just a module"): implementation, test and documentation plan

*Status: **draft for review** (2026-11-02). The open decisions are in §10.*

This is Phase 1 of [adoption-path-plan.md](adoption-path-plan.md), implementing the design
in [shell-generation.md](shell-generation.md). It builds on Phase 0
([phase0-plan.md](phase0-plan.md), [phase0-status.md](phase0-status.md)): anchors, the
`iface.block` facts and the XLS engine overlay.

Code facts were checked against this packet on 2026-11-02. All changes stay in this
packet; zuspec-* changes go under `packages/` only.

## 0. Scope

**Goal.** A designer can put a class behind a **generated** module shell, drop it into an
existing RTL design, and swap in XLS RTL under the same testbench. Both shells are checked
against one pin contract.

**Roadmap decisions this plan assumes** (adoption-path-plan.md §6, recommended options):
1. SV projections (the shell and wrapper emitters) live in **zuspec-be-sv**, as a new `fw`
   target over the fw-hdl runtime.
2. The fw runtime (`src/`) stays in fw-hdl. be-sv emitters declare the runtime version they
   need.
3. No merge of fw-hdl `fe/` and `zuspec-fe-sv` yet.

**Not in Phase 1:**
- the TB mirror shell and monitors (shell-generation S6): Phase 2, with the SVUnit emitter
- several clock domains: one clock and reset per shell
- APB, CSR and other protocol kits beyond `fw_put` and `fw_rv`
- the call-API model (Phase 2)

**Facts found while planning** (they change the roadmap's version):
- **gcd and AES are XLS *function* blocks, not class trees.**
  - Their pins are data ports plus `input_valid`/`output_valid`, not channels.
  - `signature_from_codegen` (`zuspec-be-xls/signature.py:146`) reads only
    `channel_interfaces`, so today their signature has **no data pins**.
  - `BlockSignature` has no model for data ports or valid-only flow control.

  Pin parity for gcd/AES therefore needs a signature extension (P1) and a function-block
  shell (S4). It is the biggest piece not in the roadmap.
- **The rv kit is hard-wired to 32 bits on purpose.** `tests/rv_proto/rv_proto_tb.sv:50-58`
  documents two Verilator 5.049 bugs:
  - a parameterized interface as a module port crashes
  - a `type`-parameterized interface instance doesn't see externally driven inputs

  The packet now has Verilator 5.052. K1 tests both bugs first and picks a fallback if they
  are still there.
- **`STD_TRANSACTORS` has one entry** (`fw_put_xtor_bridge`). It is keyed by **bridge class
  name**, and its entry carries **lowering** semantics (`registered`, `pin_dir`,
  `data_port`), not only wiring. The registry needs those fields and a reverse lookup by
  bridge name.
- **The runtime bind map already exists.** `+fw_bindmap` writes JSON with an `unconnected`
  list (`src/fw_component_root.svh:77-104`, `src/fw_component.svh:392-420`). No Python
  reads it yet.
- **`signature_mismatches`** (`zuspec-be-xls/signature.py:180`) already compares
  signatures. Pin parity generalizes it rather than starting fresh.
- **Branches.** zuspec-be-sv is on `main` (release 0.2.0). zuspec-synth is on
  `wpk/results-ir` and has `proc/`, but no `kits/`. The roadmap's §3 note that `proc`
  exists only in a dev checkout is out of date.

## 1. Workstream E: environment and branches (do first)

- **E1. Branches.** Create `wpk/phase1` from the current branch in fw-hdl,
  zuspec-ir-core, zuspec-synth, zuspec-be-sv and zuspec-be-xls, after the Phase 0 commits.
- **E2. Baseline.** Run every suite that Phase 1 touches and keep the logs in
  `build/phase1-baseline/`:
  - `tests/xls`
  - `tests/python`, including `test_synth_golden` and `test_bind`
  - `tests/rv_proto`
  - the four package test suites
- **E3. Dependencies.**
  - zuspec-synth gains `zuspec-ir-core`, if it doesn't already depend on it.
  - zuspec-be-sv gains `zuspec-ir-core` and `zuspec-synth` (for the registry).
  - Check that `ivpm update` and `direnv exec .` still resolve the editable installs.

## 2. Workstream K: the rv kit in `src/std/rv/` (1.1, fw-hdl)

| # | Task |
|---|---|
| K1 | **Verilator check first.** Two small tests on 5.052: a `type T` interface as a module port, and a `type T` interface instance driven from outside. Record the result in the status file |
| K2 | Move `tests/rv_proto/` into `src/std/rv/`, using the one-file-per-unit layout from `skills/fw-proto-kit/references/example/src/`: `fw_rv_{initiator,target,monitor}_xtor_if`, `_xtor_core`, `_xtor`, with bridges and macros in an `fw_rv_pkg` |
| K3 | Parameterize on `type T`. **If K1 still fails, fall back** to `int W` with packed `logic [W-1:0]` on the pins, with the bridge casting `T` to and from bits. The class API keeps `type T` either way |
| K4 | Adapter bridges: `fw_put_to_rv_bridge #(T)` (put port → rv initiator) and `fw_get_from_rv_bridge #(T)` (get port ← rv target). rle's inputs are `fw_port #(fw_get_if …)`, so the get adapter is needed |
| K5 | `src/std/rv/fw_rv_kit.yaml` and `src/std/fw_put_kit.yaml`: descriptors in the R1 format |
| K6 | Keep `tests/rv_proto/` as a thin test that includes the `src/std/rv` sources, so its sims and SBY proofs keep running at width 32 and also run at 8 and at a struct type |

**Tests.**
- The existing rv_proto sims and proofs pass on the moved kit.
- New: a struct `T` payload, round-tripped initiator → target.
- New: the put → rv adapter with backpressure, so no beat is lost when `ready` is low.

## 3. Workstream R: kit descriptor and registry (1.2, zuspec-synth `kits/`)

| # | Task |
|---|---|
| R1 | **Descriptor format** `zuspec.kit` v1 (YAML, JSON Schema in the package, following Phase 0's `formats.md` policy). Fields from shell-generation §4.1: `kit`, `transactors[]` (`api`, `endpoint`, `module`, `params`, `if_path`, `bridge`, `pins`, `mirror`, `monitor`, `clock`, `reset`) and `adapters[]`. **Added to carry `STD_TRANSACTORS`:** `protocol`, `method`, `data_pin`, `pin_dir` and `registered` per transactor |
| R2 | **Project map** `zuspec.shell-map` v1 (`shell.yaml`): `top`, `defaults`, `endpoints` (`kit`, `omit`, `pins`), `clocks`, `pin_style` |
| R3 | `KitRegistry`: load kits from search paths (fw-hdl `src/std/**` plus the project's directories). Lookups: `resolve(api, kind, type_args, overrides)`, following the resolution order in §4.3; `by_bridge(name)` for lowering (T1) |
| R4 | Errors: an unresolved endpoint names the endpoint, its API type and the nearest kits (same API with another kind; same kind through an adapter) |
| R5 | `pin_style`: `xls` (`<ep>`, `<ep>_vld`, `<ep>_rdy`, clock `clk`, reset `rst`, active high) and `fw` (the kit's own template). The `xls` style is defined from `CodegenOptions` (`zuspec-be-xls/signature.py:21-29`), so the two stay in step |
| R6 | **Stale-map check.** The wrapper's real port list, read through a small reader interface, must match the `pins` template. The SV reader (pyslang) lives in fw-hdl and is passed in, so zuspec-synth gains no slang dependency |

**Tests** (zuspec-synth `tests/kits/`):
- the descriptor and map schemas validate
- the resolution order works: override beats defaults beats an exact kit beats an adapter
- the error message names the nearest kits
- `by_bridge("fw_put_xtor_bridge")` returns today's `ProtocolSpec` values
- the stale-map check catches a renamed pin

## 4. Workstream P: the contract and pin parity (1.5, ir-core + zuspec-synth)

| # | Task |
|---|---|
| P1 | **Signature for function blocks.** `BlockSignature` gains `kind` (`proc` or `function`) and `data_ports[]` (name, direction, width, SV type). `ChannelSignature.flow_control` gains `valid` for valid-only handshakes. Function blocks put `input_valid`/`output_valid` in a `valid_ports` field. This is `zuspec.block-signature` **v3**, because a v2 reader would treat a function block as having no pins. Readers keep accepting v1 and v2 |
| P2 | `signature_from_codegen` fills `data_ports` and the valid pins from codegen's `data_ports` and its `input_valid`/`output_valid` signal names. The overlay's `iface.block` fact then carries them for gcd, AES and lfsr |
| P3 | **`zuspec.synth.check.pin_parity(a, b, *, strict_names=True)`** returns a list of mismatches: name, pin direction, width, pin naming, clock, reset name and polarity, flow control. Move the comparison from `signature_mismatches`, which stays in be-xls as a thin wrapper so its tests keep passing |
| P4 | Reset polarity: XLS `rst` is active high, while shells may use `rst_n`. Parity compares the **pin** contract, so the shell has to emit the same polarity. The check names the mismatch rather than normalizing it away |

**Tests:**
- v3 round-trips, and v1 and v2 files still load
- gcd's and AES's `iface.block` facts now list their data ports
- parity passes for identical contracts and names each injected difference
- the be-xls signature tests still pass

## 5. Workstream G: edge discovery (1.3, fw-hdl)

| # | Task |
|---|---|
| G1 | **Static discovery.** Read the endpoints declared on the top class (`fw_port`, `fw_export`, `fw_socket`, `fw_mirror`) through pyslang, with each one's resolved API type and type arguments. Reuse `fe/structure.py`'s walk (`StructureMapper`) |
| G2 | **Bind-map discovery.** A zero-time Verilator elaboration of the top with `+fw_bindmap=<file>`, then read the `unconnected` list. This finds child endpoints (`drv.out`) that static discovery misses. It runs as a dfm task, so it is cached |
| G3 | **Explicit list** from `shell.yaml` `endpoints` |
| G4 | Merge the three into a **model contract** (`BlockSignature` v3, `kind: proc`) through the registry: each endpoint's pins come from its resolved kit and the `pin_style`. Write it as `<top>.shell.json` and as an `iface.block` fact on the class's anchor in the model's bundle (Phase 0 D5) |

**Tests:**
- static discovery on blinky finds `out : fw_put_if #(led_t)`
- static discovery on rle finds both get ports and the put port
- bind-map discovery on a two-level tree finds the unbound child endpoint
- static and bind-map discovery agree wherever both see an endpoint

## 6. Workstream S: shell and wrapper emitter (1.4, zuspec-be-sv `shell/`)

| # | Task |
|---|---|
| S1 | `zuspec.be.sv.shell.emit_class_shell(contract, resolutions) -> str`: the module ports from the contract, one transactor wrapper per endpoint, and the `fw_root_begin`/`bind_*`/`end` block (shell-generation §5). Declares its fw runtime version (decision 2) |
| S2 | `emit_function_shell(contract, fn)`: for function blocks. A module with the XLS function-block pins that calls the SV function. Its latency comes from the contract (a delay line of `latency` stages on the data and `valid`), so its pins **and** its timing match the XLS module. This lets the same TB drive both |
| S3 | `emit_xls_wrapper(contract)`: a thin wrapper around the XLS module that renames pins to the project's `pin_style` when it differs from `xls`. With `pin_style: xls` it isn't needed. This merges the pin naming from `comp_api.xls_binding_sv` and `fn_api` into the emitter; the call-API side of those files stays until Phase 2 |
| S4 | fw-hdl dfm task **`fw.hdl.shell.Generate`**: inputs are the SV sources, the top, an optional `shell.yaml` and the kit paths. Outputs are `<top>_shell.sv` and `<top>.shell.json`. Edge discovery runs first (G2 is optional, switched on by `discover: bindmap`). There is also a CLI form, `fw-hdl shell <top>` |
| S5 | **Output style.** The emitted SV is deterministic and lint-clean under Verilator `-Wall` (no new waivers) |

**The `blinky_top.sv` golden test.** See decision D2 for the alternatives.
- **Recommended:** the generated `blinky_top.sv` becomes the checked-in file, after one
  reviewed diff against the hand-written one: the same ports, transactor and bindings; the
  comments and formatting may differ.
- `test_synth_golden` then lowers the **generated** top, and `golden/blinky.rtl.sv` must
  not change. That proves the generated shell means the same thing to lowering.
- A new test regenerates the top and compares it byte for byte with the checked-in file.

**Tests** (be-sv unit tests plus fw-hdl integration):
- The blinky golden test above.
- The rle shell simulates under the existing rle testbench, run through `XlsBinding`
  against the shell instead of the XLS RTL.
- The gcd and AES function shells pass the same vector tests as the XLS RTL.

## 7. Workstream L: `logic` and an early lowerability check (1.6, fw-hdl `fe/`)

| # | Task |
|---|---|
| L1 | Accept 4-state `logic [N-1:0]` wherever `bit [N-1:0]` is accepted, on both routes (`fe/type_mapper.py:36-45` and `fe/static_mapper.py:136`). It maps to the same 2-state IR type. Add one front-end note: X and Z are not modelled, so an X in simulation is a sim-only value |
| L2 | **A neutral diagnostic format in ir-core**, `zuspec.ir.core.diag`: `Diagnostic(severity, code, message, loc, anchor, notes)` plus a JSON form `zuspec.diagnostics` v1. Phase 0 named this but didn't build it. fw-hdl's `errors.Diagnostic` converts to it |
| L3 | **Early lowerability check** `fw.hdl.check.Lowerable` (dfm task and API): runs the front end and the IR checker on the class without invoking XLS, and reports every construct that won't lower, in the neutral format, with source locations. It runs before `fw.hdl.xls.IR` in the example flows |

**Tests:**
- `logic` versions of the gcd and rle sources produce the same XLS IR as the `bit` versions
- a corpus of known-unlowerable constructs each gets one diagnostic with the right `loc`
- the diagnostics JSON validates

## 8. Workstream T: retire `STD_TRANSACTORS` (1.7, fw-hdl)

| # | Task |
|---|---|
| T1 | `fe/bind/elaborate.py:115,192` look bridges up through `KitRegistry.by_bridge`, loaded from fw-hdl's kit paths. They return the same `ProtocolSpec` fields |
| T2 | Delete `STD_TRANSACTORS` and `lookup`. `protocols.py` keeps the `ProtocolSpec` dataclass, or imports it from the registry |
| T3 | Lowering (`fw.hdl.lower`) reads the generated top when there is no hand-written one. The kit registry is then the one source of truth for both generation and lowering |

**Tests:**
- `test_bind` and `test_synth_golden` pass unchanged
- a new kit, added only through YAML (a test-only `fw_put2` with another bridge name),
  lowers with no Python change

## 9. Demo and sequence

**Demo** (`examples/shell/rle_swap/`):
1. An RTL design (a ready/valid source FIFO → an RLE block → a sink FIFO), where the RLE
   block starts as a hand-written `always_ff` FSM.
2. Replace the FSM with `RunLengthEncoder32` behind its generated shell. The same
   testbench passes.
3. Swap in XLS RTL through a fileset change. Pin parity passes, and the same testbench
   passes again.

The demo runs as dfm tasks, `rle_swap.test.{rtl_fsm,model_shell,xls}`.

**Sequence:**

| Milestone | Contents | Gate |
|---|---|---|
| M1 | E1–E3, K1, R1–R2 (formats), P1 (signature v3) | The formats are reviewed |
| M2 | K2–K6, R3–R6, P2–P4 | The kit runs from `src/std/rv`; the registry tests pass; gcd/AES `iface.block` facts have data ports |
| M3 | G1, G3, G4, S1, S4, S5; the blinky golden test | **Exit 1:** `blinky_top.sv` regenerates |
| M4 | S2, S3, G2; parity for rle, gcd and AES | **Exit 2:** pin parity passes for rle, gcd and AES |
| M5 | T1–T3, L1–L3 | **Exit 3:** `STD_TRANSACTORS` is gone; `logic` is accepted |
| M6 | The demo, docs, CHANGELOGs, the full rerun against the baseline | Demo green |

L1–L3 don't depend on the rest and can run alongside M2–M4.

**Effort:** the roadmap's sum is about 5–7 weeks. P1/P2 and S2 (function blocks) add about
a week that the roadmap didn't count.

## 10. Decisions for review

- **D1. Signature v3 for function blocks** (P1).
  - **Recommended:** extend `BlockSignature` (`kind`, `data_ports`, `valid` flow control).
    One contract type covers both block kinds.
  - **Alternative:** limit pin parity to procs (rle only) and treat gcd/AES as out of scope.
    That breaks the exit criterion as written.
- **D2. What "`blinky_top.sv` regenerates" means.**
  - **Recommended:** the generated file replaces the hand-written one after one reviewed
    diff, and the lowering golden stays byte-identical.
  - **Alternative:** a byte-exact regeneration of today's hand-written file, comments
    included. That makes the emitter carry blinky-specific text.
- **D3. Verilator fallback** (K3). If `type T` interfaces still break on 5.052:
  - **Recommended:** `int W` on the pins and interfaces, `type T` on the class API, with the
    bridge casting between them.
  - **Alternative:** wait for a Verilator fix.
- **D4. Where pin parity lives.** **Recommended:** `zuspec.synth.check`, with the be-xls
  function kept as a wrapper.
- **D5. The neutral diagnostic format** (L2). **Recommended:** a small one in ir-core now,
  since both front ends need it for decision 3.

## 11. Status

| Step | State | Note |
|---|---|---|
| Plan | draft | Awaiting review of §10 |
| E1–E3 | — | |
| K1–K6 | — | |
| R1–R6 | — | |
| P1–P4 | — | |
| G1–G4 | — | |
| S1–S5 | — | |
| L1–L3 | — | |
| T1–T3 | — | |
| Demo | — | |

*Update this table as steps land, so a fresh session can resume from this file.*
