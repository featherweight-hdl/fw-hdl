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
                 encoding: str = "binary", optimize: bool = True,
                 options: Optional[Dict[str, object]] = None) -> LowerResult:
    """``options``: extra :class:`zuspec.synth.proc.lower.LowerOptions` fields,
    and ``emit``: ``flat`` (one next-state term per register) or
    ``structured`` (each process as clocked blocks in its source's
    structure; :mod:`zuspec.synth.proc.structured`)."""
    from zuspec.synth.proc.emit import emit_verilog
    from zuspec.synth.proc.structured import emit_structured
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
    options = dict(options or {})
    style = options.pop("emit", "flat")
    if style not in ("flat", "structured"):
        raise ValueError(f"emit={style}: flat or structured")
    nl = lower(d, LowerOptions(encoding=encoding, **options))
    if optimize:
        nl = opt_pass(nl)
    report = list(notes) + list(elab.interp.warnings) + list(nl.report)
    text = emit_structured(nl) if style == "structured" else emit_verilog(nl)
    return LowerResult(verilog=text, module=d.name, report=report,
                       leaf_modules=sorted(d.leaf_defs))



def parse_options(text: str) -> Dict[str, object]:
    """'a=1,b=onehot' -> {'a': True, 'b': 'onehot'} (0/1 and true/false are bools)."""
    out: Dict[str, object] = {}
    for item in (text or "").replace(" ", "").split(","):
        if not item:
            continue
        k, _, v = item.partition("=")
        lv = v.lower()
        out[k] = True if lv in ("1", "true", "") else False if lv in ("0", "false") else v
    return out


def main(argv=None) -> int:
    """Re-run a lowering from the inputs a Lower task saved (lower_inputs.json),
    with other options: python -m fw.hdl.fe.elab.flow <json> -o out.v [-O k=v,...]"""
    import argparse
    import json
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("-O", "--options", default="")
    ap.add_argument("--encoding", default=None)
    a = ap.parse_args(argv)
    j = json.load(open(a.inputs))
    opts = dict(j.get("options", {}))
    opts.update(parse_options(a.options))
    enc = a.encoding or opts.pop("encoding", None) or j.get("encoding", "binary")
    res = lower_design(j["files"], j["top"], incdirs=j["incdirs"], defines=j["defines"],
                       module=j.get("module"), encoding=enc, options=opts)
    with open(a.output, "w") as f:
        f.write(res.verilog)
    with open(a.output + ".report", "w") as f:
        f.write("\n".join(res.report) + "\n")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
