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
from zuspec.be.xls.lower_proc import codegen_flags, lower_component
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
                   inputs: Dict[str, Sequence[int]],
                   after: Optional[Dict[str, str]] = None, clocked: bool = False,
                   idle: int = 20) -> str:
    """*pkg_name* is the package to import, or a list of them. *after* maps an
    input to another: it is offered only once that one's values are all taken
    (configuration before data, as :func:`rtl_testbench`).

    *clocked*: run a free-running clock (period 10), for components with a
    step(), and end ``idle`` cycles after the inputs are all taken.
    An fw_get_nb_if port's source offers try_get as well as get."""
    after = after or {}
    pkgs = [pkg_name] if isinstance(pkg_name, str) else list(pkg_name)
    gets, puts = [], []
    flow = {}
    for f in comp.fields:
        if f.kind == ir.FieldKind.Port:
            t = f.pragmas["sv_type"]
            w = f.datatype.element_type.bits
            flow[f.name] = f.pragmas.get("fw_flow", "ready_valid")
            if f.pragmas.get("get_nb"):
                flow[f.name] = "nb"
            if f.pragmas.get("put_step"):
                flow[f.name] = "step"
            (gets if isinstance(f.datatype, ir.DataTypeGetIF) else puts).append((f.name, t, w))
    # The API each harness end provides, by the port's flow control.
    get_api = {"ready_valid": "fw_get_if", "level": "fw_level_if", "nb": "fw_get_nb_if"}
    put_api = {"ready_valid": "fw_put_if", "valid": "fw_valid_put_if", "level": "fw_level_set_if",
               "step": "fw_put_step_if"}
    L = ['`include "fw_std_macros.svh"', "module xh_proc_tb;",
         "  import fw_hdl_pkg::*;", "  import fw_std_pkg::*;"]
    L += [f"  import {p}::*;" for p in pkgs]
    # A cast needs a type name, so each payload type gets a typedef.
    for name, t, w in gets + puts:
        L.append(f"  typedef {t} xh_t_{name};")
    gets = [(n, f"xh_t_{n}", w) for n, _, w in gets]
    puts = [(n, f"xh_t_{n}", w) for n, _, w in puts]
    for name, t, w in gets:
        if flow[name] == "level":       # holds the first input value
            L += [f"  class xh_src_{name} implements fw_level_if #({t});",
                  f"    {t} q[$];",
                  f"    virtual function {t} get();",
                  "      return q.size() ? q[0] : '0;",
                  "    endfunction",
                  "  endclass"]
            continue
        L += [f"  class xh_src_{name} implements {get_api[flow[name]]} #({t});",
              f"    {t} q[$];",
              f"    virtual task get(output {t} t);",
              "      wait (q.size() > 0);",
              "      t = q.pop_front();",
              "    endtask"]
        if flow[name] == "nb":
            L += [f"    virtual function bit try_get(inout {t} t);",
                  "      if (q.size() == 0) return 1'b0;",
                  "      t = q.pop_front();",
                  "      return 1'b1;",
                  "    endfunction"]
        L += ["  endclass"]
    for name, t, w in puts:
        if flow[name] == "level":       # a level output is not observed
            L += [f"  class xh_snk_{name} implements fw_level_set_if #({t});",
                  f"    {t} q[$];",
                  f"    virtual function void set(input {t} t);",
                  "    endfunction",
                  "  endclass"]
            continue
        kw = "function void" if flow[name] == "valid" else "task"
        L += [f"  class xh_snk_{name} implements {put_api[flow[name]]} #({t});",
              f"    {t} q[$];",
              f"    virtual {kw} put(input {t} t);",
              # Print on arrival, so a run that stops at an assertion still
              # reports what it sent before.
              f'      $display("O {name} %0d %0h", q.size(), t);',
              "      q.push_back(t);",
              f"    end{kw.split()[0]}"]
        if flow[name] == "step":        # always ready: never stalls the step
            L += ["    fw_step_sent sent = new;",
                  f"    virtual function void put_or_stall(input {t} t);",
                  "      if (sent.sent) return;",
                  f'      $display("O {name} %0d %0h", q.size(), t);',
                  "      q.push_back(t);",
                  "      fw_step_ctx::sent(sent);",
                  "    endfunction"]
        L += ["  endclass"]
    L += ["  class xh_top extends fw_component;", f"    {cls} dut;"]
    for name, t, w in gets:
        L += [f"    xh_src_{name} src_{name} = new;",
              f"    fw_export #({get_api[flow[name]]} #({t})) e_{name};"]
    for name, t, w in puts:
        L += [f"    xh_snk_{name} snk_{name} = new;",
              f"    fw_export #({put_api[flow[name]]} #({t})) e_{name};"]
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
          "  bit clock = 0, reset = 0;"] + (["  always #5 clock = ~clock;"] if clocked else []) + [
          "  fw_clock_xtor_if u_clk(.clock(clock), .reset(reset));",
          "  fw_component_root #(xh_top) top;",
          "  initial begin",
          "    automatic fw_clock_xtor_bridge clk_dom;",
          '    top = new("top");',
          '    clk_dom = new("clock", top, u_clk);',
          "    top.clock.connect(clk_dom);"]
    for name, t, w in gets:
        if name in after:
            continue
        for v in inputs.get(name, []):
            L.append(f"    top.src_{name}.q.push_back({t}'({sv_hex(v, w)}));")
    L += ["    fork top.start(); join_none"]
    for name, t, w in gets:
        if name in after:
            L.append(f"    while (top.src_{after[name]}.q.size() != 0) #1;")
            L.append("    #1;")
            for v in inputs.get(name, []):
                L.append(f"    top.src_{name}.q.push_back({t}'({sv_hex(v, w)}));")
    if clocked:
        L += [f"    while (top.src_{n}.q.size() != 0) #10;" for n, _, _ in gets
              if flow[n] != "level"]
        L += [f"    #{10 * idle};"]
    else:
        L += ["    #10;"]
    for f in comp.fields:
        if f.kind != ir.FieldKind.Port and isinstance(f.datatype, ir.DataTypeInt):
            L.append(f'    $display("S {f.name} %0h", top.dut.{f.name});')
    L += ['    $display("X done");', "    $finish;", "  end", "endmodule"]
    return "\n".join(L) + "\n"


