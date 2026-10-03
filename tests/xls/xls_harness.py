"""Conformance harness: the SV source on Verilator vs our interpreter on the
emitted XLS IR (``xls-phase0.md`` §4.6, CH-1..CH-3).

Verilator running the SV is the normative reference (``sv-normative-semantics``).
Every check runs the same vectors through:

1. Verilator on the original SV (a generated testbench);
2. the fw-hdl static front end -> zuspec IR -> ``zuspec-be-xls`` -> XLS IR text
   -> our parser + type checker -> our interpreter;
3. when ``opt_main`` is on hand: XLS parses the text (X1-1) and, for
   functions, evaluates the vectors by constant folding (X1-2);
4. for procs, when ``codegen_main`` is on hand too: XLS generates RTL, its
   module signature must match the prediction (X1-3), and the RTL runs on
   Verilator behind randomly throttled ready/valid sources and sinks (X1-2).

and requires identical results.
"""
from __future__ import annotations

import dataclasses as dc
import itertools
import os
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import zuspec.ir.core as ir

from fw.hdl.xls_flow import sv_to_component, sv_to_functions
from zuspec.be.xls import xir
from zuspec.be.xls.lower_fn import lower_functions
from zuspec.be.xls.lower_proc import lower_component
from zuspec.be.xls.printer import format_package
from zuspec.be.xls.testing.interp import Interpreter, run_proc
from zuspec.be.xls.testing.parser import parse_package
from zuspec.be.xls.testing.typecheck import check_package
from zuspec.be.xls.signature import CodegenOptions, predict_signature, signature_mismatches
from zuspec.be.xls.testing.xlstools import (codegen_main, opt_main, run_codegen, run_opt,
                                            xls_eval_calls)

REPO = Path(__file__).resolve().parents[2]
VERILATOR = REPO / "packages" / "verilator" / "bin" / "verilator"
SRC = REPO / "src"
LIB_FILES = [SRC / "fw_hdl_pkg.sv", SRC / "fw_clock_xtor_if.sv",
             SRC / "fw_clock_period_xtor_if.sv", SRC / "std" / "fw_std_pkg.sv",
             SRC / "std" / "fw_put_xtor_if.sv"]


class VerilatorError(Exception):
    pass


def have_verilator() -> bool:
    return VERILATOR.exists()


def run_verilator(files: Sequence[os.PathLike], top: str, workdir: Path,
                  with_lib: bool = True, allow_stop: bool = False,
                  extra: Sequence[str] = ()) -> List[str]:
    """Build and run *top*; return the simulation's stdout lines.

    ``allow_stop``: the run may end at a failed assertion (Verilator turns
    ``$error`` into ``$stop``) instead of reaching ``X done``."""
    workdir.mkdir(parents=True, exist_ok=True)
    cmd = [str(VERILATOR), "--binary", "--timing", "-j", "0",
           "-Wno-fatal", "-Wno-lint", "-Wno-style",
           f"+incdir+{SRC}", f"+incdir+{SRC / 'std'}",
           "--top-module", top, "-Mdir", str(workdir / "obj"), "-o", "sim", *extra]
    if with_lib:
        cmd += [str(f) for f in LIB_FILES]
    cmd += [str(f) for f in files]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=workdir)
    if r.returncode != 0:
        raise VerilatorError(f"verilator build failed:\n{r.stdout[-4000:]}\n{r.stderr[-4000:]}")
    r = subprocess.run([str(workdir / "obj" / "sim")], capture_output=True, text=True,
                       cwd=workdir)
    out = r.stdout.splitlines() + r.stderr.splitlines()
    if allow_stop and any("Assertion failed" in l or "%Fatal" in l for l in out):
        return out
    if "X done" not in out:
        raise VerilatorError(f"simulation did not finish:\n{r.stdout[-4000:]}\n{r.stderr[-2000:]}")
    return out


def xls_roundtrip(pkg: xir.Package) -> xir.Package:
    """Type-check, print, re-parse; with XLS present, have XLS parse it too."""
    check_package(pkg)
    text = format_package(pkg)
    pkg2 = parse_package(text)
    check_package(pkg2)
    if opt_main() is not None:
        run_opt(text)
    return pkg2


def sv_hex(v: int, width: int) -> str:
    return f"{width}'h{v & ((1 << width) - 1):x}"


# ---------------------------------------------------------------------------
# Functions (CH-1)
# ---------------------------------------------------------------------------

