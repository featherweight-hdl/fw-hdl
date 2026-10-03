# One Model, Many Hosts — *And*, not *Or*

*Status: position and architecture, for review. This is where the discussion in
`integration-thesis.md` and `ir-primitives.md` converged.*

**Companions:**
`integration-thesis.md` (the integration argument, XLS/Bluespec/PSS survey, the SPL/HLS/CAG
model — its positioning is refined here, §9),
`ir-primitives.md` (the IR kernel sketch),
`hw-sw-interaction-patterns.md`, `actions.md`, `dynamic-coverage.md`,
`../fw-wb-dma/docs/wb_dma_operation_model.md` (a worked operation model).

---

## 0. Summary

1. **The center is not SystemVerilog or Python. It is the model.** The model is zuspec IR,
   checked into a central repository as the single source of truth. SV, Python, PSS, C —
   and whatever comes next — are **hosts**: places the model is written, executed, and
   fixed. The answer to "which language?" is *SV and Python and PSS and C*, each for the
   team that lives there.
2. **Languages are bindings.** A binding is a front end (host → IR), a back end
   (IR → idiomatic host source), a runtime library, and a published **capability
   matrix**. fw-hdl is the SV binding; zuspec-dataclasses is the Python binding. zuspec
   owns the IR, its semantics, the lowerings, and the conformance suite.
3. **Translation is honest about loss.** Hosts have different native semantics, and no
   host is a superset of another — capability is per semantic, not per language. Three
   rules govern it (§4):
   - **Shared-subset semantics flow in every direction**, including back upstream.
   - **Superset semantics do not flow upstream.**
   - **A host that lacks a semantic receives it lowered**, as a marked, read-only,
     derived region.
4. **The workflow is asymmetric, by design.** Large changes flow *down* from a component's
   primary host. Small fixes flow *up* from any host, at body granularity, through source
   maps. Fixes that cannot be lifted are kept as tracked patches. CI detects drift. The
   worst case is a once-per-program realignment, and tooling makes it routine (§5).
5. **The market is the rewriting, not the translation.** Nobody buys "convert Python to
   SV". Teams do pay to stop re-expressing the same knowledge per team — the register
   tool market (Agnisys, Semifore, SystemRDL/PeakRDL) proves it. The next layer up, the
   **operation model**, is rewritten by hand three or four times per IP block today and
   is where to lead (§8). PSS becomes one host among several, which addresses PSS's
   authoring-cost problem instead of competing with PSS tools.
6. **Synthesis is the expansion, not the opening.** SPL/HLS/CAG lowering to RTL
   (`integration-thesis.md`) remains the long-term differentiator. It is built on the
   same IR and reached after the operation-model foothold.

---

## 1. The shift

The question started as "how does fw-hdl, an SV class library, capture what XLS captures,
with better integration?" Following it through produced three corrections:

| First framing | Correction |
|---|---|
| fw-hdl is the language | The IR is the model; fw-hdl is how SV teams get in and out |
| One description, in SV | One model, written and executed in whichever host each team uses |
| Generated views are read-only | Any host can carry fixes back, within its shared subset |

The result is a **distributed model**: architects develop in Python, the DV team works in
SV classes and UVM, firmware works in C, scenario authors work in PSS — all on the same
model, with the IR reconciling them.

---

## 2. The problem being solved

Today the same behaviour is re-expressed for every team:

| Description | Language | Owner |
|---|---|---|
| architecture / performance model | Python, SystemC, C++ | architects |
| register specification | SystemRDL, IP-XACT | design + SW |
| RTL | SV | design |
| **programming sequences (operations)** | **UVM sequences, C driver, C tests, PSS** | **DV, firmware, PSS users — separately** |
| reference model | SV classes, C, Python | DV |
| scenarios | PSS, UVM virtual sequences | DV |
| coverage, assertions | SV | DV, formal |

Each row is written by hand, and the boundaries between rows are where descriptions drift.
Registers are the one row the industry has already single-sourced, and teams pay for it.
The operation row is the obvious next one:

- **OpenTitan** single-sources registers (hjson → RTL, register model, C headers), but for
  each IP maintains the operation layer by hand twice: the C device-interface functions
  (DIFs) and the UVM sequences, with chip-level C tests on top.
- **`fw-wb-dma`** shows the same thing in this workspace: `wb_dma_operation_model.md` was
  extracted from existing UVM sequences, which are then rewritten as operation calls.

---

## 3. Architecture

```
                 ┌──────────────── central repo ────────────────┐
                 │   zuspec IR (one file per component type)    │
                 │   + view headers, tracked patches, schema v  │
                 └──────▲───────────────▲───────────────▲───────┘
            lift (fe)   │ gen (be)      │               │
          ┌─────────────┴──┐   ┌────────┴───────┐   ┌───┴────────────┐
          │ Python (zdc)   │   │ SV (fw-hdl)    │   │ PSS            │  … C, cocotb
          │ runtime: zdc   │   │ runtime: fw_*  │   │ runtime: tool  │
          └────────────────┘   └────────────────┘   └────────────────┘
                 zuspec owns: IR semantics · lowerings · capability
                 matrices · conformance suite · RTL/C back ends
```

### 3.1 Bindings

| Piece | Purpose | SV (fw-hdl) | Python (zdc) | PSS |
|---|---|---|---|---|
| Front end | host → IR | `python/fw/hdl/fe` (pyslang); process bodies today | `DataModelFactory` | zuspec PSS front end |
| Back end | IR → idiomatic host source | **missing**: IR → fw-hdl classes (RTL back end exists) | `zuspec-be-py` | **missing** |
| Runtime | what generated code runs on | `fw_hdl_pkg`, `fw_std_pkg`, protocol kits; action library to build (`actions.md`) | `zuspec.dataclasses` runtime | the user's PSS tool, or zuspec |
| Capability matrix | what is native / library / lowered | to write | to write | to write |

### 3.2 What zuspec owns

The IR and its execution semantics (`ir-primitives.md` §4), the profiles, the lowerings
(including the RTL lowering in `zuspec.synth`), the RTL and C back ends, the profile
checkers (today in `zuspec-dataclasses/ir_checker/`, to move), and the conformance suite.
A binding cannot change semantics; it can only declare how it represents them.

---

## 4. Semantics, capabilities, and lossy translation

### 4.1 Capability is per semantic

No host is a superset of another. Illustrative matrix (cells to be confirmed against the
implementations):

| Semantic | PSS | Python (zdc) | SV (fw-hdl) | C |
|---|---|---|---|---|
| blocking operations over interfaces | native | native | native | native (runtime) |
| channels, fork/join, select | partial | native | native | runtime |
| constraint solving | native | library | native (`randomize`) | library |
| action inferencing, pool binding | native | library | lowered (→ library) | lowered |
| activities (seq/par/select/schedule) | native | library | lowered (→ library) | lowered |
| temporal assertions | — | lowered (monitor code) | native (SVA) | lowered |
| covergroups | native | library | native | library |
| bit-accurate arithmetic | native | library | native | native |
| unbounded ints, dynamic containers | partial | native | partial | partial |
| 4-state / X | — | — | native, **outside the IR** | — |

Legend: **native** — the host language represents it with identical semantics.
**library** — the binding's runtime implements it; still native for flow purposes.
**lowered** — represented by an equivalent or refining encoding; read-only in that host.
**outside the IR** — host-only semantics that never flow anywhere.

### 4.2 The three rules

1. **Shared-subset semantics flow in every direction.** An edit to a construct that is
   native in both the editing host and the IR lifts, lands in the IR, and regenerates into
   every host.
2. **Superset semantics do not flow upstream.** A host cannot introduce, through lifting,
   a semantic its peers lack — and a host that received a construct lowered cannot edit it
   back.
3. **The greater-capability side lowers to the lesser.** Generating a host view lowers
   every construct the host lacks, records which lowering was used (provenance), and marks
   the region.

### 4.3 Two kinds of lowering