def rtl_testbench(sig: ir.BlockSignature, inputs: Dict[str, Sequence[int]],
                  seed: int, throttle: int = 3, idle: int = 200,
                  max_cycles: int = 200000, after: Optional[Dict[str, str]] = None,
                  settle: int = 8) -> str:
    """A testbench for the RTL that XLS codegen produced, written from its
    signature alone.

    Each input channel is a source that offers the next value on about
    ``throttle`` cycles out of ``throttle + 1``; once it raises valid it holds
    valid and data until the handshake. Each output channel is a sink whose
    ready is random in the same way. Every handshake on an output prints
    ``O <channel> <index> <hex>``, the same format as :func:`proc_testbench`.
    The run ends ``idle`` cycles after the last handshake.

    By channel kind (``spl_flow.channel_kind``): a **level** input holds
    ``inputs[name][0]`` (or 0) from reset; a level output is not observed. A
    **valid-only** output has no ready: every cycle with valid is a transfer.

    *after* maps an input to another: it is offered only ``settle`` cycles
    after that one's last value is taken (configuration before data)."""
    after = after or {}
    from fw.hdl.spl_flow import channel_kind
    rst_on, rst_off = ("1'b0", "1'b1") if sig.reset_active_low else ("1'b1", "1'b0")
    L = ["module xh_rtl_tb;", "  logic clk = 0;", f"  logic rst = {rst_on};",
         "  int cycle = 0, last = 0;"]
    conns = [f".{sig.clock}(clk)", f".{sig.reset}(rst)"]
    kind = {ch.name: channel_kind(ch) for ch in sig.channels}
    streams = [ch for ch in sig.channels if kind[ch.name] != "level"]
    for ch in sig.channels:
        w, n = ch.payload.bits, ch.name
        L += [f"  logic [{w - 1}:0] {n}_d;", f"  logic {n}_v, {n}_r;"]
        conns += [f".{ch.ports[r]}({n}_{r[0]})" for r in ("data", "valid", "ready")
                  if r in ch.ports]
        if kind[n] == "level":
            if ch.direction == "in":
                v = (list(inputs.get(n, [])) or [0])[0]
                L += [f"  initial {n}_d = {sv_hex(v, w)};"]
            continue
        if kind[n] == "valid":
            L += [f"  assign {n}_r = 1'b1;"]
        if ch.direction == "in":
            vals = list(inputs.get(n, []))
            L += [f"  localparam int {n}_n = {len(vals)};",
                  f"  logic [{w - 1}:0] {n}_q [{max(len(vals), 1)}];", f"  int {n}_i = 0;",
                  f"  int {n}_at = {0 if not vals else -1};"]
            L += ["  initial begin"] + [f"    {n}_q[{i}] = {sv_hex(v, w)};"
                                        for i, v in enumerate(vals)] + ["  end"]
        else:
            L += [f"  int {n}_i = 0;"]
    L += [f"  {sig.name} dut({', '.join(conns)});",
          "  initial begin",
          f"    void'($urandom({seed}));"]
    for ch in streams:
        n = ch.name
        if ch.direction == "in":
            L += [f"    {n}_v = 0; {n}_d = 0;"]
        elif kind[n] != "valid":
            L += [f"    {n}_r = 0;"]
    L += ["    repeat (4) begin #5 clk = 1; #5 clk = 0; end",
          f"    rst = {rst_off};",
          f"    while (cycle - last < {idle} && cycle < {max_cycles}) begin",
          "      // drive, then sample on the rising edge"]
    for ch in streams:
        n = ch.name
        if ch.direction == "in":
            gate = ""
            if n in after:
                d = after[n]
                gate = f" && {d}_at >= 0 && cycle >= {d}_at + {settle}"
            L += [f"      if (!{n}_v && {n}_i < {n}_n{gate} && ($urandom % {throttle + 1}) != 0) begin",
                  f"        {n}_v = 1; {n}_d = {n}_q[{n}_i];",
                  "      end"]
        elif kind[n] != "valid":
            L += [f"      {n}_r = ($urandom % {throttle + 1}) != 0;"]
    L += ["      #5 clk = 1;"]
    for ch in streams:
        n = ch.name
        if ch.direction == "in":
            L += [f"      if ({n}_v && {n}_r) begin {n}_i++; last = cycle; "
                  f"if ({n}_i == {n}_n) {n}_at = cycle; end"]
        else:
            L += [f"      if ({n}_v && {n}_r) begin",
                  f'        $display("O {n} %0d %0h", {n}_i, {n}_d);',
                  f"        {n}_i++; last = cycle;",
                  "      end"]
    L += ["      #5 clk = 0;"]
    for ch in streams:
        if ch.direction == "in":
            n = ch.name
            L += [f"      if ({n}_v && {n}_r_q) {n}_v = 0;"]
    L += ["      cycle++;", "    end",
          '    $display("X done");', "    $finish;", "  end"]
    # ready is sampled at the edge, before the DUT's combinational outputs settle
    # on the new state, so keep a copy of the handshake for the falling edge.
    for ch in streams:
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