@dc.dataclass
class FnCheck:
    """Call ``sv_name(args)`` on *vectors*; ``name`` is the IR function name.

    With ``exhaustive=True`` leave *vectors* empty: every argument value is
    tried, and the testbench loops instead of listing each call.
    """
    name: str
    vectors: List[Tuple[int, ...]] = dc.field(default_factory=list)
    sv_name: Optional[str] = None      # e.g. "my_pkg::f" or "cls::f"
    exhaustive: bool = False


def fn_testbench(pkg_name: str, checks: Sequence[FnCheck], ir_fns: Dict[str, ir.Function]) -> str:
    lines = ["module xh_fn_tb;", f"  import {pkg_name}::*;", "  initial begin"]
    for ci, chk in enumerate(checks):
        fn = ir_fns[chk.name]
        widths = [a.datatype.bits for a in fn.args.args]
        call = chk.sv_name or chk.name
        if chk.exhaustive:
            vs = [f"a{i}" for i in range(len(widths))]
            lines.append("    begin")
            lines.append("      automatic int vi = 0;")
            ind = "      "
            for v, w in zip(vs, widths):
                lines.append(f"{ind}for (longint {v} = 0; {v} < 64'd{1 << w}; {v}++)")
                ind += "  "
            args = ", ".join(f"{w}'({v})" for v, w in zip(vs, widths))
            lines.append(f'{ind}begin $display("R {ci} %0d %0h", vi, {call}({args})); vi++; end')
            lines.append("    end")
            continue
        for vi, vec in enumerate(chk.vectors):
            args = ", ".join(sv_hex(v, w) for v, w in zip(vec, widths))
            lines.append(f'    $display("R {ci} {vi} %0h", {call}({args}));')
    lines += ['    $display("X done");', "    $finish;", "  end", "endmodule"]
    return "\n".join(lines) + "\n"


def check_functions(sv_files: Sequence[str], pkg_name: str, checks: Sequence[FnCheck],
                    workdir: Path, xls: bool = True) -> Dict[str, List[int]]:
    """Run every check through Verilator, the interpreter and (if present) XLS."""
    names = list(dict.fromkeys(c.name for c in checks))
    fns = sv_to_functions(sv_files, names)
    ir_fns = {f.name: f for f in fns}
    for chk in checks:
        if chk.exhaustive:
            widths = [a.datatype.bits for a in ir_fns[chk.name].args.args]
            chk.vectors = list(itertools.product(*[range(1 << w) for w in widths]))
    pkg = xir.Package(name=names[0])
    lower_functions(pkg, fns)
    pkg.top = names[0]
    pkg2 = xls_roundtrip(pkg)
    it = Interpreter(pkg2)

    tb = workdir / "xh_fn_tb.sv"
    workdir.mkdir(parents=True, exist_ok=True)
    tb.write_text(fn_testbench(pkg_name, checks, ir_fns))
    out = run_verilator(list(sv_files) + [tb], "xh_fn_tb", workdir)
    vlt: Dict[Tuple[int, int], int] = {}
    for line in out:
        m = re.match(r"R (\d+) (\d+) ([0-9a-fA-F]+)$", line)
        if m:
            vlt[(int(m.group(1)), int(m.group(2)))] = int(m.group(3), 16)

    results: Dict[str, List[int]] = {}
    for ci, chk in enumerate(checks):
        got = [it.call(chk.name, list(v)) for v in chk.vectors]
        want = [vlt[(ci, vi)] for vi in range(len(chk.vectors))]
        for v, g, w in zip(chk.vectors, got, want):
            assert g == w, f"{chk.name}{tuple(hex(x) for x in v)}: interp={g:#x} verilator={w:#x}"
        results[chk.name] = want
    if xls and opt_main() is not None:
        calls = [(chk.name, list(v)) for chk in checks for v in chk.vectors]
        xv = iter(xls_eval_calls(pkg, calls))
        for chk in checks:
            for v, w in zip(chk.vectors, results[chk.name]):
                x = next(xv)
                assert x == w, f"{chk.name}{tuple(hex(a) for a in v)}: xls={x:#x} verilator={w:#x}"
    return results


def check_functions_lrm(sv_files: Sequence[str],
                        expected: Dict[str, Sequence[Tuple[Sequence[int], int]]]) -> None:
    """Pin results against hand-computed LRM values, without Verilator.

    For constructs where Verilator does not follow the LRM (the
    ``verilator-oracle-holes`` in xls-phase0.md §11). *expected* maps a
    function to ``(args, result)`` pairs; the interpreter and, when present,
    XLS must both give *result*."""
    names = list(expected)
    pkg = xir.Package(name=names[0])
    lower_functions(pkg, sv_to_functions(sv_files, names))
    pkg.top = names[0]
    it = Interpreter(xls_roundtrip(pkg))
    calls = [(n, list(a)) for n in names for a, _ in expected[n]]
    want = [r for n in names for _, r in expected[n]]
    for (n, a), w in zip(calls, want):
        g = it.call(n, a)
        assert g == w, f"{n}{tuple(hex(x) for x in a)}: interp={g:#x} LRM={w:#x}"
    if opt_main() is not None:
        for (n, a), w, x in zip(calls, want, xls_eval_calls(pkg, calls)):
            assert x == w, f"{n}{tuple(hex(v) for v in a)}: xls={x:#x} LRM={w:#x}"


