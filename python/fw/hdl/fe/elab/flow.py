"""Elaborate-then-lower, end to end: SV design -> Verilog netlist.

    parse -> elaborate (interp) -> translate (processes) -> structure
          -> zuspec.synth.proc.sched (an engine) -> zuspec.synth.proc.lower
          -> optimize -> emit_verilog
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
from zuspec.synth.proc import ir as P  # noqa: F401  (types in annotations)


@dc.dataclass
class LowerResult:
    verilog: str
    module: str
    report: List[str]
    leaf_modules: List[str]
    # zuspec.synth.proc.timing.TimingReport, when lower_design(timing=...)
    timing: object = None
    # the schedule as source (lower_design(emit_sched=True)): an SV package,
    # and its name (emit_sched)
    sched: Optional[str] = None
    sched_pkg: str = ""


@dc.dataclass
class ElabStages:
    """The front end's output, before lowering: the elaboration and the
    translated, structured ``zuspec.synth.proc.ir`` Design."""
    elab: object
    design: object
    notes: List[str]
    parser: Parser


def elab_design(files: List[str], top: str, *, incdirs: Optional[List[str]] = None,
                defines: Optional[Dict[str, str]] = None,
                module: Optional[str] = None, keep_loops: bool = False) -> ElabStages:
    """parse -> elaborate -> translate -> structure (the stages before lower).
    ``keep_loops``: keep static non-blocking loops as loops (``P.Loop.trip``)
    for an engine; ``zuspec.synth.proc.unroll.unroll_loops`` unrolls them."""
    defs = {"FW_TRACE_OFF": "1"}
    defs.update(defines or {})
    cfg = FlowConfig(incdirs=list(incdirs or []), defines=defs, top_module=top)
    rep = ErrorReporter()
    p = Parser(cfg, rep)
    if not p.parse(files):
        msgs = "\n".join(str(x) for x in rep.errors()[:20])
        raise ElabError(f"parse failed:\n{msgs}")
    elab = elaborate(p.compilation, top)
    d, notes = translate(elab, keep_loops=keep_loops)
    build_structure(elab, d)
    if module:
        d.name = module
    return ElabStages(elab=elab, design=d, notes=list(notes), parser=p)


def lower_design(files: List[str], top: str, *, incdirs: Optional[List[str]] = None,
                 defines: Optional[Dict[str, str]] = None, module: Optional[str] = None,
                 encoding: str = "binary", optimize: bool = True,
                 options: Optional[Dict[str, object]] = None,
                 timing: Optional[Dict[str, object]] = None,
                 schedule: str = "as-written", emit_sched: bool = False) -> LowerResult:
    """``options``: extra :class:`zuspec.synth.proc.lower.LowerOptions` fields,
    and ``emit``: ``flat`` (one next-state term per register) or
    ``structured`` (each process as clocked blocks in its source's
    structure; :mod:`zuspec.synth.proc.structured`).

    ``schedule``: the engine (``zuspec.synth.proc.sched``) that places the
    untimed code in cycles; ``as-written`` runs it as written. ``delay``
    takes ``timing``'s model, period, wire and margin for any its spec
    doesn't give, and adds its report (``delay: ...`` lines).

    ``keep_loops`` (default on): translate keeps static non-blocking loops as
    loops, for the engine; off, translate unrolls them itself.

    ``emit_sched``: also write the schedule as source (``LowerResult.sched``,
    see :func:`emit_sched`).

    ``timing``: run the timing analysis (:mod:`zuspec.synth.proc.timing`) on
    the optimized netlist. Keys: ``model`` (a built-in delay model name or a
    JSON file), and optionally ``period`` (ns; sets the slack), ``wire`` and
    ``margin`` (ps; override the model's)."""
    from zuspec.synth.proc.emit import emit_verilog
    from zuspec.synth.proc.structured import emit_structured
    from zuspec.synth.proc.lower import LowerOptions, lower
    from zuspec.synth.proc.lower import optimize as opt_pass
    from zuspec.synth.proc import sched

    options = dict(options or {})
    keep = bool(options.pop("keep_loops", True))
    st = elab_design(files, top, incdirs=incdirs, defines=defines, module=module,
                     keep_loops=keep)
    engine, eopts = sched.parse_spec(schedule or "as-written")
    if engine == "delay":
        # the delay engine takes the timing analysis's model and period
        # unless the spec gives its own
        t = timing or {}
        for k, tk in (("model", "model"), ("period", "period"), ("wire", "wire"),
                      ("margin", "margin")):
            if k not in eopts and t.get(tk) not in (None, "", 0):
                eopts[k] = t[tk]
        if "period" not in eopts and "seed" in eopts:
            eopts["period"] = eopts.pop("seed")
        # the budget loop lowers as this flow does
        eopts["lower"] = LowerOptions(encoding=encoding, **{
            k: v for k, v in options.items() if k != "emit"})
    elab, d, notes = st.elab, sched.schedule(st.design, engine, eopts or None), st.notes
    if engine == "delay":
        from zuspec.synth.proc.sched.delay import DelayEngine
        notes = list(notes) + (DelayEngine.last.lines() if DelayEngine.last else [])
    style = options.pop("emit", "flat")
    if style not in ("flat", "structured"):
        raise ValueError(f"emit={style}: flat or structured")
    nl = lower(d, LowerOptions(encoding=encoding, **options))
    if optimize:
        nl = opt_pass(nl)
    report = list(notes) + list(elab.interp.warnings) + list(nl.report)
    trep = None
    if timing and timing.get("model"):
        trep = _timing(nl, timing)
        report += trep.lines()
    text = emit_structured(nl) if style == "structured" else emit_verilog(nl)
    res = LowerResult(verilog=text, module=d.name, report=report,
                      leaf_modules=sorted(st.design.leaf_defs), timing=trep)
    if emit_sched:
        res.sched_pkg, res.sched = emit_sched_pkg(st.design, d, name=f"{top}_sched_pkg")
    return res


def emit_sched_pkg(front: "P.Design", sched_d: "P.Design", name: str = ""):
    """The schedule ``sched_d`` (an engine's output for the front end's
    ``front``) as source: an SV package ``name`` (default
    ``<design>_sched_pkg``; ``lower_design`` names it after the design top,
    whatever the netlist module is called) with, per process of class code,
    ``<cls>_sched extends <cls>``, which drops in for ``<cls>``
    (zuspec.synth.proc.emit_src). Returns (package name, text)."""
    from zuspec.synth.proc.emit_src import Ctor, emit_class
    src = getattr(front, "class_src", {})
    name = name or f"{sched_d.name}_sched_pkg"
    pkgs: List[str] = []
    classes: Dict[str, str] = {}
    for p in sched_d.procs:
        cs = src.get(p.name)
        if cs is None:
            continue
        cls = p.task.rsplit(".", 1)[0]
        if cls in classes:
            raise ElabError(f"{p.name}: a second process of class {cls}; one emitted "
                            "class per source class")
        classes[cls] = emit_class(sched_d, p.name, ctor=Ctor(list(cs.ctor)))
        if cs.package and cs.package not in pkgs:
            pkgs.append(cs.package)
    lines = [f"// The {sched_d.scheduled or 'as-written'} schedule of {sched_d.name} as "
             "source (fw-hdl lower, emit_sched).",
             "// Each class extends the source class and drops in for it: an edge is",
             "// tick(1), a call the source made is that call, a fork is a fork.",
             f"package {name};", "    import fw_hdl_pkg::*;"]
    lines += [f"    import {pk}::*;" for pk in pkgs]
    for cls in sorted(classes):
        lines.append("")
        lines += ["    " + l if l else "" for l in classes[cls].rstrip("\n").split("\n")]
    lines.append("endpackage")
    return name, "\n".join(lines) + "\n"


def _timing(nl, spec: Dict[str, object]):
    from zuspec.synth.proc.delay import DelayModel
    from zuspec.synth.proc.timing import analyze
    m = DelayModel.load(str(spec["model"]))
    kw = {k: float(spec[k]) for k in ("wire", "margin") if spec.get(k) not in (None, "", 0)}
    if kw:
        m = m.with_(**kw)
    period = spec.get("period")
    scale = 1000.0 if m.units == "ps" else 1.0          # period is in ns
    return analyze(nl, m, period=float(period) * scale if period else None)

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
    with other options: python -m fw.hdl.fe.elab.flow <json> -o out.v [-O k=v,...]
    [--delay-model M --period NS --wire PS] (writes out.v.timing, out.v.timing.json)"""
    import argparse
    import json
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("-O", "--options", default="")
    ap.add_argument("--encoding", default=None)
    ap.add_argument("--schedule", default=None, help="the engine (default: the saved one)")
    ap.add_argument("--delay-model", default="", help="timing analysis: model name or file")
    ap.add_argument("--period", type=float, default=0, help="timing analysis: clock period, ns")
    ap.add_argument("--wire", type=float, default=0, help="timing analysis: wire per hop, ps")
    a = ap.parse_args(argv)
    j = json.load(open(a.inputs))
    opts = dict(j.get("options", {}))
    opts.update(parse_options(a.options))
    enc = a.encoding or opts.pop("encoding", None) or j.get("encoding", "binary")
    res = lower_design(j["files"], j["top"], incdirs=j["incdirs"], defines=j["defines"],
                       module=j.get("module"), encoding=enc, options=opts,
                       timing={"model": a.delay_model, "period": a.period or None,
                               "wire": a.wire or None},
                       schedule=a.schedule or j.get("schedule") or "as-written")
    with open(a.output, "w") as f:
        f.write(res.verilog)
    with open(a.output + ".report", "w") as f:
        f.write("\n".join(res.report) + "\n")
    if res.timing is not None:
        with open(a.output + ".timing", "w") as f:
            f.write("\n".join(res.timing.detail()) + "\n")
        with open(a.output + ".timing.json", "w") as f:
            json.dump(res.timing.to_json(), f, indent=1)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
