# Example: one spec in Lean and in its Python projection

Companion to `lean-positioning.md` §8.10 (projection). Status: **sketch**.

- Neither side has been run. No Lean toolchain is installed here, and the
  Python `zdc` spec vocabulary (`@zdc.spec`, `@zdc.op`, `zdc.choose`,
  `zdc.below`, `zdc.Seq`, `zdc.ghost`, ...) is the planned S1 surface; it doesn't exist yet.
- On the Lean side, the `Zuspec` import and the `@[zuspec.*]` attributes are
  the planned S4 front end, on top of the L1 core. Everything else is plain
  Lean 4.
- Proofs are elided (`sorry`), with a comment giving the intended tactic.

The design is `rr_merge`: N input streams merged onto one output. There are
two layers:

1. **`Merge`**, the abstract spec. Any non-empty input may be served next.
2. **`MergeRR`**, a round-robin policy that refines `Merge`.

Each layer is shown in native Lean, then as the Python you would get by
projecting it. §3 maps one to the other, and §4 is what comes next on the way
to SV.

---

## 1. Layer 1: the abstract spec

### Lean (native)

```lean
import Zuspec   -- Zuspec-in-Lean core (probe L1) + front-end attributes (S4)

namespace RRMerge

/-- Abstract merge: `n` inputs, one output.
    Order between inputs is unconstrained; order within an input is kept. -/
@[zuspec.spec]
structure Merge (α : Type) (n : Nat) where
  q      : Fin n → List α        -- pending, per input
  out    : List (Fin n × α)      -- everything emitted        (ghost)
  pushed : Fin n → List α        -- everything ever pushed    (ghost)

namespace Merge
variable {α : Type} {n : Nat}

def init : Merge α n := ⟨fun _ => [], [], fun _ => []⟩

/-- push: always enabled. -/
@[zuspec.op]
def push (s : Merge α n) (i : Fin n) (p : α) : Merge α n :=
  { s with q      := Function.update s.q i (s.q i ++ [p]),
           pushed := Function.update s.pushed i (s.pushed i ++ [p]) }

/-- pop: a *relation*. Any input with a pending packet may be chosen. -/
@[zuspec.op]
inductive Pop : Merge α n → (Fin n × α) → Merge α n → Prop
  | mk (s : Merge α n) (i : Fin n) (p : α) (rest : List α)
       (h : s.q i = p :: rest) :
       Pop s (i, p) { s with q   := Function.update s.q i rest,
                             out := s.out ++ [(i, p)] }

/-- The packets emitted from input i, followed by those still pending on i,
    are exactly the packets pushed on i. -/
def emittedFrom (s : Merge α n) (i : Fin n) : List α :=
  s.out.filterMap fun (j, p) => if j = i then some p else none

@[zuspec.invariant]
def orderInv (s : Merge α n) : Prop :=
  ∀ i, s.emittedFrom i ++ s.q i = s.pushed i

theorem orderInv_init : orderInv (init : Merge α n) := by
  intro i; simp [orderInv, emittedFrom, init]

theorem orderInv_push (s : Merge α n) (j : Fin n) (p : α)
    (h : orderInv s) : orderInv (s.push j p) := by
  sorry -- intro i; by_cases i = j <;> simp_all [push, Function.update, emittedFrom]

theorem orderInv_pop (s s' : Merge α n) (o : Fin n × α)
    (h : orderInv s) (hp : Pop s o s') : orderInv s' := by
  sorry -- cases hp; intro k; by_cases k = i <;> simp_all [...]; list append assoc

end Merge
```

### Python (projected)

```python
from typing import Annotated, Generic, TypeVar
import zuspec.dataclasses as zdc

P = TypeVar("P")                       # packet type   (Lean: α : Type)

# An input index: an int below N  (Lean: Fin n).
# Annotated keeps it a plain int for Python tools; the bound is metadata,
# evaluated against the instance like zdc's existing width=lambda s: ...
Input = Annotated[int, zdc.below(lambda s: s.N)]

@zdc.spec
class Merge(zdc.Spec, Generic[P]):
    """Abstract merge: N inputs, one output.
    Order between inputs is unconstrained; order within an input is kept."""
    N: zdc.u32 = zdc.const(default=2)  # number of inputs   (Lean: n : Nat)
    q:      zdc.Seq[zdc.Seq[P]]       = zdc.field(len=lambda s: s.N)  # pending, per input
    out:    zdc.Seq[tuple[Input, P]]  = zdc.ghost()
    pushed: zdc.Seq[zdc.Seq[P]]       = zdc.ghost(len=lambda s: s.N)

    @zdc.op
    def push(self, i: Input, p: P):
        """push: always enabled."""
        self.q[i] = self.q[i] + [p]
        self.pushed[i] = self.pushed[i] + [p]

    @zdc.op
    def pop(self) -> tuple[Input, P]:
        """pop: any input with a pending packet may be chosen."""
        with zdc.requires:
            any(self.q[i] for i in range(self.N))
        i = zdc.choose(i for i in range(self.N) if self.q[i])
        p, self.q[i] = self.q[i][0], self.q[i][1:]
        self.out = self.out + [(i, p)]
        return (i, p)

    @zdc.fn
    def emitted_from(self, i: Input) -> zdc.Seq[P]:
        return [p for (j, p) in self.out if j == i]

    @zdc.invariant
    def order_inv(self):
        """The packets emitted from input i, followed by those still pending
        on i, are exactly the packets pushed on i."""
        for i in range(self.N):
            assert self.emitted_from(i) + self.q[i] == self.pushed[i]

# Use site: type argument by generic, value parameter by const
m = Merge[zdc.u32](N=4)                # Lean: Merge (BitVec 32) 4
```

