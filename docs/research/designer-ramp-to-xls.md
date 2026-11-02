# A Verilog designer's ramp to XLS: story, status and build plan

*Strategy note, 2026-11-01. Companion to [xls-vs-fw-hdl.md](xls-vs-fw-hdl.md).*

There are two tracks (§6):
- **Track A, commercial adoption** (§1–§5). XLS is the recognized leader, and we use its
  engine as a black box for its validated QoR. fw-hdl's job is to make XLS reachable and
  trustworthy from an ordinary SystemVerilog RTL design practice.
- **Track B, forward-looking.** XLS is a black box, and we build incremental lowering that
  produces executable models at several levels of abstraction.

The two tracks share one spine, and Track A must be built so that it doesn't close off
Track B.

## 1. The story

**Audience.** RTL designers who write Verilog/SV every day. They have:
- an existing chip or subsystem RTL tree
- a simulator (VCS, Xcelium, Questa or Verilator) with waves
- lint and CDC signoff
- a Fusion Compiler (or DC/Genus) back end

They aren't going to learn DSLX, and they don't want an untimed C++ model they can't
instantiate.

**Promise.**
> Write the new block as a SystemVerilog class instead of an `always_ff` state machine.
> Instantiate it in your RTL **like any other module**, with the same name and the same
> ready/valid ports, and simulate it with your simulator, your testbench and your waves.
> When it's right, press a button: XLS generates the RTL behind that same module
> interface, with Google's validated QoR, and it goes to Fusion Compiler like the rest of
> your RTL.

**Why it's natural for a Verilog designer.** Every step happens in a place they already
work:

| Designer habit | What fw-hdl gives them |
|---|---|
| "I instantiate modules." | Each XLS block is a **module shell** with XLS's exact port list. Behind it is the class model, then the XLS RTL. The parent RTL never changes |
| "I debug in waves." | The shell's pins are real ready/valid signals at every level, so channel traffic looks the same in the model and in RTL |
| "I write SV." | The source is SV (classes, packed structs, functions). No DSLX and no C++ |
| "I think in clocks, latency and throughput." | `tick(n)` in the model, and latency/II taken from the XLS schedule. The design target is given as latency/II/clock period, not as a pipeline to hand-code |
| "My tests are SV/UVM." | The same test drives the shell at every level, because the pins are identical |
| "My RTL must pass lint/CDC/synthesis signoff." | XLS RTL is generated with the house reset style, naming and constraints, and it ships with its signature and schedule |

"Medium-level synthesis" is the right framing. The designer still owns the architecture:
blocks, channels, FIFO depths and clocking. XLS owns the inside of each block: scheduling,
pipelining, retiming and optimization.

## 2. The workflow, step by step: what exists and what to build

Legend: ✅ exists and is tested · 🟡 partial, prototype or demo-only · 🔴 to build

### Step 1: Write an XLS-friendly block in SV
| Item | Status | Where / notes |
|---|---|---|
| Pure functions → XLS functions (combinational or pipelined) | ✅ | `docs/methodology/synthesis.md`; 11 examples in `examples/xls/` |
| `forever {get … put}` component → XLS proc (state = class properties) | ✅ | `xls_flow.py`, `lower_proc` in zuspec-be-xls |
| Parametric functions via parameterized classes | ✅ | `lfsr_c#(8)::lfsr` |
| Located diagnostics for unlowerable code | ✅ | static mapper |
| **Accepting `logic`** (designers write `logic` everywhere; today wider `logic` is rejected) | 🔴 | `fe/type_mapper.py:40`, `fe/static_mapper.py:136`. Accept it as 2-state with a lint note. This is the first friction point every designer will hit |
| **"XLS-friendly SV" coding guide**, written for RTL designers ("instead of an FSM, write…") with a translation table: FSM / `always_ff` idioms → class idioms | 🔴 | `synthesis.md` is a reference, not an on-ramp |
| **Early "lowerable?" check** as a lint step run with the simulator, not at synthesis time | 🔴 | Run the static mapper as a standalone `fw-hdl check`. The automatic-partitioner design already proposes a try-map with `--explain` |
| Memories: `fw_mem_if` → XLS RAM channels → SRAM macros | 🔴 | XLS has `--ram_configurations` (experimental). Real blocks need SRAMs, so this is a gating feature for anything beyond datapaths |

