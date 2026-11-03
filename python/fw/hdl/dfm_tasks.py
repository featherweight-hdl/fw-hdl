"""dv-flow task implementations for fw-hdl's SPL -> RTL steps (``python/flow.yaml``).

These wrap :mod:`fw.hdl.spl_flow`. They need the fw-hdl Python package
installed in the flow's environment (``python/pyproject.toml``).
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Dict, List

from dv_flow.mgr import (FileSet, SeverityE, TaskDataInput, TaskDataResult, TaskMarker,
                         TaskMarkerLoc, TaskRunCtxt)

import zuspec.ir.core as ir

from fw.hdl.config import FlowConfig
from fw.hdl.errors import ErrorReporter, FwHdlError
from fw.hdl.fe.parser import FW_LIB_FILES
from fw.hdl.xls_flow import XlsFlowError

_LIB = {os.path.realpath(f) for f in FW_LIB_FILES}
_SRC = Path(FW_LIB_FILES[0]).resolve().parent
FIFO_SV = _SRC / "rtl" / "fw_rv_fifo.sv"
VALID_CHECK_SV = _SRC / "rtl" / "fw_valid_check.sv"
XLS_FIFO_SV = _SRC / "rtl" / "fw_xls_fifo_wrapper.sv"


def _sv_inputs(input: TaskDataInput):
    files, incdirs = [], []
    for fs in getattr(input, "inputs", []) or []:
        ft = getattr(fs, "filetype", None)
        if ft in ("systemVerilogSource", "verilogSource"):
            for f in fs.files:
                p = os.path.join(fs.basedir, f)
                # the parser always adds the fw-hdl library itself
                if os.path.realpath(p) not in _LIB:
                    files.append(p)
        incdirs += [os.path.join(fs.basedir, d) for d in getattr(fs, "incdirs", []) or []]
    return list(dict.fromkeys(files)), list(dict.fromkeys(incdirs))


def _files(input: TaskDataInput, filetype: str) -> List[str]:
    return [os.path.join(fs.basedir, f) for fs in getattr(input, "inputs", []) or []
            if getattr(fs, "filetype", None) == filetype for f in fs.files]


def _lowering_errors() -> tuple:
    """The errors XLS lowering raises for a design outside the static subset.
    A task reports them as markers; anything else is a bug and propagates."""
    from zuspec.be.xls.width import StaticSubsetError
    from zuspec.be.xls.xir import XlsTypeError
    return (FwHdlError, XlsFlowError, StaticSubsetError, XlsTypeError)


def _markers(reporter: ErrorReporter, exc: Exception) -> List[TaskMarker]:
    out = []
    for d in reporter.diagnostics:
        loc = TaskMarkerLoc(path=d.file, line=d.line or -1, pos=d.column or -1) \
            if d.file else None
        out.append(TaskMarker(msg=d.message, severity=SeverityE.Error, loc=loc))
    if not out:
        # A lowering error carries its source location (ir.Loc) itself.
        where = getattr(exc, "loc", None)
        if where is not None and getattr(where, "file", None):
            out.append(TaskMarker(msg=getattr(exc, "msg", str(exc)), severity=SeverityE.Error,
                                  loc=TaskMarkerLoc(path=where.file, line=where.line or -1,
                                                    pos=where.pos or -1)))
        else:
            out.append(TaskMarker(msg=str(exc), severity=SeverityE.Error))
    return out


async def KnobsResolve(ctxt: TaskRunCtxt, input: TaskDataInput) -> TaskDataResult:
    from fw.hdl.knobs import KnobError, load
    files = _files(input, "fwKnobFile")
    if len(files) != 1:
        return TaskDataResult(status=1, changed=False, output=[], markers=[TaskMarker(
            msg=f"fw.hdl.knobs.Resolve takes exactly one fwKnobFile; got {len(files)}",
            severity=SeverityE.Error)])
    try:
        k = load(files[0])
    except KnobError as e:
        markers = []
        for line in str(e).splitlines():
            path, _, rest = line.partition(": ")
            f, _, ln = path.rpartition(":")
            loc = TaskMarkerLoc(path=f, line=int(ln)) if f and ln.isdigit() else None
            markers.append(TaskMarker(msg=rest or line, severity=SeverityE.Error, loc=loc))
        return TaskDataResult(status=1, changed=True, output=[], markers=markers)
    out = k.write(input.rundir)
    return TaskDataResult(status=0, changed=True, output=[
        FileSet(src=input.name, filetype="fwKnobs", basedir=input.rundir,
                files=[os.path.basename(out["json"])]),
        FileSet(src=input.name, filetype="systemVerilogSource", basedir=input.rundir,
                files=[os.path.basename(out["sv"])]),
        FileSet(src=input.name, filetype="xlsCodegenOptions", basedir=input.rundir,
                files=[os.path.basename(out["codegen"])])])


#: Knob flop kinds -> the spelling of XLS IR's ``chan_interface flop_kind``.
_IR_FLOP_KIND = {"none": "none", "flop": "flop", "skid": "skid", "zerolatency": "zero_latency"}


def apply_chan_flops(pkg, block: str, knobs) -> None:
    """Set each proc channel's register from the knobs (``chan_flop``)."""
    for proc in pkg.procs:
        for ch in proc.channels:
            ch.flop_kind = _IR_FLOP_KIND[knobs.chan_flop(block, ch.name, ch.direction)]


def _by_module(input: TaskDataInput, filetype: str) -> dict:
    out = {}
    for fs in getattr(input, "inputs", []) or []:
        if getattr(fs, "filetype", None) != filetype:
            continue
        mod = (getattr(fs, "params", None) or {}).get("module")
        for f in fs.files:
            m = mod or os.path.basename(f).split(".")[0]
            out[m] = os.path.join(fs.basedir, f)
    return out


async def ReportLatency(ctxt: TaskRunCtxt, input: TaskDataInput) -> TaskDataResult:
    from fw.hdl import latency
    from fw.hdl.spl_flow import Shell
    parts = _files(input, "splPartition")
    if len(parts) != 1:
        return TaskDataResult(status=1, changed=False, output=[], markers=[TaskMarker(
            msg=f"fw.hdl.report.Latency takes one splPartition; got {len(parts)}",
            severity=SeverityE.Error)])
    shell = Shell.load(parts[0])
    opt, sched = _by_module(input, "xlsOptIR"), _by_module(input, "xlsSchedule")
    sig = _by_module(input, "xlsModuleSignature")
    groups = {c["module"]: c["group"] for sh in shell.walk() for c in sh.children
              if "group" in c}
    try:
        blocks = latency.load_blocks([(m, opt[m], sched[m], sig.get(m))
                                      for m in opt if m in sched], groups)
    except (OSError, ValueError) as e:
        return TaskDataResult(status=1, changed=False, output=[], markers=[TaskMarker(
            msg=f"fw.hdl.report.Latency: {e}", severity=SeverityE.Error)])
    rep = latency.report(shell, blocks)
    out = latency.write(rep, input.rundir)
    markers = [TaskMarker(msg=n, severity=SeverityE.Warning) for n in rep.notes]
    kfiles = _files(input, "fwKnobs")
    if kfiles:
        from fw.hdl.check.contracts import postcheck
        from fw.hdl.knobs import from_resolved
        markers += [TaskMarker(msg=m, severity=SeverityE.Error)
                    for m in postcheck(rep, from_resolved(kfiles[0]))]
    status = 1 if any(m.severity == SeverityE.Error for m in markers) else 0
    return TaskDataResult(status=status, changed=True, markers=markers, output=[
        FileSet(src=input.name, filetype="fwLatencyReport", basedir=input.rundir,
                files=[os.path.basename(out["md"]), os.path.basename(out["json"])])])