# ---------------------------------------------------------------------------
# Procs (CH-2)
# ---------------------------------------------------------------------------

@dc.dataclass
class ProcRun:
    outputs: Dict[str, List[int]]
    state: Dict[str, int]


def proc_testbench(pkg_name, cls: str, comp: ir.DataTypeComponent,
                   inputs: Dict[str, Sequence[int]]) -> str:
    """*pkg_name* is the package to import, or a list of them."""
    pkgs = [pkg_name] if isinstance(pkg_name, str) else list(pkg_name)
    gets, puts = [], []
    for f in comp.fields:
        if f.kind == ir.FieldKind.Port:
            t = f.pragmas["sv_type"]
            w = f.datatype.element_type.bits
            (gets if isinstance(f.datatype, ir.DataTypeGetIF) else puts).append((f.name, t, w))
    L = ['`include "fw_std_macros.svh"', "module xh_proc_tb;",
         "  import fw_hdl_pkg::*;", "  import fw_std_pkg::*;"]
    L += [f"  import {p}::*;" for p in pkgs]
    # A cast needs a type name, so each payload type gets a typedef.
    for name, t, w in gets + puts:
        L.append(f"  typedef {t} xh_t_{name};")
    gets = [(n, f"xh_t_{n}", w) for n, _, w in gets]
    puts = [(n, f"xh_t_{n}", w) for n, _, w in puts]
    for name, t, w in gets:
        L += [f"  class xh_src_{name} implements fw_get_if #({t});",
              f"    {t} q[$];",
              f"    virtual task get(output {t} t);",
              "      wait (q.size() > 0);",
              "      t = q.pop_front();",
              "    endtask",
              "  endclass"]
    for name, t, w in puts:
        L += [f"  class xh_snk_{name} implements fw_put_if #({t});",
              f"    {t} q[$];",
              f"    virtual task put(input {t} t);",
              # Print on arrival, so a run that stops at an assertion still
              # reports what it sent before.
              f'      $display("O {name} %0d %0h", q.size(), t);',
              "      q.push_back(t);",
              "    endtask",
              "  endclass"]
    L += ["  class xh_top extends fw_component;", f"    {cls} dut;"]
    for name, t, w in gets:
        L += [f"    xh_src_{name} src_{name} = new;", f"    fw_export #(fw_get_if #({t})) e_{name};"]
    for name, t, w in puts:
        L += [f"    xh_snk_{name} snk_{name} = new;", f"    fw_export #(fw_put_if #({t})) e_{name};"]
    L += ["    function new(string name, fw_component parent);",
          "      super.new(name, parent);", "    endfunction",
          "    function void build();", '      dut = new("dut", this);']
    for name, t, w in gets:
        L.append(f'      e_{name} = new("e_{name}", this, src_{name});')
    for name, t, w in puts:
        L.append(f'      e_{name} = new("e_{name}", this, snk_{name});')
    L += ["    endfunction", "    function void connect();"]
    for name, t, w in gets + puts:
        L.append(f"      dut.{name}.connect(e_{name});")
    L += ["    endfunction", "  endclass",
          "  bit clock = 0, reset = 0;",
          "  fw_clock_xtor_if u_clk(.clock(clock), .reset(reset));",
          "  fw_component_root #(xh_top) top;",
          "  initial begin",
          "    automatic fw_clock_xtor_bridge clk_dom;",
          '    top = new("top");',
          '    clk_dom = new("clock", top, u_clk);',
          "    top.clock.connect(clk_dom);"]
    for name, t, w in gets:
        for v in inputs.get(name, []):
            L.append(f"    top.src_{name}.q.push_back({t}'({sv_hex(v, w)}));")
    L += ["    fork top.start(); join_none", "    #10;"]
    for f in comp.fields:
        if f.kind != ir.FieldKind.Port and isinstance(f.datatype, ir.DataTypeInt):
            L.append(f'    $display("S {f.name} %0h", top.dut.{f.name});')
    L += ['    $display("X done");', "    $finish;", "  end", "endmodule"]
    return "\n".join(L) + "\n"


