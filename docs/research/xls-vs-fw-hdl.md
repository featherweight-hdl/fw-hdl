# XLS vs fw-hdl (with XLS as the synthesis engine): positioning

*Research note, 2026-11-01. XLS facts come from google/xls and xlsynth/xlsynth `main`
(`bc53272`, 2026-10-30), xlsynth v0.60.0 release assets, and xlsynth-crate (`82a8459`,
2026-10-31). fw-hdl facts come from this repo at `62ea7a0` and from `fw-aes-demo`.*

## 1. Bottom line

The claim holds, with one nuance:

> **XLS produces nothing above RTL that runs in a SystemVerilog simulator.** The only SV it
> emits is synthesizable RTL. That RTL carries SVA asserts and covers, and `$display` traces
> guarded by `` `ifdef ``. There is no behavioral, TLM or SV-class model and no DPI-C
> wrapper, upstream or in xlsynth. A grep of google/xls and xlsynth-crate for
> `dpi` / `DPI-C` / `svdpi` finds nothing relevant.

The nuance is that XLS has a **strong above-RTL world of its own**, in C++. It has the DSLX
interpreter, the IR/proc JIT, `#[quickcheck]` proofs, and a cycle-accurate *block* JIT that
runs scheduled proc networks with FIFOs. It also has AOT-compiled C++ wrapper classes for
functions, procs and blocks. A team *could* hand-build a DPI shim over those wrappers. But
none of that is designed to live inside an SV testbench, and for proc networks the shim
inherits real problems (§4).

**The value proposition in one sentence:**
*fw-hdl makes the pre-RTL model a first-class SystemVerilog citizen. It is simulated, debugged,
timed and integrated with the existing SV/UVM environment and RTL, at every abstraction
level from untimed to cycle-exact. It is still synthesized by XLS from the same source, so
nobody writes DSLX and nobody maintains a C++/DPI model.*

## 2. What XLS actually provides above RTL

