# Design: centralize transparent lowering in zuspec-synth, emit `ir.core` for be-sv

**Status:** design for review.
**Goal:** make zuspec-synth the *shared, language-independent* lowering — one
transparent (no-magic) IR→IR path that any front end (fw-hdl SV,
zuspec-dataclasses Python, future) can drive, whose output is `zuspec.ir.core`
RTL that **be-sv netlists**. Today synth is text-locked (emits SV directly via
`sprtl/sv_codegen.py`, never uses be-sv) and its transparent lowering lives in
`fw.hdl.lower.spl2rtl`. This design moves the lowering up and changes the
emission boundary.

Grounded in the reuse audit (`REUSE-AUDIT.md`): the "magic" (scheduler, hazard,
forwarding, stall, auto-thread, pipeline) is **cleanly separable**; synth's
emission is **text-locked**; and `spl2rtl` already proves an `ir.core`-native
transparent lowering that be-sv netlists.

---

## 1. Target architecture

Three layers, mediated entirely by `zuspec.ir.core`:

```
 FRONT ENDS  (language → SPL ir.core)            per-language, NOT shared
   fw.hdl.fe          SV  → ir.core   (+ fw_root binding, transactor table)
   zuspec-dataclasses @zdc Python → ir.core   (DataModelFactory)
        │   SPL IR contract (§3)
        ▼
 LOWERING    (SPL ir.core → RTL ir.core)         CENTRALIZED in zuspec-synth
   transparent mode   beats→FSM, tick→counter, put→reg beat,
                      fork→threads, join→done-AND, select→arbiter   (no magic)
   scheduler mode     pipeline/hazard/forward/auto-thread           (opt-in, firewalled)
        │   RTL IR contract (§4)
        ▼
 BACK ENDS   (RTL ir.core → text)                shared
   be-sv (Verilog)   [+ be-sw, be-fv later]
```