# --- cycle-exact traces for step-form components -----------------------
#: input port -> [(cycle, value)]: the value is offered from that cycle on
#: (a stream input, until taken) or becomes the level's value (a level input).
Schedule = Dict[str, Sequence[Tuple[int, int]]]
#: output port -> [(cycle, value)], one entry per transfer
Trace = Dict[str, List[Tuple[int, int]]]
#: stream output port -> the cycles it is not ready (an all-or-nothing step's
#: put_or_stall stalls the step in those cycles)
Stalls = Dict[str, Sequence[int]]


def _ports(comp: ir.DataTypeComponent):
    for f in comp.fields:
        if f.kind == ir.FieldKind.Port:
            yield (f.name, f.pragmas["sv_type"], f.datatype.element_type.bits,
                   isinstance(f.datatype, ir.DataTypeGetIF), f.pragmas.get("fw_flow", "ready_valid"))


def step_testbench(pkg_name: str, cls: str, comp: ir.DataTypeComponent,
                   schedule: Schedule, cycles: int, stalls: Optional[Stalls] = None) -> str:
    """The class model on a free-running clock. Rising edge n is at time
    10n + 5, so a source knows the cycle from $time and never races the steps.
    A stream source offers each value from its cycle until try_get takes it;
    each valid put, and each put_or_stall in a cycle its output is ready
    (*stalls*), prints ``C <port> <cycle> <hex>``. A put_or_stall that
    went is not undone when another output stalls the step (fw_steppable)."""
    stalls = stalls or {}
    L = ['`include "fw_std_macros.svh"', "module xh_step_tb;",
         "  import fw_hdl_pkg::*;", "  import fw_std_pkg::*;", f"  import {pkg_name}::*;",
         "  function automatic int now(); return int'(($time - 5) / 10); endfunction"]
    ports = list(_ports(comp))
    for name, t, w, is_in, flow in ports:
        L.append(f"  typedef {t} xh_t_{name};")
        t = f"xh_t_{name}"
        if is_in and flow == "level":
            L += [f"  class xh_src_{name} implements fw_level_if #({t});",
                  f"    int at[$]; {t} q[$];",
                  f"    virtual function {t} get();",
                  f"      {t} v = '0;",
                  "      foreach (q[i]) if (at[i] <= now()) v = q[i];",
                  "      return v;", "    endfunction", "  endclass"]
        elif is_in:
            # A take is undone if an all-or-nothing step stalls (fw_step_ctx).
            L += [f"  typedef class xh_src_{name};",
                  f"  class xh_undo_{name} extends fw_step_undo;",
                  f"    xh_src_{name} src; int at; {t} v;",
                  "    virtual function void undo();",
                  "      src.q.push_front(v); src.at.push_front(at);",
                  "    endfunction", "  endclass",
                  f"  class xh_src_{name} implements fw_get_nb_if #({t});",
                  f"    int at[$]; {t} q[$];",
                  f"    virtual task get(output {t} t);",
                  "      wait (q.size() > 0 && at[0] <= now());",
                  "      t = q.pop_front(); void'(at.pop_front());", "    endtask",
                  f"    virtual function bit try_get(inout {t} t);",
                  "      if (q.size() == 0 || at[0] > now()) return 1'b0;",
                  "      if (fw_step_ctx::atomic) begin",
                  f"        xh_undo_{name} u = new;",
                  "        u.src = this; u.at = at[0]; u.v = q[0];",
                  "        fw_step_ctx::record(u);", "      end",
                  "      t = q.pop_front(); void'(at.pop_front());",
                  "      return 1'b1;", "    endfunction", "  endclass"]
        elif flow == "level":           # each change, from 0 at reset
            L += [f"  class xh_snk_{name} implements fw_level_set_if #({t});",
                  f"    {t} last;",
                  f"    virtual function void set(input {t} t);",
                  "      if (t == last) return;",
                  f'      $display("C {name} %0d %0h", now(), t);',
                  "      last = t;", "    endfunction", "  endclass"]
        elif flow == "valid":
            L += [f"  class xh_snk_{name} implements fw_valid_put_if #({t});",
                  f"    virtual function void put(input {t} t);",
                  f'      $display("C {name} %0d %0h", now(), t);',
                  "    endfunction", "  endclass"]
        else:
            st = ", ".join(str(c) for c in sorted(set(stalls.get(name, [])))) or "-1"
            # Once a value goes, the output takes no more from the step
            # until it commits, though another output stalls it.
            L += [f"  class xh_snk_{name} implements fw_put_step_if #({t});",
                  f"    int stall[$] = '{{{st}}};",
                  "    fw_step_sent sent = new;",
                  f"    virtual task put(input {t} t);", "    endtask",
                  f"    virtual function void put_or_stall(input {t} t);",
                  "      if (sent.sent) return;",
                  "      foreach (stall[i]) if (stall[i] == now()) begin",
                  "        fw_step_ctx::stall(); return;", "      end",
                  f'      $display("C {name} %0d %0h", now(), t);',
                  "      fw_step_ctx::sent(sent);",
                  "    endfunction", "  endclass"]
    api = {(True, "level"): "fw_level_if", (True, "ready_valid"): "fw_get_nb_if",
           (False, "level"): "fw_level_set_if", (False, "valid"): "fw_valid_put_if",
           (False, "ready_valid"): "fw_put_step_if"}
    L += ["  class xh_top extends fw_component;", f"    {cls} dut;"]
    for name, t, w, is_in, flow in ports:
        L += [f"    xh_{'src' if is_in else 'snk'}_{name} x_{name} = new;",
              f"    fw_export #({api[(is_in, flow)]} #(xh_t_{name})) e_{name};"]
    L += ["    function new(string name, fw_component parent);",
          "      super.new(name, parent);", "    endfunction",
          "    function void build();", '      dut = new("dut", this);']
    L += [f'      e_{n} = new("e_{n}", this, x_{n});' for n, *_ in ports]
    L += ["    endfunction", "    function void connect();"]
    svn = {f.name: f.pragmas.get("sv_name", f.name) for f in comp.fields
           if f.kind == ir.FieldKind.Port}
    L += [f"      dut.{svn[n]}.connect(e_{n});" for n, *_ in ports]
    L += ["    endfunction", "  endclass",
          "  bit clock = 0, reset = 0;",
          "  always #5 clock = ~clock;",
          "  fw_clock_xtor_if u_clk(.clock(clock), .reset(reset));",
          "  fw_component_root #(xh_top) top;",
          "  initial begin",
          "    automatic fw_clock_xtor_bridge clk_dom;",
          '    top = new("top");',
          '    clk_dom = new("clock", top, u_clk);',
          "    top.clock.connect(clk_dom);"]
    for name, t, w, is_in, flow in ports:
        for c, v in (schedule.get(name, []) if is_in else []):
            L.append(f"    top.x_{name}.at.push_back({c}); "
                     f"top.x_{name}.q.push_back(xh_t_{name}'({sv_hex(v, w)}));")
    L += ["    fork top.start(); join_none",
          f"    #{10 * cycles};", '    $display("X done");', "    $finish;", "  end",
          "endmodule"]
    return "\n".join(L) + "\n"