### Step 2: Instantiate it in existing RTL and simulate
| Item | Status | Where / notes |
|---|---|---|
| Class tree under a module (`fw_root`, `` `fw_root_begin `` / `bind_port` / `bind_export``) | ✅ | `src/fw_root.sv`, `src/fw_hdl_macros.svh` |
| Put-direction transactor in the library | ✅ | `src/std/fw_put_xtor_bridge.svh` |
| Ready/valid initiator/target transactors | 🟡 | Work in `tests/rv_proto/` (3-part kit, sim + SBY) but are **not in `src/std`** |
| **Generated module shell**: for a block, emit `module <blk>` with **exactly XLS codegen's ports** (`clk`, reset name and polarity, `<ch>`/`<ch>_vld`/`<ch>_rdy`, same suffixes and widths), containing `fw_root` plus ready/valid transactors around the class | 🔴 | **The keystone.** Today the model is reached through the test API harness (`<api>_harness`), not through pins. The shell must be generated from the same naming rules that are passed to `codegen_main`, so the model and RTL shells are interchangeable by fileset |
| Pin-compatibility check: shell port list == XLS signature | 🔴 | Compare the shell against `zuspec.xls.Signature` output. Fail the build on drift |
| Packed-struct ports that use the designer's own typedefs | 🔴 / verify | XLS flattens to bit vectors unless `#[sv_type]` / `--emit_sv_types` apply. We need to emit the shell with the same typedefs, or with flat ports plus a typedef'd wrapper |

### Step 3: Verify and validate in the RTL environment
| Item | Status | Where / notes |
|---|---|---|
| One SVUnit test at model / rtl / gates | ✅ | `docs/methodology/testing.md`, `examples/xls/RESULTS.md` |
| Same pins at every level, so **any** existing TB/UVM env works unchanged | 🔴 | Falls out of the module shell (step 2) |
| SV immediate `assert` → XLS assertion → SVA in the RTL | 🟡 | Mapping exists (`synthesis.md` types table). Verify end to end that `assert property` appears under `ASSERT_ON` |
| `$display` in the class → `trace_fmt!` → `$display` under `SIMULATION` in the RTL | 🔴 | No mapping today (grep of `static_mapper.py`). Cheap, and designers will expect it |
| `cover` in the class → `cover!` → `cover property` | 🔴 | Gives functional coverage that survives into RTL |
| Model ↔ XLS IR differential check (our SV→IR translation is the new trust boundary) | 🟡 | `tests/xls/` has fuzz/golden/corpus suites. Make it a standard per-block flow step: same vectors through the SV model and the XLS IR JIT (`eval_ir_main` / `eval_proc_main`) |
| Properties proved over the whole input domain | 🔴 | Map `function bit prop_*` in SV to XLS `#[quickcheck]` and run `prove_quickcheck_main`. This is unit-level formal for free, in the designer's language |
| FIFO-depth deadlock found in the model | ✅ | `fw_channel #(T, DEPTH)` blocks at depth. This is a real advantage over XLS's own simulators (#988) |

### Step 4: Estimate timing and performance before RTL
| Item | Status | Where / notes |
|---|---|---|
| Hand annotation (`tick(n)`, quantum keeper) | ✅ | `docs/reference/clocking.md` |
| Latency from the XLS schedule (StageTLM) | 🟡 | `stage_tlm.py`. **Functions only, latency only.** One op blocks for the full pipeline, with no II or overlap |
| **Timed shell** for procs and functions: the class model wrapped with XLS-scheduled latency (delay line) and II (accept throttle) on the shell's ready/valid ports | 🔴 | Same pins as the RTL, so it drops into the same place. It gives architects throughput and back-pressure behavior before RTL |
| **Designer-facing constraints**: target clock, latency, II, I/O timing, written next to the class (SV attribute or YAML) and passed to XLS (`--clock_period_ps`, `--pipeline_stages`, `--worst_case_throughput`, `--io_constraints`, `--clock_margin_percent`) | 🟡 | Only `clock_period_ps` and `pipeline_stages` are wired (dv-flow-libsynth `xls/codegen.py`) |
| Report: per-block latency/II/stages/critical path (`delay_info_main`) plus an area estimate, in designer terms | 🔴 | XLS produces it all; we just collect it into one table per build |

