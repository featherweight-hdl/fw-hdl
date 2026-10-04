"""dv-flow task implementations for fw-hdl's SPL -> RTL steps (``python/flow.yaml``).

These wrap :mod:`fw.hdl.spl_flow`. They need the fw-hdl Python package
installed in the flow's environment (``python/pyproject.toml``).
"""
from __future__ import annotations

import os
import time
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
                ports.append(comp_api.CompPort(f.name, role, t, f.datatype.element_type.bits,
                                               bool(f.pragmas.get("get_nb"))))
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