async def CheckContracts(ctxt: TaskRunCtxt, input: TaskDataInput) -> TaskDataResult:
    from fw.hdl.check.contracts import precheck
    from fw.hdl.knobs import from_resolved
    from fw.hdl.spl_flow import Shell
    parts, kfiles = _files(input, "splPartition"), _files(input, "fwKnobs")
    if len(parts) != 1 or len(kfiles) != 1:
        return TaskDataResult(status=1, changed=False, output=[], markers=[TaskMarker(
            msg="fw.hdl.check.Contracts takes one splPartition and one fwKnobs",
            severity=SeverityE.Error)])
    errs = precheck(Shell.load(parts[0]), from_resolved(kfiles[0]))
    return TaskDataResult(status=1 if errs else 0, changed=True, output=[], markers=[
        TaskMarker(msg=e, severity=SeverityE.Error) for e in errs])


async def ReportPpa(ctxt: TaskRunCtxt, input: TaskDataInput) -> TaskDataResult:
    from fw.hdl import ppa
    from zuspec.be.xls.signature import signature_from_codegen
    opt, sched = _by_module(input, "xlsOptIR"), _by_module(input, "xlsSchedule")
    sigs = _by_module(input, "xlsModuleSignature")
    rows = []
    for m in sorted(opt):
        if m not in sched:
            continue
        ii = None
        if m in sigs:
            with open(sigs[m]) as f:
                ii = signature_from_codegen(f.read()).initiation_interval
        rows += ppa.load([(m, opt[m], sched[m], ii)])
    os.makedirs(input.rundir, exist_ok=True)
    with open(os.path.join(input.rundir, "xls_ppa.csv"), "w") as f:
        f.write(ppa.to_csv(rows))
    return TaskDataResult(status=0, changed=True, output=[
        FileSet(src=input.name, filetype="fwPpaReport", basedir=input.rundir,
                files=["xls_ppa.csv"])])


async def Partition(ctxt: TaskRunCtxt, input: TaskDataInput) -> TaskDataResult:
    from zuspec.be.xls.lower_proc import lower_component
    from zuspec.be.xls.printer import format_package
    from zuspec.be.xls.signature import CodegenOptions, predict_signature

    from fw.hdl.spl_flow import module_name, partition
    p = input.params
    files, incdirs = _sv_inputs(input)
    reporter = ErrorReporter()
    knobs = None
    kfiles = _files(input, "fwKnobs")
    if kfiles:
        from fw.hdl.knobs import from_resolved
        knobs = from_resolved(kfiles[0])
    extern = knobs.extern_blocks() if knobs is not None else {}
    groups = knobs.groups() if knobs is not None else {}
    try:
        part = partition(files, p.top, list(p.xls or []), FlowConfig(incdirs=incdirs), reporter,
                         extern=extern, groups=groups)
    except (FwHdlError, XlsFlowError) as e:
        return TaskDataResult(status=1, changed=True, output=[], markers=_markers(reporter, e))
    rundir = input.rundir
    os.makedirs(rundir, exist_ok=True)
    # Native children are emitted here; Integrate finds them as it finds extern
    # blocks, by the signature and files on their shell entry.
    from fw.hdl import native
    native_files = {}
    for spelling, rc in part.natives.items():
        sig, text = native.reg_child_rtl(rc)
        sv, sj = os.path.join(rundir, f"{rc.module}.sv"), os.path.join(rundir, f"{rc.module}.sig.json")
        with open(sv, "w") as f:
            f.write(text)
        sig.sources = [sv]
        ir.save_signature(sig, sj)
        native_files[spelling] = {"signature": sj, "files": [sv]}
    for sh in part.shell.walk():
        for c in sh.children:
            if c.get("engine") == "native":
                c["native"].update(native_files[c["class"]])
    part.shell.save(os.path.join(rundir, "partition.json"))
    from zuspec.be.xls.multi_proc import MULTI_PROC_FLAGS
    known = knobs.xls_blocks() + list(knobs.get("xls", "blocks", default={}) or {}) \
        if knobs is not None else []
    known_mods = {module_name(b) for b in known}
    irs, preds, markers = [], [], []
    cg_mods: Dict[str, dict] = {}

    def emit(module: str, text: str, comp) -> None:
        with open(os.path.join(rundir, f"{module}.ir"), "w") as f:
            f.write(text)
        irs.append(f"{module}.ir")
        ir.save_signature(predict_signature(comp, CodegenOptions(module_name=module)),
                          os.path.join(rundir, f"{module}.pred.json"))
        preds.append(f"{module}.pred.json")

    for spelling, comp in part.standalone().items():
        module = module_name(spelling)
        key = part.knob_key(spelling, known)
        try:
            if spelling in part.texts:
                # The registry's lowering: its channels keep their own flops.
                text = part.texts[spelling]
            else:
                pkg = lower_component(comp)
                if knobs is not None:
                    apply_chan_flops(pkg, key, knobs)
                text = format_package(pkg)
        except _lowering_errors() as e:
            markers += _markers(ErrorReporter(), e)
            continue
        emit(module, text, comp)
        # A block the knob file names by class, not by its generated module
        # (a specialization, a parameter object), gets its options here.
        if knobs is not None and module not in known_mods and key != spelling:
            cg_mods[module] = knobs.codegen_module_options(key)
    for g, entry in part.groups.items():
        module = module_name(g)
        keys = {m["name"]: part.knob_key(m["class"], known) for m in entry["members"]}
        if knobs is not None:
            for e in entry["external"]:
                comp = part.blocks[next(m["class"] for m in entry["members"]
                                        if m["name"] == e["inst"])]
                f = next(x for x in comp.fields if x.name == e["port"])
                d = "receive" if isinstance(f.datatype, ir.DataTypeGetIF) else "send"
                e["flop_kind"] = _IR_FLOP_KIND[knobs.chan_flop(keys[e["inst"]], e["port"], d)]
        try:
            text = part.group_text(g)
        except _lowering_errors() as e:
            markers += _markers(ErrorReporter(), e)
            continue
        emit(module, text, part.group_component(g))
        # One schedule per package: the members' (the knob check makes them equal).
        opts = dict(knobs.codegen_module_options(next(iter(keys.values())))) \
            if knobs is not None else {}
        opts["args"] = list(opts.get("args", [])) + MULTI_PROC_FLAGS
        cg_mods[module] = opts
    if markers:
        return TaskDataResult(status=1, changed=True, output=[], markers=markers)
    part.shell.save(os.path.join(rundir, "partition.json"))
    out = [FileSet(src=input.name, filetype="splPartition", basedir=rundir,
                   files=["partition.json"]),
           FileSet(src=input.name, filetype="xlsIR", basedir=rundir, files=irs),
           FileSet(src=input.name, filetype="blockSignaturePrediction", basedir=rundir,
                   files=preds)]
    if cg_mods:
        with open(os.path.join(rundir, "partition.codegen.json"), "w") as f:
            json.dump({"format": "xls.codegen-options", "modules": cg_mods}, f, indent=2)
        out.append(FileSet(src=input.name, filetype="xlsCodegenOptions", basedir=rundir,
                           files=["partition.codegen.json"]))
    return TaskDataResult(status=0, changed=True, output=out)