What's recognizable, and what changed:

- **Same structure.** The structure becomes a class, each `def`/`inductive` op
  becomes a `@zdc.op` method, and docstrings and field comments carry over.
- **The relation `Pop` becomes a method with `zdc.choose`.** The relation's
  premise `s.q i = p :: rest` splits into two parts: a `requires`, which says
  when the op is enabled, and a `choose` filter, which says which inputs it may
  pick.
- **Three Lean theorems become one `@zdc.invariant`.** In Python,
  "holds at init and is preserved by every op" is derived from the
  declaration, following the minimal-user-spec rule.
- **The Python source holds no proofs and no references to proofs.** The Lean
  proofs still discharge these obligations, but that link lives in the flow's
  evidence record (§5), not in the code.
- **If the invariant is written in Python first**, nothing in Lean matches it,
  and the engines take it on: bounded SMT for small N and depth, then k-induction. If
  they fail, the obligation is exported back to Lean.

---

## 2. Layer 2: round-robin refinement

### Lean (native)

```lean
namespace RRMerge
variable {α : Type} {n : Nat} [NeZero n]

/-- Round-robin policy. `extends` gives the abstraction map `toMerge` for free. -/
@[zuspec.spec, zuspec.refines Merge (rel := .E0)]
structure MergeRR (α : Type) (n : Nat) [NeZero n] extends Merge α n where
  ptr : Fin n

namespace MergeRR

/-- First input at or after `ptr` (wrapping) with a pending packet. -/
def pick (s : MergeRR α n) : Option (Fin n) :=
  (List.range n).findSome? fun k =>
    let j := s.ptr + Fin.ofNat' n k
    if (s.q j).isEmpty then none else some j

/-- pop is now a *function*: deterministic. -/
@[zuspec.op]
def pop? (s : MergeRR α n) : Option ((Fin n × α) × MergeRR α n) := do
  let j ← s.pick
  match s.q j with
  | []        => none
  | p :: rest => some ((j, p),
      { s with q   := Function.update s.q j rest,
               out := s.out ++ [(j, p)],
               ptr := j + 1 })

/-- How many grants input i is from the head of the round-robin order. -/
def wait (s : MergeRR α n) (i : Fin n) : Nat := (i - s.ptr).val

/-- Refinement (E0): each concrete step is an abstract step. -/
theorem refines_pop (s s' : MergeRR α n) (o : Fin n × α)
    (h : s.pop? = some (o, s')) : Merge.Pop s.toMerge o s'.toMerge := by
  sorry -- unfold pop?; split at h; exact Merge.Pop.mk _ _ _ _ ‹_›

/-- No new deadlock: if the spec can pop, so can the policy. -/
theorem enabled (s : MergeRR α n) (h : ∃ i, s.q i ≠ []) : s.pick.isSome := by
  sorry -- findSome? over all offsets covers every i

/-- Fairness, stated so it can be proven by induction: a waiting input is
    either served now or moves closer to the head of the order. -/
theorem rr_progress (s s' : MergeRR α n) (o : Fin n × α) (i : Fin n)
    (hi : s.q i ≠ []) (hp : s.pop? = some (o, s')) :
    o.1 = i ∨ s'.wait i < s.wait i := by
  sorry -- o.1 is the first non-empty input from ptr, so it lies in [ptr, i);
        -- ptr' = o.1 + 1, so (i - ptr') < (i - ptr); omega on Fin vals

end MergeRR
end RRMerge
```

### Python (projected)

