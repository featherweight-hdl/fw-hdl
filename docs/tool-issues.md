# Issues found in the doc tools

Found while standing up these docs (2026-10-04), against sphinx-systemverilog 0.6.1
and sphinx-dv-flow 0.0.x (the copy in `packages/`). The sphinx-systemverilog items,
with root causes and the SVUnit proposal, are filed as a request in that repo:
`docs/design/svunit-and-fw-hdl-requests.md` (S-1 to S-7 are B-1, B-2, B-3, B-5, B-7,
B-6 and B-4 there; S-8 is §2). Not part of the published docs
(`conf.py` excludes this file). Each item says how these docs work around it today.

## sphinx-systemverilog

### S-1 Members of a parameterized class lose characters after non-ASCII text (bug)

A member signature sliced from the source of a **parameterized** class is shifted
by one character for each multi-byte UTF-8 character earlier in the file. It looks
like byte offsets used as character offsets. `fw_channel` renders as
`property ocal longint m_n_put;` and `function unction int size()`, because of a `§`
in a comment above it.

Repro (`p.sv`; with `S` in place of `§` it renders correctly, and a
non-parameterized class is unaffected):

```systemverilog
package p;
// A § B
class c #(type T = int);
    // doc
    local int a;
    // doc2
    function int f(); return 0; endfunction
endclass
endpackage
```

```python
extensions = ["sphinx_systemverilog"]
sv_build_units = ["p.sv"]
```

```rst
.. autosvclass:: p::c
   :members:
```

Output: `property ocal int a;` and `function unction int f()`.

Workaround: none yet. The fw-hdl sources use `§`, `—` and `→` widely in comments.

### S-2 Two signature renderings, depending on whether the class is parameterized

A parameterized class's members are rendered from source text, while a plain class's
members are rendered from the elaborated model. The two disagree:

| | parameterized (`RunLengthEncoder #(...)`) | plain (`rle_loopback`) |
|---|---|---|
| property | `property bit [W-1:0] prev_symbol = '0;` (trailing `;`, initializer) | `property fw_port#(fw_get_if#(...)) input_r` (no `;`, types resolved) |
| `static` | dropped: `function bit [N-1:0] lfsr(...)` for a `static function` | — |
| `virtual` | dropped on overrides | shown when inherited |
| constructor | `function new(string name, ...)` | `function void new(string name, ...)` (wrong: `new` has no return type) |

### S-3 An `interface class` renders as "parameterized class"

`fw_get_if`, `fw_put_if` and the other API interface classes render as
`parameterized class`, and their `pure virtual` methods are hidden unless they have a
doc comment or `:undoc-members:` is given. For an interface class the pure methods
are the whole point. Workaround: `:undoc-members:` on those directives.

### S-4 `auto` style takes SV token-pasting for a reST literal

The ``` ``literal`` ``` signal crosses lines, so two SV token-paste operators in one
comment (`` NAME``_write(...) and read(...) to NAME``_read ``) look like a reST
literal. The comment then goes through as reST, and its leading macro reference
(`` `FW_MEM_IMP(...) ``) fails with `Inline interpreted text ... without end-string`.
Workaround: `:doc-style: naturaldocs` on the macro pages, which also reflows the
macros' indented usage examples into prose (S-6).

### S-5 A banner comment becomes the next member's doc

`// --- fw_dbg_bindable ----------...` (a section divider directly above a member)
renders as that member's description. A comment that is only a rule line, or a
`--- title ---` line, could be dropped. Workaround: none; it shows on `fw_port` and
`fw_export`.

### S-6 Plain prose loses indented examples

Under the non-reST paths an indented block in a comment (a usage example, a plusarg
table) is reflowed into the surrounding paragraph, and lines that start `+opt` or
`-opt` are read by docutils as an option list, which warns. Workaround in the source: end the
lead-in with `::` so the block is a literal block under reST (done for
`fw_component_root::emit_bind_map` and `fw_dbg_console`).

### S-7 `autosvpackage :members:` is not in source order across `` `include ``s

`fw_std_pkg` includes `fw_put_if`, `fw_get_if`, `fw_get_nb_if`, `fw_reqrsp_if`,
`fw_mem_if` in that order; the package renders `fw_reqrsp_if` before `fw_get_nb_if`.
`fw_hdl_pkg` comes out thoroughly shuffled. It looks like members are sorted by
offset within their own file. Workaround: the reference pages list classes one
`autosvclass` at a time.

### S-8 Proposal: recognize SVUnit tests

`autosvmodule` on an SVUnit test module (`rle_unit_test`) renders nothing, even
with `:undoc-members:`. Each `` `SVTEST(name) `` expands to a class registered from
a function, which the extension rightly does not show. What a reader wants is the
test inventory: each test's name, the comment above its `` `SVTEST ``, the
`setup`/`teardown`, and the unit under test. These docs show the test files as
listings instead. See the summary for the value of doing this.

## sphinx-dv-flow

### D-1 `dvf:autopackage` ignores an argument

`.. dvf:autopackage:: fw.hdl.api` documents the project's root package (`fw-hdl`)
and says nothing about the argument. The way to document a plug-in package is
`:root: <path to its .dv file>`. An argument that names a package should either
select it or warn.

### D-2 The default `dvflow_examples_dir` excludes a real docs subtree

`dvflow_examples_dir` defaults to `examples` and is added to `exclude_patterns`. A
doc set with its own `examples/` section loses it, and the only sign is
`toctree contains reference to excluded document`. Workaround:
`dvflow_examples_dir = "_dvf_examples"` in `conf.py`.

### D-3 Tasks with no scope are invisible to `dvf:autopackage`

Not a defect: unscoped tasks are package-internal, and the page is empty without
`:internal:`. But `dfm` lets another package use an unscoped task, so a package can
work for years with nothing documented. The fw-hdl tasks now declare
`scope: export`. A warning when `autopackage` finds no published task would catch it.