_SEV = {"error": SeverityE.Error, "warn": SeverityE.Warning}


def _boundary_markers(input: TaskDataInput, shell, sigs) -> List[TaskMarker]:
    """Boundary checks on the blocks' Verilog. ``boundary`` sets the severity of the
    loop, loopback and valid-on-ready rules; ``registered_boundaries`` that of
    the registered-both-ways rule. Knob exceptions (``island.exceptions``)
    waive the latter per channel."""
    from fw.hdl.check import boundary as B
    p = input.params
    sev_hard = getattr(p, "boundary", "error") or "error"
    sev_reg = getattr(p, "registered_boundaries", "warn") or "warn"
    if sev_hard == "off" and sev_reg == "off":
        return []
    exceptions = []
    kfiles = _files(input, "fwKnobs")
    if kfiles:
        from fw.hdl.knobs import from_resolved
        exceptions = from_resolved(kfiles[0]).exceptions()
    try:
        blocks = {c["name"]: B.block_ports(sigs[c["module"]], list(sigs[c["module"]].sources))
                  for c in shell.children if sigs[c["module"]].sources}
        found = B.check(shell, blocks, exceptions, require_registered=sev_reg != "off")
    except B.BoundaryError as e:
        return [TaskMarker(msg=f"boundary check: {e}", severity=SeverityE.Warning)]
    out = []
    for f in found:
        sev = sev_reg if f.rule == "registered" else sev_hard
        if sev != "off":
            out.append(TaskMarker(msg=f"boundary {f}", severity=_SEV[sev]))
    return out


async def Integrate(ctxt: TaskRunCtxt, input: TaskDataInput) -> TaskDataResult:
    from fw.hdl import ir_build as _b
    from fw.hdl.emit.be_sv import emit_sv
    from fw.hdl.spl_flow import Shell, extern_signatures, integrate
    shells = _files(input, "splPartition")
    if len(shells) != 1:
        return TaskDataResult(status=1, changed=False, output=[], markers=[TaskMarker(
            msg=f"Integrate needs exactly one splPartition input, got {len(shells)}",
            severity=SeverityE.Error)])
    shell = Shell.load(shells[0])
    sigs = {}
    for path in _files(input, "blockSignature"):
        s = ir.load_signature(path)
        sigs[s.name] = s
    rundir = input.rundir
    os.makedirs(rundir, exist_ok=True)
    nested = []
    try:
        sigs.update({k: v for k, v in extern_signatures(shell).items() if k not in sigs})
        top, top_sig = integrate(shell, sigs, top_name=input.params.top_name or None,
                                 nested=nested)
    except (XlsFlowError, OSError, ValueError) as e:
        return TaskDataResult(status=1, changed=True, output=[], markers=[TaskMarker(
            msg=str(e), severity=SeverityE.Error)])
    # Each structural module (innermost first, then the top) is written next
    # to the others; its sources list its own file after everything under it.
    written = []
    for comp, sig in nested + [(top, top_sig)]:
        path = os.path.join(rundir, f"{sig.name}.sv")
        with open(path, "w") as f:
            f.write(emit_sv(_b.context([comp])))
        sig.sources = _child_sources(_shell_of(shell, sig.name), sigs) + [path]
        sigs[sig.name] = sig
        written.append(path)
    markers = []
    for sh in shell.walk():
        markers += _boundary_markers(input, sh, sigs)
    if any(m.severity == SeverityE.Error for m in markers):
        return TaskDataResult(status=1, changed=True, output=[], markers=markers)
    ir.save_signature(top_sig, os.path.join(rundir, f"{top_sig.name}.sig.json"))
    # Everything a simulator or synthesis tool needs, in compile order: the
    # channel FIFO, the blocks, then the structural modules and the top.
    out = [FileSet(src=input.name, filetype="systemVerilogSource",
                   basedir=str(FIFO_SV.parent), files=[FIFO_SV.name, VALID_CHECK_SV.name, XLS_FIFO_SV.name])]
    for src in dict.fromkeys(_child_sources(shell, sigs)):
        if src in written:
            continue
        out.append(FileSet(src=input.name, filetype="systemVerilogSource",
                           basedir=os.path.dirname(src), files=[os.path.basename(src)]))
    out = list({(fs.basedir, tuple(fs.files)): fs for fs in out}.values())
    out += [FileSet(src=input.name, filetype="systemVerilogSource", basedir=rundir,
                    files=[os.path.basename(p) for p in written], params={"top": top_sig.name}),
            FileSet(src=input.name, filetype="blockSignature", basedir=rundir,
                    files=[f"{top_sig.name}.sig.json"])]
    return TaskDataResult(status=0, changed=True, output=out, markers=markers)


def _shell_of(shell, module: str):
    return next(sh for sh in shell.walk() if sh.module == module) \
        if module != shell.module else shell


def _child_sources(shell, sigs) -> List[str]:
    """Every source under *shell*'s children, innermost first."""
    out: List[str] = []
    for c in shell.children:
        if c.get("engine") == "structural":
            out += _child_sources(shell.nested(c), sigs)
        out += [s for s in sigs[c["module"]].sources if s not in out]
    return list(dict.fromkeys(out))