def rtl_testbench(sig: ir.BlockSignature, inputs: Dict[str, Sequence[int]],
                  seed: int, throttle: int = 3, idle: int = 200,
                  max_cycles: int = 200000) -> str:
    """A testbench for the RTL that XLS codegen produced, written from its
    signature alone.

    Each input channel is a source that offers the next value on about
    ``throttle`` cycles out of ``throttle + 1``; once it raises valid it holds
    valid and data until the handshake. Each output channel is a sink whose
    ready is random in the same way. Every handshake on an output prints
    ``O <channel> <index> <hex>``, the same format as :func:`proc_testbench`.
    The run ends ``idle`` cycles after the last handshake."""
    rst_on, rst_off = ("1'b0", "1'b1") if sig.reset_active_low else ("1'b1", "1'b0")
    L = ["module xh_rtl_tb;", "  logic clk = 0;", f"  logic rst = {rst_on};",
         "  int cycle = 0, last = 0;"]
    conns = [f".{sig.clock}(clk)", f".{sig.reset}(rst)"]
    for ch in sig.channels:
        w, n = ch.payload.bits, ch.name
        L += [f"  logic [{w - 1}:0] {n}_d;", f"  logic {n}_v, {n}_r;"]
        conns += [f".{ch.ports['data']}({n}_d)", f".{ch.ports['valid']}({n}_v)",
                  f".{ch.ports['ready']}({n}_r)"]
        if ch.direction == "in":
            vals = list(inputs.get(n, []))
            L += [f"  localparam int {n}_n = {len(vals)};",
                  f"  logic [{w - 1}:0] {n}_q [{max(len(vals), 1)}];", f"  int {n}_i = 0;"]
            L += ["  initial begin"] + [f"    {n}_q[{i}] = {sv_hex(v, w)};"
                                        for i, v in enumerate(vals)] + ["  end"]
        else:
            L += [f"  int {n}_i = 0;"]
    L += [f"  {sig.name} dut({', '.join(conns)});",
          "  initial begin",
          f"    void'($urandom({seed}));"]
    for ch in sig.channels:
        n = ch.name
        L += [f"    {n}_v = 0; {n}_d = 0;" if ch.direction == "in" else f"    {n}_r = 0;"]
    L += ["    repeat (4) begin #5 clk = 1; #5 clk = 0; end",
          f"    rst = {rst_off};",
          f"    while (cycle - last < {idle} && cycle < {max_cycles}) begin",
          "      // drive, then sample on the rising edge"]
    for ch in sig.channels:
        n = ch.name
        if ch.direction == "in":
            L += [f"      if (!{n}_v && {n}_i < {n}_n && ($urandom % {throttle + 1}) != 0) begin",
                  f"        {n}_v = 1; {n}_d = {n}_q[{n}_i];",
                  "      end"]
        else:
            L += [f"      {n}_r = ($urandom % {throttle + 1}) != 0;"]
    L += ["      #5 clk = 1;"]
    for ch in sig.channels:
        n = ch.name
        if ch.direction == "in":
            L += [f"      if ({n}_v && {n}_r) begin {n}_i++; last = cycle; end"]
        else:
            L += [f"      if ({n}_v && {n}_r) begin",
                  f'        $display("O {n} %0d %0h", {n}_i, {n}_d);',
                  f"        {n}_i++; last = cycle;",
                  "      end"]
    L += ["      #5 clk = 0;"]
    for ch in sig.channels:
        if ch.direction == "in":
            n = ch.name
            L += [f"      if ({n}_v && {n}_r_q) {n}_v = 0;"]
    L += ["      cycle++;", "    end",
          '    $display("X done");', "    $finish;", "  end"]
    # ready is sampled at the edge, before the DUT's combinational outputs settle
    # on the new state, so keep a copy of the handshake for the falling edge.
    for ch in sig.channels:
        if ch.direction == "in":
            n = ch.name
            L += [f"  logic {n}_r_q = 0;",
                  f"  always @(posedge clk) {n}_r_q <= {n}_v && {n}_r;"]
    L += ["endmodule"]
    return "\n".join(L) + "\n"


