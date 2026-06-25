"""Compact textual dump of a :class:`zuspec.ir.core.Context` for inspection.

Not a serializer (that's the IR's own JSON converter) — a human-readable view of
the components/fields/processes a stage produced, used by ``--dump-ir`` and the
``sv2ir`` / ``spl2rtl`` CLI output.
"""
from __future__ import annotations

import sys
from typing import List

import zuspec.ir.core as ir


def dump_context(ctxt: ir.Context, out=sys.stdout) -> None:
    for name, dtype in ctxt.type_m.items():
        if isinstance(dtype, ir.DataTypeComponent):
            _dump_component(dtype, out)


def _dump_component(comp: ir.DataTypeComponent, out) -> None:
    print(f"component {comp.name}", file=out)
    for i, f in enumerate(comp.fields):
        print(f"  field[{i}] {_field_str(f)}", file=out)
    for bucket, label in (("sync_processes", "sync"),
                          ("comb_processes", "comb"),
                          ("proc_processes", "proc")):
        for fn in getattr(comp, bucket, []):
            print(f"  process[{label}] {fn.name}"
                  + (" (async)" if getattr(fn, "is_async", False) else ""), file=out)
            for s in fn.body:
                _dump_stmt(s, out, 2)


def _field_str(f) -> str:
    dt = _type_str(f.datatype)
    bits = []
    if isinstance(f, ir.FieldInOut):
        bits.append("output" if f.is_out else "input")
    if getattr(f, "kind", None) is not None and f.kind is not ir.FieldKind.Field:
        bits.append(f.kind.name.lower())
    if getattr(f, "is_reg", False):
        bits.append("reg")
    tags = (" [" + ",".join(bits) + "]") if bits else ""
    init = ""
    if getattr(f, "initial_value", None) is not None:
        init = f" = {_expr_str(f.initial_value)}"
    pragmas = getattr(f, "pragmas", None)
    prag = ("  {" + ", ".join(f"{k}={v}" for k, v in pragmas.items()) + "}") if pragmas else ""
    return f"{f.name}: {dt}{tags}{init}{prag}"


def _type_str(dt) -> str:
    if isinstance(dt, ir.DataTypeInt):
        return f"int{dt.bits}{'s' if dt.signed else 'u'}"
    return type(dt).__name__


def _dump_stmt(s, out, ind: int) -> None:
    pad = "  " * ind
    if isinstance(s, ir.StmtWhile):
        print(f"{pad}while {_expr_str(s.test)}:", file=out)
        for sub in s.body:
            _dump_stmt(sub, out, ind + 1)
    elif isinstance(s, ir.StmtIf):
        print(f"{pad}if {_expr_str(s.test)}:", file=out)
        for sub in s.body:
            _dump_stmt(sub, out, ind + 1)
        if s.orelse:
            print(f"{pad}else:", file=out)
            for sub in s.orelse:
                _dump_stmt(sub, out, ind + 1)
    elif isinstance(s, ir.StmtAssign):
        tgt = ", ".join(_expr_str(t) for t in s.targets)
        print(f"{pad}{tgt} = {_expr_str(s.value)}", file=out)
    elif isinstance(s, ir.StmtExpr):
        print(f"{pad}{_expr_str(s.expr)}", file=out)
    else:
        print(f"{pad}<{type(s).__name__}>", file=out)


def _expr_str(e) -> str:
    if isinstance(e, ir.ExprConstant):
        return str(e.value)
    if isinstance(e, ir.TypeExprRefSelf):
        return "self"
    if isinstance(e, ir.ExprRefField):
        return f"{_expr_str(e.base)}.#{e.index}"
    if isinstance(e, ir.ExprAttribute):
        return f"{_expr_str(e.value)}.{e.attr}"
    if isinstance(e, ir.ExprAwait):
        return f"await {_expr_str(e.value)}"
    if isinstance(e, ir.ExprCall):
        args = ", ".join(_expr_str(a) for a in e.args)
        return f"{_expr_str(e.func)}({args})"
    if isinstance(e, ir.ExprUnary):
        return f"{e.op.name}({_expr_str(e.operand)})"
    if isinstance(e, ir.ExprBin):
        return f"({_expr_str(e.lhs)} {e.op.name} {_expr_str(e.rhs)})"
    if isinstance(e, ir.ExprCompare):
        parts = " ".join(f"{op.name} {_expr_str(c)}"
                         for op, c in zip(e.ops, e.comparators))
        return f"({_expr_str(e.left)} {parts})"
    return f"<{type(e).__name__}>"
