# Legacy split: keep the old front end on a branch, out of `main`

## User benefit

A fresh clone or work packet of fw-hdl contains only the canonical code, so an
agent (or a person) cannot build on the old front end by accident: there is
nothing there to build on. The old code stays one `git` command away for the
rare "how did we do X before?" lookup. Work that does reach for it fails fast
(missing paths, merge conflicts, a CI check) instead of quietly landing in
`src/` for a reviewer to catch later.

## §0 Status

- 2026-11-27: design drafted, nothing executed. Open decisions in §6.
- 2026-11-27: owner settled §6 (keep a minimal umbrella `pyproject.toml`; skill
  moves out of fw-hdl and is rewritten around modeling; remove `docs/reference`;
  family convention yes).
- 2026-11-27: skill home settled: fw-hdl-spec. In-flight packets (§4) are out of
  scope for this plan. All decisions settled.
- 2026-11-27: §5 step 1 inventory drafted (`legacy-split-inventory.md`: 12 keep,
  7 port, 89 legacy). `wb_initiator` found to be legacy; §2.2 corrected.
  Next: owner review of the inventory's open items.
- 2026-11-27: owner agreed the inventory recommendations (Sphinx scaffold,
  `tests/formal`, `tests/fw_tools.py`, `skills/fw-api-kit` → legacy; prune
  old-only ivpm deps). Executing §5 steps 3-8 in the working tree, no commit:
  local tag `legacy-fe-final` + branch `legacy` at 3d0d67b (not pushed); new
  minimal `pyproject.toml`, umbrella `flow.yaml`, CI rewired, `ivpm.yaml`
  pruned, `AGENTS.md`, `tools/check-no-legacy.sh`; two `docs/design` docs got
  the legacy header.
- 2026-11-27: removal staged in the index (`git rm` of `src/`, `python/`,
  `tests/`, old examples, `docs/` except `docs/design`, old skills); ignored
  leftovers (caches, rundirs, `docs/_build`) deleted; `test_wb_xtor.py` moved
  into `examples/wb_xtor/`; venv's editable `fw-hdl` reinstalled as the
  umbrella. Checks: `tools/check-no-legacy.sh` OK; `dfm run tests` at the root
  runs the 11 `wb_xtor` tests, all pass (baseline before removal: 11 pass).
  Modeling skill written at `packages/fw-hdl-spec/skills/fw-hdl/SKILL.md`
  (untracked in fw-hdl-spec). Nothing committed or pushed.
- 2026-11-27: committed and pushed. fw-hdl `main` 2df9eb9 (removal, rebased
  over b190e3e, an old-tree elab commit pushed meanwhile); branch `legacy` at
  b190e3e; tag `legacy-fe-final` at 3d0d67b (one commit short of `legacy`:
  move it?). fw-hdl-spec `main` 0163c78 (modeling skill). Planning docs
  (this file, the inventory, two `docs/design` legacy headers) left
  uncommitted by owner request.
- 2026-11-27: protection set. Forgejo: branch rule `legacy` (push allow-list
  mballance; force-push and delete blocked) + tag rule `legacy-fe-final`.
  GitHub: rulesets "legacy frozen" and "legacy-fe-final tag frozen" (update,
  delete, non-fast-forward blocked; repo admins bypass, so git-sync still
  works). git-sync: all aligned. Fresh clone of `main` + `ivpm update` +
  `dfm run tests`: 11 passed. Left: tag position (3d0d67b vs `legacy`
  b190e3e); family-convention paragraph (§6.4).
- 2026-11-27: skill follow-ups, owner decisions: (1) rt-sv only simulates; its
  `+fw_netlist` dump is conformance/diagnostic only (spec `semantics/netlist.md`
  already says so; the name misleads); lowering is fe-sv + fw-hdl/Zuspec.
  rt-sv still needs a public elaborate-and-run entry. (2) `fw_pin_bridge` out of
  the skill; revisit the concept (at best for ad-hoc non-protocol signals).
  (3) Redo fw-hdl-spec protocol docs and the fw-proto-kit/fw-hdl skills around
  fw-hdl domain crossings. Skill text for (1)/(2) edited in fw-hdl-spec,
  uncommitted.

## §1 Problem

`AGENTS.md` says `src/` and `python/fw/hdl` are historical and not to be built
on. Two packets built on them anyway:

| Packet | What it added to the old tree |
|---|---|
| fw-hdl-weave | `src/std/fw_resource.svh`; edits to `src/fw_component.svh`, `fw_clock_domain_if.svh`, `fw_event_set.svh`, `fw_reg_set.svh`; ~900 lines in `python/fw/hdl/fe/elab/`; `lower.dv`, `dfm_tasks.py` |
| fw-hdl-sv-weave | edits `src/fw_extern.svh`; new `tests/abstractor_proto/` |

Why a note isn't enough:

1. **The old tree is most of the repo.** On `main` it holds 58 files in `src/`,
   ~100 in `python/fw`, 64 of 79 Python tests, every `tests/*` sim fragment, the
   root `flow.yaml` regression, and `examples/xls`, `resp_tracker`, `rr_merge*`.
   The canonical code sits under `packages/`, which looks like third-party
   dependencies. An agent that looks for "the fw-hdl SV library" finds `src/`.
2. **The installed `fw-hdl` skill teaches the old tree.** `skills/fw-hdl/SKILL.md`
   points at `src/fw_component.svh`, `src/std/`, `src/flow.yaml` and others (about 15
   references), and ivpm puts it in every agent's context. A skill outweighs one
   paragraph in `AGENTS.md`.
3. **The namespace is shared.** The old `python/fw/hdl/fe/` and the canonical
   `packages/fw-hdl-fe-sv/python/fw/hdl/fe/sv/` are both `fw.hdl.fe.*`, and dfm
   tasks `fw.hdl.api.*`, `fw.hdl.xls.*` (old) sit next to `fw.hdl.fe.sv.Scan`
   (new). Nothing in a name tells old from new.
4. **The old tree works.** Its regression passes, so building on it looks
   productive.

The fix is to take the old tree off `main`. Better wording won't do it.

## §2 Design

### 2.1 Freeze the old tree on a branch

- Tag `legacy-fe-final` at the cut commit (the last `main` commit before the
  removal). Make a branch `legacy` from it.
- `legacy` is **frozen**: no feature work. On the remote, protect it with a ruleset
  that blocks pushes (you may push, nobody else). The tag is the stable reference;
  the branch exists so `git worktree add` and the GitHub UI work without extra
  steps.
- No history rewrite. A clone of `main` still has the old objects in its
  history, but they are not in the working tree, in `git grep`, in `ls`, or in
  what an agent explores. That is enough. Rewriting history to drop the objects
  would break every existing packet and fork, and wouldn't stop any of the
  failures in §1.

### 2.2 Remove the old tree from `main`

One commit, "Move the old front end to branch `legacy`", removes:

| Path | Why |
|---|---|
| `src/` | old SV kernel + std library |
| `python/` (all of `python/fw/hdl`, `fw_hdl.egg-info`, README) | old Python front end, lowering, XLS flow |
| `tests/` except what §2.3 keeps | old regression (sim fragments, `tests/python`, `tests/xls`, `tests/sync`, …) |
| root `flow.yaml` `tests` regression and the `src/flow.yaml` fragment | old regression entry point |
| `examples/xls`, `examples/resp_tracker`, `examples/rr_merge`, `examples/rr_merge_pipe`, `examples/counter*.sv`, `examples/cag-risc`, `examples/log` | built on old dfm tasks (`fw.hdl.api.*`, `fw.hdl.xls.*`, `fw.hdl.spl.*`) or old `src/` |
| `docs/reference/*` and `docs/methodology/*` pages that document old tasks/APIs | they describe code that is no longer on `main` |
| The old package's contents of `pyproject.toml`: `fw-hdl` CLI, `dv_flow.mgr` / `zuspec.lowering` entry points, deps on `zuspec-be-xls`, `zuspec-synth`, `pyslang`, `python/` package discovery | they exist only to install the old package. The file itself stays, cut down to the minimal umbrella package (§6.1) |

What stays on `main`: `packages/` deps via `ivpm.yaml`, `examples/wb_xtor`
(the only canonical example; `examples/wb_initiator` is built on old `src/` and
`fw.hdl.emit`, so it goes to `legacy`), `docs/design/` (design history is still
useful and isn't code), `skills/` (rewritten, §2.4), `tools/` (checked case by
case), `AGENTS.md`.

`docs/design/` stays whole even where a doc describes old-tree work. A doc that
describes how the old tree was implemented gets a one-line header: "Describes
the legacy front end (branch `legacy`)".

### 2.3 Inventory before deleting

Do the removal from an inventory, not by guessing. Step 1 of §5 makes
`docs/design/legacy-split-inventory.md`: every tracked top-level path under
`tests/`, `examples/`, `docs/reference`, `docs/methodology`, `tools/`, each marked
**legacy** (goes), **keep** (canonical, stays) or **port** (wanted on `main`, has
to move to the canonical API first). How to classify: does it import or `uses:`
anything from `fw.hdl.*` other than `fw.hdl.fe.sv` / `fw.hdl.gen`, or include
`src/`? A rough count today: 1 of 79 Python tests touches the canonical front end;
`examples/wb_xtor` is the only canonical example.

A **port** item that can't move to the canonical API yet goes to `legacy` with
everything else, plus a to-do. Never leave it on `main` "for now". Leaving things
for now is how we got here.

### 2.4 Make the skills and AGENTS.md describe only `main`

- Move the `fw-hdl` skill out of this repo into `fw-hdl-spec/skills/` (§6.2)
  and rewrite it around **modeling**: how to describe a design with the fw-hdl API (components, bundles, sync/comb, std classes),
  not how the runtime or front end implements it. No paths into `src/`,
  `fw-hdl-rt-sv` internals or lowering code. fw-hdl keeps umbrella-level skills
  only. Fix the `fw-proto-kit` skill's paths the same way.