| Kind | Effect | Example | May flow up? |
|---|---|---|---|
| **Equivalence-preserving** | form changes, behaviour does not | PSS activity → SV task with fork/join | no — the original form is lost |
| **Refining** | a choice is fixed; the behaviour set shrinks | pre-solved scenario; bound arbitration policy; one expansion of inferencing | **never** — lifting would replace a specification with one instance of it |

Refining regions are flagged distinctly; a lifter that sees an edit there refuses with a
message naming the host where the construct is native.

### 4.4 Libraries widen the shared subset

A binding's capability is its language **plus its runtime**. zuspec-dataclasses already
implements actions, pools, and activities in Python, so those are native in the Python
host. For each superset construct, a binding chooses:

- implement it in the runtime → native, editable, liftable; or
- lower it → derived, read-only.

Prefer the library where it is cheap: it enlarges the subset that can be fixed anywhere.
The fw-hdl action library is exactly this decision for SV.

### 4.5 Regions, not files

An element can sit in the shared subset while its children do not — an action whose
`body` is plain sequential code, inside an activity that relies on inferencing. Views
therefore mark **regions**, backed by the source map:

- **native region** — editable, liftable;
- **derived region** — a marker comment plus a source-map entry: *derived from X by
  lowering L; edit in a host where X is native.*

---

## 5. Workflow

### 5.1 Direction of flow

| Direction | Typical change | Mechanism |
|---|---|---|
| **Down** (main path) | large: new components, structure, behaviour | deterministic generation from the primary host's IR |
| **Up** (fixes) | small: a body, an expression, a constant, a depth | body-level lift via source maps |
| **Realign** (worst case) | accumulated divergence | per-element status report + manual resolution |

### 5.2 Mechanisms

1. **One primary host per component.** Usually Python for new design, SV for DV-owned
   components, PSS for scenarios. Edits elsewhere are fixes, not co-development.
2. **Deterministic generation.** Same IR + same plugin version → byte-identical view. Each
   view carries a header: base IR hash, plugin version, canonical-print hash.
3. **Canonical printers.** Every host has a canonical style (as gofmt/black). Law:
   `print(lift(v)) == v` for any canonical view `v`.
4. **Source maps.** The generator records view ranges → IR element IDs. A text diff of an
   edited view against its regenerated pristine copy identifies exactly which bodies
   changed; only those are lifted and replaced.
5. **Scaffold vs editable.** Declarations, ports, bindings and boilerplate are marked
   do-not-edit; structural change happens in the primary host. Bodies, constants and
   parameter values — where bugs live — stay plain and idiomatic.
6. **Lift is strict.** The lifting front end enforces the shared subset and the region
   markers, and reports violations in the host's own terms at the source line.
7. **Tracked patches.** A fix that cannot be lifted is stored as a view-level patch keyed
   by element ID and reapplied after regeneration. Fixes are never lost; divergence is a
   visible queue.
8. **CI drift check.** Regenerate every committed view and diff: none = in sync;
   explained by a tracked patch = known divergence; anything else = failure.
9. **Differential check after every upward fix.** Regenerate the other hosts and compare
   executions (channel traces per channel for latency-insensitive components; legal-set
   membership otherwise). Record the stimulus that exposed the bug as an IR scenario so the
   test flows down with the fix.
10. **Realignment report.** Per element: unchanged / changed down / changed up / changed
    both. Only the last needs a person.

---

## 6. The serialized model

- **Stable identity.** Declarations are identified by qualified path, with an explicit
  rename operation. Bodies are the merge unit; statements do not need identity. The
  existing YAML serializer (`zuspec-ir-core/serializer.py`) numbers references by
  `id(obj)`, which changes every run, and embeds Python class names — usable for
  snapshots, not as a source of truth.
- **One file per component type**, so ownership (CODEOWNERS), review and merges stay
  local.