**Dependency rule (important):** zuspec-synth lowers to `ir.core` and **does not
depend on be-sv**. The *driver* (fw-hdl's flow, or a zdc flow) hands synth's RTL
`Context` to be-sv. So synth = IR→IR; back end is the caller's choice. This keeps
synth back-end-agnostic and lets be-fv/be-sw reuse the same RTL IR.

---

## 2. The two asks, concretely

1. **Augment zuspec-synth** → add a transparent, `ir.core`-native lowering
   (`zuspec.synth.spl`, seeded by migrating `fw.hdl.lower.spl2rtl`), firewalled
   from the scheduler.
2. **Update zuspec-synth to emit `ir.core` that be-sv can netlist** → the
   lowering's *output* is an RTL `ir.core` `Context`; for synth's *existing*
   FSM-producing passes, add an **`FSMModule → ir.core` materializer** so they
   too become be-sv-netlistable. Deprecate `sprtl/sv_codegen.py` for the netlist
   path (it stays only for legacy/HLS flows not yet migrated).

---

## 3. The SPL IR contract (the multi-language enabler)

For one lowering to serve many front ends, they must produce the **same** SPL
`ir.core` shape. Today fw-hdl and zdc describe the same hardware differently;
converging them is the core integration task. The canonical SPL component:

- **Pins** — `FieldInOut(is_out=...)` for module ports.
  *Convergence:* fw-hdl tags clock/reset/data pins via `Field.pragmas`
  (`fw_role=clock|reset|pin`); zdc uses `@zdc.input()/output()` + the
  `@zdc.sync(clock=…, reset=…)` lambdas surfaced as `Function.metadata`. **Pick
  one canonical form** — recommend: clock/reset carried on the *process* as
  `Function.metadata['clock'|'reset'] = ExprRefField(self, idx)` (what be-sv
  already reads), and data-pin protocol roles as a documented pragma/Field-kind.
- **State** — `Field(is_reg=True)` (internal registers / hoisted process locals).
- **Behaviour** — one of:
  - `sync_processes` : already-clocked RTL processes (`@zdc.sync`) → lowering is
    near pass-through (be-sv already renders these).
  - `proc_processes` : async coroutines (fw-hdl `run`, `@zdc.proc`) — `forever`
    loops of **awaited beats** (`put`/`tick`/`get`/`fork`/`join`/`select`) → the
    beat→FSM lowering.
- **Protocol ports / bindings** — the abstract port + its binding to a pin and
  protocol. *Convergence:* fw-hdl uses `Field.pragmas`
  (`fw_protocol=put, fw_pin=led`); `ir.core` also has first-class
  `DataTypePutIF`/`DataTypeGetIF`/protocol-port machinery. **Decide** whether the
  contract standardizes on the pragma convention or the first-class protocol
  types (recommend the latter long-term; pragmas as the v1 bridge).

**Deliverable:** a written "SPL IR contract" doc + a tiny conformance validator,
so both front ends target an agreed shape and the lowering has one input spec.

---

## 4. The RTL IR contract (already proven)

The lowering's *output* — what be-sv netlists — is exactly what `spl2rtl`
produces today:

- `DataTypeComponent` with `FieldInOut` pins + `Field(is_reg)` registers +
  (later) sub-component instances for FIFOs/arbiters.
- `sync_processes : [Function]` whose body is the FSM as nested `StmtIf`
  (`if reset … else if state==i …`), with `metadata['clock'|'reset']`.
- `comb_processes` / `wire_processes` for combinational / continuous logic.

This is the materialization target for everything below. be-sv consumes it
unmodified (verified for blinky; Verilator-lint-clean; passes the real TB).

---

## 5. Pillar 1 — augment synth: the transparent lowering (`zuspec.synth.spl`)

Create a new, `ir.core`-native lowering module in zuspec-synth, **seeded by
moving `fw.hdl.lower.spl2rtl` there essentially verbatim** (it already does
SPL `ir.core` → RTL `ir.core`):

- `lower(spl_ctxt: ir.Context, cfg) -> ir.Context` — per component:
  - sync process → RTL sync process (pass-through / minor normalization).
  - proc process (coroutine) → beat parser → FSM (`state`/`count` regs;
    put→registered beat; `tick(N)`→down-counter w/ MSB terminal; comb between
    beats) → `sync_processes` nested-`StmtIf`.
- **Transparency contract enforced here:** 1 awaited beat = 1 state = 1 cycle;
  no state merging/reordering; no scheduler. A conformance test asserts the
  module never imports/touches `schedule`/`scheduler`/hazard/forwarding.
- **Capability growth happens here, once, for all languages:** control-dependent
  beats (`if cond await X else await Y`), loops with awaits, protocol-call beats.
  We use synth's existing `SPRTLTransformer` as the *algorithmic reference* for
  await-sequencing, re-implemented against `ir.core` to preserve transparency
  (the audit flagged `SPRTLTransformer` itself as opaque/contract-risk, so we
  don't adopt it wholesale — we adopt its *logic*).

This is the canonical no-magic lowering. fw-hdl and zdc both call it.

---

## 6. Pillar 2 — un-text-lock: `FSMModule → ir.core` materializer

To bring synth's *existing* (more capable, but text-locked) lowering into the
be-sv path without rewriting it, add a materializer:

- `materialize(fsm: FSMModule) -> ir.DataTypeComponent`:
  - `FSMPort`/`FSMRegister` → `FieldInOut`/`Field`.
  - `domain_binding` → `Function.metadata['clock'|'reset']`.
  - **single-state** (`fsm.single_state`): `body_stmts` are *already* `ir.core`
    stmts → trivial wrap (~150 LOC).
  - **multi-state**: emit the same nested-`StmtIf` FSM chain `spl2rtl` produces
    (states → `if state==i` branches; `FSMAssign`/`FSMCond` →
    `StmtAssign`/`StmtIf`; `FSMPortCall` → the protocol-beat lowering). `ir.core`
    has no native FSM node, but the nested-`StmtIf` encoding is exactly how we
    already represent FSMs for be-sv — so this is well-trodden.
- Net effect: **`FSMToRTLPass` (FSMModule→text) is replaced/supplemented by
  `FSMToIRPass` (FSMModule→ir.core)** for the netlist flow; be-sv emits.
  `sprtl/sv_codegen.py` becomes legacy.

**Why both Pillar 1 and Pillar 2?** Pillar 1 is the clean, transparent path for
the common case and the place capability grows. Pillar 2 is the *bridge* that
un-text-locks whatever already builds `FSMModule`s — notably the concurrency /
protocol lowering (spawn/select) we'll want next — so be-sv becomes the single
SV netlister immediately, before everything is rewritten. They converge over
time (as Pillar 1 gains capability, Pillar 2's role shrinks to legacy).

---

## 7. Concurrency (fork/join/select) — how it slots in

Out of scope to *build* here, but the architecture must accommodate it:
- Source constructs are already `ir.core` (`SpawnStmt`/`SelectStmt`/
  `CompletionSetStmt`/`CompletionAwaitExpr`/`QueueGet|PutExpr`) — both front ends
  emit them; the lowering consumes them.
- `spawn_lower`/`select_lower` (structural, audit-approved) become passes in the
  centralized lowering; their **text** FIFO/arbiter templates
  (`sprtl/protocol_sv.py`) are ported to `ir.core` sub-component builders so
  be-sv netlists them (single emitter).
- The **join barrier** (an AND of per-branch done flags) is new RTL we add
  (`completion_analysis` validates but emits nothing today).

---

## 8. What stays where (the boundary)

- **Front end (fw-hdl, language-specific):** SV parsing, and the **`fw_root`
  binding elaboration + std-transactor table** — these are SV idioms that produce
  the pins/pragmas. They do *not* move to synth.
- **Synth (shared, language-independent):** everything from "SPL `ir.core`
  component" onward — beat→FSM, tick→counter, fork→threads, materialization.
- **be-sv (shared):** RTL `ir.core` → Verilog. The only SV netlister.

---

## 9. Validation — "did centralization work?"

1. **No-regression:** existing zuspec-synth tests stay green; fw-hdl's golden +
   `blinky_tb` stay green after `fw.hdl.flow.synth` repoints to
   `zuspec.synth.spl` (same code, new home → byte-identical RTL).
2. **Multi-language proof (the litmus test):** an `@zdc` Python blinky and the
   fw-hdl SV blinky, lowered through the **same** `zuspec.synth.spl`, produce
   **byte-identical** `blinky.rtl.sv`. This proves language lives in the front
   end and hardware in the shared middle.
3. **No-magic conformance:** a test asserting the transparent path never invokes
   scheduler/hazard/forwarding/auto-thread.

---

## 10. Phased plan

- ✅ **C0 — mechanical migration (done).** `zuspec.synth.spl` created
  (`builders.py` from `ir_build`, `config.py` = `SplConfig`/`SplLowerError`,
  `lower.py` from `spl2rtl`, `ir.core`-only, no fw-hdl deps). fw-hdl repoints via
  thin shims (`fw.hdl.ir_build` re-exports `…spl.builders`; `fw.hdl.lower.spl2rtl`
  adapts `FlowConfig`/`ErrorReporter` → `SplConfig`/`SplLowerError`).
  `zuspec-synth` is now a real fw-hdl dependency. **Result: 60/60 unit tests
  green, golden byte-identical (no regen), `blinky_tb` PASS** through the migrated
  flow. The lowering is now centralized and shared-ready; be-sv netlists its
  `ir.core` output (lowering has no back-end dep).
- ✅ **C1 — SPL IR contract (done).** Written to `SPL-IR-CONTRACT.md`, grounded by
  probing what `@zdc`'s `DataModelFactory` actually emits. The lowering now
  accepts **both** conventions front-end-neutrally: clock/reset via
  `Function.metadata` (preferred) *or* `Field.pragmas` (fw-hdl); process from
  `proc_processes` *or* `sync_processes`; `tick`/`cycles` beats; `reset_value`
  *or* `initial_value`; data pins = `FieldInOut` minus clock/reset. fw-hdl output
  stays byte-identical.
- ✅ **C2 — multi-language proof (done).** A `@zdc` Python blinky, built by
  `DataModelFactory` and lowered through the **same** `zuspec.synth.spl`, emits
  Verilator-lint-clean RTL **using zero fw-hdl code** (`test_multilang_lowering`).
  fw-hdl + zdc both drive one lowering; 63/63 tests green. *Note:* the two RTLs
  are **not** byte-identical because the descriptions differ (fw-hdl's put-port
  adds a cycle/state the zdc direct-toggle doesn't) — language-independence is
  proven; byte-identity needs structurally-identical descriptions.
- **C3 — FSMModule→ir.core materializer (Pillar 2).** `FSMToIRPass`; be-sv emits
  synth's existing FSM output; deprecate `sv_codegen` for netlisting.
- ◐ **C4 — firewall + capability (in progress).**
  - ✅ **No-magic firewall** — `test_nomagic_firewall` AST-scans `zuspec.synth.spl`
    and asserts it imports no scheduling/pipeline modules and nothing outside
    `zuspec.ir.core`. Regression-locks the "no magic" guarantee.
  - ✅ **`cycles(1)`/`tick()` every-cycle semantics** — a 1-cycle beat is now a
    pure per-cycle boundary (the @zdc.sync "run every cycle" idiom), not a
    counter wait; `needs_counter` only when a tick has N>1. `test_every_cycle`
    proves a `@zdc` `cycles(1)` ticker emits a free-running counter (no spurious
    down-counter); blinky (`cycles(100)`) stays byte-identical. **67/67 green.**
  - ☐ control-dependent beats (`if cond: await X else await Y`), loops with
    awaits — the real FSM frontier, using `SPRTLTransformer` as reference.
- **C5 — concurrency.** fork/join/select lowering + FIFO/arbiter as `ir.core`
  sub-components + join barrier (§7).

---

## 11. Open decisions (for review)

1. **Module name/home in synth** for the transparent lowering — `zuspec.synth.spl`
   vs extending `sprtl` (the existing `sprtl` is text-locked; a clean new name
   avoids confusion). *Recommend `zuspec.synth.spl`.*
2. **Rewrite vs materialize as the primary path.** Pillar 1 (transparent rewrite,
   our `spl2rtl`) vs Pillar 2 (materialize synth's existing capable-but-opaque
   FSMModule). *Recommend Pillar 1 primary (transparency), Pillar 2 as the bridge
   for concurrency/legacy — converge over time.*
3. **SPL contract: pragmas vs first-class protocol types** for ports/bindings.
   *Recommend pragmas as the v1 bridge, migrate to `DataTypePutIF`/protocol-port.*
4. **Clock/reset canonical carrier** — `Function.metadata` refs (be-sv reads
   these) vs `Field.pragmas`. *Recommend `Function.metadata` for RTL processes.*
5. **Dependency direction** — confirm synth must NOT depend on be-sv (driver
   chooses back end). *Recommend yes; keeps synth back-end-agnostic.*
6. **Backward compatibility** — keep `sprtl/sv_codegen.py` + the FSMModule→text
   path for existing HLS/pipeline users; only the *netlist* flow moves to
   ir.core+be-sv. *Recommend yes (no breakage).*