def rtl_step_testbench(sig: ir.BlockSignature, schedule: Schedule, cycles: int,
                       stalls: Optional[Stalls] = None) -> str:
    """XLS's RTL on the same schedule as :func:`step_testbench`: cycle 0 is
    the first rising edge after reset, every output is ready except in its
    *stalls* cycles, and each output transfer prints ``C <port> <cycle> <hex>``."""
    stalls = stalls or {}
    from fw.hdl.spl_flow import channel_kind
    rst_on, rst_off = ("1'b0", "1'b1") if sig.reset_active_low else ("1'b1", "1'b0")
    L = ["module xh_rtl_step_tb;", "  logic clk = 0;", f"  logic rst = {rst_on};",
         "  int cycle = 0;"]
    conns = [f".{sig.clock}(clk)", f".{sig.reset}(rst)"]
    body_drive, body_edge, body_fall = [], [], []
    for ch in sig.channels:
        w, n = ch.payload.bits, ch.name
        # The class's name for the channel: the IR escapes a keyword (ret_).
        sv = n[:-1] if n.endswith("_") and n[:-1] in xir.IR_KEYWORDS else n
        kind = channel_kind(ch)
        L += [f"  logic [{w - 1}:0] {n}_d = 0;", f"  logic {n}_v = 0, {n}_r;"]
        conns += [f".{ch.ports[r]}({n}_{r[0]})" for r in ("data", "valid", "ready")
                  if r in ch.ports]
        if ch.direction == "out":
            st = sorted(set(stalls.get(sv, [])))
            L += [f"  bit {n}_st [{cycles + 1}];",
                  "  initial begin"] + [f"    {n}_st[{c}] = 1;" for c in st if c <= cycles] + \
                 ["  end", f"  assign {n}_r = !(cycle <= {cycles} && {n}_st[cycle]);"]
            if kind != "level":
                body_edge += [f"      if ({n}_v && {n}_r) $display(\"C {sv} %0d %0h\", cycle, {n}_d);"]
            else:                       # each change, from 0 at reset
                L += [f"  logic [{w - 1}:0] {n}_last = 0;"]
                body_edge += [f"      if ({n}_d != {n}_last) begin"
                              f" $display(\"C {sv} %0d %0h\", cycle, {n}_d); {n}_last = {n}_d; end"]
            continue
        sched = list(schedule.get(sv, []))
        L += [f"  int {n}_at [{max(len(sched), 1)}];",
              f"  logic [{w - 1}:0] {n}_q [{max(len(sched), 1)}];",
              f"  int {n}_n = {len(sched)}, {n}_i = 0;",
              "  initial begin"] + \
             [f"    {n}_at[{i}] = {c}; {n}_q[{i}] = {sv_hex(v, w)};"
              for i, (c, v) in enumerate(sched)] + ["  end"]
        if kind == "level":
            body_drive += [f"      while ({n}_i < {n}_n && {n}_at[{n}_i] <= cycle) begin",
                           f"        {n}_d = {n}_q[{n}_i]; {n}_i++;", "      end"]
            continue
        L += [f"  logic {n}_r_q = 0;", f"  always @(posedge clk) {n}_r_q <= {n}_v && {n}_r;"]
        body_drive += [f"      if (!{n}_v && {n}_i < {n}_n && {n}_at[{n}_i] <= cycle) begin",
                       f"        {n}_v = 1; {n}_d = {n}_q[{n}_i];", "      end"]
        body_edge += [f"      if ({n}_v && {n}_r) {n}_i++;"]
        body_fall += [f"      if ({n}_v && {n}_r_q) {n}_v = 0;"]
    L += [f"  {sig.name} dut({', '.join(conns)});",
          "  initial begin",
          "    repeat (4) begin #5 clk = 1; #5 clk = 0; end",
          f"    rst = {rst_off};",
          f"    for (cycle = 0; cycle < {cycles}; cycle++) begin"]
    L += body_drive + ["      #5 clk = 1;"] + body_edge + ["      #5 clk = 0;"] + body_fall
    L += ["    end", '    $display("X done");', "    $finish;", "  end", "endmodule"]
    return "\n".join(L) + "\n"