- **Format.** Depends on who reads IR diffs:
  - if review happens in host views, the IR is machine-facing → schema-validated JSON with
    stable key order;
  - if people review the IR itself → a compact canonical text form (in the style of
    MLIR/FIRRTL/XLS IR), with JSON as its lossless machine form. Structure-only YAML with
    expression strings is the fallback hybrid. YAML alone is unreadable for behaviour and
    has typing pitfalls.
  Leaning: canonical text + JSON, because the IR diff then becomes a language-neutral
  review surface.
- **Versioning.** Schema version in every file; migrations shipped with zuspec; plugin
  version recorded in every view header.

---

## 7. Presentation

- `Doc` (leading comment, trailing comment, docstring) and `hints` on every IR node
  (`ir-primitives.md` §2). pyslang exposes comments as trivia; the Python front end needs a
  `tokenize` pass because `ast` drops comments.
- Hints are namespaced per binding (`fw.idiom: FW_PUT_IMP`, `py.decorator: zdc.proc`) and
  never semantic. Stripping them must not change behaviour — a testable invariant.
- Names: the IR keeps the source name; each back end legalizes deterministically and
  records the map for debugging.
- Comments that talk about one host ("see the FW_PUT_IMP macro") are an accepted wart.

---

## 8. Market and positioning

### 8.1 Lead with operation models

An operation model (`wb_dma_operation_model.md`) is the programming contract of an IP:
blocking operations, a requirement contract (the PSS memory primitives), configuration,
and a re-evaluation event. It maps almost directly onto the IR kernel and sits **almost
entirely in the shared subset** — so fixes from any host flow back. Its superset parts
(scenario inferencing, solver-driven composition) are authored in PSS or Python and arrive
in SV/C as derived regions, which matches ownership: scenario authors own scenarios,
integrators fix operations.

From one operation model:

| Host | Artifact | Replaces |
|---|---|---|
| SV (fw-hdl) | UVM-usable operation classes / sequences | hand-written `*_seq.svh` |
| C | operation library for firmware and C tests | hand-written driver / DIF code |
| Python | cocotb-usable operations, architecture model | ad-hoc Python models |
| PSS | a PSS model for whichever PSS tool the customer owns | hand-written PSS |

### 8.2 Who pays

1. **IP vendors** — ship an operation model with the IP, as they ship IP-XACT and register
   models today. Fewer integration support cases, faster adoption. A distribution play:
   the value grows with the number of IPs that carry a model.
2. **SoC verification and integration teams** — stop rewriting sequences, C tests and PSS
   per IP.
3. **Firmware teams** — operations from the same source, runnable against the class model
   before RTL exists.
4. **Open hardware** (OpenTitan, CHIPS Alliance, RISC-V) — adoption channel and
   credibility.

### 8.3 Relationship to PSS tools

Complementary. PSS adoption is limited by the cost of writing models and by the bespoke
realization layer. Authoring in Python or SV and emitting PSS lowers the first; generating
the realization layer from the same model removes the second. Commercial PSS tools become
consumers of the model.

### 8.4 Validation before building more

1. **Measure OpenTitan:** for two or three IPs, the operation knowledge duplicated across
   DIFs, UVM sequences and chip-level tests — lines, operations, and bugs where copies
   disagreed.
2. **Demonstrate on `fw-wb-dma`:** `dma_mmio_c` → IR → generated UVM sequences that pass
   the existing UVM tests in place of the hand-written ones, plus C, cocotb and PSS
   renderings.
3. **Interview 5–10 people** (IP vendor, SoC DV lead, firmware lead): how many times is a
   programming sequence written; what broke last time copies disagreed; would they accept
   a model shipped with IP, and in what form; do they own a PSS tool, and is it used.

### 8.5 Expansion

Once the operation model is established, the same IR carries the design-side story from
`integration-thesis.md`: SPL (explicit timing), HLS (static scheduling with real delay
models), and CAG (dynamic scheduling synthesized from activities), with the class-vs-RTL
differential check. That is the long-term differentiator against XLS-style HLS; it is not
the beachhead.

---

## 9. Changes to earlier positions

