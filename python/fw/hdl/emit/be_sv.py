"""Render RTL-level :mod:`zuspec.ir.core` IR to Verilog via ``zuspec.be.sv``.

A thin wrapper: the RTL ``Context`` produced by ``lower`` is exactly what
``SVGenerator.generate`` consumes (DESIGN §9.1).  No emitter logic lives here —
any gap is fixed upstream in ``zuspec-be-sv`` (DESIGN §7.2).
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Optional

import zuspec.ir.core as ir
from zuspec.be.sv import SVGenerator


def emit_sv(ctxt: ir.Context, *, top: Optional[str] = None,
            out_dir: Optional[str] = None) -> str:
    """Emit SystemVerilog text for the (single-module) RTL *ctxt*.

    Returns the generated SV as a string.  When *out_dir* is given the ``.sv``
    files are written there; otherwise a temp dir is used and the text returned.
    """
    target = Path(out_dir) if out_dir else Path(tempfile.mkdtemp())
    target.mkdir(parents=True, exist_ok=True)
    files = SVGenerator(target).generate(ctxt)
    text = "\n".join(f.read_text() for f in files)
    if top:
        # be-sv names the module after the component; honour an explicit override.
        text = _retop(text, [d.name for d in ctxt.type_m.values()
                             if isinstance(d, ir.DataTypeComponent)], top)
    return text


def _retop(text: str, comp_names, top: str) -> str:
    for name in comp_names:
        if name != top:
            text = text.replace(f"module {name}(", f"module {top}(", 1)
            text = text.replace(f"module {name} (", f"module {top} (", 1)
    return text
