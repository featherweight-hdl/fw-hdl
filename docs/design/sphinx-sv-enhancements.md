# sphinx-systemverilog enhancements

Found while documenting the fw-hdl-spec API (`packages/fw-hdl-spec/docs`).
Source: `packages/sphinx-systemverilog` (fvutils/sphinx-systemverilog, editable
install; `ivpm.yaml` points at the git repo). Run its tests with the workspace
env: `direnv exec /packets/featherweight-hdl/fw-hdl-sync python -m pytest -q`
from the package dir (its own `.envrc` is not approved). Baseline at 0.6.2:
817 passed, 56 skipped.

Each item: a failing test from an fw-hdl-spec case, then the fix. No commits;
the user handles commits and the upstream PR.

| # | Item | Status |
|---|---|---|
| 1 | Native parser: a line beginning with a role is taken as a field | done: field needs whitespace after its colon, and no indent |
| 2 | Native parser: a field's continuation lines are not joined | done: multi-line field bodies, rendered indented |
| 3 | Qualifiers: `static`, `pure`, `extern`, `interface class` | done: flags were tested as strings but are ints; syntax path reads qualifier tokens; SV order in the domain. `extern` deliberately not shown |
| 4 | Parameterized classes: show `#(...)`; class parameters as members | done: listed as members only when documented; last parameter's trailing comment now kept (modules too) |
| 5 | Typedef names: signatures as written; package typedefs indexed | done: argument, return and property types as written; typedef signature is its declaration (`{ ... }` for bodies); typedefs in parameterized classes now extracted |
| 6 | Macro bodies in signatures: optional, off by default | done as config `sv_macro_body` = `short` (default, unchanged) / `constants` / `none`. Default kept: hiding `` `define WIDTH 32 `` would lose the useful case |

When all are done: rebuild `packages/fw-hdl-spec/docs` with `-W`, and undo the
comment workarounds there (role-led lines, one-line fields; README note).

**Status: all done (2026-11-15).** Suite: 857 passed, 56 skipped. The
extension's docs build with `-W`; its docs (`docs/usage/*`) and shipped skill
(`share/skills/.../references`) describe the changes, and the skill's config
reference now lists all 22 `sv_*` values (it was missing two before this work).
fw-hdl-spec workarounds removed; its docs build with `-W` (`sv_macro_body =
"none"`); `dfm run smoke` passes. Nothing committed. Not done: a CHANGELOG
entry (the repo has none) and a version bump, left for the release.
