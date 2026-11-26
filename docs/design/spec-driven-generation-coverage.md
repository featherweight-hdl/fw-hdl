# Spec-driven test generation and coverage

Status: idea / design sketch (2026-11-25). Follows from `lean-positioning.md`
§8–§9 and `lean-python-example.md`. Nothing has been built yet.

## User benefit

- **Random tests that are legal by construction and checked by construction.**
  - The spec's ops and `requires` give the legal sequences.
  - Its constraints give the legal arguments.
  - Its state, `ensures` and invariants give the expected results.
  - DV doesn't write sequences, scoreboards or a reference model for anything
    the spec already says.
- **Coverage models that are derived, not hand-written.**
  - Targets come from the predicates the user already wrote (guards, choices,
    invariants, theorem cases).
  - They are measured on the RTL through the refinement map.
  - They are limited to *reachable* targets, so there are no unreachable bins
    to waive.
- **Closure counts proofs.** A target covered by a formal proof needs no
  simulation hit, and an uncovered target becomes a directed test
  automatically.

## 0. Status

| Step | State |
|------|-------|
| Generation ideas (§1) | sketched |
| Coverage ideas (§2) | sketched |
| Closure loop (§3) | sketched |
| Probes G1–G4 (§5) | not started |

---

## 1. Better random generation: yes, in five ways

Today's SV constrained random draws each transaction from its constraints on
its own. Legal *sequencing* is hand-written in sequences, and the oracle (the
scoreboard or reference model) is hand-written too. A spec with ops,
`requires` and invariants provides all three. This is stateful, model-based
property testing, the way Hypothesis's `RuleBasedStateMachine` or QuickCheck
state-machine testing work, with Zuspec's constraint solver choosing the
arguments.

1. **Legal op sequences come from the guards.**
   - At each step, pick an op whose `requires` is satisfiable in the current
     spec state, and have the solver pick arguments that satisfy it.
   - The spec state advances with the op, so the next choice depends on real
     state, not on a hand-written sequence.
   - This is PSS scenario generation (actions plus preconditions) in
     Zuspec's own terms. Zuspec's activity, scenario and coverage IR (in
     `zuspec-ir-core`) are already the right place for it.
   - The ops are the same interface operations as the DV-ops methodology
     (`hw-sw-interface.md` §4a.7). They are the cookbook ops, now with
     contracts.
2. **The oracle is free.** Run the spec alongside the design (on RTL, through
   the protocol-kit transactors). Then check:
   - the refinement relation through `abs()`, under the protocol's E-relation;
   - each `ensures`;
   - each invariant.
3. **Shrinking.** A failing trace is a sequence of spec ops. It can be shrunk
   (drop ops, simplify arguments) while staying legal, because the guards are
   re-checked at each shrink step. Shrink at the spec level, then replay the
   short trace on the RTL. This is Hypothesis's strongest feature, and it
   needs a legal-sequence model, which the spec is.
4. **Generation aimed at a theorem.** A theorem says: for every state that
   satisfies `requires`, the asserts hold.
   - The solver generates pre-states that satisfy `requires` and are near the
     edge of each `assert`: equality cases of `<`, `wait(i)` at 0 and at
     `N-1`, queues empty or with one entry.
   - These are generated *directly as states*, not reached by sequences.
5. **Two modes that answer different questions.**
   - **Direct states (mode 4):** any state that satisfies `requires`,
     reachable or not. A failure may be in a state no run can reach. That
     isn't a design bug: it means an invariant is missing. In k-induction
     terms it's a counterexample to induction (CTI). So this mode cheaply
     finds the invariants the formal proof will need, at the spec level, in
     milliseconds.
   - **Reachable traces (mode 1):** only states reached from `init` by legal
     ops. A failure here is a real bug.

   The flow labels which mode a failure came from, so users can tell "missing
   invariant" from "bug".

---

## 2. Better coverage metrics: derived from the spec's own predicates

Today's coverage is code coverage (structural, says nothing about intent) plus
hand-written covergroups (expensive, and they fall out of date). The spec
already holds the predicates that matter, so the coverage model can be
derived from it.

