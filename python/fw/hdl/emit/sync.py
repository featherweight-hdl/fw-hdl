"""Emit sync classes (``step()``/``comb()``) as Verilog modules, one per class.

The top is a module that declares one variable per specialization::

    module rung1_emit_top;
        import fw_std_pkg::*;
        fw_rv_slice #(bit [36:0]) fw_rv_slice_w37;
    endmodule

Each variable becomes a module named after the variable: front end
:func:`fw.hdl.fe.elab.sync.sync_component` to IR, then be-sv
(:func:`fw.hdl.emit.be_sv.emit_sv`). A variable whose class has a member
with a pin preset (``(* fw_pins = "s_axi_" *)``) also gets a pin shell module
``<var>_pins`` (:mod:`fw.hdl.emit.pins`). A class with neither ``step()`` nor
``comb()`` is a composite: it is elaborated statically
(:func:`fw.hdl.fe.elab.hier.elaborate_tree`) and emitted with its children's
modules (:func:`fw.hdl.fe.elab.sync_tree.composite_components`). The ``fw.hdl.sync.Emit`` dfm task wraps
:func:`emit_sync`.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import zuspec.ir.core as ir
from pyslang import ast

from fw.hdl.config import FlowConfig
from fw.hdl.errors import ErrorReporter
from fw.hdl.fe.elab import hier
from fw.hdl.fe.elab.sync import SyncElabError, _sub, find_class_var, sync_component
from fw.hdl.fe.elab.sync_tree import composite_components
from fw.hdl.fe.parser import Parser

from .be_sv import emit_sv
from .pins import pin_shell


def class_vars(compilation, module: str) -> List[str]:
    """The class-typed variables of top module ``module``, in declaration order."""
    for top in compilation.getRoot().topInstances:
        if top.name == module:
            return [m.name for m in top.body if m.kind == ast.SymbolKind.Variable
                    and m.type.canonicalType.kind == ast.SymbolKind.ClassType]
    raise SyncElabError(f"no top module {module}")


def emit_sync(files: List[str], top: str, *, incdirs: Optional[List[str]] = None,
              defines: Optional[Dict[str, str]] = None,
              vars: Optional[List[str]] = None) -> Dict[str, str]:
    """Parse ``files`` and emit each class variable of ``top`` (or only
    ``vars``). Returns ``{module name: SystemVerilog text}``, with a
    ``<var>_pins`` shell where the class has pin presets."""
    defs = {"FW_TRACE_OFF": "1"}
    defs.update(defines or {})
    rep = ErrorReporter()
    p = Parser(FlowConfig(incdirs=list(incdirs or []), defines=defs, top_module=top), rep)
    if not p.parse(list(files), include_root=False):
        raise SyncElabError("parse failed: " + "; ".join(str(e) for e in rep.errors()[:5]))
    names = list(vars) if vars else class_vars(p.compilation, top)
    if not names:
        raise SyncElabError(f"{top}: no class variables to emit")
    out = {}
    for var in names:
        ct = find_class_var(p.compilation, top, var)
        if _sub(ct, "step") is None and _sub(ct, "comb") is None:
            # A composite: its children's modules, then the composite.
            tree = hier.elaborate_tree(p.compilation, ct, var)
            out[var] = emit_sv(ir.Context(type_m=composite_components(tree)))
            continue
        comp = sync_component(ct, var)
        out[var] = emit_sv(ir.Context(type_m={var: comp}))
        shell = pin_shell(ct, comp, var)
        if shell is not None:
            out[f"{var}_pins"] = shell
    return out