| Document | Earlier position | Now |
|---|---|---|
| `integration-thesis.md` §0, §9 | beachhead = synthesize a DMA engine | beachhead = the DMA's **operation model**; synthesis is the expansion |
| `integration-thesis.md` §1 | one description, in SV | one model, many hosts |
| earlier discussion | generated views are read-only; never lift | shared-subset regions lift; derived regions do not |
| `ir-primitives.md` §5 | bindings listed | bindings also publish capability matrices; libraries widen the shared subset |

---

## 10. What exists, what is missing

| Piece | Status |
|---|---|
| zuspec IR with actions, activities, pools, constraints, coverage | exists (heterogeneous; needs the kernel consolidation in `ir-primitives.md` §8) |
| SV → IR (fw-hdl) | exists for process bodies, registers, MMIO FSMs |
| Python → IR (zdc) | exists |
| IR → Python | `zuspec-be-py` exists |
| IR → RTL SV, IR → C | exist (`zuspec-be-sv`, `zuspec-be-sw`) |
| IR → fw-hdl SV classes | **missing — first build item** |
| IR → PSS, PSS → IR | front end in progress; back end missing |
| fw-hdl action library | sketched (`actions.md`, `cag_risc_c.svh`) |
| stable-ID serialization | **missing** (current serializer unsuitable) |
| source maps, view headers, canonical printers | **missing** |
| capability matrices | **missing** |
| profile checkers on IR | exist in zdc; move to zuspec |
| conformance / differential harness | **missing** |

---

## 11. Roadmap

| Stage | Content | Delivers |
|---|---|---|
| **M1** | Stable-ID serialization; one file per component; schema version | a source of truth that can be checked in |
| **M2** | IR → fw-hdl class back end with canonical style, headers, source maps | "develop in Python, hand SV to DV" |
| **M3** | CI drift check | divergence cannot go unnoticed |
| **M4** | `dma_mmio_c` operation model in IR → SV sequences passing existing UVM tests; C rendering | the market demo, first half |
| **M5** | Body-level lift via source maps; tracked patches | fixes flow up |
| **M6** | Capability matrices + region marking; lifter enforcement | the three rules, enforced |
| **M7** | PSS back end (and front end completion) | PSS as a host; demo second half |
| **M8** | Differential execution harness across hosts | equivalence checked, not assumed |
| **M9** | Realignment report | worst case made routine |
| **M10+** | Synthesis expansion per `integration-thesis.md` §11 | the design-side story |

M1–M3 are useful immediately. M4 is the external proof point and should not wait for M5–M9.

---

## 12. Risks

| Risk | Mitigation |
|---|---|
| A permissive lifter lets host-specific behaviour (SV scheduling order, X semantics) leak into the IR | strict lifting, outside-IR classification, differential checks |
| Capability claims drift from reality | conformance tests per (binding, construct) claimed native |
| Generated host code is unidiomatic and teams refuse it | canonical style owned with each host's users; hints for idioms |
| The IR keeps growing front-end-specific encodings | kernel consolidation; one encoding per concept; interchange vs pass IR split |
| Too many hosts too early | SV + Python + C first; PSS at M7 |
| The operation-model market is narrower than hoped | validate (§8.4) before M7; the synthesis expansion remains |

---

## 13. Open questions

| # | Question |
|---|---|
| Q1 | Are host views committed (alongside the IR, or in team repos), or generated on demand only? Leaning: on demand, with a CI check on any that are committed. |
| Q2 | Are tests and scenarios part of the model, so a fix arrives upstream with the test that exposed it? Leaning: yes, as IR scenarios. |
| Q3 | Who owns each host's canonical style? |
| Q4 | Is an interface-method `Call` the IR primitive, with `Channel` a standard interface — or the reverse? (`ir-primitives.md` Q1) |
| Q5 | Canonical text + JSON, or JSON only? Depends on Q1 and on who reviews IR diffs. |
| Q6 | Which superset constructs does the fw-hdl runtime implement natively (widening the shared subset), and which stay lowered? |
| Q7 | Where does the realization layer of an operation model live — in the model, or per host? |
