# Lean and fw-hdl: positioning and relationship

Status: research and recommendation (2026-11-25). No code yet.

## User benefit

- **Lean users:** keep writing specs and proofs in Lean, but don't hand-code a
  second RTL model and glue it to Lean. fw-hdl supplies the implementation and
  the proof that links the two.
- **fw-hdl users who never write Lean:** contracts and refinement checks are
  stated in fw-hdl. When an automatic engine can't discharge an obligation, it
  can be passed to Lean (by a person or an AI prover) without rewriting
  anything.
- **The project:** answers "why not just use Lean?" by placing Lean as the
  layer above fw-hdl, not a rival HDL.

## 0. Status

| Step | State |
|------|-------|
| Landscape survey (Lean for hardware, 2024–2026) | done (§1) |
| Map fw-hdl's method-level and formal layer | done (§2) |
| Positioning and relationship options | done (§3–§5) |
| Probes L1–L5 (§6) | not started |
| Spec layer above fw-hdl, Python surface vs Lean surface, per-language subsets (§8) | done (recommendation) |
| Probes S1–S4 (§8.7), S5 end-to-end thread (§8.8), S6 projection (§8.10) | not started |

---

## 1. What Lean is actually used for in hardware (as of late 2026)

Lean's hardware value comes from four things, all solid and none of them an HDL.

