# Sphinx configuration for the fw-hdl documentation.
#
# Build: packages/python/bin/sphinx-build -W -b html docs docs/_build/html
# (see docs/README.md).

import os
import re

_here = os.path.dirname(os.path.abspath(__file__))
_root = os.path.dirname(_here)


def _r(*p):
    return os.path.join(_root, *p)


# -- Project information -----------------------------------------------------

project = "fw-hdl"
copyright = "2026, Featherweight-HDL"
author = "Featherweight-HDL"
release = "0.1.0"

# -- General configuration ---------------------------------------------------

extensions = [
    "myst_parser",
    "sphinx_copybutton",
    "sphinx_systemverilog",
    "sphinx_dv_flow",
]

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "fieldlist",
]
myst_heading_anchors = 3

templates_path = ["_templates"]
exclude_patterns = ["_build", "README.md", "tool-issues.md", "Thumbs.db", ".DS_Store"]

# -- SystemVerilog (sphinx-systemverilog) ------------------------------------
#
# Explicit build units, not directory scans: the .svh files are fragments of
# fw_hdl_pkg/fw_std_pkg and do not parse alone (the two macro files are the
# exception). fw_root.sv is left out: elaborated with its default parameter
# (Tbind=int) it does not type-check, so reference/rtl.md documents it by hand. The examples' *_unit_test.sv
# files are left out; they import API packages that the flows generate (and
# the docs show them as listings).

_examples = [
    "adler32/adler32_pkg.sv",
    "aes/aes_pkg.sv",
    "aes_ctr/aes_ctr_pkg.sv",
    "crc32/crc32_pkg.sv",
    "fir_dot/fir_dot_pkg.sv",
    "gcd/gcd_pkg.sv",
    "idct_chen/idct_chen_pkg.sv",
    "lfsr/lfsr_pkg.sv",
    "lfsr/lfsr_proc_pkg.sv",
    "prefix_sum/prefix_sum_pkg.sv",
    "rle/rle_pkg.sv",
    "sha256/sha256_pkg.sv",
]

sv_build_units = [
    _r("src", "fw_clock_xtor_if.sv"),
    _r("src", "fw_clock_period_xtor_if.sv"),
    _r("src", "std", "fw_put_xtor_if.sv"),
    _r("src", "fw_hdl_pkg.sv"),
    _r("src", "fw_hdl_macros.svh"),
    _r("src", "std", "fw_std_macros.svh"),
    _r("src", "std", "fw_std_pkg.sv"),
    _r("src", "rtl", "fw_rv_fifo.sv"),
    _r("examples", "xls", "common", "xls_std_pkg.sv"),
] + [_r("examples", "xls", e) for e in _examples]

sv_include_dirs = [_r("src"), _r("src", "std")]

# The source comments are a mix of prose and reST; "auto" passes reST through
# and escapes plain prose.
sv_doc_style = "auto"

# fw-hdl's declaration macros generate members worth reading; document them.
sv_ignore_macro_content = []

# -- dv-flow tasks (sphinx-dv-flow) ------------------------------------------

# The task packages' doc: prose is Markdown (dfm show reads it too).
dvflow_doc_format = "markdown"
dvflow_diagram_backend = "graphviz"
# Its default examples dir, "examples", would exclude the XLS example pages.
dvflow_examples_dir = "_dvf_examples"

# -- Options for HTML output -------------------------------------------------

html_theme = "furo"
html_title = "fw-hdl"
html_static_path = ["_static"]

highlight_language = "text"
pygments_style = "friendly"
pygments_dark_style = "monokai"

# Pygments' SV lexer cannot tokenize every compiler-directive backtick.
suppress_warnings = ["misc.highlighting_failure"]


# -- Including the example READMEs -------------------------------------------
#
# Each example's README.md is the prose of its page, included as is. Links in
# a README are relative to its own directory: a link to another example or to
# RESULTS.md becomes a link to that page; a link to a source file becomes its
# name as a literal (the page shows the source itself).

_EX = _r("examples", "xls")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")


def _rewrite_link(m, srcdir):
    text, target = m.group(1), m.group(2)
    if re.match(r"^[a-z]+://", target) or target.startswith("#"):
        return m.group(0)
    path = os.path.normpath(os.path.join(srcdir, target.split("#")[0]))
    rel = os.path.relpath(path, _EX)
    if rel.startswith(".."):
        return text
    # docs/examples/xls/<page> is reached from the including page, which sits
    # at docs/examples/xls/<name>.md: link by document name.
    if rel == "RESULTS.md":
        return "[%s](results.md)" % text
    if rel == "README.md":
        return "[%s](index.md)" % text
    parts = rel.split(os.sep)
    if len(parts) == 1 and os.path.isdir(path):
        return "[%s](%s.md)" % (text, parts[0])
    if len(parts) == 2 and parts[1] == "README.md":
        return "[%s](%s.md)" % (text, parts[0])
    if text.startswith("`"):
        return text
    return "%s (`%s`)" % (text, rel) if text != rel else "`%s`" % rel


def _include_read(app, relative_path, parent_docname, content):
    p = os.path.normpath(os.path.join(app.srcdir, str(relative_path)))
    if not p.startswith(_EX + os.sep) or not p.endswith(".md"):
        return
    srcdir = os.path.dirname(p)
    content[0] = _LINK.sub(lambda m: _rewrite_link(m, srcdir), content[0])


def setup(app):
    app.connect("include-read", _include_read)
