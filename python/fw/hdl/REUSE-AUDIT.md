# zuspec-synth reuse audit — what to harvest vs. exclude

**Question:** how much of zuspec-synth can fw-hdl reuse, under the principle
*"very little magic — an engineer can imagine how the description lowers to RTL"*?

**Litmus test per pass:** does it **translate** an explicit construct the engineer
wrote (reuse), or **infer** hardware they didn't write (exclude)? And does it
preserve **1 beat = 1 state = 1 cycle** predictability?

Two findings dominate and they pull in opposite directions:

1. **Separability — GOOD.** The "magic" (scheduler, hazard/forwarding, auto-thread,
   pipelining) is **cleanly isolated**. The sequential-FSM path and the
   concurrency/protocol path **never call the scheduler**; it lives only in the
   `_synthesize_pipeline` chain. `ProcessToFSM` even runs `FSMOptimizer` with
   `minimize_states=False, merge_operations=False`. So we can take the structural
   half without inheriting the HLS half.

2. **Materialization — the CATCH.** zuspec-synth is **text-locked**: every pass
   produces synth's own `FSMModule` IR → **text** via `sprtl/sv_codegen.py`. It
   **never uses be-sv** and there is no `zuspec.ir.core` step. So "reuse a synth
   pass" means leaving our single-IR (`ir.core`) / single-emitter (be-sv)
   architecture — unless we add an adapter. And its multi-state FSM construction
   (`SPRTLTransformer`) is **opaque** (state-per-await, black-box) — *less*
   transparent than the `ir.core` `sync_processes` our `spl2rtl` already emits.

---

## Tagged inventory

### Concurrency / protocol — the part worth harvesting (structural, separable)
| pass | verdict | driven by | emits |
|---|---|---|---|
| `spawn_lower` | **reuse (pattern)** | explicit `SpawnStmt` | `SpawnIR` → text |
| `select_lower` | **reuse (pattern)** | explicit `SelectStmt` | `SelectIR` → arbiter text |
| `completion_analysis` | **reuse (pattern)** | explicit `Completion.set/await` | metadata only — **no RTL codegen yet** |
| `if_protocol_lower` | **reuse (pattern)** | explicit `IfProtocol` typed port | `IfProtocolPortIR` → text |
| `protocol_sv_emit` / `sprtl/protocol_sv.py` | **reuse (templates)** | — | FIFO + priority/RR arbiter SV (proven RTL) |
| `protocol_compat` | reuse (optional) | explicit protocol props | validation only |

*All zero-entanglement with the scheduler. Emit text, not `ir.core`.*

### Sequential FSM core — text-locked, and our `spl2rtl` is more transparent
| pass | verdict | note |
|---|---|---|
| `component_fields` | structural | field classification; we already do this |
| `process_to_fsm` (`SPRTLTransformer`) | **contract-risk** | opaque state-per-await; text-locked |
| `fsm_to_rtl` / `sv_codegen` | structural | `FSMModule` → **text** (not `ir.core`) |
| `comb_lower`, `module_assemble` | structural | text assembly |
| single-state `FSMModule.body_stmts` | note | these *are* `ir.core` stmts already (easy materialize) |

### Scheduling / pipeline / HLS — exclude (inferential "magic")
| pass | why excluded |
|---|---|
| `schedule`, `sdc_schedule`, `sprtl/scheduler.py` | ASAP/ALAP/list/SDC op scheduling |
| `hazard_analysis` | infers RAW/WAW/WAR across stages |
| `forwarding_gen` | infers bypass muxes |
| `stall_gen` | infers stall/bubble/valid-chain logic |
| `auto_thread` | **inserts pipeline registers the engineer didn't write** |
| `pipeline_frontend`, `pipeline_annotation`, `async_pipeline_*`, `pipeline_sv_emit` | pipeline inference/codegen |

---

> **Verdict superseded.** The decision below ("keep lowering in fw-hdl") was the
> conservative read. Per the centralization direction, it's inverted in
> `CENTRALIZED-LOWERING-DESIGN.md`: **move the transparent lowering UP into
> zuspec-synth** so multiple front ends share it, and make synth emit `ir.core`
> that be-sv netlists. The **inventory and the two findings (separability ✓,
> text-lock ✗) below remain valid** — they're the work-list for that design.

## Verdict — "harvest the design, not the pass pipeline" (superseded — see above)

The instinct "leverage more of zuspec-synth" is right about *where the value is*,
but the evidence says the value is in **IR primitives + proven RTL templates +
algorithms as reference**, NOT in grafting its pass pipeline — because the
pipeline is text-locked and bypasses our transparent `ir.core`/be-sv spine.

1. **Sequential FSM core → keep `fw.hdl.lower.spl2rtl`.** It already emits
   transparent `ir.core` `sync_processes` (the `if state==N` chain) that an
   engineer can read, and be-sv renders it. synth's equivalent is text-locked and
   its state creation is opaque (contract-risk). We do **not** adopt it. When we
   grow `spl2rtl` to handle control-dependent beats and protocol awaits (the next
   correctness frontier), we use `SPRTLTransformer` as an **algorithmic
   reference**, re-implemented against `ir.core` to keep transparency.

2. **Concurrency (fork/join/select) → harvest, re-home into `ir.core`.**
   - **Reuse the IR primitives directly:** `zuspec.ir.core.SpawnStmt`,
     `SelectStmt`, `CompletionSetStmt`, `CompletionAwaitExpr`, `QueueGet/PutExpr`
     are the explicit source constructs — adopt them as fw-hdl's fork/join/select
     representation (they're in `ir.core`, not synth — no text-lock).
   - **Reuse `spawn_lower`/`select_lower` as the lowering algorithm** (the DFS
     scan → structural node), re-targeted to build `ir.core` RTL.
   - **Reuse `protocol_sv.py`'s FIFO + arbiter as proven RTL templates** —
     replicate them as `ir.core` so be-sv emits them (keeps one emitter).
   - **Build the join-barrier RTL ourselves:** `completion_analysis` validates but
     emits no hardware; the join = an AND of per-branch done flags is ours to add.

3. **Scheduling / pipeline / auto-thread → exclude entirely.** Confirmed
   inferential and confirmed separable — we simply never run those passes.

### Architecture decision: single IR, one emitter
Keep **`ir.core` as the only IR and be-sv as the only emitter** end-to-end. This
is what makes "no magic" *enforceable and legible* — an engineer can dump SPL IR →
RTL IR and trace every construct, with one emitter. Adopting synth's text path for
concurrency would split us into two IRs (`ir.core` + `FSMModule`) and two emitters
(be-sv + `sv_codegen`), re-introducing the opacity we're trying to avoid. The cost
of "harvest, don't graft" is re-implementing the concurrency lowering — but guided
by proven synth code and reusing its IR primitives and SV templates, so it's
transcription, not invention.

### Net
- **Reuse as code:** `zuspec.ir.core` concurrency IR (SpawnStmt/SelectStmt/
  Completion*), be-sv (already), the `SynthPass` framework shape if convenient.
- **Reuse as reference/templates:** `spawn_lower`/`select_lower` algorithms,
  `protocol_sv.py` FIFO/arbiter RTL, `SPRTLTransformer` await-sequencing logic.
- **Keep ours:** `spl2rtl` (transparent, `ir.core`-native), the SV→IR front end.
- **Exclude:** the entire scheduling/pipeline/auto-thread half.

The principle wins the tie-breaks: where synth is more *capable* but less
*transparent* (its sequential FSM path), transparency + single-IR wins, and we
grow our own lowering using synth as the reference.