### Step 5: Generate RTL with XLS for Fusion Compiler
| Item | Status | Where / notes |
|---|---|---|
| SV → XLS IR → `opt_main` → `codegen_main` | ✅ | `fw.hdl.xls.IR` → `synth.xls.Codegen` |
| QoR parity with hand-written DSLX | ✅ | AES: 6975 vs 6976 IR nodes; equivalence "equivalent" for most examples |
| Reset style | 🟡 | `--reset` and `--reset_active_low` are wired. **Not wired:** `--reset_asynchronous` and `--reset_data_path`, which most ASIC houses need set explicitly |
| I/O flop policy | 🟡 | `flop_inputs` only. Wire `--flop_inputs_kind` / `--flop_outputs_kind` (`flop`/`skid`/`zerolatency`) so blocks meet timing at the boundary or chain without extra latency |
| Source annotation (generated RTL points at SV class lines) | 🟡 | XLS IR already carries SV `pos=` (zuspec-be-xls `printer.py`), and `--source_annotation_strategy` is wired. Verify end to end, then make `comment` the default |
| Readable state names in RTL (class property names, not `__state_N`) | 🔴 / verify | XLS issue #2042. We control IR state-element names, so name them after the SV properties |
| Multi-block network → one RTL top | 🟡 | `fw.hdl.spl.Integrate` (signatures → instances + `fw_rv_fifo`) works for all-XLS children. **Alternative to evaluate:** emit one IR package with spawned procs and let XLS `--multi_proc` codegen build the top (see §5.2) |
| Mixed XLS + hand-RTL blocks in one network | 🔴 | Out of scope in `xls-phase2.md` §6. With pin-identical shells, though, this is just ordinary RTL instantiation. The designer's own RTL is the integration fabric (§5.1) |
| Handoff package for Fusion Compiler: RTL, an SDC stub (clock at the scheduled period, I/O delays used by the scheduler), a filelist, signature, schedule report | 🔴 | XLS emits no constraints. We know everything needed to write them |
| Lint/CDC-clean output (house rules) | 🔴 / verify | Run the designer's lint (Spyglass/Verilator `-Wall`) in CI on generated RTL. Per-block XLS RTL is single-clock; CDC lives in the designer's RTL |

### Step 6: Iterate and close timing
| Item | Status | Where / notes |
|---|---|---|
| Re-target the clock period with an unedited test | ✅ | sha256 at 1000/2000/4000 ps |
| **Delay model for the designer's process node** | 🔴 | XLS ships asap7, sky130 and unit models only. "Validated QoR" means a schedule that holds up in *their* library. XLS has a characterization flow; wrap it as a one-time per-node task that drives their synthesis tool, or use XLS FDO (yosys/OpenSTA) where possible. **Without this, the schedule is a guess on commercial nodes** |
| Feedback from Fusion timing reports into the schedule (`--clock_margin_percent`, per-block overrides) | 🔴 | A manual loop at first |

## 3. Status summary

**Works today (✅):**
- SV classes and functions are lowered to XLS IR at QoR parity.
- XLS codegen is driven from a flow.
- One test runs at the model, RTL and gate levels.
- Deadlocks show up in the model.
- An all-XLS network can be assembled into an RTL top.

**Missing for the designer story (🔴), in order of leverage:**
1. **The generated module shell** (pin-identical to XLS output), and moving ready/valid
   transactors into `src/std`. Without it, the model can't be instantiated in RTL the way a
   designer expects.
2. **Accepting `logic`, an RTL-designer coding guide, and an early lowerability check.**
   These make up the on-ramp.
3. **ASIC codegen knobs:** async reset, data-path reset, I/O flop kinds, throughput/II and
   I/O constraints, plus an SDC/handoff package.
4. **The timed shell** (XLS latency + II on the pins). This is the pre-RTL performance
   story.
5. **Debug fidelity:** SV line annotations, property-named state, `$display`/`cover`
   mapping.
6. **SRAM support** via XLS RAM channels.
7. **A delay model for the target node.**

## 4. Proposed build order