async def XlsIR(ctxt: TaskRunCtxt, input: TaskDataInput) -> TaskDataResult:
    """fw.hdl.xls.IR: one XLS IR package per entry of `top` -- a function or a
    component class."""
    from zuspec.be.xls import xir
    from zuspec.be.xls.lower_fn import lower_functions
    from zuspec.be.xls.lower_proc import lower_component
    from zuspec.be.xls.printer import format_package
    from zuspec.be.xls.signature import CodegenOptions, predict_signature
    from zuspec.ir.core.anchor import assign_anchors

    from fw.hdl.spl_flow import module_name
    from fw.hdl.xls_flow import _find_class, _find_functions, _parse, sv_to_component, \
        sv_to_functions
    p = input.params
    tops = list(p.top or [])
    if not tops:
        return TaskDataResult(status=1, changed=False, output=[], markers=[TaskMarker(
            msg="fw.hdl.xls.IR: `top` names no function or class", severity=SeverityE.Error)])
    files, incdirs = _sv_inputs(input)
    config = FlowConfig(incdirs=incdirs)
    rundir = input.rundir
    os.makedirs(rundir, exist_ok=True)
    irs, preds, anchor_files, markers = [], [], [], []
    for top in tops:
        reporter = ErrorReporter()
        try:
            # A function if one has that name (or path); otherwise a class.
            parser = _parse(files, config, reporter)
            try:
                _find_functions(parser, [top])
                is_fn = True
            except XlsFlowError as e:
                if "ambiguous" in str(e):
                    raise
                _find_class(parser, top)
                is_fn = False
            module = module_name(top)
            # Anchors are assigned before lowering, on the IR the front end
            # produced (phase0-plan.md D5); zuspec.xls.Overlay reads them.
            if is_fn:
                fns = sv_to_functions(files, [top], config, reporter, rename={top: module})
                anchors = assign_anchors(fns)
                pkg = xir.Package(name=module)
                lower_functions(pkg, fns)
                pkg.top = module
            else:
                comp = sv_to_component(files, top, config, reporter)
                anchors = assign_anchors([comp])
                pkg = lower_component(comp)
                ir.save_signature(predict_signature(comp, CodegenOptions(module_name=module)),
                                  os.path.join(rundir, f"{module}.pred.json"))
                preds.append(f"{module}.pred.json")
        except _lowering_errors() as e:
            markers += _markers(reporter, e)
            continue
        with open(os.path.join(rundir, f"{module}.ir"), "w") as f:
            f.write(format_package(pkg))
        irs.append(f"{module}.ir")
        anchors.save(os.path.join(rundir, f"{module}.anchors.json"))
        anchor_files.append(f"{module}.anchors.json")
    if markers:
        return TaskDataResult(status=1, changed=True, output=[], markers=markers)
    out = [FileSet(src=input.name, filetype="xlsIR", basedir=rundir, files=irs),
           FileSet(src=input.name, filetype="zuspecAnchorTable", basedir=rundir,
                   files=anchor_files)]
    if preds:
        out.append(FileSet(src=input.name, filetype="blockSignaturePrediction",
                           basedir=rundir, files=preds))
    return TaskDataResult(status=0, changed=True, output=out)


async def XlsStageTLM(ctxt: TaskRunCtxt, input: TaskDataInput) -> TaskDataResult:
    """fw.hdl.xls.StageTLM: stage-TLM classes timed by the XLS schedule."""
    from fw.hdl import stage_tlm
    p = input.params
    api, err = _one_api(input)
    if err is not None:
        return err
    scheds = {}
    for f in _files(input, "xlsSchedule"):
        with open(f) as fp:
            scheds.update(stage_tlm.parse_schedules(fp.read()))
    # An IR bundle's overlay, when there is one, is the schedule (D4).
    for f in _files(input, "zuspecIRBundle"):
        s = stage_tlm.schedule_from_bundle(os.path.dirname(f))
        scheds[s.function] = s
    missing = [f.module for f in api.functions if f.module not in scheds]
    if missing:
        return _api_error(f"StageTLM: no zuspecIRBundle or xlsSchedule for module(s) "
                          f"{missing}; run zuspec.xls.Overlay (or synth.xls.Codegen) on them")
    pkg = p.pkg_name or f"{api.name}_stage_tlm_pkg"
    clk_if = p.clk_if or f"{pkg}_clk_if"
    rundir = input.rundir
    os.makedirs(rundir, exist_ok=True)
    tables = []
    for f in api.functions:
        tables.append(f"{f.module}.stages.txt")
        with open(os.path.join(rundir, tables[-1]), "w") as fp:
            fp.write(stage_tlm.stage_table(scheds[f.module]))
    with open(os.path.join(rundir, f"{pkg}.sv"), "w") as fp:
        fp.write(stage_tlm.stage_tlm_sv(api, scheds, pkg, clk_if, list(p.imports or []),
                                        bool(p.flop_inputs), bool(p.flop_outputs)))
    return TaskDataResult(status=0, changed=True, output=[
        FileSet(src=input.name, filetype="systemVerilogSource", basedir=rundir,
                files=[f"{pkg}.sv"]),
        FileSet(src=input.name, filetype="text", basedir=rundir, files=tables)])


def _api_error(msg: str) -> TaskDataResult:
    return TaskDataResult(status=1, changed=False, output=[], markers=[TaskMarker(
        msg=msg, severity=SeverityE.Error)])


async def ApiFunctions(ctxt: TaskRunCtxt, input: TaskDataInput) -> TaskDataResult:
    """fw.hdl.api.Functions: the call API of SV functions."""
    from fw.hdl import fn_api
    from fw.hdl.spl_flow import module_name
    from fw.hdl.xls_flow import _find_functions, _parse
    p = input.params
    names = list(p.functions or [])
    if not names:
        return _api_error("fw.hdl.api.Functions: `functions` is empty")
    files, incdirs = _sv_inputs(input)
    reporter = ErrorReporter()
    try:
        parser = _parse(files, FlowConfig(incdirs=incdirs), reporter)
        subs = _find_functions(parser, names)
        name = p.name or fn_api.default_api_name([s.hierarchicalPath for s in subs])
        # The module of each function is named as fw.hdl.xls.IR names it,
        # after the entry it was given by.
        mods = {s.hierarchicalPath: module_name(n) for s, n in zip(subs, names)}
        api = fn_api.api_from_subroutines(name, subs, lambda s: mods[s.hierarchicalPath])
    except (FwHdlError, XlsFlowError, ValueError) as e:
        return TaskDataResult(status=1, changed=True, output=[], markers=_markers(reporter, e))
    api.sources = files
    rundir = input.rundir
    os.makedirs(rundir, exist_ok=True)
    with open(os.path.join(rundir, f"{api.pkg}.sv"), "w") as f:
        f.write(fn_api.api_pkg_sv(api))
    api.save(os.path.join(rundir, f"{api.name}.api.json"))
    return TaskDataResult(status=0, changed=True, output=[
        FileSet(src=input.name, filetype="systemVerilogSource", basedir=rundir,
                files=[f"{api.pkg}.sv"], attributes=[f"api={api.name}"]),
        FileSet(src=input.name, filetype="fwFnApi", basedir=rundir,
                files=[f"{api.name}.api.json"], attributes=[f"api={api.name}"])])