def _trace(out: Sequence[str]) -> Trace:
    got: Trace = {}
    for line in out:
        m = re.match(r"C (\w+) (\d+) ([0-9a-fA-F]+)$", line)
        if m:
            got.setdefault(m.group(1), []).append((int(m.group(2)), int(m.group(3), 16)))
    return got


def check_step(sv_files: Sequence[str], pkg_name: str, cls: str, schedule: Schedule,
               cycles: int, workdir: Path, rtl_stages: Sequence[int] = (1,),
               rtl_flags: Sequence[Sequence[str]] = ((),),
               stalls: Optional[Stalls] = None) -> Trace:
    """The class model's per-cycle output trace, and XLS's RTL against
    it cycle for cycle at each of *rtl_stages*. *stalls* back-pressures stream
    outputs (an all-or-nothing step's), in model and RTL alike. At k stages each RTL output
    may come a fixed 0 to k - 1 cycles later (the stage XLS schedules its
    send in), plus one per flopped side named in *rtl_flags* (codegen
    flags, one set per RTL build), plus one for a level output (a register);
    nothing else may differ. A level output's trace is its changes, after
    the first (out of reset)."""
    comp = sv_to_component(sv_files, cls)
    pkg = lower_component(comp)
    workdir.mkdir(parents=True, exist_ok=True)
    tb = workdir / "xh_step_tb.sv"
    tb.write_text(step_testbench(pkg_name, cls, comp, schedule, cycles, stalls))
    model = _trace(run_verilator(list(sv_files) + [tb], "xh_step_tb", workdir / "model"))
    if codegen_main() is None or opt_main() is None:
        return model
    for stages, flags in ((st, fl) for st in rtl_stages for fl in rtl_flags):
        res = run_codegen(format_package(pkg), CodegenOptions(), stages=stages,
                          extra=[*codegen_flags(comp, pkg), *flags])
        d = workdir / f"xls_s{stages}{''.join(f.split('=')[0].replace('-', '_') for f in flags)}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "xls_rtl.sv").write_text(res.verilog)
        (d / "xh_rtl_step_tb.sv").write_text(rtl_step_testbench(res.signature, schedule,
                                                                 cycles + stages, stalls))
        from fw.hdl.spl_flow import channel_kind
        levels = {c.name[:-1] if c.name.endswith("_") and c.name[:-1] in xir.IR_KEYWORDS
                  else c.name for c in res.signature.channels if channel_kind(c) == "level"}
        rtl = _trace(run_verilator([d / "xls_rtl.sv", d / "xh_rtl_step_tb.sv"],
                                   "xh_rtl_step_tb", d / "rtl", with_lib=False,
                                   extra=["--assert", "+define+ASSERT_ON"]))
        for name in set(model) | set(rtl):
            m, r = model.get(name, []), rtl.get(name, [])
            # A level's first change, from 0 to the value it takes out of
            # reset, comes when the register leaves reset, whatever the
            # depth: compare the changes after it.
            if name in levels and m and r and m[0][1] == r[0][1]:
                m, r = m[1:], r[1:]
            # The output's pipeline delay: the stage its send is scheduled in.
            lag = r[0][0] - m[0][0] if m and r else 0
            r = [(c, v) for c, v in r if c < cycles + lag]      # the model's window
            want = [(c + lag, v) for c, v in m]
            # Each flopped side (--flop_inputs/--flop_outputs=true) may add a
            # cycle, and a level output is a register (one more).
            most = stages - 1 + sum(f.endswith("=true") for f in flags) + (name in levels)
            assert 0 <= lag <= most and r == want, \
                f"{cls}.{name} ({stages} stage(s) {list(flags)}): rtl={r} model+{lag}={want}"
    return model