| Phase | Deliverable | Demo it enables |
|---|---|---|
| **P0: "It's just a module"** | rv transactors moved to `src/std`; module-shell generator; pin-compatibility check; `logic` accepted | Replace one `always_ff` FSM block in an existing RTL design with a class behind a module shell. Simulate, swap in XLS RTL by fileset, rerun the same TB |
| **P1: "Ready for the back end"** | Reset/flop/II/io-constraint knobs; SDC + handoff bundle; SV-line annotations and named state verified; lint gate in CI | Generated RTL goes into a commercial synthesis run with no hand edits; a reviewer can map any RTL line back to SV |
| **P2: "Know your performance early"** | Timed shell from the XLS schedule (latency + II); per-block report; proc support in StageTLM | An architect runs a SoC-level sim with the timed shell, sees throughput and FIFO occupancy, and the numbers match RTL |
| **P3: "Designer ergonomics"** | Coding guide with FSM→class recipes; `fw-hdl check`; `$display`/`cover`/property mapping; `prove_quickcheck` on SV properties | A designer new to fw-hdl gets their first block through in a day |
| **P4: "Real blocks"** | SRAM via RAM channels; target-node delay-model characterization; multi-proc via XLS codegen | A memory-backed, multi-process block (e.g. GCM, a packet parser) on a commercial node |

## 5. Opportunities we're overlooking

### 5.1 The designer's RTL *is* the integration fabric
We've been building integration (`spl.Integrate`) and an automatic partitioner (XLS vs glue
vs transactor). For this audience a simpler model fits better:
- Each XLS-friendly class lives behind a module shell.
- The designer composes shells, FIFOs, CDC and hand RTL **in Verilog, as they always have**.
- Partitioning becomes the designer's choice of what to write as a class.

That removes the hardest open items:
- XLS↔native channels
- automatic classification
- transactor recognition

What's left is a small, reliable core: class → XLS → module. Keep `Integrate` for networks
that are all classes.

### 5.2 Let XLS build multi-proc tops
XLS's `--multi_proc` codegen instantiates procs and FIFOs (through an `xls_fifo_wrapper`
contract that we can satisfy with `fw_rv_fifo`). Emitting a network as one IR package with
spawned procs:
- puts more of the flow on XLS's validated path
- lets XLS optimize across procs
- gives one signature for the whole network

It's worth a spike against `rle_loop` to compare with `Integrate`.

### 5.3 Use XLS's own cycle-accurate model behind the shell
XLS AOT-compiles BLOCK wrappers (`cc_xls_ir_jit_wrapper`, with `Set<Port>` / `Get<Port>` /
`RunOneCycle()`). A thin generated DPI layer behind the same module shell would give a
**cycle-exact, XLS-produced fast model** for Track A, with no dependency on our own V4.
That's "leverage XLS" applied to verification. Behind the same shell it also becomes an
oracle for Track B's V4 class (§6). It is also something no XLS user has today:
nothing in google/xls or xlsynth targets DPI.

### 5.4 Track A cosynthesis: through XLS knobs, not RTL rewriting
On Track A, most of the AES cosynth transforms map onto XLS inputs, so XLS's optimizer, not
our rewrite pass, does the work. The transforms that need control over binding or sharing
(X4, X5) stay on Track B.

| Transform | XLS mechanism |
|---|---|
| X6 (tie unused key bits) and X2 (constant inputs) | Specialize the IR by substituting literals for contract-constant ports before `opt_main` |
| X1 (no input flops) | `--flop_inputs_kind` |
| X3 (no data resets) | `--reset_data_path=false` |

Contracts proved with SBY stay as they are; they become **justification for XLS
configuration**. That makes cosynthesis general instead of AES-shaped.

### 5.5 Formal for free, in SV
The designer writes `function bit prop_roundtrip(...)` in SV, and we lower it to IR and run
`prove_quickcheck_main` / `check_ir_equivalence_main`. Unit-level proofs with no SVA
expertise is a strong selling point for RTL designers, who rarely get formal on datapaths.

### 5.6 Incremental adoption inside a legacy block
A designer doesn't have to convert a whole block. Because the shell is just a module, they
can extract **one datapath function** (checksum, CRC, crypto round, FIR) as an SV function,
synthesize it with XLS, and instantiate it from hand RTL. That is the lowest-risk first use,
and the function flow already supports it (✅). Lead with it.

### 5.7 xlsynth as the distribution channel
xlsynth ships prebuilt `codegen_main`, `opt_main` and the equivalence and quickcheck
binaries, plus `dslx2sv-types`. Pinning to xlsynth releases gives designers XLS with no
Bazel build. Two caveats:
- xlsynth doesn't ship `eval_proc_main`. That matters for §5.3 and for the differential
  check, so we may need the C API / `libxls` instead.
