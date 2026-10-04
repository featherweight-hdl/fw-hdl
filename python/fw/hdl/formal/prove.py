"""Prove SVUnit tests for every input (``formal-svunit.md`` §3, §4; F0/F1).

For each test, two queries on the lifted function ``__prove_<test>``:

1. Is there an input with ``failed`` set? ``sat`` gives a counterexample: the
   value of every randomized variable, and the obligation that failed.
2. If not, is there an input with ``assume`` set? ``unsat`` means the
   constraints exclude every input: the test is **vacuous**, which fails.

Results: ``proven``, ``counterexample``, ``vacuous``, ``unknown`` (solver
timeout, or output we cannot read) and ``not-formal`` (outside the liftable
subset; the reason and position are given, and the test still runs
dynamically).

The solver is ``dv-solve-smt2`` (``$DV_SOLVE_SMT2``, or on ``PATH``), run with
``--engine=bitblast`` (``dv-solve/docs/fw_hdl_requests.md`` R3). Its answer is
read strictly: anything but a lone ``sat``/``unsat``/``unknown`` line is
``unknown`` (R2). Values are read back only for symbols, never terms (R1).
"""
from __future__ import annotations

import dataclasses as dc
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from pyslang import ast

from ..config import FlowConfig
from ..errors import ErrorReporter, FwHdlError
from ..fe.parser import Parser
from ..fn_api import FnApi
from . import smt
from .lift import LiftedTest, Obligation, TestLifter

_REPO = Path(__file__).resolve().parents[4]
SVUNIT_BASE = _REPO / "packages" / "svunit" / "svunit_base"

PROVEN, CEX, VACUOUS, UNKNOWN, NOT_FORMAL = (
    "proven", "counterexample", "vacuous", "unknown", "not-formal")


@dc.dataclass
class Solver:
    """An SMT-LIB2 solver command. The file is appended."""
    cmd: List[str]
    timeout: float = 300.0

    @staticmethod
    def default(timeout: float = 300.0) -> "Solver":
        exe = os.environ.get("DV_SOLVE_SMT2") or shutil.which("dv-solve-smt2")
        if exe is None:
            raise FileNotFoundError("dv-solve-smt2 not found: set $DV_SOLVE_SMT2 or put it on "
                                    "PATH")
        return Solver([exe, "--engine=bitblast"], timeout)

    @staticmethod
    def named(name: str, timeout: float = 300.0) -> "Solver":
        """*name* is one of :data:`SOLVERS`, or a command line (``"z3 -smt2"``)."""
        if name == "dv-solve":
            return Solver.default(timeout)
        cmd = list(SOLVERS[name]) if name in SOLVERS else name.split()
        if not cmd or shutil.which(cmd[0]) is None:
            raise FileNotFoundError(f"solver {name!r}: {cmd[0] if cmd else name!r} not found "
                                    f"on PATH")
        return Solver(cmd, timeout)


#: The solvers known by name. dv-solve is found by :meth:`Solver.default`.
SOLVERS = {
    "dv-solve": None,
    "z3": ["z3", "-smt2"],
    "bitwuzla": ["bitwuzla"],
    "boolector": ["boolector", "--smt2"],
}


@dc.dataclass
class TestResult:
    test: str
    status: str
    message: str = ""
    obligation: Optional[Obligation] = None
    #: per randomize() call, in the order a run reaches them: its values.
    inputs: List[dict] = dc.field(default_factory=list)
    seconds: float = 0.0
    file: str = ""
    line: int = 0

    @property
    def ok(self) -> bool:
        return self.status == PROVEN

    def summary(self) -> str:
        if self.status == CEX:
            o = self.obligation
            vals = ", ".join(f"{v['name']}={v['value']:#x}" for s in self.inputs
                             for v in s["vars"])
            return (f"{show_path(o.file)}:{o.line}: {o.kind}({o.expr}) fails for "
                    f"{vals or 'the fixed inputs'}")
        return self.message


def show_path(p: str) -> str:
    """*p* relative to the working directory when it is below it."""
    if not p:
        return p
    a = os.path.abspath(p)
    r = os.path.relpath(a)
    return a if r.startswith("..") else r


@dc.dataclass
class _Answer:
    status: str                  # sat | unsat | unknown
    values: List[int]
    raw: str