| Capability | XLS | Where it runs |
|---|---|---|
| Untimed function execution | DSLX interpreter, IR interpreter, LLVM JIT | XLS tools / C++ |
| Untimed proc-network execution | `eval_proc_main --backend=serial_jit` and `ProcRuntime::Tick()` (activation-based) | XLS tools / C++ |
| FIFO depth / back-pressure in untimed proc sim | **Not honored.** Queues are unbounded and sends never block ([#988](https://github.com/google/xls/issues/988), open since 2023, "would like to … see deadlock problems before RTL") | — |
| Timed proc model (latency/II applied to activations) | **None.** Nothing sits between untimed procs and block IR | — |
| Cycle-accurate pre-RTL | Block interpreter / block JIT on **scheduled block IR**, with FIFO and delay-line models | XLS tools / C++ |
| Embeddable C++ models | `cc_xls_ir_jit_wrapper`: FUNCTION / PROC / BLOCK wrappers, AOT-compilable | C++ (user must glue) |
| Model inside an SV simulator | **None**: no DPI, TLM, SV class or SystemC output | — |
| SV types | `#[sv_type]`, and xlsynth `dslx2sv-types` / `dslx_to_sv_types` (packed structs, enums) | SV packages, types only |
| Assertions / covers / traces | `assert!` → SVA under `` `ifdef ASSERT_ON ``; `cover!` → `cover property`; `trace_fmt!` → `$display` under `` `ifdef SIMULATION `` | Inside the generated RTL |
| Formal | Z3/Bitwuzla IR equivalence (procs bounded by activation count), `prove_quickcheck`, symex; xlsynth adds `ir-equiv-blocks`, `dslx-equiv` and a Lean path | XLS tools |
| Coverage above RTL | Essentially none. Interpreter/JIT coverage is a no-op ([#1126](https://github.com/google/xls/issues/1126)), there is no DSLX source coverage ([#2139](https://github.com/google/xls/issues/2139)), and only IR node bit-coverage exists | — |
| Timing visibility pre-RTL | Per-node stage assignment, `delay_info_main` critical path, static per-proc latency/II. **No network-level performance model** | XLS tools |
| Mixing with hand RTL | `#[extern_verilog]` FFI, **combinational only** (sequential FFI is [#1301](https://github.com/google/xls/issues/1301), open). DSLX-vs-Verilog FFI consistency check is [#1400](https://github.com/google/xls/issues/1400), open | Codegen-time substitution |
| Co-simulating DSLX with surrounding RTL | **Not provided.** Composing a DSLX model with a DUT in the C++ evaluator is "a fair amount of toil" ([#1638](https://github.com/google/xls/issues/1638)) | — |
| Debug of XLS RTL in a chip sim | Source annotations (`--source_annotation_strategy`), Verilog→IR line map, labelled SVA. Proc state flattens to mangled `__state` names that Verilator VCDs hide ([#2042](https://github.com/google/xls/issues/2042)) | SV sim |

Other relevant facts:
- Open-source RTL simulation in XLS is iverilog only. xlsynth adds its own `vastly` simulator.
- xlsynth's release binaries **omit `eval_proc_main` and `simulate_module_main`**, so xlsynth
  users without a Bazel build of XLS don't even get the proc/block evaluators.
- xlsynth-crate (Rust) exposes a **function-only** JIT. It has no proc or block JIT bindings
  and no Python bindings.
- Recent xlsynth activity (Sep–Oct 2026) is mostly gate-level work: tech mapping, STA, AIG,
  proofs and the Lean path. Nothing targets SV co-simulation.
- Multi-proc codegen (`--multi_proc`) instantiates FIFOs through a user-supplied
  `xls_fifo_wrapper` contract, and is still under-documented
  ([#1560](https://github.com/google/xls/issues/1560)).

**So the XLS verification story is "verify in XLS-land, then verify the RTL."** The model
and the system it lives in meet for the first time at RTL.

## 3. The status-quo alternative: DSLX/XLScc plus an untimed C++ model via DPI

A team using XLS today that wants a pre-RTL model in its SV environment typically does one of
the following:

1. **Wait for RTL.** Integrate the XLS-generated RTL and debug at RTL in the SoC sim. This is
   the slowest sim and the latest feedback, and debug happens on flattened, mangled state.
2. **Hand-write a DPI shim** over a separately maintained C++ golden model, or over the XLS
   JIT/AOT wrapper:
   - **Function-only blocks**: fine. A DPI call returns the answer, and timing is either
     ignored or a hand-added `repeat (N) @(posedge clk)`.
   - **Proc networks**: this is where it breaks down. See §4.

## 4. Why proc networks are the decisive case

Take a model of several processes connected by channels: a crypto engine fed by a DMA, a
packet pipeline, or GCM (AES-CTR plus GHASH).

| Concern | DSLX procs + JIT behind DPI | fw-hdl |
|---|---|---|
| What the SV sim sees | One opaque C++ blob. All procs and channels are hidden inside `ProcRuntime` | Each process is an SV class and each channel is an SV object (`fw_channel #(T, DEPTH)`), visible to the SV debugger, `$display` and waves via transactors |
| Notion of time | None: `Tick()` is "one activation of each proc". The shim author invents a clock mapping | Native: each component has a clock domain; `tick(n)`, `fw_quantum_keeper`; generated StageTLM timing |
| FIFO depth / back-pressure | Ignored: unbounded queues (#988), so a deadlock from undersized FIFOs is invisible until RTL | `put` blocks at `DEPTH`, and depth 0 is a rendezvous, so a deadlock shows up in the model, in the SV sim, with an SV call stack |
| Determinism | Kahn semantics within XLS | Kahn semantics by construction: blocking get/put, no peek, polling only through explicit `try_get` |
| Partial refinement | All-or-nothing: the whole network is either in C++ or in RTL | Per-instance view selection: one block at V0, another at V3, another as RTL, in the same sim (fw-aes bench: rtl / v3 / v0 by define) |
| Splicing real RTL into the network | Not possible inside the blob. Sequential FFI doesn't exist (#1301) | Transactors (bridge class plus virtual interface) put an RTL block on any channel edge |
| Connecting to the existing TB | Hand-written DPI marshalling per channel, plus a hand-written clock/handshake adapter | `fw_root` plus `` `fw_root_bind_port/export `` macros; generated `<module>_xtor_if` around each XLS module |
| Single source of truth | No: DSLX for synthesis, plus either JIT glue or a separate C++ model that can drift | Yes: the same SV class is simulated and lowered to XLS IR (no DSLX) |
| Debug language | DSLX/C++ (different debugger, separate process) for the model, SV for everything else | SV throughout |
| Who writes it | HW team learns DSLX, plus someone owns C++/DPI glue | HW/DV team writes SystemVerilog classes it already knows |

## 5. What fw-hdl offers, with XLS still doing the synthesis

The flow, as implemented in this repo:

1. **Write behavior** as SV classes (`fw_component`) connected by FIFOs/channels
   (`src/std/fw_channel.svh`). It is plain IEEE 1800 and runs in any SV simulator without
   preprocessing.
2. **Integrate early.** Drop the model into the existing TB or RTL via transactors at the pin
   edge (`src/fw_root.sv`, `src/fw_hdl_macros.svh`, `src/std/fw_put_xtor_bridge.svh`).
3. **Annotate timing before RTL**, in three ways:
   - by hand with `tick(n)`
   - from the XLS schedule itself (`fw.hdl.xls.StageTLM`, which reads XLS's schedule
     textproto and produces a V3 class that waits the XLS pipeline latency)
   - from architecture specs (`ii`, `latency`, `fold`) via ArchSched for exploration
4. **Partition and synthesize.** SV is parsed (slang), mapped to zuspec IR, and lowered
   directly to **XLS IR**. Then XLS `opt_main` and `codegen_main` run. QoR tracks hand DSLX
   closely (AES: 6975 vs 6976 IR nodes).
5. **Assemble.** `fw.hdl.spl.Integrate` builds the RTL top from XLS signatures:
   per-block instances, with an `fw_rv_fifo` or wire per channel.
6. **Re-verify at every level with one test.** The same unedited SVUnit file runs at the
   `model`, `rtl` and `gates*` levels through generated bindings. In
   `examples/xls/RESULTS.md`, 11 ported XLS examples pass with identical test hashes at every
   level, and sha256 also passes at three clock periods.

### Things XLS structurally can't do that fw-hdl does

- **System-context-driven synthesis (cosynthesis).** fw-hdl knows the system the block lives
  in. Contract records (sidecar YAML), proved with SBY on the *implementing transactor*, let
  `fw.hdl.cosynth` remove logic the system never exercises, followed by a pre==post
  equivalence check. On AES A0 that gives FF 999→418, LUT4 111073→83329, and 4→3 clk/op.
  XLS sees one block in isolation and can't make these cuts.
- **A ladder of views the user moves along, not a cliff.** V0 is the algorithm, V1 the
  untimed network, V3 the scheduled TLM, V4 the cycle class and V5 the RTL. Every view uses
  the same API and runs in the same SV sim. XLS jumps from untimed procs straight to block IR
  and RTL.
- **Fast timed models that scale.** StageTLM is 2.8–4.7× faster than RTL on Verilator, and
  flat in idle instances (0.18 s from 1 to 64 instances, vs 33 s for RTL). That is the
  property that matters at SoC scale.
- **Architecture exploration in the user's own sim.** A0–A4 give 4 to 200 clk/op with area
  numbers, each as a drop-in V3 class.

### What we still take from XLS (and should say so)

The XLS optimizer, scheduler, delay models, codegen (ready/valid, FIFOs, I/O flops), IR
equivalence (fw-hdl reports "equivalent" for most examples) and the open-source PDK delay
models. fw-hdl is **a front end and verification environment for XLS**, not a competitor to
its back end. `xls-native-roadmap.md` keeps XLS as the oracle even as native lowering grows.

## 6. Comparison at a glance

| Dimension | XLS (DSLX / XLScc) | fw-hdl → XLS |
|---|---|---|
| Source language | DSLX (Rust-like) or C++ subset | SystemVerilog classes |
| Pre-RTL model in SV sim | ✗ (RTL only; DPI is DIY) | ✓ native |
| Proc network visibility in SV | ✗ | ✓ per-process, per-channel |
| FIFO depth honored pre-RTL | ✗ untimed / ✓ block JIT (C++ only, post-schedule) | ✓ in the SV model |
| Timed TLM between untimed and RTL | ✗ | ✓ V3 (latency from XLS schedule) |
| Cycle-accurate pre-RTL | ✓ block JIT (C++) | ✓ V4 class in SV (A0) |
| Mixed-abstraction sim per instance | ✗ | ✓ |
| Sequential RTL in the model | ✗ (#1301) | ✓ via transactors |
| One test across model/RTL/gates | Partial (same vectors via tools; different harnesses) | ✓ same SVUnit file, generated bindings |
| Unit-level property proofs | ✓ strong (`prove_quickcheck`, IR equiv) | Inherits XLS IR equiv; SBY for contracts |
| Synthesis QoR | XLS | XLS (≈ identical IR) |
| System-aware optimization | ✗ | ✓ contracts → cosynth (prototype) |
| Coverage above RTL | ✗ | SV functional coverage on the model (standard SV) |
| Maturity | Production use at Google; large corpus | Prototype; see §7 |

## 7. Where the fw-hdl story is still thin

These need fixing, or careful wording, before the pitch is put in front of skeptics:

1. **StageTLM models latency only.** An `op` blocks for the full pipeline latency, with no II
   or overlap of ops in flight. That is fine for a non-pipelined use, but it under-reports
   throughput for a pipelined XLS block. Needed: an II-aware V3 (accept every II clocks,
   deliver after latency). Also, the cycle-fidelity check is a 32-op run, not a proof.
2. **Partitioning is manual.** `fw.hdl.spl.Partition` requires all children to be XLS.
   Channels between XLS and native blocks are out of scope (`xls-phase2.md` §6), and the
   automatic partitioner is design-only. The "write a mixed network, partition it" story is
   the headline, but end to end it works today only for all-XLS networks.
3. **The proc subset is restricted.** These are rejected with a located diagnostic:
   - get/put inside loops
   - two operations on one channel per activation
   - `#delay` and `@`
   - task calls
   
   The rules should be documented as a modeling guideline, to frame them as a feature
   (lowerable by construction) rather than a surprise.
4. **Cosynthesis is AES-A0-specific** (hard-wired port names). X4, X5 and X7 aren't
   implemented, and the sequential pre==post proof uses abstracted stages.
5. **Test health and reproducibility.**
   - There are no repo tests for StageTLM or cosynth; they are exercised only through
     fw-aes.
   - The `tests/python/unit` baseline is 81 pass / 34 fail.
   - Several dependency branches aren't pushed, so fw-aes can't be rebuilt elsewhere.
6. **There is no AES-scale proc-network demo yet.** The proc-network argument (§4) is the
   strongest one, but the flagship demo is a single function block. GCM (CTR plus GHASH plus
   DMA) is designed (`fw-aes-demo/docs/design/gcm-partition.md`) and would be the ideal
   showcase:
   - a visible network in SV
   - a deadlock caught pre-RTL by FIFO depth
   - a V3 timing estimate vs RTL
   - mixed views
   - contract-driven trimming

## 8. Suggested pitch

**For the architect:** You get a timed, executable model of the subsystem inside your
existing SV environment weeks before RTL. Its latency comes from the real XLS schedule, its
FIFOs have real depths, and you can swap any block for RTL as it lands.

**For the DV engineer:** There's no DSLX, no C++ golden model and no DPI glue. The model is
SystemVerilog classes. You debug it with your simulator's debugger, and one test runs
unchanged against model, RTL and gates.

**For the designer:** You write behavior once, in SV, and XLS synthesizes it. QoR matches
hand-written DSLX. And because the flow knows the system context, it can strip logic that
the system provably never uses, which XLS on its own can't do.

**For the XLS user:** Keep XLS. fw-hdl is the missing layer between untimed DSLX procs and
RTL. That layer is a timed, SV-native, system-integrated model, and XLS has no equivalent
for it today.

## Appendix: key sources

- XLS `eval_proc_main` backends: `xls/tools/eval_proc_main.cc`. Untimed runtime:
  `xls/interpreter/proc_runtime.h`. Block FIFO models: `xls/interpreter/block_interpreter.cc`.
- JIT wrappers: `xls/build_rules/xls_ir_wrapper_rules.bzl`, `xls/jit/jit_proc_wrapper_h.tmpl`,
  `xls/jit/jit_block_wrapper_h.tmpl`.
- Assert/cover/trace emission: `xls/codegen/module_builder.cc`.
- Docs: https://google.github.io/xls/ (interpreters, tools, codegen_options, scheduling,
  dslx_ffi, solvers).
- xlsynth: https://github.com/xlsynth/xlsynth/releases/tag/v0.60.0,
  https://github.com/xlsynth/xlsynth-crate, https://github.com/xlsynth/rules_xlsynth.
- Open issues: #988 (FIFO depth in sim), #1126 / #2139 / #4963 (coverage), #1301 (sequential
  FFI), #1400 (FFI consistency), #1560 (multi-proc docs), #1638 (model+DUT composition toil),
  #2042 (mangled state in VCD).
- fw-hdl: `docs/methodology/{overview,components,synthesis,flows,testing}.md`,
  `python/fw/hdl/{xls_flow,stage_tlm,spl_flow}.py`, `python/fw/hdl/cosynth/`,
  `examples/xls/RESULTS.md`, `xls-phase2.md`; fw-aes: `fw-aes-demo/docs/summary.md`,
  `docs/design/baseline.md`, `docs/walkthrough/*`; plan:
  `featherweight-hdl/fw-hdl/multi-view-hls.md`.
