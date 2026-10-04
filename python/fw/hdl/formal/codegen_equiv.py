"""XLS codegen checked: the optimized IR function against the Verilog module
generated from it (``formal-svunit.md`` §6, the link from IR to RTL).

The IR function is encoded as SMT by :mod:`.smt` (from XLS's own text, read
by ``zuspec.be.xls.testing.parser``). The module is encoded by Yosys
(``write_smt2 -stbv``): its state, its transition relation and its wires.
The query unrolls the module over the pipeline's latency, from the module
signature (``xlsModuleSignature``):

* the state before the first cycle is free -- what earlier inputs left;
* reset is inactive in every cycle;
* in cycle 0, the input valid signal is set and the data inputs hold the
  function's arguments; in later cycles every input is free;
* in cycle *latency*, the output must equal the function's result and the
  output valid signal must be set.

``unsat`` -- no state and no inputs break it -- is ``equivalent``; ``sat``
is ``not-equivalent``, with the inputs and both results.
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

from . import smt
from .prove import Solver, _run

EQUIVALENT, NOT_EQUIVALENT, INCONCLUSIVE, ERROR = (
    "equivalent", "not-equivalent", "inconclusive", "error")
RANK = {EQUIVALENT: 0, INCONCLUSIVE: 1, NOT_EQUIVALENT: 2, ERROR: 3}


class CodegenEquivError(Exception):
    pass


@dc.dataclass
class Port:
    name: str
    width: int


@dc.dataclass
class Signature:
    """What the check needs of ``xls/codegen/module_signature.proto``."""
    module: str
    inputs: List[Port]
    outputs: List[Port]
    clock: str = ""
    reset: str = ""
    reset_active_low: bool = False
    latency: int = 0
    input_valid: str = ""
    output_valid: str = ""


def _block(text: str, name: str) -> List[str]:
    """The bodies of the top-level ``name { ... }`` blocks of a text proto."""
    out, i = [], 0
    pat = re.compile(r"\b" + re.escape(name) + r"\s*\{")
    while True:
        m = pat.search(text, i)
        if m is None:
            return out
        depth, j = 1, m.end()
        while j < len(text) and depth:
            depth += {"{": 1, "}": -1}.get(text[j], 0)
            j += 1
        out.append(text[m.end():j - 1])
        i = j


def _field(text: str, name: str) -> Optional[str]:
    m = re.search(r"\b" + re.escape(name) + r'\s*:\s*("(?:[^"\\]|\\.)*"|\S+)', text)
    if m is None:
        return None
    v = m.group(1)
    return v[1:-1] if v.startswith('"') else v


def parse_signature(text: str) -> Signature:
    sig = Signature(module=_field(text, "module_name") or "", inputs=[], outputs=[])
    for p in _block(text, "data_ports"):
        port = Port(_field(p, "name") or "", int(_field(p, "width") or 0))
        (sig.inputs if "INPUT" in (_field(p, "direction") or "") else sig.outputs).append(port)
    sig.clock = _field(text, "clock_name") or ""
    for r in _block(text, "reset"):
        sig.reset = _field(r, "name") or ""
        sig.reset_active_low = (_field(r, "active_low") or "false") == "true"
    for pl in _block(text, "pipeline"):
        sig.latency = int(_field(pl, "latency") or 0)
        for v in _block(pl, "valid"):
            sig.input_valid = _field(v, "input_name") or ""
            sig.output_valid = _field(v, "output_name") or ""
    return sig


@dc.dataclass
class Result:
    module: str
    verdict: str
    detail: str = ""
    seconds: float = 0.0
    counterexample: Dict[str, int] = dc.field(default_factory=dict)

    def as_dict(self, ir: str, verilog: Sequence[str], latency: int) -> dict:
        return {"lhs": ir, "rhs": list(verilog), "module": self.module, "verdict": self.verdict,
                "detail": self.detail, "method": f"smt unrolled {latency} cycles",
                "seconds": self.seconds, "counterexample": self.counterexample}


_SORT = re.compile(r"^\(define-sort (\|[^|]+\|) \(\) (\(_ BitVec \d+\))\)\s*$", re.M)


def yosys_smt2(verilog: Sequence[str], top: str, workdir: Path,
               yosys: Optional[str] = None) -> str:
    """The module as Yosys encodes it, with the state sort written out (some
    solvers, dv-solve among them, do not take ``define-sort``)."""
    yosys = yosys or shutil.which("yosys")
    if yosys is None:
        raise CodegenEquivError("yosys not found on PATH")
    out = workdir / f"{top}.rtl.smt2"
    reads = "; ".join(f"read_verilog {'-sv ' if v.endswith('.sv') else ''}{v}" for v in verilog)
    cmd = f"{reads}; prep -top {top}; flatten; async2sync; write_smt2 -stbv -wires {out}"
    log = workdir / f"{top}.yosys.log"
    p = subprocess.run([yosys, "-q", "-l", str(log), "-p", cmd], capture_output=True, text=True)
    if p.returncode != 0:
        err = [ln for ln in (p.stdout + p.stderr).splitlines() if "ERROR" in ln]
        raise CodegenEquivError(f"yosys could not read {top}: "
                                f"{err[0] if err else 'exit %d' % p.returncode} (see {log})")
    text = out.read_text()
    aliases = _SORT.findall(text)
    text = _SORT.sub("", text)
    for alias, sort in aliases:
        text = text.replace(alias, sort)
    return "\n".join(ln for ln in text.splitlines()
                     if not ln.startswith("(set-") and not ln.startswith("; yosys-smt2-witness"))


def _is_bool(rtl: str, accessor: str) -> bool:
    m = re.search(r"\(define-fun " + re.escape(accessor) + r" \(\(state \(_ BitVec \d+\)\)\) (\S+)", rtl)
    if m is None:
        raise CodegenEquivError(f"the Yosys encoding has no {accessor}")
    return m.group(1) == "Bool"


def query(fn_defs: str, fn: str, rtl: str, sig: Signature, args: Sequence[Port],
          ret_width: int, get_values: bool = False) -> str:
    """The unrolled check (see the module doc); sat means a difference."""
    m = sig.module
    L = sig.latency
    s = [f"s{k}" for k in range(L + 1)]

    def n(port, st):
        return f"(|{m}_n {port}| {st})"

    def bit(port, st, value: bool):
        acc = f"|{m}_n {port}|"
        if _is_bool(rtl, acc):
            return n(port, st) if value else f"(not {n(port, st)})"
        return f"(= {n(port, st)} #b{int(value)})"

    out = sig.outputs[0].name
    lines = ["(set-logic QF_BV)", "(set-option :produce-models true)", fn_defs, rtl]
    lines += [f"(declare-fun {st} () {_state_sort(rtl, m)})" for st in s]
    for st in s:
        lines.append(f"(assert (|{m}_h| {st}))")
        lines.append(f"(assert (|{m}_u| {st}))")
        if sig.reset:
            lines.append(f"(assert {bit(sig.reset, st, sig.reset_active_low)})")
    for a, b in zip(s, s[1:]):
        lines.append(f"(assert (|{m}_t| {a} {b}))")
    if sig.input_valid:
        lines.append(f"(assert {bit(sig.input_valid, s[0], True)})")
    for p in args:
        lines.append(f"(declare-fun |in.{p.name}| () (_ BitVec {p.width}))")
        lines.append(f"(assert (= |in.{p.name}| {n(p.name, s[0])}))")
    call = f"({smt.sym(fn)} {' '.join(f'|in.{p.name}|' for p in args)})" if args \
        else smt.sym(fn)
    lines.append(f"(declare-fun |out.ir| () (_ BitVec {ret_width}))")
    lines.append(f"(assert (= |out.ir| {call}))")
    lines.append(f"(declare-fun |out.rtl| () (_ BitVec {ret_width}))")
    lines.append(f"(assert (= |out.rtl| {n(out, s[-1])}))")
    ok = "(= |out.ir| |out.rtl|)"
    if sig.output_valid:
        lines.append(f"(declare-fun |out.valid| () (_ BitVec 1))")
        lines.append(f"(assert (= (= |out.valid| #b1) {bit(sig.output_valid, s[-1], True)}))")
        ok = f"(and {ok} (= |out.valid| #b1))"
    lines.append(f"(assert (not {ok}))")
    lines.append("(check-sat)")
    names = [f"|in.{p.name}|" for p in args] + ["|out.ir|", "|out.rtl|"]
    if get_values:
        lines += [f"(get-value ({nm}))" for nm in names]
    return "\n".join(lines) + "\n"


def _state_sort(rtl: str, m: str) -> str:
    """The state's sort, as the encoding writes it after the alias is gone."""
    mm = re.search(r"\(define-fun \|" + re.escape(m) + r"_t\| \(\(state (\(_ BitVec \d+\))\)",
                   rtl)
    if mm is None:
        raise CodegenEquivError(f"the Yosys encoding of {m} has no transition relation")
    return mm.group(1)