def check_proc_rtl(pkg_text: str, comp: ir.DataTypeComponent, cls: str,
                   inputs: Dict[str, Sequence[int]], expected: Dict[str, List[int]],
                   workdir: Path, stages: int = 1, seed: int = 1,
                   expect_assert: Optional[str] = None) -> None:
    """X1-2 / X1-3 for one proc: XLS codegen, the signature against the
    prediction, and the RTL's output streams against *expected*."""
    opts = CodegenOptions()
    res = run_codegen(pkg_text, opts, stages=stages)
    diffs = signature_mismatches(predict_signature(comp, opts), res.signature)
    assert not diffs, f"{cls}: codegen signature differs from the prediction:\n" + \
        "\n".join(diffs)
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "xls_rtl.sv").write_text(res.verilog)
    (workdir / "xls_rtl.ir").write_text(res.opt_ir)
    tb = workdir / "xh_rtl_tb.sv"
    tb.write_text(rtl_testbench(res.signature, inputs, seed))
    out = run_verilator([workdir / "xls_rtl.sv", tb], "xh_rtl_tb", workdir / "rtl",
                        with_lib=False, allow_stop=expect_assert is not None,
                        extra=["--assert", "+define+ASSERT_ON"])
    if expect_assert is not None:
        assert any(expect_assert in l for l in out), \
            f"XLS RTL: expected assertion {expect_assert!r}:\n" + "\n".join(out[-20:])
    got: Dict[str, List[int]] = {}
    for line in out:
        m = re.match(r"O (\w+) (\d+) ([0-9a-fA-F]+)$", line)
        if m:
            got.setdefault(m.group(1), []).append(int(m.group(3), 16))
    for ch in res.signature.channels:
        if ch.direction != "out":
            continue
        g, e = got.get(ch.name, []), expected.get(ch.name, [])
        if expect_assert is not None and len(g) == len(e) + 1:
            # D-11: an assertion checks, it does not gate. The RTL may still
            # complete the failing activation's effects: one per channel (P10).
            g = g[:-1]
        assert g == e, f"{cls}.{ch.name} (XLS RTL, {stages} stage(s)): " \
            f"rtl={got.get(ch.name)} interp={e}"


def check_proc(sv_files: Sequence[str], pkg_name, cls: str,
               inputs: Dict[str, Sequence[int]], workdir: Path,
               expect_assert: Optional[str] = None,
               rtl_stages: Sequence[int] = (1, 2)) -> ProcRun:
    """``expect_assert``: the run must stop at a failed assertion whose message
    contains this text, in both Verilator and the interpreter, after the same
    outputs.

    ``rtl_stages``: with ``codegen_main`` on hand, the pipeline depths at which
    XLS's RTL is also checked (:func:`check_proc_rtl`)."""
    comp = sv_to_component(sv_files, cls)
    pkg = lower_component(comp)
    pkg2 = xls_roundtrip(pkg)
    r = run_proc(pkg2, pkg2.top, {k: list(v) for k, v in inputs.items()})
    if expect_assert is None:
        assert r.stop in ("blocked", "limit"), f"interpreter stopped: {r.stop} {r.assertion}"
    else:
        assert r.stop == "assert" and expect_assert in str(r.assertion), \
            f"interpreter: expected assertion {expect_assert!r}, got {r.stop} {r.assertion}"

    workdir.mkdir(parents=True, exist_ok=True)
    tb = workdir / "xh_proc_tb.sv"
    tb.write_text(proc_testbench(pkg_name, cls, comp, inputs))
    out = run_verilator(list(sv_files) + [tb], "xh_proc_tb", workdir,
                        allow_stop=expect_assert is not None)
    if expect_assert is not None:
        assert any("Assertion failed" in l and expect_assert in l for l in out), \
            f"verilator: expected assertion {expect_assert!r}:\n" + "\n".join(out[-20:])
    outputs: Dict[str, List[int]] = {}
    state: Dict[str, int] = {}
    for line in out:
        m = re.match(r"O (\w+) (\d+) ([0-9a-fA-F]+)$", line)
        if m:
            outputs.setdefault(m.group(1), []).append(int(m.group(3), 16))
        m = re.match(r"S (\w+) ([0-9a-fA-F]+)$", line)
        if m:
            state[m.group(1)] = int(m.group(2), 16)
    for f in comp.fields:
        if isinstance(f.datatype, ir.DataTypePutIF):
            assert r.outputs.get(f.name, []) == outputs.get(f.name, []), \
                f"{cls}.{f.name}: interp={r.outputs.get(f.name)} verilator={outputs.get(f.name)}"
    for name, v in state.items():      # (absent when the run stopped early)
        assert r.state[name] == v, f"{cls}.{name}: interp={r.state[name]:#x} verilator={v:#x}"
    if codegen_main() is not None and opt_main() is not None:
        for stages in rtl_stages:
            check_proc_rtl(format_package(pkg), comp, cls, inputs, r.outputs,
                           workdir / f"xls_s{stages}", stages=stages,
                           expect_assert=expect_assert)
    return ProcRun(outputs, state)
