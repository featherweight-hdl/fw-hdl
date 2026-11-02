# Proposed changes to the anchor ADR (for review)

*Status: **accepted 2026-11-01 and applied** (ADR §2.3, §2.6; format v2). Result: A6 re-keying in edited scopes 254/623 (41%) → 58/588 (10%), (a) still 0; canary user anchors SV 40 / zdc 37, 36 shared (was 14 of 59/46). Original proposal below.*

*Was: proposed, not applied. The ADR is `packages/zuspec-ir-core/docs/anchors.md` (accepted). Evidence comes from A6 (`tools/anchor_churn.py`, report in `build/anchor_churn/churn.md`) and the F1 canary (`canary-gaps.md`).*

Both proposals keep the property A6 gates on: an edit re-keys nothing outside the scope it touches (A6 (a) = 0 on all 15 edit pairs). They change how much churn there is **inside** an edited scope, and whether two front ends agree.

## P1. Synthesized nodes do not take an ordinal

**Problem.** Statement and expression ordinals count every node, including the ones a front end makes up:
- the SV front end adds a return variable
- zdc adds `pass` for an empty branch
- the two front ends insert different casts

So the same source logic gets different anchors. In the GCD canary, SV has 59 anchors and zdc 46, and only 14 are shared.

**Proposal.**
- A front end marks each node it synthesizes, using the existing `provenance` field: `provenance="synth:<reason>"`, for example `synth:return-var` or `synth:cast`.
- `assign_anchors` skips marked nodes when it counts ordinals.
- A marked node gets a qualified anchor on its nearest unmarked ancestor or sibling: `<anchor>@synth:<reason>[:<k>]`.
- Casts are anchored on the expression they wrap: `…e7@cast`.

**Effect.**
- Anchors match across front ends wherever the user wrote the same thing.
- An edit that only changes which casts are needed no longer re-keys the expressions that follow it.

**Cost.**
- The ADR's grammar section and `_Assigner` change.
- Front ends need a new obligation (mark what you synthesize); "front-end obligations" in the docs would list it.
- Unmarked front ends keep working as they do today, just less neutrally.

## P2. Named locals: anchor statements that declare a name by that name

**Problem.** Statement ordinals are positional, so inserting at the head of a block re-keys every later sibling and its whole subtree:

| Edit | Re-keyed / matched |
|---|---|
| gcd, insert at head of a loop | 50 / 82 |
| gcd, insert at head of a function | 43 / 46 |
| rle encoder, insert at head of the `forever` loop | 153 / 154 |
| tail insert | 0 / 154 |
| expression change | 4 / 69 |

Process bodies make this worst: rle's whole behaviour sits in one block. Facts (schedule, timing, notes) attached to those anchors become `stale` and have to be re-derived on the next build.

**Options.**
- **(a) Keep it.** The churn stays inside the scope, which is the guarantee. Stale facts are rebuilt on the next run.
- **(b) Named locals.** A declaration statement is keyed by the variable it declares (`#v:<name>` instead of `#sN`). Other statements keep ordinals counted *since the previous named statement*: `#v:count.s2`. A head insert then re-keys only up to the next declaration.
- **(c) Content-keyed ordinals:** `#sN` plus a short hash of the statement. This is stable under inserts but breaks on any edit to the statement itself, and it makes anchors unreadable.

**Recommendation: (b).**
- It is readable and stays local.
- SV and zdc both name their locals, so it also helps P1's neutrality.
- It costs one more grammar rule and a note on shadowed names (`~N`, as for members).

I would rerun A6 after the change. The expected result is that head inserts drop from about 90% re-keyed to the share of statements before the first declaration.

## Asked of you

Accept, change or reject P1 and P2. If you accept them, both go into the ADR, `assign_anchors`, its tests and the A6 rerun before the grammar is frozen (M2).