- `AGENTS.md`: delete the "this repo's own code is the old front end"
  paragraph (no old code left to warn about) and put one line in its place:

  > The pre-2026-11 front end is frozen on branch `legacy` (tag
  > `legacy-fe-final`). Don't base work on it. To consult it, see
  > `docs/design/legacy-split.md` §3.

  An agent never meets the old code unless it goes looking.

### 2.5 Tripwires

Removing the code is the main guard: imports of `fw.hdl.lower`, `uses:
fw.hdl.api.*` and `` `include "fw_component.svh" `` all fail to resolve. On top
of that:

- **Merge conflicts.** A packet branched before the cut that edits old files gets
  modify/delete conflicts when it merges `main`. That's intended: the conflict
  forces the decision in §4.
- **CI check** `tools/check-no-legacy.sh` (also usable as a pre-commit hook), run
  on PRs to `main`. It fails if any tracked path matches `^src/` or
  `^python/fw/hdl/`, or any `flow.yaml` has `uses: fw.hdl.(api|xls|spl|report|knobs|formal|check|lower|sync)\.`.
  It's cheap and catches someone copying old files back in by hand.

## §3 Consulting the old code

The old code is for reference only. Look at it without checking it out into a packet:

```
git show legacy-fe-final:src/fw_component.svh        # one file
git grep -n fw_resource legacy-fe-final -- src python # search
git worktree add ../fw-hdl-legacy legacy-fe-final     # browse; detached, read-only by convention
```

The worktree goes **outside** the packet directory, so packet-wide search and
agents don't see it. No ivpm dep-set brings it back. A `legacy` dep-set would put it
under `packages/`, where canonical code lives, which is the same confusion in
another place.

## §4 In-flight packets on the old tree

Out of scope for this plan (owner decision, 2026-11-27): the packets handle
their own fate. The notes below are guidance only.

fw-hdl-weave and fw-hdl-sv-weave each pick one:

- **Retarget to `legacy`**: the work stays an experiment on the old front end. Rebase
  the branch onto `legacy`, merge it there (this is the one allowed kind of `legacy`
  commit, done once at cut time, or the freeze in §2.1 is relaxed for it), and
  record the idea as a to-do to re-do it on the canonical packages.
- **Port**: redo the change in fw-hdl-rt-sv / fw-hdl-spec / fw-hdl-fe-sv
  (e.g. `fw_resource` as a std class in the spec + runtime; the elab
  timing-attribute work as fe-sv/Zuspec IR). The old-tree diff is the reference.
- **Drop**: the experiment answered its question; keep only the write-up.

Either way, the packet doesn't merge old-tree edits into `main`. The §2.5 check
enforces that.

## §5 Plan

1. Inventory (`legacy-split-inventory.md`, §2.3). Review with the owner.
2. ~~Settle §6 decisions.~~ Done 2026-11-27.
3. Tag `legacy-fe-final` and branch `legacy` at current `main`. (Owner pushes,
   and sets the ruleset.)
4. Port any **port** items that are cheap; the rest go to legacy with a to-do.
5. Removal commit on `main` (§2.2), including `pyproject.toml`, root
   `flow.yaml`, and docs headers.
6. Skills and `AGENTS.md` (§2.4).
7. `tools/check-no-legacy.sh` and CI wiring (§2.5).
8. Check: a fresh clone + `ivpm update` + the canonical examples' dfm flows run;
   `git grep -E 'src/|python/fw/hdl'` on `main` only finds this doc and the check
   script.

## §6 Decisions

1. **Root `pyproject.toml`: keep a minimal umbrella package.** fw-hdl is the
   umbrella project and needs a package of its own. Minimal means: `name =
   "fw-hdl"`, dependencies on the canonical packages (fw-hdl-spec, fw-hdl-fe-sv,
   fw-hdl-rt-sv, fw-hdl-dv) plus the test extras the examples need, and pytest
   config pointing at the examples' tests. No CLI, no `dv_flow.mgr` or
   `zuspec.lowering` entry points, and no Python code until umbrella code exists.
   `fw` and `fw.hdl` are namespace packages, so the umbrella must not add an
   `fw/hdl/__init__.py`.
2. **`fw-hdl` skill: move it out of fw-hdl and focus it on modeling (§2.4).**
   It lives in fw-hdl-spec (`skills/`): the skill teaches the modeling API,
   fw-hdl-spec owns that API, so the two change in the same PR. If a skill ever
   has to span several packages (spec + dv + proto), split it into an
   `agent-skills-fw-hdl` repo then.
3. **`docs/reference`: remove for now.** The canonical packages' docs are the
   replacement; concept pages can be rewritten there later.
4. **Family convention: yes.** Once this has been done here, add one short
   paragraph to the global agent instructions: frozen `legacy` branch + tag, hard
   removal from `main`, a tripwire check, skills that describe only `main`.