| What | Examples | Maturity |
|------|----------|----------|
| **Bit-vector automation that produces checked proofs** | `bv_decide` (LeanSAT, in Lean core since 4.12): bit-blast with a verified bit-blaster, solve with CaDiCaL, check the LRAT proof with a verified checker | production |
| **ISA and algorithm golden models** | LNSym (AArch64, AWS crypto proofs); Sail→Lean RISC-V (`opencompl/sail-riscv-lean`), used by zkVM verification | production / maturing |
| **Transition-system verification frameworks** | Veil and Loom (POPL'26): model checking, SMT and interactive proof over one shared semantics | research, protocol-level |
| **AI provers** | Harmonic Aristotle (compiles C, Verilog and Rust into Lean theorems; vendor claims bugs found >100k cycles deep on 20–30M-gate designs); CircuitProver; Rtl2lean | fast-moving, mostly vendor and academic claims |

Lean-native HDLs exist but are early-stage:

- **Sparkle (Verilean):** a Clash-style HDL embedded in Lean that emits SV. It
  claims an RV32IMA SoC that boots Linux.
- **CktLean:** extends Sparkle with memories, multiple clocks and signed
  arithmetic.

Both are rebuilding, one feature at a time, things fw-hdl already has: clocks,
memories, protocols and DV.

**Every Lean-to-RTL flow keeps a trusted gap.** Each one relies on an
unverified translation or emission step:

- **Lean → Verilog** (Sparkle, CktLean): proofs cover the Lean source only. The
  CktLean paper says so directly: "Proofs of CktLean circuits do not
  automatically guarantee the behavior of generated RTL". The emitted SV is
  then checked by Yosys equivalence or simulation.
- **RTL → Lean** (Rtl2lean, Harmonic): an unverified front end produces a step
  function, and proofs are about that function.
- **Lean spec ↔ hand-written RTL** (the common case, and what the brief
  describes): two representations joined by DPI co-simulation or ad-hoc
  translation.

**Lean has no built-in notion of time, concurrency or protocol.** Each project
re-encodes cycles as streams or step functions. Each also has to rediscover
the hard part of a hardware proof: the abstraction function, i.e. which
implementation state corresponds to which architectural state, and in which
cycle a transaction commits.

Full sources are kept in the research brief; key links:
- Sparkle: https://github.com/Verilean/sparkle
- CktLean: https://arxiv.org/abs/2605.07782
- Rtl2lean: https://arxiv.org/html/2607.16855
- `bv_decide` (OOPSLA'25): https://doi.org/10.1145/3763167
- LNSym: https://github.com/leanprover/LNSym
- Sail→Lean RISC-V: https://github.com/opencompl/sail-riscv-lean
- Loom: https://verse-lab.org/papers/loom-popl26.pdf
- VeIR (verified CIRCT `comb` rewrites): https://github.com/opencompl/veir
- Harmonic: https://www.eetimes.com/ai-makes-formal-verification-practical/
- Kami / Koika (Coq analogues): http://plv.csail.mit.edu/kami/papers/icfp17.pdf

## 2. What fw-hdl already has that Lean lacks, and the reverse

**fw-hdl has, and Lean projects keep re-inventing:**

- **One description across abstraction rungs:**
  - R3 untimed process network, R2 timed process, R1 sync `step`/`comb`, then SV
    (`docs/design/process-synthesis.md:178`).
  - Methods are untimed and ordered only by data, control and per-port program
    order (`docs/methodology/timing.md`).
- **Protocols as first-class objects** (`packages/fw-hdl-spec/semantics/protocols.md`):
  - a method-level API and a pin-level bundle;
  - transactors that convert between them without adding cycles;
  - any loss of detail must be declared.
- **A named ladder of refinement relations**
  (`docs/design/automated-lifting.md:239`):
  - E0 cycle-exact, E1 latency-tolerant in order, E2 per-interface order, E3
    protocol reordering, E4 effect-level;
  - each connection carries the relation its protocol declares.
- **Guarded atomic steps at sync level:** `fw_atomic_step` / `put_or_stall`
  (`docs/methodology/components.md:146`). This is the Bluespec/Kami rule
  semantics.
- **A working DV flow, SV interop, and synthesis through several engines.**

**Lean has, and fw-hdl does not (and should not rebuild):**

- a small trusted kernel and machine-checked proofs;
- dependent types;
- mathlib;
- tactics, `bv_decide`, and the AI-prover ecosystem;
- existing golden models: Sail RISC-V, AArch64.

**fw-hdl's gap today** (`docs/design/verification-support-review.md:395-460`):

- There is no method-level property or contract language. F1–F7 and the
  temporal property layer are only planned.
- The E0–E4 relations are checked by simulation. A formal method→RTL
  refinement proof doesn't exist yet.
- What exists is narrow: formal SVUnit (`python/fw/hdl/formal/`, SMT-LIB QF_BV),
  XLS codegen equivalence, SBY proofs of hand-written ready/valid RTL, and
  netlist-level k-induction miters in zuspec-synth.

## 3. The positioning

> **Lean says what a computation means. fw-hdl says how hardware carries out
> that meaning over time, and produces the evidence that it does.**

This puts Lean and fw-hdl at different layers:

```
   Lean        mathematical spec, ISA / algorithm model, theorems
     │  ← refinement obligation (pure function, BitVec)
   fw-hdl R3   untimed methods/processes   (method contracts)
     │  ← E-relation obligations (E4 → E1)
   fw-hdl R2/R1 timed / cycle-level        (protocols, atomic steps)
     │  ← lowering (by construction + translation validation)
   SV / RTL    generated, plain SV
```

The argument to make to a Lean-oriented team:

1. **One fewer hand-written representation.** Today: a Lean model, plus
   hand-written RTL, plus glue. With fw-hdl: a Lean spec, plus an fw-hdl
   design, and the RTL is generated.
   - The second representation is not redundant. It adds the information the
     spec deliberately leaves out: timing, pipelining, protocols and resource
     sharing.
2. **fw-hdl knows the abstraction function.** This is the strongest technical
   argument.
   - fw-hdl builds the RTL by lowering from the method level, so it knows the
     refinement map: which registers hold which architectural state, and when
     each transaction commits.
   - RTL→Lean flows (Rtl2lean, Harmonic) must rediscover that map, and it is
     the hardest part of a hardware proof.
   - fw-hdl can emit the map, plus the invariants it relies on, as Lean
     lemmas. The remaining proof is mostly mechanical, the kind that
     `bv_decide` or an AI prover handles well.
3. **The trusted gap is smaller.** Lean-HDLs trust their emitter, and RTL→Lean
   flows trust their parser. fw-hdl can translation-validate each lowering
   step in Zuspec IR, and its last step is a short, regular IR→SV print, not a
   parse of arbitrary SV.
4. **Time and protocols are native, not encoded.** Lean HDLs are adding clocks,
   memories and multiple clock domains one paper at a time, and they still
   have no transactors and no DV.

**What we should not claim:** that fw-hdl replaces Lean as a proof language.
It doesn't, and it shouldn't try to. The goal is *Lean-compatible*, not
*Lean-equivalent*.

## 4. Relationship options, ranked

### A. Lean as an engine backend for Zuspec IR proof obligations (recommended first step)

Zuspec IR already has the pieces (`StmtAssert`/`StmtAssume`/`StmtCover`,
`SVAEmittableInterface`). The planned F-series turns method contracts and
E-relations into proof obligations.

- **Lean is one engine among peers:** SBY, XLS proving and `dv-solve` are the
  others. This follows the same rule as XLS: Zuspec IR stays the source of
  truth, and only the Lean adapter emits Lean.
- **Easy obligations** (pure bit-vector, bounded) go to SMT/SBY.
- **Hard obligations** (unbounded, parameterized, induction) are exported as
  Lean theorems. They come with the refinement map and helper lemmas, ready
  for a person, `bv_decide` or an AI prover.
- **Evidence:** a Lean proof, or an LRAT certificate replayed with `bv_check`,
  gives a checkable artifact for the obligation. No other engine here produces
  one.

### B. A Lean semantics for the Zuspec core ("Zuspec-in-Lean")

Write a small Lean library that defines:

- **Values:** BitVec values and structs.
- **R1 sync step:** a step function.
- **Atomic commit:** `fw_atomic_step` guarded commit as a rule that either
  commits or stalls.
- **R3 methods:** an interaction-tree or free-monad program over port events,
  which matches "ordered only by per-port program order".
- **E0–E4:** trace relations.

What it enables:

- **Exported theorems become meaningful.** A theorem exported by option A has a
  defined meaning, instead of depending on a one-off encoding.
- **Lowering passes can be proven or translation-validated in Lean**, the way
  VeIR does for CIRCT `comb`.
- **The E-ladder becomes formal mathematics.** That is useful in its own right,
  and it can be published.

This is where "capture much the same thing that Lean does" actually happens.
fw-hdl gets a formal semantics. Users don't have to write Lean to benefit,
because the semantics sits under the tooling.

### C. Import Lean functions into fw-hdl (the strongest "one representation" story)

- **What a Lean user writes:** a datapath function in Lean (a `BitVec → BitVec`
  definition, e.g. an ALU or decoder from Sail-RISC-V-Lean, a CRC, an AES
  round), plus proofs of its properties.
- **What fw-hdl does with it:**
  - imports a restricted executable subset (first-order, BitVec,
    structural recursion with fixed bounds) as a Zuspec IR function;
  - uses that function as the body of an R3 method;
  - adds the pipelining, protocol and resource sharing;
  - generates the RTL.
- **What links the two:**
  - the Lean function and the imported IR function must be equal, discharged
    by translation validation in Lean;
  - the IR function and the generated pipelined RTL must be equivalent up to
    latency, which fw-hdl already checks with `codegen_equiv`-style proofs.
- **Mechanism:** a Lean metaprogram dumps the elaborated definition as an
  IR-like JSON. Lean's metaprogramming is good at this.

Result: the Lean user never writes RTL. That answers "integration effort
doesn't scale" directly.

### D. Lean executable models as DV reference models

Use Lean models (compiled to C, or interpreted) as fw-hdl predictors and
scoreboards at the method level. This is mostly the "DPI integration" the
brief wants to go beyond.

- It's cheap and useful as an on-ramp, since Lean's executable specs are fast.
- It is not the main story.
- Method-level APIs make it cleaner than RTL-level DPI: a predictor consumes
  transactions, not pins.

### E. Lean-HDL (Sparkle) designs as fw-hdl components

Import Sparkle IR, or its emitted SV, as a lifted component. Low priority.
Revisit if Sparkle gains users.

## 5. Guard rails

- **Zuspec must not become Lean-centric** (the same rule as for XLS). Python
  and SV front ends build Zuspec IR, and only a Lean adapter emits or reads
  Lean. Nothing outside that adapter may emit Lean or Lean-shaped constructs.
- **Native contracts first.** Most hardware engineers won't write Lean. Method
  contracts, invariants and the E-relations must be stated in fw-hdl
  (F1–F7 and the temporal property layer). Lean is where hard obligations go,
  not where users must start.
- **Keep the Lean surface small and pinned.** Lean and mathlib change between
  versions; depend on core `BitVec` and `Std.Tactic.BVDecide` only, not
  mathlib, for the generated code.
- **No proof-burden surprises.** Every exported obligation should first be
  tried by an automatic engine (SBY, `bv_decide`). Only what remains open
  reaches a person.

## 6. Proposed probes

Each probe is small and stands alone, in the style of `docs/design/probes/`.

| ID | Probe | Shows |
|----|-------|-------|
| L1 | Zuspec-in-Lean core (BitVec, sync step, guarded atomic step), ~300 lines of Lean | option B is tractable; fixes the semantic target |
| L2 | Export one existing comb/sync IR function (e.g. the `rr_merge` arbiter grant function) to Lean; prove it against a hand-written Lean spec with `bv_decide` | option A end to end; compare with SBY on the same obligation |
| L3 | Import a Lean `BitVec` function (CRC-32 or a Sail RV32I ALU) to Zuspec IR → pipelined fw-hdl method → Verilator, plus a latency-shifted equivalence proof | option C; the demo for Lean users |
| L4 | E1 refinement of a 2-stage pipeline against its R3 method, as a Lean theorem using a Burch–Dill flush with the refinement map supplied by fw-hdl | the "fw-hdl knows the abstraction function" claim |
| L5 | Feed L4's exported theorem and lemmas to an AI prover (Aristotle or an open one) and compare with the same task starting from raw RTL | evidence for the pitch: proofs are easier from fw-hdl than from RTL |

Order: L1 → L2 → L3 (the demo), then L4/L5 (the differentiating claim).
L2 and L3 can reuse `python/fw/hdl/formal/` only as reference, since that
emits XLS IR and SMT. A new Lean adapter belongs beside the other engines,
reading Zuspec IR.

## 7. Open questions

- **Which Lean community to approach first:**
  - ISA (Sail/LNSym users) favors option C with an ISA model;
  - AI-prover vendors (Harmonic) favor A plus L5, offering fw-hdl as a richer
    input than raw Verilog;
  - PL researchers (Veil/Loom, opencompl) favor option B.
- **Proof status in reports:** whether a Lean-discharged obligation counts as
  "proven" alongside SBY results in the verification dashboard, and what
  certificate is kept.
- **Ownership:** whether the Lean semantics library lives in the Zuspec org (as
  the IR's formal semantics) or with fw-hdl. Option B suggests Zuspec.

---

## 8. A spec layer above fw-hdl: Python surface, Lean semantics

The direction (2026-11-25): model and prove high-level relationships in a
layer above fw-hdl, with Lean semantics, then lower that layer to fw-hdl,
perhaps as a Zuspec task. The question here is whether that layer can be
written in Python, using the parse approach Zuspec already uses for
constraints, and whether a dedicated language would make it more accessible.

### 8.1 Short answer: the flow is the accessibility

The Python path:

```
 spec DSL (Python, Lean semantics)        ── what: ops, invariants, theorems
   │  lower: automatic where deterministic/executable, by hand elsewhere
   │         every step keeps a refinement link + generated obligations
 executable semantics (Python / Zuspec)   ── how and when: fw-hdl R3 → R2 → R1
   │  translate (by construction)
 SV handoff                               ── plain SV
```

Accessibility here means **a connected flow, not a standalone language**.

- **Lean's problem is that it stands alone.** A team using it ends up with:
  - a model in a separate language and build;
  - hand-written RTL;
  - glue between the two that doesn't scale;
  - proofs that silently fall out of date when the RTL changes.

  That cost comes from the seam between Lean and the rest of the flow, not
  from Lean's syntax.
- **The DSL wins by having no seam.** The point is not that Python is easier
  than Lean (§8.8).
- **Lean still has a defined place:**
  - it defines what the DSL means (option B, §4);
  - it finishes the hard proofs;
  - it is a second way in for people who already use Lean.

  Lean users join the same flow through the same IR. They don't get a parallel
  one.
- **No new standalone language.** It would bring back exactly the seam this
  removes. The auto-active proof style (§8.3) still matters, because a
  connected flow that needs tactic proofs at every step isn't usable either.

### 8.2 How much of the Lean-style layer Python can express

Precedent in our own code: `constraint_parser.py` already parses `@constraint`
bodies. It also parses `with zdc.requires:` / `with zdc.ensures:` blocks on
async methods (`extract_method_contracts`, `constraint_parser.py:455`), which
are checked at run time by `zuspec-be-py/.../rt/contract_checker.py`. So
Python-syntax, Zuspec-semantics method contracts already exist. Precedents
outside the project include Nagini (Python → Viper), CrossHair (symbolic
execution of Python contracts), and in other languages Dafny and Verus.

| Lean feature a hardware spec needs | In parsed Python | Notes |
|---|---|---|
| Pure total functions over BitVec / Nat / Int | `@zdc.fn` def; types say BitVec vs unbounded int | Recursion needs `zdc.decreases(...)` or a fixed bound |
| Structures and enums | dataclasses, `IntEnum` (already Zuspec types) | |
| Inductive sum types | `Union` of dataclasses + `match` | Covers ASTs and instruction formats |
| Ghost math collections | `zdc.Seq`, `zdc.Map`, `zdc.Set` (spec-only, never lowered) | New; this is the main gap |
| Quantifiers | `all(... for i in range(n))`, `any(...)`, `zdc.forall(lambda x: ...)` | Bounded ones lower to SMT; unbounded ones go to Lean |
| Nondeterminism | `zdc.choose(...)` | Needed for abstract specs (§8.4) |
| State machines and operations | `@zdc.spec` class with `@zdc.op` methods, plus requires/ensures | Extends the existing contracts |
| Invariants | `@zdc.invariant` | Proved by induction over ops |
| Theorem statements | `@zdc.theorem` def whose body is `assert`s | |
| Refinement between layers | `@zdc.refines(Spec, rel=E2)` + `def abs(self) -> Spec` | E0–E4 from `automated-lifting.md` |
| Proof hints | `@zdc.lemma`, intermediate `assert`, `zdc.induct(on=...)` | Auto-active style |
| Tactic proofs | **no** | Export to Lean and finish there (§8.5) |
| Dependent types, typeclasses, mathlib | **no** | Can refer to a Lean definition as an opaque spec function, e.g. `zdc.lean_ref("...")` |

The rule that makes this safe is the one constraints already follow: **Python
syntax, Zuspec semantics.** `+` on a `BitVec[8]` wraps; on an unbounded
`int` it does not; aliasing and mutation inside `@zdc.fn` are rejected. Each
construct either has a defined meaning in Lean or is rejected with a clear
message. Python code that parses but means something else is the main risk of
this approach, so diagnostics matter more than coverage.

### 8.3 Why auto-active, not interactive

Interactive proof (Lean tactics) is what puts most hardware engineers off. For
hardware specs, most obligations are:

- bounded bit-vector facts, which go to SMT or `bv_decide`;
- inductive invariants over a small state, which go to k-induction;
- refinement steps whose abstraction map fw-hdl already knows.

Dafny and Verus show that specs, invariants and occasional lemma calls in the
host language are enough for most proofs in practice. The Python surface
should aim for that. When the solvers fail, the obligation is exported to
Lean with its context (§8.5); it is not a dead end.

### 8.4 Example: the `rr_merge` relationship, top layer only

```python
@zdc.spec
class Merge(zdc.Spec):
    N: int = zdc.param()
    q:   zdc.Seq[zdc.Seq[Pkt]]      # ghost: pending per input
    out: zdc.Seq[tuple[int, Pkt]]   # ghost: everything emitted

    @zdc.op
    def push(self, i: int, p: Pkt):
        with zdc.requires:
            0 <= i < self.N
        self.q[i] = self.q[i].append(p)

    @zdc.op
    def pop(self) -> tuple[int, Pkt]:
        with zdc.requires:
            any(len(self.q[i]) > 0 for i in range(self.N))
        i = zdc.choose(i for i in range(self.N) if len(self.q[i]) > 0)
        p, self.q[i] = self.q[i].head(), self.q[i].tail()
        self.out = self.out.append((i, p))
        return (i, p)

@zdc.theorem
def per_input_order(s: Merge, i: int):
    # what was emitted from input i, followed by what is pending on it,
    # is exactly the sequence pushed on input i
    assert [p for (j, p) in s.out if j == i] + s.q[i] == s.pushed(i)
```

Below it, a policy layer resolves `choose` as round-robin and states fairness
(for example, no input waits more than `N` grants), and the
existing fw-hdl component declares
`@zdc.refines(MergeRR, rel=E2)` with an `abs()` that maps its FIFOs to `q`.

This one spec is useful in three ways:

- **Run in Python simulation**, it is the reference model and scoreboard.
- **Given to the solvers**, it produces the per-input-order and fairness
  proofs.
- **Lowered**, it generates the fw-hdl API (`push`/`pop` become a protocol-kit
  API class), which follows the minimal-user-specification rule.

### 8.5 Lowering: what a "spec → fw-hdl" Zuspec task can and can't do

| Spec content | Lowering | Obligation |
|---|---|---|
| `@zdc.op` signatures | generate the fw-hdl API / protocol-kit API class | none |
| Deterministic, executable `@zdc.fn` | becomes the body of an R3 method, then the existing ladder down to RTL (option C) | equivalence, by construction or translation validation |
| Executable spec as a whole | reference model / predictor / scoreboard for DV | none (simulation check) |
| `choose`, ghost `Seq`/`Map`, unbounded state | **not lowered automatically.** The user supplies the concrete design, and the task generates the `refines` harness: a monitor in simulation plus formal obligations | refinement under the declared E-relation |
| Theorems, invariants | not lowered; sent to engines | SMT/SBY first, Lean export for what remains |

This is a refinement method in the style of Event-B: abstract to concrete in
stages, with a proof obligation at each step. The task's job is to
**generate** the obligations and harnesses, not to invent the design. Only
deterministic, executable pieces are lowered automatically.

Engine routing for obligations, in order:

1. run-time checks (exist today, via `contract_checker`);
2. bounded SMT, reusing the QF_BV path in `python/fw/hdl/formal/smt.py` as a
   reference;
3. SBY k-induction on the lowered design;
4. Lean export.

Each is a peer behind the engine interface, so Zuspec doesn't become centered
on Lean or on any one solver.

### 8.6 Python surface vs Lean surface: who each serves

| | Python surface | Lean surface |
|---|---|---|
| Audience | hardware and DV engineers; fw-hdl users | formal and PL engineers; Lean shops (ISA, crypto, zk) |
| Writes | specs, invariants, refinement maps, hints | the same, plus tactic proofs and links to mathlib or ISA models |
| Same file as the design | yes | no (a sibling Lean package) |
| Executable as a reference model | immediately, in Python simulation | through Lean's compiler, or by importing into the spec IR |
| Trust | the proof is checked by the solvers, or by Lean after export | Lean's kernel |
| Produces | Zuspec spec IR | Zuspec spec IR (via a Lean metaprogram), and/or proofs of exported obligations |

A dedicated new language would add a third surface that serves neither group
better, and its separate toolchain would bring back the seam (§8.8).

### 8.7 Probes

| ID | Probe | Shows |
|----|-------|-------|
| S1 | Extend `constraint_parser` to `@zdc.fn`, `@zdc.spec`/`@zdc.op`, ghost `Seq`, bounded `all`/`any`, `choose`; emit spec IR; run `Merge` (§8.4) as a Python reference model | the Python surface works and is executable on day one |
| S2 | Lean export of the S1 spec IR against the L1 Zuspec-in-Lean core; state `per_input_order` as a Lean theorem and prove it | the Python spec has a meaning in Lean; checks how hard proofs are when exported |
| S3 | `@zdc.refines(MergeRR, rel=E2)` on the existing `rr_merge` design: generated simulation monitor + SBY obligation for the fairness bound | the lowering task generates obligations rather than designs |
| S4 | Lean front end: a small Lean DSL that elaborates to the same spec IR as S1, round-tripped through the S2 export | two surfaces, one semantics |

Order: L1 (the core semantics) is a prerequisite for S2 and S4. S1 and S3 can
start right away, since they build on existing parser and contract code.

### 8.8 What a connected flow gives that a standalone Lean model can't

These are the claims to make to Lean users, and the things to demonstrate.
Each comes from there being no seam between layers, not from the surface
language.

| Connected flow | Standalone Lean + hand-written RTL |
|---|---|
| **Every layer runs**, in one simulator. Even `choose` in the spec can run as random selection. The spec is the scoreboard for the lower layers and for the SV, via Verilator. | Only computable Lean definitions run, and comparing them to RTL needs DPI glue |
| **One IR and one type system across layers.** A `BitVec[8]` means the same thing in spec, model and SV. | Widths, encodings and enums are mapped by hand at the seam |
| **Refinement links are recorded.** Each lowering step, automatic or manual, records its abstraction map and E-relation. Each SV transaction traces back to a spec op. | The abstraction map is rebuilt in a proof script, or never written down |
| **Obligations are generated at every step** and checked in the cheapest engine first (run time → SMT → SBY → Lean). | Each property is hand-picked, encoded and run separately |
| **Changes are re-checked, so proofs don't silently go stale.** Editing any layer re-runs the obligations at its two neighbouring steps in the same regression. | The proof keeps passing against a model the RTL no longer matches |
| **One repo, one build, one report**, and one context for agents and LLM provers | Two toolchains, two CI flows, two places to look |
| **The handoff is ordinary SV**, produced by construction from the bottom layer | The RTL is the hand-written source; the proof is a side artifact |

**Manual steps are where the obligations matter.** Automatic lowering
(op signatures → API, pure functions → method bodies, R1 → SV) is correct by
construction or translation-validated. Hand-written refinement (resolving
`choose`, choosing data structures, pipelining) is where the user does the
creative work. The flow never trusts these steps: each one gets a generated
monitor and formal obligations. This is the Event-B discipline, without a
separate tool.

**Consequence for S1–S4 (§8.7):** add **S5**, an end-to-end `rr_merge` thread
through every layer:

- spec DSL;
- a hand-written round-robin refinement;
- the existing fw-hdl model;
- SV under Verilator.

At every step the obligations are generated and checked in one regression.
Then edit one layer and show the right obligation failing. That demonstration
is the accessibility argument, more than any single proof.

### 8.9 Each language covers a different subset of the semantics

fw-hdl already includes several languages. Nothing requires them to cover the
same semantics: each covers the subset it is good at, and Zuspec IR covers all
of them. The spec layer can therefore live in Python (and Lean) without being
added to SV or C.

| Layer | Python | SV (fw-hdl-spec / fe-sv) | C | Lean |
|---|---|---|---|---|
| Spec: ghost collections, `choose`, theorems, invariants | yes | no | no | yes (plus proofs) |
| Refinement declarations (`refines`, abstraction map, E-relation) | yes | later, if wanted | no | yes |
| Executable method level (R3) | yes | yes | yes (pure functions, method bodies) | pure functions only (option C import) |
| Timed and cycle level (R2/R1), protocols, transactors | yes | yes (canonical) | no | no |
| SV handoff | generated | the source, or generated | n/a | n/a |

What this requires:

- **Each language front end declares its subset.** A construct outside that
  subset is rejected with a clear message, never translated approximately.
- **Refinement links can cross languages.** A Python spec must be able to
  declare `refines` against a component written in SV through fe-sv, by
  referring to its IR entity, not its Python class. The design that ships may
  well be SV, and the spec doesn't need to care which language it came from.
  This makes S3 (§8.7) a cross-language probe: a Python spec over the
  existing design.
- **Obligations and reports speak IR.** Generated monitors and obligations
  attach to IR ports and operations, so they work whichever language wrote
  each layer.
- **Lean is one more front end, with its own subset** (spec plus proofs). It
  is special in only one way: it also *defines* the semantics the other
  front ends are measured against (option B).

### 8.10 Projection: one ecosystem, not only one IR

The goal goes beyond "every language reaches the same IR". A developer should
be able to move a design **between languages** and keep working in the
ecosystem:

1. Start in Lean.
2. Project to Python and see recognizable code.
3. Keep refining in Python.
4. Project to SV for the hardware implementor.

So front ends need partners that run the other way: **projections** that emit
*idiomatic source* in each language, not an IR dump.

**A projection starts a new refinement layer at identity.**

- **It doesn't make a copy that must be kept in sync.** Projecting layer *n*
  (say, Lean) into another language creates layer *n+1*. That new layer
  `refines` layer *n* under E0, which holds by construction since the
  projection preserves meaning.
- **Ownership is clear.** The Lean file stays the source for the spec. The
  projected Python file is the source for the refinement, and the user edits
  it freely.
- **Edits produce obligations.** Once the user changes the Python, the
  generated monitors and obligations at that link apply, as in §8.8.
- **No round-trip merge.** The upper layer is never regenerated from the lower
  one, so there are no merge conflicts.

**What "recognizable" requires of the IR and the projections:**

- **Keep source-level structure.**
  - Names, ops, structs, docstrings and comments are kept.
  - Contracts stay as contracts.
  - Spec constructs stay as spec constructs, not lowered early.
  - For example, a Lean `structure` with `def` operations projects to a
    `@zdc.spec` class with `@zdc.op` methods, and a `theorem` to a
    `@zdc.theorem`.
- **Use each language's idioms.**
  - Python projects to zdc decorators.
  - SV projects to fw-hdl-spec classes and APIs, with plain parameterized
    modules for the RTL handoff. This follows the existing rule that sync
    lowering emits one module per class, so the RTL follows the classes.
  - Lean projects to `structure`/`def`/`theorem`, with the Zuspec-in-Lean
    core library.
- **Project only into the target's subset (§8.9).** Constructs outside it
  stay in the upper layer and are referred to, not dropped. If a spec layer is
  projected to SV, its theorems and spec-only state stay in Lean or Python,
  and the SV gets the operations, protocols and generated monitors.
- **Projections are tested by round trip.** Parsing the projected source must
  give IR equal to the original, for the constructs in the target's subset.
  That round trip is the translation-validation evidence for the E0 link.

**Ecosystem services follow the IR, not the language.** Simulation, the
generated scoreboard and monitors, the engines, the reports, protocol kits and
handoff packaging work the same whichever language wrote each layer. A Lean
developer gets fw-hdl's DV, protocols and SV handoff without leaving Lean
until they choose to.

**Probe S6:**

1. Write the §8.4 `Merge` spec in Lean (or a small part of it).
2. Project it to Python and diff it against the hand-written §8.4 version,
   which should be recognizably the same.
3. Refine it to round-robin in Python.
4. Project to SV for handoff.

Check the round trip at each projection.

**Worked sketch:** `docs/design/lean-python-example.md` shows `Merge` and its
round-robin refinement `MergeRR` in native Lean next to their Python
projections, with the rules that map one to the other and the remaining
layers down to the SV handoff.

**Tooling note (Lean in edapack / IVPM).**

- **How Lean tooling splits:**
  - **elan** manages toolchains, like rustup. A project's `lean-toolchain`
    file picks the version, and elan downloads it on demand.
  - **Lake** is the build system and package manager, like cargo or pip.
    `lakefile.toml`/`.lean` lists requirements, `lake-manifest.json` locks
    them, packages land in `.lake/packages/`, and the Reservoir index lists
    them.
- **Plan:**
  - Ship the Zuspec Lean library as an ordinary Lake package, so Lean users
    never need IVPM.
  - If demand grows, IVPM support should:
    - fetch the pinned toolchain from the project's `lean-toolchain`, as a
      GitHub release;
    - put it on PATH through the direnv view;
    - leave Lean dependencies to Lake, the way IVPM leaves PyPI packages to
      pip.
  - edapack can ship one pinned core toolchain once the L1/S2 probes need it.

**Guard rail: no proof references in spec source.** Proof status is evidence
kept by the flow, keyed by obligation identity in the IR. Lean theorems are
matched to derived obligations by their statement. Any binding a person must
write lives in flow configuration, not in the spec. See
`lean-python-example.md` §5.

**Design rule for the Python spec surface: valid Python syntax, Zuspec
semantics. Running it is meaningful only for some roles.**

"Runs as plain Python" means something different for each kind of construct.
Constraints show this clearly:

- `implies`, `dist` and `solve_order` return marker objects that are "never
  actually executed" (`constraint_helpers.py`).
- A bare `self.a < self.b` in a constraint, run as plain Python, computes a
  bool and throws it away.
- Contracts are not run as Python either. `contract_checker` evaluates the
  *parsed IR* with `ExprEval`.

So for constraints today, the requirement is only that the code parses and
type-checks. What the code means is what the parser produces from it.

| Role | Constructs | What running it as plain Python must do |
|---|---|---|
| **Statements** | `@zdc.op` and `@zdc.fn` bodies | Produce **one valid behavior.** `choose` picks at random, `u32` wraps. This is what lets the spec act as a reference model. |
| **Predicates** | `requires`, `ensures`, `@zdc.invariant`, `assert`s in theorems, constraints used as checks | **Check the current concrete state:** pass exactly when that state satisfies the predicate. Running it must never silently do nothing (see below). |
| **Declarative directives** | `dist`, `soft`, `solve_order`, `decreases`, proof hints | **No procedural meaning.** Plain execution may do nothing, and that's acceptable because these constructs claim no procedural reading. |

- **Which runner counts.** The guarantee is about the Zuspec Python runtime
  (zuspec-be-py), not CPython running the raw function. The runtime runs
  native Python where the two readings agree (op bodies) and interprets IR
  where they don't (constraints, contracts, `choose`). Native execution of a
  raw function body is a convenience, guaranteed meaningful only for
  statements.
- **Predicates must not silently do nothing.** In a predicate, a bare
  expression is a check only when the runtime evaluates it. Run natively, it
  does nothing. So the runtime always evaluates predicates (as
  `contract_checker` does), or the linter requires `assert` wherever a
  predicate may be run natively.
- **Theorems use both readings.** A theorem means "for every pre-state
  satisfying `requires`, the body's asserts hold after the step." Its
  `requires` block is a constraint on the pre-state, so the constraint solver
  can *generate* pre-states that satisfy it, using the constraint's
  declarative reading. The body then *checks* each one, using its procedural
  reading. That is property-based testing built from existing machinery,
  before any formal engine runs.

**Assumption (2026-11-25): a well-formed constraint function either passes or
asserts.** It is written as `assert self.a < self.b`, so running it natively
checks the current values. Constraints then move from "parse only" into the
**predicates** row above. Consequences:

- **One predicate form everywhere.** Constraints, `requires`/`ensures`,
  invariants and theorem bodies are all functions of `assert`s over state, and
  each can be read in three ways:
  - **generate:** the solver produces values that satisfy it;
  - **check:** running it natively, or through the IR, tests concrete values;
  - **prove or assume:** a formal engine proves it, or uses it as an
    assumption.

  A constraint on random fields *is* an assumption, which is exactly what a
  theorem's `requires` is.
- **They compose by calling each other.** `with zdc.requires:
  self.legal_cfg()` calls a constraint function. Run natively, its asserts
  fire. Parsed, it is inlined. No names are passed as strings.
- **The free check is useful in DV.** After `randomize()`, calling the
  constraint natively checks the solver's result. On directed stimulus it
  checks that hand-set values are legal. On transactions a monitor
  observes, it checks the DUT's output against the same rules used to
  generate input.
- **Helpers must compute real values on concrete data.** Today several are
  placeholders that would make a correct constraint fail when run natively:
  - `sum` returns `0`, so `assert zdc.sum(self.arr) == 10` fails;
  - `ascending`, `descending` and the array form of `unique` return `True`;
  - `implies` and `dist` return marker objects, which are always truthy, so
    an `assert` on them passes vacuously.

  Fix: when called on concrete values they return real bools or ints, e.g.
  `implies(a, b)` returns `(not a) or b`, and `dist` checks the value is in
  the listed set (as SV `dist` does). The parser is unchanged, because it
  never calls them.
- **Directives don't get an `assert`.** `soft`, `solve_order`, the weights in
  `dist`, and `valid`/`internal` steer generation; they aren't checks. A soft
  constraint may legitimately be violated, so asserting it would be wrong.
  The flake8 plugin (`flake8_zdc_struct.py`) can enforce both sides:
  predicates need `assert`, and directives must not have one.
- **Moving off bare expressions.** The parser keeps accepting bare-expression
  constraints, and the linter warns. Existing zuspec-dataclasses tests and
  users depend on them, so this is a gradual change across Zuspec.
- **Pressure points:**
  - `python -O` removes `assert`s. Native checking must not be the only
    check; the runtime evaluates the IR wherever it matters.
  - Quantifiers over wide domains (`for x in range(2**32)`) are valid but
    not practical to run natively. Native checking is for quantifiers over
    data structures, not over value domains.
  - Side effects inside an `assert` are rejected by the linter.

**Converged framing (2026-11-25): the checker defines what the constructs
mean, and the engines quantify over it.**

- **Users are told what a construct means as a checker.** Run on one concrete
  state, it passes or asserts. That one reading defines which states are
  good, for every construct.
- **Engines don't run the checker. They ask one of two questions about the
  set of states that pass**, depending on the construct's role:

| Role | Engine question | Result the user sees |
|---|---|---|
| Constraints (generation) | **∃**: is there a state that passes? Find one. | a solution, or "unsatisfiable" (with an unsat core) |
| Assumptions: `requires`, constraints used as assumptions, theorem pre-states | **∃**: is the assumption satisfiable at all? | "vacuous" if not, as `python/fw/hdl/formal/prove.py` already reports |
| Obligations: `ensures`, invariants, theorem asserts, refinement | **∀**: does every state allowed by the assumptions pass? Asked as "is the negation unsatisfiable?" | proven, or a counterexample (which can be replayed in simulation) |

- At the solver both questions are satisfiability checks, so "rules the
  engine checks for satisfiability" is accurate there. For users, the
  difference that matters is **witness vs counterexample**.
- **An obligation counts as proven only once its assumptions are shown to be
  satisfiable.** Otherwise every ∀ holds trivially.

## 9. Would anyone outside fw-hdl want a "Python flavor of Lean"? (judgment, not market research)

**As a standalone product: probably few people. As the way into a connected
flow: yes, and it can draw people into that flow.**

- **The name invites the wrong comparison.**
  - Lean users will see "no dependent types, no kernel, so not Lean".
  - Python users will ask why they need proofs.

  Position it as *a Python spec layer with a formal semantics, that exports
  to Lean*. Lean is the backend for meaning and proof, not the brand.
- **Analogues show there's demand for friendlier syntax on formal semantics,
  but a niche one:**
  - Quint (TLA+ semantics, programmer syntax);
  - P (used at AWS);
  - Verus (auto-active verification in Rust).

  None of them won on syntax alone. Each won where it was built into a
  workflow its users already had.
- **Python verification of general software hasn't caught on** (Nagini and
  CrossHair stay niche). Our DSL avoids that problem: it's a restricted DSL
  embedded in Python, like Amaranth, PyMTL, JAX or Triton, and it doesn't try
  to verify Python itself.
- **The most plausible outside audience is Python-based DV: cocotb users.**
  - They get value with no proofs at all: theorems as property-based tests,
    with pre-states generated by the constraint solver, the same constraint
    used as both generator and checker, and the spec as a scoreboard.
  - Proofs come later and can be added one at a time.
  - That's "Hypothesis for hardware, which can grow into formal proof".
- **For the Lean community, the draw is the projection** (S6):
  - their hardware collaborators can read and refine the spec in Python
    without learning Lean;
  - their Lean proofs keep counting through the evidence record.

  That makes it feed people into Lean, not compete with it.
- **Areas not to chase:**
  - AI-generated code verification in general. It's crowded and well
    funded, and our differentiators (time, protocols, refinement down to SV)
    don't matter there.
  - Software verification in general.
- **Ways to test interest cheaply:**
  - the S6 projection demo on Lean Zulip or at Lean Together;
  - theorem-as-property-test with cocotb, shown to the cocotb community;
  - a paper on the E0–E4 ladder's Lean semantics (FMCAD, or a CAV tool
    paper), for credibility with formal-methods researchers.

**Follow-on:** `spec-driven-generation-coverage.md` covers how the spec drives
random generation (stateful property testing with shrinking, and direct-state
mode for finding missing invariants), coverage derived from the spec's
predicates and measured through `abs()`, and a closure loop that counts proofs.