def _one_api(input: TaskDataInput):
    """The one API description among the inputs: a function API (fwFnApi)
    or a component API (fwCompApi)."""
    from fw.hdl import comp_api, fn_api
    fns, comps = _files(input, "fwFnApi"), _files(input, "fwCompApi")
    if len(fns) + len(comps) != 1:
        return None, _api_error(f"needs exactly one fwFnApi or fwCompApi input, got "
                                f"{len(fns) + len(comps)}")
    if fns:
        return fn_api.FnApi.load(fns[0]), None
    return comp_api.CompApiSet.load(comps[0]), None


async def ApiModelBinding(ctxt: TaskRunCtxt, input: TaskDataInput) -> TaskDataResult:
    """fw.hdl.api.ModelBinding: <api>_harness, with the SV functions answering."""
    from fw.hdl import comp_api, fn_api
    api, err = _one_api(input)
    if err:
        return err
    gen = comp_api if isinstance(api, comp_api.CompApiSet) else fn_api
    rundir = input.rundir
    os.makedirs(rundir, exist_ok=True)
    with open(os.path.join(rundir, f"{api.name}_model.sv"), "w") as f:
        f.write(gen.model_harness_sv(api))
    return TaskDataResult(status=0, changed=True, output=[
        FileSet(src=input.name, filetype="systemVerilogSource", basedir=rundir,
                files=[f"{api.name}_model.sv"], attributes=[f"harness={api.name}_harness"])])


async def ApiXlsBinding(ctxt: TaskRunCtxt, input: TaskDataInput) -> TaskDataResult:
    """fw.hdl.api.XlsBinding: <api>_harness, with the XLS modules answering."""
    from fw.hdl import comp_api, fn_api
    api, err = _one_api(input)
    if err:
        return err
    if isinstance(api, comp_api.CompApiSet):
        return _comp_xls_binding(input, api)
    mods = {}
    for path in _files(input, "xlsModuleSignature"):
        with open(path) as f:
            text = f.read()
        try:
            m = fn_api.fn_module_from_signature(text)
        except ValueError:
            continue            # a proc's signature: not this API's
        mods[m.module] = m
    missing = [f.module for f in api.functions if f.module not in mods]
    if missing:
        return _api_error(f"XlsBinding: no xlsModuleSignature for module(s) {missing}; "
                          f"run synth.xls.Codegen on fw.hdl.xls.IR's output for each function")
    try:
        text = fn_api.xls_binding_sv(api, mods, period=input.params.clock_period,
                                     reset_cycles=input.params.reset_cycles,
                                     timeout_cycles=input.params.timeout_cycles)
    except ValueError as e:
        return _api_error(str(e))
    rundir = input.rundir
    os.makedirs(rundir, exist_ok=True)
    with open(os.path.join(rundir, f"{api.name}_xls.sv"), "w") as f:
        f.write(text)
    return TaskDataResult(status=0, changed=True, output=[
        FileSet(src=input.name, filetype="systemVerilogSource", basedir=rundir,
                files=[f"{api.name}_xls.sv"], attributes=[f"harness={api.name}_harness"])])


async def ApiComponents(ctxt: TaskRunCtxt, input: TaskDataInput) -> TaskDataResult:
    """fw.hdl.api.Components: the call API of SV components (procs)."""
    from pyslang import ast
    from fw.hdl import comp_api
    from fw.hdl.spl_flow import module_name
    from fw.hdl.xls_flow import _find_class, _parse
    from fw.hdl.fe.static_mapper import StaticMapper
    p = input.params
    names = list(p.components or [])
    if not names:
        return _api_error("fw.hdl.api.Components: `components` is empty")
    files, incdirs = _sv_inputs(input)
    reporter = ErrorReporter()
    config = FlowConfig(incdirs=incdirs)
    comps = []
    try:
        parser = _parse(files, config, reporter)
        for n in names:
            cls = _find_class(parser, n)
            # A component with a run() task or a step() is a block; one
            # without is structural (it builds and connects children), whose
            # own ports the structure mapper reads.
            from fw.hdl.fe.static_mapper import find_behavior
            try:
                has_run = find_behavior(cls)[0] is not None
            except ValueError:
                has_run = True          # map_component reports it
            if has_run:
                comp = StaticMapper(config, reporter, parser.source_manager).map_component(
                    cls, spelling=n)
            else:
                from fw.hdl.fe.structure import StructureMapper
                comp = StructureMapper(config, reporter, parser.source_manager).map_structure(
                    cls, spelling=n).component
            # The package-qualified spelling: a typedef's or the class's path.
            path = [None]

            def visit(sym, n=n):
                if path[0] is None and getattr(sym, "name", None) == n and sym.kind in (
                        ast.SymbolKind.TypeAlias, ast.SymbolKind.ClassType,
                        ast.SymbolKind.GenericClassDef):
                    path[0] = sym.hierarchicalPath
                return True
            parser.get_root().visit(visit)
            sv = path[0] or n
            # A structural top is written at package scope, so a port's
            # payload is spelled as its declaration writes it (the mapper
            # gives the generic class's name, losing the specialization).
            declared = {}
            if not has_run:
                import re as _re
                for m in cls:
                    if m.kind == ast.SymbolKind.ClassProperty and m.syntax is not None:
                        t = str(getattr(m.syntax.parent, "type", "") or "").strip()
                        mt = _re.search(r"fw_(?:get|put)_if\s*#\s*\(\s*(.+?)\s*\)\s*\)$", t)
                        if mt:
                            declared[m.name] = mt.group(1)
            ports = []
            for f in comp.fields:
                if f.kind != ir.FieldKind.Port:
                    continue
                t = declared.get(f.name) or f.pragmas.get("sv_type", "")
                role = "put" if isinstance(f.datatype, ir.DataTypeGetIF) else "get"
                ports.append(comp_api.CompPort(f.name, role, t, f.datatype.element_type.bits,
                                               bool(f.pragmas.get("get_nb")),
                                               bool(f.pragmas.get("put_step"))))
            comps.append(comp_api.CompApi(n, sv, module_name(n), ports))
    except (FwHdlError, XlsFlowError, ValueError) as e:
        return TaskDataResult(status=1, changed=True, output=[], markers=_markers(reporter, e))
    pkg = comps[0].sv.split("::")[0] if "::" in comps[0].sv else comps[0].name
    api = comp_api.CompApiSet(p.name or f"{pkg}_api", comps, files)
    rundir = input.rundir
    os.makedirs(rundir, exist_ok=True)
    with open(os.path.join(rundir, f"{api.pkg}.sv"), "w") as f:
        f.write(comp_api.api_pkg_sv(api))
    api.save(os.path.join(rundir, f"{api.name}.comp.json"))
    return TaskDataResult(status=0, changed=True, output=[
        FileSet(src=input.name, filetype="systemVerilogSource", basedir=rundir,
                files=[f"{api.pkg}.sv"], attributes=[f"api={api.name}"]),
        FileSet(src=input.name, filetype="fwCompApi", basedir=rundir,
                files=[f"{api.name}.comp.json"], attributes=[f"api={api.name}"])])