- Watch XLS proc-scoped channels and codegen 2.0, which change the IR we emit.

## 6. Two tracks, one spine

### 6.1 The tracks

| | **Track A: commercial adoption** | **Track B: incremental lowering** |
|---|---|---|
| Stance on XLS | The engine. A recognized leader with validated QoR; we use it as is | A black box. It jumps from untimed procs to scheduled blocks to RTL in one step, and exposes only end artifacts (schedule, scheduled IR, block IR) |
| Goal | A Verilog designer gets XLS QoR without leaving their SV practice | Every refinement step (V0 → V1 → V2 → V3 → V4 → V5) produces an **executable SV model** with a checked link to the step before |
| Who it's for | Design teams shipping silicon now | Methodology, architecture exploration, research, and long-term independence from one engine |
| Synthesis | XLS `opt_main` / `codegen_main` | Native: `zuspec.synth.ArchSched` (V2/V3), `synth.xls.Lower` (V4/V5). XLS remains the oracle |
| Cycle-accurate model | XLS block JIT/AOT behind DPI (§5.3) | Generated V4 SV class |
| System-aware optimization | Contracts → XLS knobs and IR specialization (§5.4) | Contracts → transforms inside lowering, including what XLS can't express: resource sharing and folding (X4/X5), binding |
| Architecture exploration | XLS sweeps (stages, II, clock) | ArchSched specs (`ii`, `latency`, `fold`, `sbox_count`), which make binding choices XLS doesn't expose |
| What "done" means | Generated RTL in a Fusion Compiler run with no hand edits | Each view links to the next by a proof or a check; native QoR at parity with XLS |

### 6.2 What Track B offers that Track A can't

XLS's internal steps aren't visible to the user. In XLS they are:
- binding (which operation uses which resource)
- scheduling (which operation happens in which cycle)
- register allocation
- codegen

Only the final schedule and block can be inspected, and nothing between untimed procs and
RTL is an executable model you can put in an SV simulator. Track B makes each decision a
visible, separately checked refinement:
- **Models at every level, from the same flow.** An architect can stop at V2 (bound) or V3
  (scheduled) and simulate that view in the SoC. A verifier can link each view to the next
  instead of trusting one big jump.
- **Context-driven synthesis at the right level.** A contract can change binding or
  scheduling (sharing an S-box, folding rounds), not just tie off ports.
- **Explainability.** A designer can see why a block has N stages or M multipliers, because
  that decision is an artifact in its own right.
- **Engine independence.** XLS stays the QoR baseline and equivalence oracle, and native
  steps replace XLS steps one at a time, as `xls-native-roadmap.md` already plans.

### 6.3 The shared spine: build Track A so it doesn't close off Track B

| Shared piece | Rule |
|---|---|
| SV front end → zuspec IR | One front end. Track A lowers zuspec IR → XLS IR; Track B lowers zuspec IR natively. No XLS-only shortcuts in the front end |
| **Pin contract** (the signature) | The module shell (§2 step 2) is generated from a *signature*, not from XLS's Verilog. XLS codegen and native V5 both produce one. Lowered V5 already keeps `codegen_main`'s ports and latency, so this holds today |
| **Schedule abstraction** | The timed shell (Track A, P2) reads a schedule interface that the XLS schedule textproto **or** an ArchSched spec can fill. ArchSched already emits V3 with the same API |
| Module shell and transactors | One shell. The views behind it are interchangeable by fileset: V0/V1 class, V3 timed, XLS-JIT-DPI, V4 class, XLS RTL, native V5 |
| One test at every level | Unchanged. Track B adds levels; it doesn't add tests |
| Contracts (SBY-proved) | One record format. Each track has its own consumer: XLS knobs (A) or lowering transforms (B) |
| Equivalence | XLS IR equivalence, plus same-test-everywhere for both. Track B adds per-step link checks |

The two tracks also check each other:
- XLS RTL vs native V5 (QoR and equivalence)
- XLS block JIT vs the V4 class (cycle behavior)
- XLS schedule vs ArchSched (latency/II)

### 6.4 Track B's honest state and next steps

Today it covers V0, V3, V4 and V5 for AES A0 only. Gaps:
- There is no V1 or V2 tooling and no V4 parser.
- A1–A4 have no V4 or link checks.
- The V4↔V5 proof shares expression strings, so it checks registers and the stage split,
  not each op's lowering.