```python
@zdc.spec
class MergeRR(Merge[P]):
    """Round-robin policy. Subclassing Merge declares refinement (E0);
    the abstraction map drops `ptr` and is derived."""
    ptr: Input = zdc.field(default=0)

    @zdc.fn
    def pick(self) -> Input | None:
        """First input at or after ptr (wrapping) with a pending packet."""
        for k in range(self.N):
            j = (self.ptr + k) % self.N
            if self.q[j]:
                return j
        return None

    @zdc.op
    def pop(self) -> tuple[Input, P]:
        """pop is now deterministic."""
        with zdc.requires:
            self.pick() is not None
        j = self.pick()
        p, self.q[j] = self.q[j][0], self.q[j][1:]
        self.out = self.out + [(j, p)]
        self.ptr = (j + 1) % self.N
        return (j, p)

    @zdc.fn
    def wait(self, i: Input) -> int:
        """How many grants input i is from the head of the round-robin order."""
        return (i - self.ptr) % self.N

    @zdc.theorem
    def rr_progress(self, i: Input):
        """A waiting input is served now or moves closer to the head."""
        with zdc.requires:
            self.q[i]
        j, _ = self.pop()                    # in a theorem: take one step
        assert j == i or self.wait(i) < zdc.old(self).wait(i)
```

What's recognizable, and what changed:

- **Lean `extends` + `@[zuspec.refines]` becomes Python subclassing.** In both,
  the abstraction map is derived: Lean's `toMerge`, and in Python, dropping the
  added fields.
- **`refines_pop` and `enabled` aren't written in Python.** Overriding an op in
  a refining subclass *generates* both obligations: each step must be allowed,
  and the guard must not get stronger. The evidence record matches them to
  the Lean theorems (§5). Python users who write `MergeRR` from scratch get
  the same obligations, discharged by the engines or exported to Lean.
- **`Option`-returning `pop?` becomes an op with a `requires`.** The guard is
  the `isSome` case.
- **A theorem quantified over before and after states becomes a theorem
  method.** It takes one op step, and `zdc.old(self)` names the state before
  that step.

---

## 3. Construct map (the projection's rules)

| Lean | Python | Notes |
|---|---|---|
| `structure S (n : Nat)` with `@[zuspec.spec]` | `@zdc.spec class S(zdc.Spec)` with `N = zdc.param()` | |
| type parameter `(α : Type)` | `Generic[P]` (`TypeVar`); use site `Merge[zdc.u32]` | Python generics carry *types* only |
| value parameter `(n : Nat)` | `N: zdc.u32 = zdc.const(...)`; use site `Merge(N=4)` | zdc's existing const-parameter idiom |
| `Fin n` | `Annotated[int, zdc.below(lambda s: s.N)]` | A type in Lean; a range check / obligation in Python. Wrap-around is written as explicit `% self.N` |
| `List α` / `Fin n → α` | `zdc.Seq[α]` / `zdc.Seq[α]` with `len=lambda s: s.N` | Spec-only unless a later layer gives it a bound |
| field marked ghost by comment / usage | `= zdc.ghost()` | The projection infers ghost status: a field is ghost when no op's result depends on it |
| `def op (s) ... : S` | `@zdc.op` method that updates `self` | |
| `inductive Op : S → α → S → Prop` | `@zdc.op` with `requires` + `zdc.choose` | Its premises split into a `requires` and the `choose` filter |
| `def op? : S → Option (α × S)` | `@zdc.op` with `requires` | `none` ↔ guard false |
| `def f` (pure, not an op) | `@zdc.fn` | |
| `@[zuspec.invariant] def inv : Prop` + `_init`/`_op` theorems | `@zdc.invariant` (obligations derived) | Lean proofs matched in the evidence record (§5) |
| `theorem` over one step | `@zdc.theorem` method, with `zdc.old(self)` for the pre-state | |
| `extends` + `@[zuspec.refines Spec (rel := .E0)]` | subclass (E0), or `@zdc.refines(Spec, rel=...)` + `abs()` when not a field projection | |
| `refines_op`, `enabled` theorems | generated obligations | |
| `∀ i, P i` (bounded index) | `for i in range(self.N): assert P(i)` | An unbounded `∀` uses `zdc.forall(lambda x: ...)` |
| `Function.update f i v` | `self.m[i] = v` | |
| proof terms / tactics | — (nothing in the source) | Proofs stay in Lean; the evidence record (§5) says which obligations they discharge |
| docstrings `/-- -/`, `--` comments | docstrings, `#` comments | Kept by the IR (§8.10) |

Round-trip check for S6: parse each Python block above, project it back to
Lean, and compare the IR. The comparison covers declarations, op bodies,
contracts and theorem statements. Proofs are not part of the source on either
side, so they are not compared.

---

## 4. Continuing toward SV (Python only, not shown in full)

