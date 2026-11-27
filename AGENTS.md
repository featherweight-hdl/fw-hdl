
# Environment
Managed by direnv. Use the following to run commands properly:
```
% direnv exec . <command>
```

# Relationship to Zuspec
- fw-hdl is just a front-end
- Prefer representing something in Zuspec to directly in fw-hdl
- Prefer performing a manipulation on Zuspec IR to writing bespoke code in fw-hdl

# Where the canonical code lives
- `packages/fw-hdl-spec`: the canonical API.
- `packages/fw-hdl-rt-sv`: the canonical SV runtime.
- `packages/fw-hdl-fe-sv`: the compile (static-analysis) front end.
- `packages/fw-hdl-dv`: the DV library (only started).
- fw-hdl is the umbrella project that pulls the pieces together. Examples
  belong here (`examples/`) and are encouraged; they use the packages above.
- The pre-2026-11 front end is frozen on branch `legacy` (tag
  `legacy-fe-final`). Don't base work on it. Consult it without checking it
  out into a packet: `git show legacy-fe-final:<path>`,
  `git grep <pat> legacy-fe-final -- src python`, or a worktree outside the
  packet directory (`git worktree add ../fw-hdl-legacy legacy-fe-final`).

# SystemVerilog code style
- Each class in a package gets its own .svh file that is 'included' in the parent package
- Macros go in a _macros.svh file
- A macros file is the only one with ifndef/define/endif guards