_PAIR = re.compile(r"\(\s*\|?([^\s()|]+)\|?\s+(#b[01]+|#x[0-9a-fA-F]+)\s*\)")


def _run(solver: Solver, path: Path, names: Sequence[str] = ()) -> _Answer:
    """Run *path*; on ``sat``, read the value of each of *names* (symbols)."""
    try:
        p = subprocess.run(solver.cmd + [str(path)], capture_output=True, text=True,
                           timeout=solver.timeout)
    except subprocess.TimeoutExpired:
        return _Answer("unknown", [], f"timeout after {solver.timeout:.0f} s")
    raw = p.stdout + p.stderr
    lines = [ln.strip() for ln in p.stdout.splitlines() if ln.strip()]
    if not lines or lines[0] not in ("sat", "unsat", "unknown") or "error" in raw.lower():
        return _Answer("unknown", [], f"unreadable solver output (exit {p.returncode}): "
                                      f"{raw.strip()[:400]!r}")
    rest = "\n".join(lines[1:])
    if lines[0] != "sat" or not names:
        if rest:
            return _Answer("unknown", [], f"unexpected solver output: {raw.strip()[:400]!r}")
        return _Answer(lines[0], [], raw)
    got = dict(_PAIR.findall(rest))
    if set(got) != set(names) or len(_PAIR.findall(rest)) != len(names):
        return _Answer("unknown", [], f"unreadable model: {raw.strip()[:400]!r}")
    vals = [int(got[n][2:], 2) if got[n].startswith("#b") else int(got[n][2:], 16)
            for n in names]
    return _Answer("sat", vals, raw)


def query(defs: str, lt: LiftedTest, bit: int, get_values: bool) -> str:
    """Is there an input whose result has bit *bit* set?"""
    width = len(lt.obligations) + 2
    ps = lt.params
    q = ["(set-logic QF_BV)", "(set-option :produce-models true)", defs.rstrip()]
    q += [f"(declare-const {p.param} (_ BitVec {p.width}))" for p in ps]
    call = f"({smt.sym(lt.function)} {' '.join(p.param for p in ps)})" if ps \
        else smt.sym(lt.function)
    q += [f"(declare-const __result (_ BitVec {width}))",
          f"(assert (= __result {call}))",
          f"(assert (= ((_ extract {bit} {bit}) __result) #b1))",
          "(check-sat)"]
    if get_values:
        q += [f"(get-value ({p.param}))" for p in ps] + ["(get-value (__result))"]
    return "\n".join(q) + "\n"


def _signed(v: int, w: int) -> int:
    return v - (1 << w) if v >> (w - 1) & 1 else v


def solve(lt: LiftedTest, defs: str, solver: Solver, workdir: Path) -> TestResult:
    t0 = time.monotonic()
    res = TestResult(test=lt.name, status=UNKNOWN)
    fq = workdir / f"{lt.name}.fail.smt2"
    fq.write_text(query(defs, lt, 1, False))
    a = _run(solver, fq)
    if a.status == "sat":
        # Values are asked for only once the answer is sat: a solver may
        # reject get-value after unsat (z3 does).
        mq = workdir / f"{lt.name}.cex.smt2"
        mq.write_text(query(defs, lt, 1, True))
        a = _run(solver, mq, [p.param for p in lt.params] + ["__result"])
    if a.status == "sat":
        result = a.values[-1]
        fired = [o for o in lt.obligations if result >> (2 + o.index) & 1]
        if len(fired) != 1 or (result & 3) != 3:
            res.message = f"inconsistent model: result {result:#x}"
        else:
            res.status, res.obligation = CEX, fired[0]
            i = 0
            for s in lt.sites:
                vs = []
                for v in s.vars:
                    x = a.values[i]
                    i += 1
                    vs.append({"name": v.name, "width": v.width, "signed": v.signed,
                               "value": _signed(x, v.width) if v.signed else x})
                res.inputs.append({"site": s.index, "file": s.file, "line": s.line,
                                   "start": s.start, "end": s.end, "text": s.text,
                                   "vars": vs})
    elif a.status == "unsat":
        vq = workdir / f"{lt.name}.vacuity.smt2"
        vq.write_text(query(defs, lt, 0, False))
        v = _run(solver, vq)
        if v.status == "sat":
            res.status = PROVEN
            res.message = (f"no input reaches a failure ({len(lt.obligations)} checks, "
                           f"{len(lt.params)} free values)")
        elif v.status == "unsat":
            res.status = VACUOUS
            res.message = "the constraints exclude every input: every randomize() fails"
        else:
            res.message = v.raw
    else:
        res.message = a.raw
    res.seconds = time.monotonic() - t0
    return res


