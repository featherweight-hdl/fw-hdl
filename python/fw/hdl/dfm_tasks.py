"""dv-flow task implementations for fw-hdl's SPL -> RTL steps (``python/flow.yaml``).

These wrap :mod:`fw.hdl.spl_flow`. They need the fw-hdl Python package
installed in the flow's environment (``python/pyproject.toml``).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List

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


def _markers(reporter: ErrorReporter, exc: Exception) -> List[TaskMarker]:
    out = []
    for d in reporter.diagnostics:
        loc = TaskMarkerLoc(path=d.file, line=d.line or -1, pos=d.column or -1) \
            if d.file else None
        out.append(TaskMarker(msg=d.message, severity=SeverityE.Error, loc=loc))
    if not out:
        out.append(TaskMarker(msg=str(exc), severity=SeverityE.Error))
    return out


async def Partition(ctxt: TaskRunCtxt, input: TaskDataInput) -> TaskDataResult:
    from zuspec.be.xls.lower_proc import lower_component
    from zuspec.be.xls.printer import format_package
    from zuspec.be.xls.signature import CodegenOptions, predict_signature

    from fw.hdl.spl_flow import module_name, partition
    p = input.params
    files, incdirs = _sv_inputs(input)
    reporter = ErrorReporter()
    try:
        part = partition(files, p.top, list(p.xls or []), FlowConfig(incdirs=incdirs), reporter)
    except (FwHdlError, XlsFlowError) as e:
        return TaskDataResult(status=1, changed=True, output=[], markers=_markers(reporter, e))
    rundir = input.rundir
    os.makedirs(rundir, exist_ok=True)
    part.shell.save(os.path.join(rundir, "partition.json"))
    irs, preds = [], []
    for spelling, comp in part.blocks.items():
        module = module_name(spelling)
        with open(os.path.join(rundir, f"{module}.ir"), "w") as f:
            f.write(format_package(lower_component(comp)))
        irs.append(f"{module}.ir")
        ir.save_signature(predict_signature(comp, CodegenOptions(module_name=module)),
                          os.path.join(rundir, f"{module}.pred.json"))
        preds.append(f"{module}.pred.json")
    return TaskDataResult(status=0, changed=True, output=[
        FileSet(src=input.name, filetype="splPartition", basedir=rundir,
                files=["partition.json"]),
        FileSet(src=input.name, filetype="xlsIR", basedir=rundir, files=irs),
        FileSet(src=input.name, filetype="blockSignaturePrediction", basedir=rundir,
                files=preds)])


async def Integrate(ctxt: TaskRunCtxt, input: TaskDataInput) -> TaskDataResult:
    from fw.hdl import ir_build as _b
    from fw.hdl.emit.be_sv import emit_sv
    from fw.hdl.spl_flow import Shell, integrate
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
    try:
        top, top_sig = integrate(shell, sigs, top_name=input.params.top_name or None)
    except XlsFlowError as e:
        return TaskDataResult(status=1, changed=True, output=[], markers=[TaskMarker(
            msg=str(e), severity=SeverityE.Error)])
    rundir = input.rundir
    os.makedirs(rundir, exist_ok=True)
    top_sv = os.path.join(rundir, f"{top_sig.name}.sv")
    with open(top_sv, "w") as f:
        f.write(emit_sv(_b.context([top])))
    top_sig.sources = [top_sv]
    ir.save_signature(top_sig, os.path.join(rundir, f"{top_sig.name}.sig.json"))
    # Everything a simulator or synthesis tool needs, in compile order: the
    # channel FIFO, the blocks, then the top.
    out = [FileSet(src=input.name, filetype="systemVerilogSource",
                   basedir=str(FIFO_SV.parent), files=[FIFO_SV.name])]
    for c in shell.children:
        for src in dict.fromkeys(sigs[c["module"]].sources):
            out.append(FileSet(src=input.name, filetype="systemVerilogSource",
                               basedir=os.path.dirname(src), files=[os.path.basename(src)]))
    out = list({(fs.basedir, tuple(fs.files)): fs for fs in out}.values())
    out += [FileSet(src=input.name, filetype="systemVerilogSource", basedir=rundir,
                    files=[os.path.basename(top_sv)], params={"top": top_sig.name}),
            FileSet(src=input.name, filetype="blockSignature", basedir=rundir,
                    files=[f"{top_sig.name}.sig.json"])]
    return TaskDataResult(status=0, changed=True, output=out)