| Metric | Target set | Example (`Merge` / `MergeRR`) |
|---|---|---|
| **Op and guard coverage** | each op taken; each op attempted while its guard is false (on the implementation, it stalled) | `pop` taken; `push` back-pressured once layer 3 bounds the FIFOs |
| **Choice coverage** (spec behaviors) | for each `zdc.choose`, which outcome classes the implementation actually exhibits, relative to which ones the spec allowed | which input wins when 1, 2 or all N are non-empty |
| **Predicate coverage**, MC/DC over invariants, `requires`/`ensures` and theorem asserts | each atomic condition shown to independently decide the outcome; boundary values of comparisons | `j == i` true and false; `wait(i)` at 0 and `N-1` |
| **Vacuity coverage** | every `implies` antecedent, and every theorem `requires`, made true at least once at run time | an `implies(mode == 1, ...)` whose antecedent never fires is flagged |
| **Case coverage of theorems** | each disjunct of an `assert`, and each `if` branch in a theorem body | `rr_progress`: both "served now" and "wait decreased" seen |
| **Abstract-state coverage** (predicate abstraction) | each *reachable* combination of the atoms that appear in guards, choice filters and invariants, measured on the RTL through `abs()` | the empty/non-empty pattern of `q[0..N-1]` × whether `ptr` points at a non-empty input |
| **Abstract-transition coverage** | (abstract state, op, choice class) triples | `pop` with exactly one non-empty input that isn't at `ptr` (a skip) |
| **Refinement coverage** | stuttering steps; occupied reorder windows under E2/E3; back-pressure under the declared relation | a pop stalled while the abstract pop was enabled |

What makes these better than hand-written covergroups:

- **They mean something.** Every target is a condition the user already said
  matters to correctness, so coverage now measures how much of the spec's
  behavior has been exercised.
- **The target set is reachable, not combinatorial.**
  - Abstract-state and transition targets are computed by exploring the spec,
    or by a formal reachability check. The goal is then 100% of what's
    reachable, not 100% of the cross product minus hand waivers.
  - Abstract state spaces are small, which is what makes this tractable.
  - When there are many atoms, limit crosses to atoms that appear in the same
    guard, filter or assert.
- **Each layer gets its own.**
  - Every refinement layer has its own spec and predicates. Layer 3's FIFO
    bound adds `len(q[i]) == DEPTH` to `push`'s guard, so "FIFO full" becomes
    a derived target there.
  - Microarchitecture with no spec layer above it still needs code coverage
    or hand-written covergroups. Derived coverage replaces covergroups only
    where a spec exists.
- **Measurement is the refinement map.** RTL coverage is sampled as the
  predicates applied to `abs(rtl_state)`. There's no separate sampling code
  to write.

---

## 3. Closure: generation and coverage share one loop

```
 derive targets from spec predicates ─┐
                                      ▼
 random op sequences (§1) ──► run RTL + spec ──► measure through abs()
                                      │
                    uncovered target ─┤
                                      ▼
            engine asks ∃: is there a trace from init that reaches it?
              ├── unreachable ─► drop it (with evidence), no waiver needed
              ├── witness ─────► replay that trace as a directed test on RTL
              └── unknown ─────► report to the user
 target already covered by a formal proof ─► closed in the evidence record
```

- **Asking "can this be reached?" at the spec level is cheap.** The spec's
  state is abstract and small. A witness trace is a sequence of ops, so
  it's directly a directed test, replayed through the transactors, and
  already short.
- **Closure is proof-aware.** A coverage target that lies inside an
  obligation proven for all states (the ∀ question) doesn't need a
  simulation hit. The evidence record (`lean-python-example.md` §5) holds
  both proofs and coverage, so the report shows "closed by proof" next to
  "closed by simulation".
- **This uses existing pieces.** The witness search is the ∃ question from
  `lean-positioning.md` (constraints and assumptions), here posed for a
  sequence of ops rather than one state. PSS-style scenario inference is the
  same question too.

---

## 4. Caveats

- **Spec coverage measures the spec's behaviors, not the microarchitecture's.**
  Pipeline hazards, arbitration inside a stage, and similar details are
  covered only if some refinement layer states them as predicates.
- **The RTL can still miss a state the spec can reach.** The design may
  never produce it (for example, a strict round-robin never shows some choice
  classes). Choice coverage is therefore measured *relative to the
  implementation's own refined layer*, where the choice has been resolved,
  not against everything the abstract spec allows.
- **Simulation cost.** Generating direct states is spec-level only. RTL
  coverage needs traces, so spec-level witness search matters for
  efficiency.
- **Too many abstraction atoms.** Use the same-predicate locality rule (§2),
  and let users exclude atoms with `zdc.coverage(ignore=...)`, written as
  code, not strings.

## 5. Probes

| ID | Probe | Shows |
|----|-------|-------|
| G1 | Stateful random runner for `Merge`/`MergeRR` in Python: guard-driven op choice, solver-chosen arguments, invariant checks, shrinking | generation (§1.1–1.3) without any RTL |
| G2 | Direct-state mode for `rr_progress` with a deliberately weakened invariant; show it finds the CTI | the "missing invariant vs bug" split (§1.5) |
| G3 | Derive predicate, vacuity and abstract-state targets for `MergeRR`; measure them on the existing `rr_merge` RTL through `abs()` under Verilator | derived coverage on real RTL (§2) |
| G4 | Closure loop: for G3's uncovered targets, spec-level witness search, then replay as directed tests; mark targets inside proven obligations as closed by proof | §3 end to end |

G1 and G2 need only the S1 spec surface. G3 and G4 also need S3 (the `refines`
harness on `rr_merge`).
