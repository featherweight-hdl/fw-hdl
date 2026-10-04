# fw-hdl documentation

Sphinx, with MyST Markdown pages and two autodoc extensions:

* **sphinx-systemverilog** documents the SV classes, modules and macros from their
  doc comments (`reference/`, and each example's port).
* **sphinx-dv-flow** documents the fw.hdl flow tasks from their `.dv` files
  (`reference/tasks.md`).

## Build

```
packages/python/bin/sphinx-build -W -b html docs docs/_build/html
```

Then open `docs/_build/html/index.html`. `-W` keeps the build honest: a warning is
an error. Use `-E` after changing SV sources, since the SV index is cached.

The dependencies are in `ivpm.yaml` (myst-parser, sphinx-copybutton, furo,
sphinx-systemverilog, sphinx-dv-flow), and, for a docs-only environment, in
`docs/requirements.txt`. Graphviz's `dot` draws the diagrams.

## Publishing

The docs are published to `dvkit.org/featherweight-hdl/fw-hdl/`, and only by the
DVKit docs pipeline. `.forgejo/workflows/docs.yml` builds them on every push (with
`-W` and sanity checks) and uploads the HTML as the artifact
`docs-featherweight-hdl-fw-hdl`. The host side fetches it, and a run on `main` goes
live automatically; other branches are staged for review. Nothing in this repo
deploys, and nothing should: a deploy replaces the whole dvkit.org site.

The job installs `docs/requirements.txt` into a fresh Python 3.10 venv, not the
ivpm environment, because the docs need no EDA tools. Keep the two lists in step.
`dv-flow-mgr` and `sphinx-dv-flow` are pinned to commits; bump them deliberately.

The sanity checks count pages and rendered objects per section. Raise the page floor
(85 today; a good build has 98) as pages are added.

## Layout

```
index.md              the landing page
methodology/          how fw-hdl works: components, synthesis, testing, flows
examples/xls/         one page per XLS example; see below
reference/            generated: the SV library by topic, macros, modules, tasks
conf.py               the SV build units, and the README include hook
requirements.txt      the docs toolchain, for CI
tool-issues.md        defects found in the doc tools (not published)
```

## The example pages

Each `examples/xls/<name>.md` includes that example's `README.md`, so the README
stays the one place its prose lives. `conf.py` rewrites the README's relative
links as it is included: a link to another example becomes a link to its page, and
a link to a source file becomes the file's name (the page lists the source). After
the README, the page has the port's reference, generated from its doc comments, and
listings of the tests, the flow and the original DSLX.

The pages were generated once from a table (the packages, tests, flows and DSLX
files of each example). Edit them by hand from now on. A new example needs a page,
an entry in `examples/xls/index.md`'s toctree, and its `_pkg.sv` in `conf.py`'s
`_examples`.

## Doc comments

The SV sources use `sv_doc_style = "auto"`. A comment written as reStructuredText is
passed through as reST, and anything else is shown as plain prose. Two things to
know when writing one:

* an indented example under a plain comment is reflowed into the paragraph unless
  the line before it ends in `::`;
* a single backtick before a macro name (`` `fw_root_begin ``) makes the comment look
  like reST and then breaks it (tool-issues.md S-4).