| Layer | Written by hand | Generated |
|---|---|---|
| 3. Bounded | `q` becomes `zdc.Fifo[P, DEPTH]` per input. `push` gets `requires len(q[i]) < DEPTH`, which is back-pressure. | Obligation: refines `MergeRR` under **E2** (per-input order) rather than E0, because pushes can now stall. `order_inv` carries over, and only the new guard is new. |
| 4. fw-hdl component (R3 → R1) | The existing `rr_merge` design, with `abs()` mapping its FIFOs and pointer to layer 3 | Simulation monitor plus SBY obligations for `rr_progress` on the RTL. The ghost fields `out`/`pushed` become monitor state, not hardware. |
| 5. SV handoff | — | Projection to SV: fw-hdl-spec API for `push`/`pop` (protocol kit), the component as one parameterized module per class, plus the generated checkers as a DV package |

The Lean user stops wherever they like. Layers 1 and 2 stay as Lean sources,
the Python layers below refer to them through `refines`, their proofs count
through the evidence record, and the
person implementing the hardware receives plain SV.

---

## 5. Where proof evidence lives: in the flow, not the source

A spec says *what* must hold. Whether something has been proven, and by what,
is **evidence**. Evidence changes when a tool version, a design or a solver
changes, even if the spec doesn't. It belongs with test results and coverage,
not in decorator arguments. A `proof="lean:..."` string would be a reference
to something outside Python that no linter, IDE or type checker can check.

- **Obligations are identified by IR identity**, not by name strings. For
  example: `(MergeRR, pop, refines Merge)`, `(Merge, order_inv, preserved-by
  push)`. They are derived from the declarations, as described above.
- **Engines produce evidence records** keyed by that identity:
  - a Lean theorem, kept with the toolchain version and the Lean package and
    revision it came from;
  - an LRAT certificate from `bv_decide`;
  - an SBY run with its depth and result;
  - or "checked in simulation only".

  The records live in the flow's results area. Reports and the dashboard read
  them, and a status of "proven" means a record exists.
- **Lean theorems are matched to obligations by statement, not by name.**
  Projecting Lean to Python is an identity step (§8.10), so the obligations
  derived on the Python side have the same statements, in IR, as the Lean
  theorems. The flow matches them structurally. No one writes a link, which
  follows the minimal-user-spec rule.
  - A Lean theorem that matches no derived obligation is reported as an extra
    lemma.
  - An obligation that matches no theorem goes to the other engines.
- **Where a person really must point at a proof,** for example when a
  hand-written Python invariant is proven by a Lean lemma with a different
  statement, the binding goes in flow configuration, not in the spec source.
  An example is a `proofs:` entry on the formal task in `flow.yaml` naming the
  Lean package. The spec stays clean, and the binding is versioned with the
  flow that uses it.
- **Python-side proof hints stay Python.** Users steer a proof by writing
  lemmas, intermediate `assert`s and `@zdc.lemma` functions that call each
  other, as in Dafny or Verus. Those are code, and linters and type checkers
  can check them.

---

## 6. Parameters: generics for types, `zdc.const` for values

`N` is the number of inputs, Lean's `n : Nat`. It is a **value** parameter.
Lean makes no distinction here: `Merge (α : Type) (n : Nat)` takes a type and
a value the same way, and `Fin n` is a type that depends on a value. Python
draws the line, and the projection follows it:

- **Type parameters become Python generics.** The packet type `α` becomes
  `Generic[P]`, and the use site is `Merge[zdc.u32]`. Type checkers and IDEs
  understand this. zdc already uses `Generic[T]` (`InPort`, `OutPort`,
  `Completion`, the queue type). `class Merge[P]` syntax would need Python
  3.12, and zuspec-dataclasses supports 3.10+.
- **Value parameters stay `zdc.const`**, as they are today: `WIDTH:
  zdc.u32 = zdc.const(default=32)` in `tests/unit/test_parameterization_ir.py`.
  Python typing has no value generics. `Merge[4]` isn't a valid type, and
  `Merge[Literal[4]]` is a hack that type checkers can't do arithmetic on.
- **Types that depend on values use `Annotated` plus a lambda over the
  instance.** Examples are `Fin n` and a list of length `n`. This reuses two
  existing zdc idioms: `zdc.u32` and friends are already `Annotated` types,
  and dependent widths are already `width=lambda s: s.WIDTH`. Python tools see
  an `int` or a `Seq`. The bound shows up as metadata, which becomes a type in
  the Lean projection and a range check or obligation in the Python engines.
- **The cost:** dependent types turn into obligations. In Lean, an out-of-range
  index is a type error. In Python, it's a generated proof obligation, or a
  failure at run time in simulation. That fits the auto-active style (§8.3 of
  the positioning doc). It's also why wrap-around is written as an explicit
  `% self.N`, rather than hidden in a `Fin` type that Python doesn't have.

The earlier draft's `zdc.Fin["N"]` used a string as a forward reference to a
field. Like the `proof=` strings, it was invisible to Python tooling, and it
also invented a third parameter convention next to two existing ones.