def _comp_xls_binding(input: TaskDataInput, api) -> TaskDataResult:
    from zuspec.be.xls.signature import signature_from_codegen
    from fw.hdl import comp_api
    sigs = {}
    for path in _files(input, "xlsModuleSignature"):
        with open(path) as f:
            sig = signature_from_codegen(f.read())
        sigs[sig.name] = sig
    # A structural top's signature, from fw.hdl.spl.Integrate.
    for path in _files(input, "blockSignature"):
        sig = ir.load_signature(path)
        sigs[sig.name] = sig
    missing = [c.module for c in api.components if c.module not in sigs]
    if missing:
        return _api_error(f"XlsBinding: no xlsModuleSignature or blockSignature for "
                          f"module(s) {missing}; run synth.xls.Codegen on fw.hdl.xls.IR's "
                          f"output for each component, or fw.hdl.spl.Integrate for a "
                          f"structural one")
    try:
        text = comp_api.xls_binding_sv(api, sigs, period=input.params.clock_period,
                                       reset_cycles=input.params.reset_cycles,
                                       timeout_cycles=input.params.timeout_cycles)
    except ValueError as e:
        return _api_error(str(e))
    rundir = input.rundir
    os.makedirs(rundir, exist_ok=True)
    with open(os.path.join(rundir, f"{api.name}_xls.sv"), "w") as f:
        f.write(text)
    return TaskDataResult(status=0, changed=True, output=[
        FileSet(src=input.name, filetype="systemVerilogSource", basedir=rundir,
                files=[f"{api.name}_xls.sv"], attributes=[f"harness={api.name}_harness"])])


async def FormalProve(ctxt: TaskRunCtxt, input: TaskDataInput) -> TaskDataResult:
    """fw.hdl.formal.Prove: SVUnit tests proven for every input (formal-svunit.md)."""
    from fw.hdl import fn_api
    from fw.hdl.formal import prove
    from dv_flow.libhdlsim.sim_check import _case_name
    p = input.params
    gate = bool(p.gate)
    rundir = input.rundir
    os.makedirs(rundir, exist_ok=True)
    apis = _files(input, "fwFnApi")
    if len(apis) > 1:
        return _api_error(f"fw.hdl.formal.Prove: at most one fwFnApi input, got {len(apis)}")
    tests = _files(input, "svunitTest")
    if not tests:
        return _api_error("fw.hdl.formal.Prove: no svunitTest input")
    try:
        solver = prove.Solver.named(p.solver or "dv-solve", float(p.timeout))
    except FileNotFoundError as e:
        return _api_error(f"fw.hdl.formal.Prove: {e}")
    files, incdirs = _sv_inputs(input)
    incdirs += [os.path.join(fs.basedir, d) for fs in getattr(input, "inputs", []) or []
                if getattr(fs, "filetype", None) == "svunitTest"
                for d in getattr(fs, "incdirs", []) or []]
    incdirs += list(dict.fromkeys(os.path.dirname(t) for t in tests))
    cfg = FlowConfig(incdirs=list(dict.fromkeys(incdirs)))
    for d in p.defines or []:
        k, _, v = str(d).partition("=")
        cfg.defines[k] = v
    api = fn_api.FnApi.load(apis[0]) if apis else None
    t0 = time.time()
    design_ir: List[str] = []
    try:
        results = prove.prove_files(files + tests, api=api, tests=list(p.tests or []) or None,
                                    solver=solver, workdir=rundir, config=cfg,
                                    design_ir=design_ir)
    except RuntimeError as e:          # the sources do not parse
        return _api_error(f"fw.hdl.formal.Prove: {e}")
    walltime = time.time() - t0
    prove.write_results(results, Path(rundir) / "results.json")
    report = prove.report(results)
    with open(os.path.join(rundir, "formal.log"), "w") as f:
        f.write(report + "\n")

    counts = {s: sum(r.status == s for r in results)
              for s in (prove.PROVEN, prove.CEX, prove.VACUOUS, prove.UNKNOWN,
                        prove.NOT_FORMAL)}
    if counts[prove.UNKNOWN]:
        status = "error"
    elif counts[prove.CEX] or counts[prove.VACUOUS]:
        status = "fail"
    else:
        status = "pass"
    passed = status == "pass"

    sev = SeverityE.Error if (gate and not passed) else SeverityE.Info
    for r in results:
        if r.status == prove.PROVEN:
            continue
        if r.status == prove.CEX:
            path, line = r.obligation.file, r.obligation.line
        else:
            path, line = r.file, r.line
        s = SeverityE.Warning if r.status == prove.NOT_FORMAL else sev
        msg = f"{r.test}: {r.status}: {r.summary()}"
        ctxt.add_marker(TaskMarker(severity=s, msg=msg, loc=TaskMarkerLoc(path=path, line=line))
                        if path else TaskMarker(severity=s, msg=msg))

    cex = [f"{r.test}.cex.json" for r in results if r.status == prove.CEX]
    artifacts = [FileSet(src=input.name, filetype="fwFormalResults", basedir=rundir,
                         files=["results.json"]),
                 FileSet(src=input.name, filetype="simLog", basedir=rundir,
                         files=["formal.log"])]
    if cex:
        artifacts.append(FileSet(src=input.name, filetype="fwFormalCex", basedir=rundir,
                                 files=cex))
    formal = len(results) - counts[prove.NOT_FORMAL]
    stats = {f"tests_{k.replace('-', '_')}": v for k, v in counts.items()}
    stats.update({"tests_run": formal, "tests_passed": counts[prove.PROVEN],
                  "tests_failed": formal - counts[prove.PROVEN]})
    name = _case_name(input)
    tr = ctxt.mkDataItem(
        "hdlsim.TestResult", testname=p.testname or "svunit",
        sim=f"formal:{p.solver or 'dv-solve'}", status=status, passed=passed, run_status=0,
        errors=formal - counts[prove.PROVEN], warnings=counts[prove.NOT_FORMAL], fatals=0,
        seed=0, walltime_s=walltime, stats=stats, runinfo={"solver": " ".join(solver.cmd)},
        artifacts=artifacts)
    tr.name = name           # reserved by mkDataItem; see hdltest.svunit.Check
    tr.src = name
    ctxt.info(f"formal {status}: {counts[prove.PROVEN]} of {formal} tests proven"
              + (f", {counts[prove.NOT_FORMAL]} not formal" if counts[prove.NOT_FORMAL] else ""))
    output = [tr] + artifacts[:1] + artifacts[2:]
    if design_ir:
        # The design as the proofs encoded it, for synth.xls.Equiv against
        # the IR XLS optimized (formal-svunit.md §6, the first link).
        output.append(FileSet(src=input.name, filetype="xlsIR", basedir=rundir,
                              files=[os.path.basename(f) for f in design_ir],
                              attributes=["fwFormalDesign"]))
    return TaskDataResult(status=1 if (gate and not passed) else 0, changed=True,
                          output=output)


