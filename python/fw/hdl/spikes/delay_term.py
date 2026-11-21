"""Spike (micro-pipelining D0, F5c route i): estimate the delay of a map's f
from sync IR, with zuspec-synth's timing machinery.

Throwaway-quality code (docs/design/micro-pipelining-feasibility.md F5c).
``f_term`` symbolically executes one of a component's functions (sync IR
``Stmt``/``Expr``, packed-struct arguments and locals) into a hash-consed
``Term`` (zuspec.synth.proc.term) at a given specialization of the type
parameters; ``estimate`` puts it in a one-output ``Netlist`` and runs
``timing.analyze``. ``characterize`` builds a width-aware ``DelayModel`` by
synthesizing each operator alone with yosys (generic gates, ``ltp -noff``
levels), since the only built-in model (``unit``) counts every operator as
one level whatever its width.

Width rules are SV's for unsigned operands: an expression is evaluated at
the larger of its operands' widths and its assignment target's.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from typing import Dict, List, Optional, Tuple

import zuspec.ir.core as ir
from zuspec.ir.core.data_type import DataTypeComponent, DataTypeInt, DataTypeRef, DataTypeStruct
from zuspec.synth.proc import term as T
from zuspec.synth.proc.delay import DelayModel
from zuspec.synth.proc.lower import Netlist
from zuspec.synth.proc.timing import analyze


class SpikeError(Exception):
    pass


def _width(dt, types: Dict[str, ir.DataType]) -> int:
    dt = _resolve(dt, types)
    if isinstance(dt, DataTypeInt):
        if dt.bits is None or dt.bits < 0:
            raise SpikeError(f"width of {dt} is symbolic")
        return dt.bits
    if isinstance(dt, DataTypeStruct):
        return sum(_width(f.datatype, types) for f in dt.fields)
    raise SpikeError(f"no width for {dt}")


def _resolve(dt, types):
    while isinstance(dt, DataTypeRef):
        if dt.ref_name not in types:
            raise SpikeError(f"type {dt.ref_name} not bound")
        dt = types[dt.ref_name]
    return dt


def _layout(dt, types) -> Dict[str, Tuple[int, int, ir.DataType]]:
    """``{field: (lsb, width, type)}`` of a packed struct (first field MSB)."""
    st = _resolve(dt, types)
    if not isinstance(st, DataTypeStruct):
        raise SpikeError(f"{st} is not a struct")
    out = {}
    lo = 0
    for f in reversed(st.fields):
        w = _width(f.datatype, types)
        out[f.name] = (lo, w, f.datatype)
        lo += w
    return out


_BIN = {ir.BinOp.Add: T.add, ir.BinOp.Sub: T.sub, ir.BinOp.Mult: T.mul,
        ir.BinOp.BitAnd: lambda a, b: T.and_(a, b), ir.BinOp.BitOr: lambda a, b: T.or_(a, b),
        ir.BinOp.BitXor: lambda a, b: T.xor(a, b),
        ir.BinOp.LShift: T.shl, ir.BinOp.RShift: T.lshr}


class _Sym:
    """Symbolic execution of one function body."""

    def __init__(self, comp: DataTypeComponent, types: Dict[str, ir.DataType]):
        self.comp = comp
        self.types = types
        self.vals: Dict[str, T.Term] = {}
        self.vtype: Dict[str, ir.DataType] = {}

    # natural width of an expression (SV self-determined, unsigned)
    def nat(self, e) -> int:
        if isinstance(e, ir.ExprConstant):
            return max(1, int(e.value).bit_length())
        if isinstance(e, ir.ExprRefLocal):
            return self.vals[e.name].w
        if isinstance(e, ir.ExprAttribute) and isinstance(e.value, ir.ExprRefLocal):
            return _layout(self.vtype[e.value.name], self.types)[e.attr][1]
        if isinstance(e, ir.ExprBin):
            if e.op in (ir.BinOp.LShift, ir.BinOp.RShift):
                return self.nat(e.lhs)
            return max(self.nat(e.lhs), self.nat(e.rhs))
        raise SpikeError(f"unsupported expression {type(e).__name__}")

    def ev(self, e, w: int) -> T.Term:
        """``e`` evaluated at context width ``w`` (``w`` >= its natural width)."""
        if isinstance(e, ir.ExprConstant):
            return T.const(int(e.value), w)
        if isinstance(e, ir.ExprRefLocal):
            return T.zext(self.vals[e.name], w)
        if isinstance(e, ir.ExprAttribute) and isinstance(e.value, ir.ExprRefLocal):
            lo, fw, _ = _layout(self.vtype[e.value.name], self.types)[e.attr]
            return T.zext(T.slice_(self.vals[e.value.name], lo, fw), w)
        if isinstance(e, ir.ExprBin) and e.op in _BIN:
            if e.op in (ir.BinOp.LShift, ir.BinOp.RShift):
                return _BIN[e.op](self.ev(e.lhs, w), self.ev(e.rhs, max(1, self.nat(e.rhs))))
            return _BIN[e.op](self.ev(e.lhs, w), self.ev(e.rhs, w))
        raise SpikeError(f"unsupported expression {e}")

    def assign(self, tgt, value):
        if isinstance(tgt, ir.ExprRefLocal):
            w = self.vals[tgt.name].w
            self.vals[tgt.name] = T.resize(self.ev(value, max(w, self.nat(value))), w)
            return
        if isinstance(tgt, ir.ExprAttribute) and isinstance(tgt.value, ir.ExprRefLocal):
            n = tgt.value.name
            lay = _layout(self.vtype[n], self.types)
            lo, fw, _ = lay[tgt.attr]
            v = T.resize(self.ev(value, max(fw, self.nat(value))), fw)
            old = self.vals[n]
            parts = []
            if lo + fw < old.w:
                parts.append(T.slice_(old, lo + fw, old.w - lo - fw))
            parts.append(v)
            if lo > 0:
                parts.append(T.slice_(old, 0, lo))
            self.vals[n] = T.concat(*parts)
            return
        raise SpikeError(f"unsupported target {tgt}")

    def run(self, fn: ir.Function, args: Dict[str, T.Term]) -> T.Term:
        for a in fn.args.args:
            self.vals[a.arg] = args[a.arg]
            self.vtype[a.arg] = a.datatype
        ret = None
        for s in fn.body:
            if isinstance(s, ir.StmtAssign):
                t = s.targets[0]
                name = t.name if isinstance(t, ir.ExprRefLocal) else t.value.name
                if name not in self.vals:                   # a local: zeroed
                    raise SpikeError(f"local {name} has no declared type")
                self.assign(t, s.value)
            elif isinstance(s, ir.StmtReturn):
                ret = self.ev(s.value, self.nat(s.value))
            else:
                raise SpikeError(f"unsupported statement {type(s).__name__}")
        if ret is None:
            raise SpikeError(f"{fn.name}: no return")
        return ret


def f_term(comp: DataTypeComponent, fname: str, types: Dict[str, ir.DataType],
           arg: str = "x") -> Tuple[T.Term, int]:
    """``(term, input width)``: function ``fname`` of ``comp`` over one
    struct argument, with the component's type parameters bound in
    ``types`` (``{"TI": struct, ...}`` plus the structs by name)."""
    fn = next((f for f in comp.functions if f.name == fname), None)
    if fn is None:
        raise SpikeError(f"{comp.name}: no function {fname}")
    sym = _Sym(comp, types)
    for name, dt in fn.metadata.get("locals", []):
        sym.vals[name] = T.const(0, _width(dt, types))
        sym.vtype[name] = dt
    a = fn.args.args[0]
    wi = _width(a.datatype, types)
    return sym.run(fn, {a.arg: T.var(f"in_{a.arg}", wi)}), wi


def estimate(t: T.Term, wi: int, model: DelayModel) -> float:
    """Worst arrival at ``t`` (an output) from one input of width ``wi``,
    the input arriving at 0."""
    nl = Netlist(name="f", inputs=[(n.name, n.w) for n in T.leaves(t) if n.op == "var"],
                 outputs=[("y", t)], regs=[], wires=[], instances=[], clock="clk", reset=None)
    rep = analyze(nl, model, input_delay=0.0)
    w = rep.worst
    return 0.0 if w is None else w.arrival


# -- a width-aware model, characterized with yosys -----------------------------

_OPS = {"add": "a + b", "sub": "a - b", "mul": "a * b", "xor": "a ^ b", "and": "a & b",
        "or": "a | b", "lshr": "a >> 3", "shl": "a << 3"}


def _levels(expr: str, w: int, yosys: str = "yosys") -> Tuple[int, int]:
    with tempfile.TemporaryDirectory() as d:
        v = os.path.join(d, "m.v")
        with open(v, "w") as fp:
            fp.write(f"module m(input [{w-1}:0] a, b, output [{w-1}:0] y);\n"
                     f"  assign y = {expr};\nendmodule\n")
        r = subprocess.run([yosys, "-q", "-p", f"read_verilog {v}; synth -flatten -top m; "
                            f"tee -o {d}/s stat; tee -o {d}/l ltp -noff"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise SpikeError(r.stderr[-500:])
        m = re.search(r"length=(\d+)", open(f"{d}/l").read())
        c = re.findall(r"^\s+(\d+) cells$", open(f"{d}/s").read(), re.M)
        # wiring only (a shift by a constant): no cells, no levels
        lev = int(m.group(1)) if m else 0
        cells = int(c[-1]) if c else 0
        return lev, cells


def characterize(widths=(4, 8, 16, 32, 64, 128), ops=None, yosys: str = "yosys") -> dict:
    """A DelayModel dict: per operator, yosys generic-gate levels and cells at
    each width (``by: width``). The bitwise operators are one level per bit
    (``by: width`` here, so a fan-in lookup isn't used)."""
    out = {"name": "yosys_generic", "units": "levels", "clk_to_q": 0, "setup": 0,
           "wire": 0, "margin": 0, "ops": {}}
    for op in ops or _OPS:
        pts = [[w, *_levels(_OPS[op], w, yosys)] for w in widths]
        out["ops"][op] = {"by": "width", "points": pts}
    return out


def load_model(path: str, **kw) -> DelayModel:
    """The characterized model at ``path``, made (and saved) if missing."""
    if not os.path.isfile(path):
        d = characterize(**kw)
        with open(path, "w") as fp:
            json.dump(d, fp, indent=1)
    return DelayModel.load(path)
