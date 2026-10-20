"""Elaborate-then-lower, end to end: SV design -> Verilog netlist.

    parse -> elaborate (interp) -> translate (processes) -> structure
          -> zuspec.synth.proc.lower -> optimize -> emit_verilog
"""
from __future__ import annotations

import dataclasses as dc
from typing import Dict, List, Optional

from ...config import FlowConfig
from ...errors import ErrorReporter
from ..parser import Parser
from .entry import elaborate
from .interp import ElabError
from .structure import build_structure
from .translate import translate


@dc.dataclass
class LowerResult:
    verilog: str
    module: str
    report: List[str]
    leaf_modules: List[str]


def lower_design(files: List[str], top: str, *, incdirs: Optional[List[str]] = None,
                 defines: Optional[Dict[str, str]] = None, module: Optional[str] = None,
                 encoding: str = "binary", optimize: bool = True) -> LowerResult:
    from zuspec.synth.proc.emit import emit_verilog
    from zuspec.synth.proc.lower import LowerOptions, lower
    from zuspec.synth.proc.lower import optimize as opt_pass

    defs = {"FW_TRACE_OFF": "1"}
    defs.update(defines or {})
    cfg = FlowConfig(incdirs=list(incdirs or []), defines=defs, top_module=top)
    rep = ErrorReporter()
    p = Parser(cfg, rep)
    if not p.parse(files):
        msgs = "\n".join(str(x) for x in rep.errors()[:20])
        raise ElabError(f"parse failed:\n{msgs}")
    elab = elaborate(p.compilation, top)
    d, notes = translate(elab)
    build_structure(elab, d)
    if module:
        d.name = module
    nl = lower(d, LowerOptions(encoding=encoding))
    if optimize:
        nl = opt_pass(nl)
    report = list(notes) + list(elab.interp.warnings) + list(nl.report)
    return LowerResult(verilog=emit_verilog(nl), module=d.name, report=report,
                       leaf_modules=sorted(d.leaf_defs))

