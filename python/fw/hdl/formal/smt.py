"""XLS IR (``zuspec.be.xls.xir``) functions -> SMT-LIB2 QF_BV.

One ``define-fun`` per function, its nodes as a ``let`` chain, in the order
the package holds them (callees first). Each op follows XLS's semantics
(``ir_semantics.md``): shifts by at least the width give 0 (or the sign),
``dynamic_bit_slice`` reads 0 past the top, ``bit_slice_update`` ignores bits
past the top, ``sel`` takes its default past the last case.

Bits types only. A function with arrays or tuples raises :class:`NotFormal`.
"""
from __future__ import annotations

from typing import Callable, Dict, List

from zuspec.be.xls import xir


class NotFormal(Exception):
    """The IR has something the SMT printer does not encode."""


def sym(s: str) -> str:
    return "|" + s + "|"


def lit(v: int, w: int) -> str:
    return f"(_ bv{v & ((1 << w) - 1)} {w})"


def _w(n) -> int:
    t = n.type
    if not isinstance(t, xir.BitsType):
        raise NotFormal(f"{n.op} of type {t}: only bits values are supported formally")
    return t.width


def _resize(e: str, frm: int, to: int, signed: bool = False) -> str:
    if to == frm:
        return e
    if to < frm:
        return f"((_ extract {to - 1} 0) {e})"
    return f"((_ {'sign' if signed else 'zero'}_extend {to - frm}) {e})"


def _b2bv(e: str) -> str:
    return f"(ite {e} #b1 #b0)"


_NARY = {"and": "bvand", "or": "bvor", "xor": "bvxor"}
_BIN = {"add": "bvadd", "sub": "bvsub", "udiv": "bvudiv", "umod": "bvurem",
        "sdiv": "bvsdiv", "smod": "bvsrem"}
_CMP = {"eq": "=", "ult": "bvult", "ule": "bvule", "ugt": "bvugt", "uge": "bvuge",
        "slt": "bvslt", "sle": "bvsle", "sgt": "bvsgt", "sge": "bvsge"}
_SHIFT = {"shll": "bvshl", "shrl": "bvlshr", "shra": "bvashr"}


def _shift_amount(amt: str, aw: int, w: int) -> str:
    """The shift amount at width *w*; an amount of at least *w* stays at least *w*."""
    if aw == w:
        return amt
    if aw < w:
        return _resize(amt, aw, w)
    return f"(ite (bvuge {amt} {lit(w, aw)}) {lit(w, w)} ((_ extract {w - 1} 0) {amt}))"


def node_expr(n, r: Callable) -> str:
    op = n.op
    o = [r(x) for x in n.operands]
    w = _w(n)
    if op == "literal":
        return lit(int(n.attrs["value"]), w)
    if op == "identity":
        return o[0]
    if op in _NARY:
        e = o[0]
        for x in o[1:]:
            e = f"({_NARY[op]} {e} {x})"
        return e
    if op in ("nand", "nor"):
        e = o[0]
        for x in o[1:]:
            e = f"({'bvand' if op == 'nand' else 'bvor'} {e} {x})"
        return f"(bvnot {e})"
    if op == "not":
        return f"(bvnot {o[0]})"
    if op == "neg":
        return f"(bvneg {o[0]})"
    if op in _BIN:
        return f"({_BIN[op]} {o[0]} {o[1]})"
    if op in ("umul", "smul"):
        s = op == "smul"
        a, b = n.operands
        return f"(bvmul {_resize(o[0], _w(a), w, s)} {_resize(o[1], _w(b), w, s)})"
    if op in _CMP:
        return _b2bv(f"({_CMP[op]} {o[0]} {o[1]})")
    if op == "ne":
        return _b2bv(f"(not (= {o[0]} {o[1]}))")
    if op in _SHIFT:
        return f"({_SHIFT[op]} {o[0]} {_shift_amount(o[1], _w(n.operands[1]), w)})"
    if op == "and_reduce":
        return _b2bv(f"(= {o[0]} {lit(-1, _w(n.operands[0]))})")
    if op == "or_reduce":
        return _b2bv(f"(not (= {o[0]} {lit(0, _w(n.operands[0]))}))")
    if op == "xor_reduce":
        xw = _w(n.operands[0])
        bits = [f"((_ extract {i} {i}) {o[0]})" for i in range(xw)]
        e = bits[0]
        for x in bits[1:]:
            e = f"(bvxor {e} {x})"
        return e
    if op in ("zero_ext", "sign_ext"):
        return _resize(o[0], _w(n.operands[0]), w, op == "sign_ext")
    if op == "bit_slice":
        s = n.attrs["start"]
        return f"((_ extract {s + w - 1} {s}) {o[0]})"
    if op == "dynamic_bit_slice":
        xw, sw = _w(n.operands[0]), _w(n.operands[1])
        m = max(xw + w, sw)
        return f"((_ extract {w - 1} 0) (bvlshr {_resize(o[0], xw, m)} {_resize(o[1], sw, m)}))"
    if op == "bit_slice_update":
        xw, sw, vw = (_w(x) for x in n.operands)
        m = max(xw + vw, sw)
        s = _resize(o[1], sw, m)
        mask = f"(bvshl {_resize(lit(-1, vw), vw, m)} {s})"
        upd = f"(bvor (bvand {_resize(o[0], xw, m)} (bvnot {mask})) " \
              f"(bvshl {_resize(o[2], vw, m)} {s}))"
        return f"((_ extract {xw - 1} 0) {upd})"
    if op == "concat":
        return o[0] if len(o) == 1 else "(concat " + " ".join(o) + ")"
    if op == "sel":
        sel_w = _w(n.operands[0])
        cases = [r(c) for c in n.attrs["cases"]]
        d = n.attrs.get("default")
        e = r(d) if d is not None else cases[-1]
        last = len(cases) if d is not None else len(cases) - 1
        for i in reversed(range(last)):
            e = f"(ite (= {o[0]} {lit(i, sel_w)}) {cases[i]} {e})"
        return e
    if op == "priority_sel":
        cases = [r(c) for c in n.attrs["cases"]]
        e = r(n.attrs["default"])
        for i in reversed(range(len(cases))):
            e = f"(ite (= ((_ extract {i} {i}) {o[0]}) #b1) {cases[i]} {e})"
        return e
    if op == "invoke":
        f = n.attrs["to_apply"]
        f = getattr(f, "name", f)
        return f"({sym(f)} {' '.join(o)})" if o else sym(f)
    raise NotFormal(f"XLS op {op!r} is not supported formally")


def function(f) -> str:
    for p in f.params:
        _w(p)
    names: Dict[int, str] = {id(p): sym(p.name) for p in f.params}
    lets: List = []
    for n in f.nodes:
        if n.op == "param":
            continue
        e = node_expr(n, lambda x: names[id(x)])
        names[id(n)] = sym(n.ref)
        lets.append((names[id(n)], e))
    body = names[id(f.ret)]
    for nm, e in reversed(lets):
        body = f"(let (({nm} {e}))\n  {body})"
    ps = " ".join(f"({sym(p.name)} (_ BitVec {_w(p)}))" for p in f.params)
    rw = f.ret.type.width if isinstance(f.ret.type, xir.BitsType) else _w(f.ret)
    return f"(define-fun {sym(f.name)} ({ps}) (_ BitVec {rw})\n  {body})"


def package(pkg) -> str:
    return "\n".join(function(f) for f in pkg.functions) + "\n"