# ----------------------------------------------------------------------
# Finding and lifting the tests
# ----------------------------------------------------------------------

def find_tests(root) -> List[object]:
    """The SVUnit test tasks (``SVTEST_<name>``), in source order."""
    found = []

    def visit(sym):
        if sym.kind == ast.SymbolKind.Subroutine and sym.name.startswith("SVTEST_") \
                and sym.subroutineKind == ast.SubroutineKind.Task and sym.body is not None:
            found.append(sym)
        return True

    root.visit(visit)
    return found


def _resolver(parser: Parser):
    from ..xls_flow import _find_functions
    cache: Dict[str, object] = {}

    def resolve(path: str):
        if path not in cache:
            cache[path] = _find_functions(parser, [path])[0]
        return cache[path]
    return resolve


def lift(parser: Parser, task, api: Optional[FnApi], config: FlowConfig) -> LiftedTest:
    reporter = ErrorReporter()
    lifter = TestLifter(config, reporter, parser.source_manager, api, _resolver(parser))
    return lifter.lift_test(task, task.name[len("SVTEST_"):])


def to_smt(lt: LiftedTest) -> str:
    from zuspec.be.xls import xir
    from zuspec.be.xls.lower_fn import lower_functions
    pkg = xir.Package(name=lt.function)
    lower_functions(pkg, lt.functions)
    return smt.package(pkg)


def design_packages(lifted: Sequence[LiftedTest]) -> Dict[str, object]:
    """The design as the proofs encoded it: for each API function a test
    reached, an XLS IR package (``xir.Package``) whose top is that function,
    named as ``synth.xls.Codegen`` names its module (`crc32_pkg::main` ->
    `crc32_pkg__main`). ``synth.xls.Equiv`` of this package against the IR
    that XLS optimized ties the proven model to the synthesized design
    (formal-svunit.md §6)."""
    from zuspec.be.xls import xir
    from zuspec.be.xls.lower_fn import lower_functions
    from ..spl_flow import module_name
    out: Dict[str, object] = {}
    for lt in lifted:
        design = [f for f in lt.functions if f.name != lt.function]
        for path, fname in lt.api_functions.items():
            module = module_name(path)
            if module in out:
                continue
            top = next(f for f in design if f.name == fname)
            pkg = xir.Package(name=module)
            lower_functions(pkg, design + [dc.replace(top, name=module)])
            pkg.top = module
            out[module] = pkg
    return out


def write_design_ir(lifted: Sequence[LiftedTest], workdir: Path) -> List[str]:
    """Write :func:`design_packages` as ``<module>.formal.ir``; the paths."""
    from zuspec.be.xls.printer import format_package
    paths = []
    for module, pkg in design_packages(lifted).items():
        path = Path(workdir) / f"{module}.formal.ir"
        path.write_text(format_package(pkg))
        paths.append(str(path))
    return paths


def _not_formal_errors():
    from zuspec.be.xls.width import StaticSubsetError
    from zuspec.be.xls.xir import XlsTypeError
    return (FwHdlError, smt.NotFormal, StaticSubsetError, XlsTypeError)


_NOT_FORMAL = _not_formal_errors()


def _diag_text(e: Exception) -> str:
    d = getattr(e, "diagnostic", None)
    if d is not None and getattr(d, "file", None):
        return f"{d.file}:{d.line}: {d.message}"
    return str(e)