- Native QoR is already close: +4.6% LUT4 vs XLS on AES A0 (111073 vs 106170), a gap we
  expect to close. This is a credible start for an engine-independent path, not a blocker.
- Decrypt lowering ran out of memory.
- Cosynth is AES-specific.

Suggested next steps, chosen to also pay off on Track A:
1. **An II-aware V3**, which is the same work as Track A's timed shell.
2. **A schedule interface** shared by XLS and ArchSched.
3. **An independent V4↔V5 link** (per-op lowering, not shared strings), checked against
   the XLS block JIT.
4. **V2 binding** as an explicit artifact.
5. **X4/X5** on a design that has something to share (A1–A4).
6. **Close the ~5% QoR gap to XLS on A0.** Diff the native V5 against XLS RTL per stage to
   find where the extra LUTs come from.

### 6.5 Deprioritized on Track A only

These remain Track B work:
- native lowering
- the RTL-rewriting cosynth pass
- the automatic partitioner and transactor recognition, which sit behind the
  module-shell model (§5.1) for designers

## 7. Risks and open questions

1. **Simulator class support.** Classes and fork/join in Verilator are good but not
   universal. Confirm VCS/Xcelium/Questa run the fw-hdl runtime and transactors unmodified,
   and measure model-shell sim speed against RTL.
2. **The subset ceiling.** These are rejected today:
   - get/put in loops
   - two operations on one channel per activation
   - task calls
   
   Designers with an FSM background will hit them. Task calls (inline) and multi-op
   channels (unroll into states?) are the likeliest asks.
3. **XLS IR drift.** Proc-scoped channels and codegen 2.0 are in flight upstream. Pin to an
   xlsynth release and gate upgrades on the example corpus.
4. **Port-naming contract.** The shell and XLS must agree on names, widths, reset and flop
   policy. The pin-compatibility check (step 2) has to be part of the build, not a test.
5. **The trust boundary moved.** Designers will ask "how do I know the RTL matches my
   class?". The answer needs to be layered:
   - the model ↔ IR differential check
   - XLS IR ↔ RTL, which is XLS's job, plus our same-test-at-every-level runs
   - RTL ↔ gates, which is Fusion/LEC
   
   We should state it explicitly in the docs.

## 8. Parked: multiple entry languages

*Agreed direction (2026-11-01), deliberately out of scope for now.*

Design and verification should each fit the environments people already use:
- A designer who is most comfortable in Python writes the block with zuspec-dataclasses and
  tests it with pytest.
- A designer who is most comfortable in SV writes the block in SV.
- Both lower through the same IR to XLS.
- Verification works on an SV projection of the design, for early integration testing, with
  XLS timing back-annotated through the timing shell and with generated shells.

The current focus is narrower: **SV as a low-impact entry point for XLS.** The shell, timing
shell and signature pieces are being built in a way that would later serve a Python-authored
source as well.

## 9. Long-term framing: portfolio synthesis (forward-looking; focus stays on XLS)

*Recorded 2026-11-01. This is not part of the near-term plan.*

fw-hdl's value is what happens before RTL goes to synthesis: integration and automation
around the synthesis engine. Taken one level up, Zuspec is a **portfolio synthesis**
front end, in the way SMT solvers are portfolios:
- **Theory combination.** The design is split by description style, and each part goes to
  the engine that suits it. Parts exchange only their channel and pin contracts (signature
  / `shell.json`).
  - XLS: dataflow, pipelines, streaming procs
  - native FSM lowering: control-heavy glue
  - library or hand RTL: transactor cores
  - generators: CSRs, interconnect, memories
  - native V3→V5 lowering (Track B): a second datapath engine
- **Portfolio solving.** Where more than one engine accepts a block, build each and keep
  the best. This is safe because every engine's output must meet the same pin contract and
  pass the same tests and lockstep check.
- **The unifying layer is shared by all engines:** one source, one IR, one pin contract,
  one test at every level, one set of monitors, reports mapped back to source.
- **Seed:** the automatic-partitioner design in this work packet (try-map classification
  into XLS / glue / transactor, `--explain`, XLS fallback) is the dispatcher.
- **Costs:**
  - optimization stops at partition boundaries (cosynthesis contracts recover some)
  - QoR comparison needs a common back end
  - each engine needs its own trust story
  - automatic engine choice must be explainable