async def FormalReplay(ctxt: TaskRunCtxt, input: TaskDataInput) -> TaskDataResult:
    """fw.hdl.formal.Replay: the test files, with each counterexample's values."""
    from fw.hdl.formal import replay
    p = input.params
    tests = _files(input, "svunitTest")
    cex = _files(input, "fwFormalCex")
    if p.tests:
        want = set(p.tests)
        cex = [c for c in cex if replay.load(c)["test"] in want]
    rundir = input.rundir
    try:
        out = replay.replay_files(tests, cex, rundir)
    except (replay.ReplayError, OSError) as e:
        return _api_error(f"fw.hdl.formal.Replay: {e}")
    # Each original's directory stays on the include path, for its `includes.
    incdirs = list(dict.fromkeys(os.path.dirname(os.path.abspath(t)) for t in tests))
    output = [FileSet(src=input.name, filetype="svunitTest", basedir=rundir,
                      files=[os.path.basename(f) for f in out], incdirs=incdirs)]
    names = [replay.load(c)["test"] for c in cex]
    if names and p.filter:
        output.append(ctxt.mkDataItem(
            "hdlsim.SimRunArgs",
            plusargs=["SVUNIT_FILTER=" + ":".join(f"*.{n}" for n in names)]))
    ctxt.info(f"replay: {len(names)} counterexample(s)"
              + (f" ({', '.join(names)})" if names else ""))
    return TaskDataResult(status=0, changed=True, output=output)


async def FormalCodegenEquiv(ctxt: TaskRunCtxt, input: TaskDataInput) -> TaskDataResult:
    """fw.hdl.formal.CodegenEquiv: each XLS-generated module against its optimized IR."""
    from fw.hdl.formal import codegen_equiv as ce, prove
    p = input.params
    mods = {}
    for fs in getattr(input, "inputs", []) or []:
        ft = getattr(fs, "filetype", None)
        if ft not in ("xlsOptIR", "xlsModuleSignature", "systemVerilogSource", "verilogSource"):
            continue
        attrs = dict(a.partition("=")[::2] for a in getattr(fs, "attributes", None) or [])
        m = attrs.get("module") or (getattr(fs, "params", None) or {}).get("module")
        if not m:
            continue
        mods.setdefault(m, {}).setdefault(ft, []).extend(
            os.path.join(fs.basedir, f) for f in fs.files)
    mods = {m: d for m, d in mods.items() if "xlsOptIR" in d}
    if not mods:
        return _api_error("fw.hdl.formal.CodegenEquiv: no module (the xlsOptIR, "
                          "xlsModuleSignature and Verilog outputs of synth.xls.Codegen)")
    try:
        solver = prove.Solver.named(p.solver or "dv-solve", float(p.timeout))
    except FileNotFoundError as e:
        return _api_error(f"fw.hdl.formal.CodegenEquiv: {e}")
    rundir = Path(input.rundir)
    rundir.mkdir(parents=True, exist_ok=True)
    entries, markers, fail = [], [], False
    for m, d in sorted(mods.items()):
        ir_, sig = d["xlsOptIR"][0], (d.get("xlsModuleSignature") or [None])[0]
        verilog = d.get("systemVerilogSource", []) + d.get("verilogSource", [])
        if sig is None or not verilog:
            return _api_error(f"fw.hdl.formal.CodegenEquiv: module {m} has no "
                              f"{'signature' if sig is None else 'Verilog'}")
        r = ce.check(ir_, verilog, sig, solver, rundir)
        lat = ce.parse_signature(Path(sig).read_text()).latency
        entries.append(r.as_dict(ir_, verilog, lat))
        what = f"{m}: XLS IR vs the generated Verilog ({lat} cycles)"
        if r.verdict == ce.EQUIVALENT:
            ctxt.info(f"equivalent: {what} ({r.seconds}s)")
        elif r.verdict == ce.NOT_EQUIVALENT:
            markers.append(TaskMarker(msg=f"NOT equivalent: {what}; {r.detail}",
                                      severity=SeverityE.Error if p.gate else SeverityE.Warning))
            fail |= bool(p.gate)
        elif r.verdict == ce.ERROR:
            markers.append(TaskMarker(msg=f"cannot compare {what}: {r.detail}",
                                      severity=SeverityE.Error))
            fail = True
        else:
            markers.append(TaskMarker(msg=f"inconclusive: {what}; {r.detail}",
                                      severity=SeverityE.Error if p.require_proof
                                      else SeverityE.Warning))
            fail |= bool(p.require_proof)
    worst = ce.write_report(entries, rundir / "equiv.json")
    return TaskDataResult(status=1 if fail else 0, changed=True, markers=markers, output=[
        FileSet(src=input.name, filetype="fwCodegenEquivReport", basedir=str(rundir),
                files=["equiv.json"], attributes=[f"verdict={worst}"])])


#: The links of the chain (formal-svunit.md §6), in order: report filetype -> what it checks.
_CHAIN_LINKS = [
    ("xlsEquivReport", "XLS IR", "the proven model's IR = the IR XLS optimized"),
    ("fwCodegenEquivReport", "RTL", "the optimized IR = the Verilog XLS generated"),
    ("yosysEquivReport", "netlist", "the RTL = the netlist"),
]


def _entries(report: dict, key: str) -> List[dict]:
    return list(report.get(key) or [report])


def _real(paths) -> set:
    if isinstance(paths, str):
        paths = [paths]
    return {os.path.realpath(p) for p in paths or []}


