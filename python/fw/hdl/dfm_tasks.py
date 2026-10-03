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


async def XlsIR(ctxt: TaskRunCtxt, input: TaskDataInput) -> TaskDataResult:
    """fw.hdl.xls.IR: one XLS IR package per entry of `top` -- a function or a
    component class."""
    from zuspec.be.xls.lower_proc import lower_component
    from zuspec.be.xls.printer import format_package
    from zuspec.be.xls.signature import CodegenOptions, predict_signature

    from fw.hdl.spl_flow import module_name
    from fw.hdl.xls_flow import (_find_class, _find_functions, _parse, sv_function_package,
                                 sv_to_component)
    p = input.params
    tops = list(p.top or [])
    if not tops:
        return TaskDataResult(status=1, changed=False, output=[], markers=[TaskMarker(
            msg="fw.hdl.xls.IR: `top` names no function or class", severity=SeverityE.Error)])
    files, incdirs = _sv_inputs(input)
    config = FlowConfig(incdirs=incdirs)
    rundir = input.rundir
    os.makedirs(rundir, exist_ok=True)
    irs, preds, markers = [], [], []
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
            if is_fn:
                pkg = sv_function_package(files, top, module, config, reporter)
            else:
                comp = sv_to_component(files, top, config, reporter)
                pkg = lower_component(comp)
                ir.save_signature(predict_signature(comp, CodegenOptions(module_name=module)),
                                  os.path.join(rundir, f"{module}.pred.json"))
                preds.append(f"{module}.pred.json")
        except (FwHdlError, XlsFlowError) as e:
            markers += _markers(reporter, e)
            continue
        with open(os.path.join(rundir, f"{module}.ir"), "w") as f:
            f.write(format_package(pkg))
        irs.append(f"{module}.ir")
    if markers:
        return TaskDataResult(status=1, changed=True, output=[], markers=markers)
    out = [FileSet(src=input.name, filetype="xlsIR", basedir=rundir, files=irs)]
    if preds:
        out.append(FileSet(src=input.name, filetype="blockSignaturePrediction",
                           basedir=rundir, files=preds))
    return TaskDataResult(status=0, changed=True, output=out)


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
            # A component with a run() task is a block; one without is
            # structural (it builds and connects children), whose own ports
            # the structure mapper reads.
            has_run = any(getattr(m, "name", None) == "run"
                          and m.kind == ast.SymbolKind.Subroutine for m in cls)
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
                ports.append(comp_api.CompPort(f.name, role, t, f.datatype.element_type.bits))
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