def make_api(files: Sequence[str], functions: Sequence[str], workdir: str,
             name: Optional[str] = None, config: Optional[FlowConfig] = None):
    """The call API of *functions*, as ``fw.hdl.api.Functions`` makes it: the
    FnApi and the path of the generated ``<api>_pkg.sv`` in *workdir*."""
    from .. import fn_api
    from ..spl_flow import module_name
    from ..xls_flow import _find_functions, _parse
    parser = _parse(list(files), config or FlowConfig(), ErrorReporter())
    subs = _find_functions(parser, list(functions))
    name = name or fn_api.default_api_name([s.hierarchicalPath for s in subs])
    mods = {s.hierarchicalPath: module_name(n) for s, n in zip(subs, functions)}
    api = fn_api.api_from_subroutines(name, subs, lambda s: mods[s.hierarchicalPath])
    api.sources = list(files)
    os.makedirs(workdir, exist_ok=True)
    pkg = os.path.join(workdir, f"{api.pkg}.sv")
    with open(pkg, "w") as f:
        f.write(fn_api.api_pkg_sv(api))
    return api, pkg


def prove_files(files: Sequence[str], api: Optional[FnApi] = None,
                tests: Optional[Sequence[str]] = None, solver: Optional[Solver] = None,
                workdir: Optional[str] = None,
                config: Optional[FlowConfig] = None,
                design_ir: Optional[List[str]] = None) -> List[TestResult]:
    """Prove the SVUnit tests in *files*.

    *files* holds everything the test compiles with: the design, the API
    package and the test files (SVUnit's own package is added). *api* is the
    call API, for devirtualizing ``api.f(...)``. *tests* selects tests by name.
    With *design_ir* (a list), the design's IR as the proofs encoded it is
    written to *workdir* (:func:`write_design_ir`) and the paths appended.
    """
    config = config or FlowConfig()
    # SVUnit's package, unless *files* bring their own (hdltest.svunit.Lib).
    if any(os.path.basename(f) == "svunit_pkg.sv" for f in files):
        svunit = []
    else:
        svunit = [str(SVUNIT_BASE / "junit-xml" / "junit_xml.sv"),
                  str(SVUNIT_BASE / "svunit_pkg.sv")]
        config.incdirs = list(config.incdirs) + [str(SVUNIT_BASE), str(SVUNIT_BASE / "junit-xml")]
    config.defines.setdefault("FW_FORMAL", "1")
    solver = solver or Solver.default()
    wd = Path(workdir or ".")
    wd.mkdir(parents=True, exist_ok=True)
    reporter = ErrorReporter()
    parser = Parser(config, reporter)
    if not parser.parse(svunit + list(files), include_lib=False):
        raise RuntimeError("SV parse failed:\n" + "\n".join(str(d) for d in reporter.diagnostics))
    results: List[TestResult] = []
    lifted: List[LiftedTest] = []
    for task in find_tests(parser.get_root()):
        name = task.name[len("SVTEST_"):]
        if tests and name not in tests:
            continue
        loc = parser.source_manager
        file = str(loc.getFileName(task.location))
        line = int(loc.getLineNumber(task.location))
        try:
            lt = lift(parser, task, api, config)
            defs = to_smt(lt)
        except _NOT_FORMAL as e:
            results.append(TestResult(test=name, status=NOT_FORMAL, message=_diag_text(e),
                                      file=file, line=line))
            continue
        lifted.append(lt)
        (wd / f"{name}.defs.smt2").write_text(defs)
        r = solve(lt, defs, solver, wd)
        r.file, r.line = file, line
        if r.status == CEX:
            write_replay(r, wd / f"{name}.cex.json")
        results.append(r)
    if design_ir is not None:
        design_ir += write_design_ir(lifted, wd)
    return results


def write_results(results: Sequence[TestResult], path: Path) -> None:
    path.write_text(json.dumps({"format": "fw.hdl.formal-results", "version": 1,
                                "results": [dc.asdict(r) for r in results]}, indent=2) + "\n")


def write_replay(r: TestResult, path: Path) -> None:
    """The counterexample as a replay file: the values each randomize() call
    must return, in order (F4 feeds it to the dynamic run)."""
    o = r.obligation
    path.write_text(json.dumps({
        "format": "fw.hdl.formal-cex", "version": 1, "test": r.test,
        "failure": {"kind": o.kind, "expr": o.expr, "file": o.file, "line": o.line},
        "randomize": r.inputs}, indent=2) + "\n")


def report(results: Sequence[TestResult]) -> str:
    out = []
    for r in results:
        out.append(f"{r.status:15} {r.test:32} {r.seconds:6.2f} s  {r.summary()}")
    n = sum(r.ok for r in results)
    out.append(f"{n}/{len(results)} proven")
    return "\n".join(out)