async def FormalChain(ctxt: TaskRunCtxt, input: TaskDataInput) -> TaskDataResult:
    """fw.hdl.formal.Chain: proven at the model + equivalent at each step, as a TestResult."""
    import json
    from dv_flow.libhdlsim.sim_check import _case_name
    p = input.params
    ins = getattr(input, "inputs", []) or []
    trs = [i for i in ins if getattr(i, "type", None) == "hdlsim.TestResult"]
    if len(trs) != 1:
        return _api_error(f"fw.hdl.formal.Chain: one hdlsim.TestResult (of "
                          f"fw.hdl.formal.Prove) expected, got {len(trs)}")
    proof = trs[0]
    design = _real(f for fs in ins if getattr(fs, "filetype", None) == "xlsIR"
                   and "fwFormalDesign" in (getattr(fs, "attributes", None) or [])
                   for f in [os.path.join(fs.basedir, x) for x in fs.files])
    reports = {}
    for fs in ins:
        ft = getattr(fs, "filetype", None)
        if ft in dict((k, 0) for k, _, _ in _CHAIN_LINKS):
            if ft in reports:
                return _api_error(f"fw.hdl.formal.Chain: more than one {ft} input")
            with open(os.path.join(fs.basedir, fs.files[0])) as f:
                reports[ft] = (os.path.join(fs.basedir, fs.files[0]), json.load(f))

    rows = []        # (step, verdict, what, detail)
    pstat = getattr(proof, "status", "error")
    st = getattr(proof, "stats", {}) or {}
    rows.append(("model", "proven" if pstat == "pass" else pstat,
                 f"{st.get('tests_passed', 0)} of {st.get('tests_run', 0)} tests proven "
                 f"({getattr(proof, 'sim', 'formal')})", ""))
    broken = []
    # Each link must start where the one before it ended: the file sets connect.
    cur, cur_what = design, "the proven model's IR (fw.hdl.formal.Prove)"
    if not design:
        broken.append("Prove gave no design IR (does the test call the design through the API?)")
    for ft, step, what in _CHAIN_LINKS:
        if ft not in reports:
            continue
        path, rep = reports[ft]
        es = _entries(rep, "pairs" if ft == "xlsEquivReport" else "modules")
        nxt = set()
        for e in es:
            lhs, rhs = _real(e.get("lhs")), _real(e.get("rhs"))
            if ft == "xlsEquivReport":
                # unordered: one side is where the chain is
                if cur & lhs:
                    nxt |= rhs
                elif cur & rhs:
                    nxt |= lhs
                else:
                    broken.append(f"{ft} ({path}) compares neither side with {cur_what}")
                    nxt |= lhs | rhs        # go on from it: report one break once
            else:
                ok = cur & lhs if ft == "fwCodegenEquivReport" else \
                    (cur and cur <= lhs)    # the netlist's gold holds every module reached
                if not ok:
                    broken.append(f"{ft} ({path}) does not start from {cur_what}")
                nxt |= rhs
        cur, cur_what = nxt, f"the files {ft} ends at"
        v = rep.get("verdict", "error")
        detail = rep.get("detail") or ""
        if ft == "yosysEquivReport":
            what = f"{what} ({rep.get('target', '?')})"
        rows.append((step, v, what, detail))
    links = rows[1:]
    if not links:
        broken.append("no equivalence report (synth.xls.Equiv, fw.hdl.formal.CodegenEquiv, "
                      "synth.yosys.Equiv)")
    verdicts = [v for _, v, _, _ in links]
    if broken or pstat == "error" or any(v in ("error", "inconclusive") for v in verdicts):
        status = "error"
    elif pstat != "pass" or any(v != "equivalent" for v in verdicts):
        status = "fail"
    else:
        status = "pass"
    passed = status == "pass"

    level = p.level or (links[-1][0] if links else "model")
    if level.startswith("formal-"):         # the view's name: formal-<level>
        level = level[len("formal-"):]
    lines = [f"formal chain to level {level}: {status}", ""]
    w = max(len(r[0]) for r in rows)
    for i, (step, v, what, detail) in enumerate(rows):
        lines.append(f"  {'  ' if i == 0 else '= '}{step:<{w}}  {v:<15} {what}"
                     + (f"\n    {'':<{w}}  {'':<15} {detail}" if detail else ""))
    for b in broken:
        lines.append(f"  broken: {b}")
    text = "\n".join(lines) + "\n"
    rundir = input.rundir
    os.makedirs(rundir, exist_ok=True)
    with open(os.path.join(rundir, "chain.log"), "w") as f:
        f.write(text)
    for b in broken:
        ctxt.add_marker(TaskMarker(severity=SeverityE.Error, msg=f"chain broken: {b}"))
    for step, v, what, detail in links:
        if v != "equivalent":
            ctxt.add_marker(TaskMarker(
                severity=SeverityE.Error if p.gate else SeverityE.Warning,
                msg=f"chain link {step}: {v}: {what}" + (f"; {detail}" if detail else "")))
    artifacts = [FileSet(src=input.name, filetype="simLog", basedir=rundir, files=["chain.log"])]
    stats = {k: st.get(k, 0) for k in ("tests_run", "tests_passed", "tests_failed")}
    stats.update({"links": len(links),
                  "links_equivalent": sum(v == "equivalent" for v in verdicts)})
    tr = ctxt.mkDataItem(
        "hdlsim.TestResult", testname=p.testname or "svunit", sim="formal-chain",
        status=status, passed=passed, run_status=0,
        errors=len(broken) + sum(v != "equivalent" for v in verdicts)
        + (0 if pstat == "pass" else 1), warnings=0, fatals=0, seed=0,
        walltime_s=0.0, stats=stats,
        runinfo={"level": level, "chain": [{"step": s, "verdict": v, "what": wh}
                                           for s, v, wh, _ in rows]},
        artifacts=artifacts)
    name = _case_name(input)
    tr.name = name
    tr.src = name
    ctxt.info(f"formal chain to {level}: {status} ("
              + " = ".join(f"{s} {v}" for s, v, _, _ in rows) + ")")
    return TaskDataResult(status=1 if (p.gate and not passed) else 0, changed=True,
                          output=[tr])


async def Lower(ctxt: TaskRunCtxt, input: TaskDataInput) -> TaskDataResult:
    """Elaborate-then-lower an fw_root design to a Verilog netlist (fe/elab)."""
    from fw.hdl.fe.elab.flow import lower_design
    from fw.hdl.fe.elab.interp import ElabError
    p = input.params
    files, incdirs = _sv_inputs(input)
    defines = {}
    for fs in getattr(input, "inputs", []) or []:
        for dname in getattr(fs, "defines", []) or []:
            k, _, v = str(dname).partition("=")
            defines[k] = v or "1"
    rundir = input.rundir
    os.makedirs(rundir, exist_ok=True)
    from fw.hdl.fe.elab.flow import parse_options
    opts = parse_options(getattr(p, "options", "") or "")
    # the inputs, so a lowering can be re-run with other options
    # (python -m fw.hdl.fe.elab.flow lower_inputs.json -o out.v -O k=v)
    import json
    with open(os.path.join(rundir, "lower_inputs.json"), "w") as f:
        json.dump({"files": files, "incdirs": incdirs, "defines": defines, "top": p.top,
                   "module": p.module or None, "encoding": p.encoding, "options": opts},
                  f, indent=1)
    try:
        res = lower_design(files, p.top, incdirs=incdirs, defines=defines,
                           module=(p.module or None), encoding=p.encoding, options=opts)
    except (FwHdlError, ElabError, Exception) as e:   # report any lowering failure
        return TaskDataResult(status=1, changed=True, output=[],
                              markers=[TaskMarker(msg=f"{type(e).__name__}: {e}",
                                                  severity=SeverityE.Error)])
    vfile = f"{res.module}.v"
    with open(os.path.join(rundir, vfile), "w") as f:
        f.write(res.verilog)
    with open(os.path.join(rundir, "lower_report.txt"), "w") as f:
        f.write("\n".join(res.report) + "\n")
    markers = [TaskMarker(msg=r, severity=SeverityE.Warning)
               for r in res.report if r.startswith("warning")]
    return TaskDataResult(status=0, changed=True, markers=markers, output=[
        FileSet(src=input.name, filetype="verilogSource", basedir=rundir, files=[vfile]),
        FileSet(src=input.name, filetype="text", basedir=rundir, files=["lower_report.txt"])])
