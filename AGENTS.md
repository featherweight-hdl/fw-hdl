
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
- This repo's own code (fw-hdl: `src/`, `python/fw/hdl`) is the *old* front
  end, full of experiments that will be removed soon. It is historical and
  not canonical. Use it only for reference, and very selectively, while
  features are built out in the packages above. Don't build new examples,
  tests or features on it.
- fw-hdl is becoming the umbrella project that pulls the pieces together.
  Examples belong here (`examples/`) and are encouraged, as long as they use
  the canonical API (the packages above), not `src/` or `python/fw/hdl`.

# SystemVerilog code style
- Each class in a package gets its own .svh file that is 'included' in the parent package
- Macros go in a _macros.svh file
- A macros file is the only one with ifndef/define/endif guards