def check(opt_ir: str, verilog: Sequence[str], signature: str, solver: Solver,
          workdir: Path) -> Result:
    """Check one module: *opt_ir* (an IR file), the Verilog files of the
    module and its signature file."""
    from zuspec.be.xls.testing.parser import IrParseError, parse_package
    workdir.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    sig = parse_signature(Path(signature).read_text())
    res = Result(module=sig.module, verdict=ERROR)

    def done(verdict, detail="", cex=None):
        res.verdict, res.detail = verdict, detail
        res.counterexample = cex or {}
        res.seconds = round(time.monotonic() - t0, 2)
        return res

    try:
        pkg = parse_package(Path(opt_ir).read_text())
    except IrParseError as e:
        return done(INCONCLUSIVE, f"the IR is outside what the IR reader takes: {e}")
    fn = next((f for f in pkg.functions if f.name == pkg.top), None)
    if fn is None:
        return done(ERROR, f"{opt_ir}: no top function (procs are not checked)")
    try:
        defs = smt.package(pkg)
        params = [(p.name, smt._w(p)) for p in fn.params]
        ret = smt._w(fn.ret)
    except smt.NotFormal as e:
        return done(INCONCLUSIVE, f"the IR is outside what the SMT encoding takes: {e}")
    if len(sig.outputs) != 1:
        return done(ERROR, f"{sig.module}: {len(sig.outputs)} output data ports; one expected")
    by_name = {p.name: p for p in sig.inputs}
    args = []
    for name, w in params:
        p = by_name.get(name)
        if p is None or p.width != w:
            return done(ERROR, f"{sig.module}: argument {name} (bits[{w}]) has no input port of "
                               f"that name and width; ports {[(p.name, p.width) for p in sig.inputs]}")
        args.append(p)
    ret_w = sig.outputs[0].width
    if ret != ret_w:
        return done(ERROR, f"{sig.module}: the result is bits[{ret}], port "
                           f"{sig.outputs[0].name} is {ret_w} bits")
    try:
        rtl = yosys_smt2(list(verilog), sig.module, workdir)
        q = query(defs, fn.name, rtl, sig, args, ret_w)
    except CodegenEquivError as e:
        return done(ERROR, str(e))
    path = workdir / f"{sig.module}.codegen.smt2"
    path.write_text(q)
    a = _run(solver, path)
    if a.status == "unsat":
        return done(EQUIVALENT)
    if a.status == "sat":
        # Again, for the values (a solver may not answer get-value after unsat).
        path = workdir / f"{sig.module}.codegen.cex.smt2"
        path.write_text(query(defs, fn.name, rtl, sig, args, ret_w, get_values=True))
        # (not the valid bit: some solvers print a 1-bit value as a Bool)
        names = [f"in.{p.name}" for p in args] + ["out.ir", "out.rtl"]
        a = _run(solver, path, names)
        if a.status != "sat":
            return done(INCONCLUSIVE, f"sat, but no values: {a.raw.strip()[:400]}")
        cex = dict(zip(names, a.values))
        shown = ", ".join(f"{k[3:]}={v:#x}" for k, v in cex.items() if k.startswith("in."))
        # Equal results: the difference is the output valid, not set.
        what = (f"output valid not set in cycle {sig.latency}" if cex["out.ir"] == cex["out.rtl"]
                else f"IR {cex['out.ir']:#x}, RTL {cex['out.rtl']:#x} in cycle {sig.latency}")
        return done(NOT_EQUIVALENT, f"for {shown or 'no inputs'}: {what}", cex)
    return done(INCONCLUSIVE, a.raw.strip()[:400])


def write_report(results: Sequence[dict], path: Path) -> str:
    """``equiv.json`` (one module: its entry; several: the worst verdict and
    one entry each), as ``synth.xls.Equiv`` writes it. The worst verdict."""
    worst = max((r["verdict"] for r in results), key=RANK.get)
    report = dict(results[0]) if len(results) == 1 else {"verdict": worst, "modules": list(results)}
    path.write_text(json.dumps(report, indent=2))
    return worst
