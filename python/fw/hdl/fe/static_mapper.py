"""Map the fw-hdl static subset (SV classes) to zuspec IR for the XLS back end.

This is the X0 front end (``xls-phase0.md`` §4.2). It is separate from the
SPL mapper (``class_mapper.py``) because its IR contract differs in ways the
SPL path does not accept yet:

* **Exact widths (FE-1, R1).** Every pyslang ``Conversion`` becomes an
  ``ExprCast`` and every constant is cast to its SV type, so each expression's
  width follows bottom-up from its operands (the contract in
  ``zuspec-be-xls/width.py``). The SPL mapper drops conversions.
* **State vs temporaries (FE-7, D-8).** Locals declared inside ``forever`` are
  ``StmtAnnAssign`` temporaries; locals before it are state. The SPL mapper
  hoists every local to a field.
* **Typed ports and channel ops (FE-8, R6, R7).** ``fw_port#(fw_get_if#(T))``
  is ``DataTypeGetIF(T)``; ``in.t.get(x)`` becomes
  ``x = await in.get()``.

Packed structs and packed arrays are bit vectors (D-2, D-10): a member or
element select is an ``ExprPartSelect`` at the member's bit offset; an
assignment pattern is an ``ExprConcat``. Unpacked fixed arrays are
``DataTypeArray``.

Unsupported constructs raise :class:`~fw.hdl.errors.FwHdlError` with the SV
location (FE-12).
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import pyslang
import zuspec.ir.core as ir
from zuspec.ir.core.anchor import mark_synthesized as _synth
from pyslang import ast

from ..config import FlowConfig
from ..errors import Diagnostic, ErrorReporter, FwHdlError, Severity

EK = ast.ExpressionKind
SK = ast.StatementKind
UO = ast.UnaryOperator
BO = ast.BinaryOperator


def _int_dt(width: int, signed: bool) -> ir.DataTypeInt:
    return ir.DataTypeInt(bits=width, signed=signed)


_BIN = {
    BO.Add: ir.BinOp.Add, BO.Subtract: ir.BinOp.Sub, BO.Multiply: ir.BinOp.Mult,
    BO.Divide: ir.BinOp.Div, BO.Mod: ir.BinOp.Mod,
    BO.BinaryAnd: ir.BinOp.BitAnd, BO.BinaryOr: ir.BinOp.BitOr, BO.BinaryXor: ir.BinOp.BitXor,
    BO.LogicalShiftLeft: ir.BinOp.LShift, BO.ArithmeticShiftLeft: ir.BinOp.LShift,
    BO.LogicalShiftRight: ir.BinOp.RShift, BO.ArithmeticShiftRight: ir.BinOp.ARShift,
}
_CMP = {
    BO.Equality: ir.CmpOp.Eq, BO.Inequality: ir.CmpOp.NotEq,
    BO.CaseEquality: ir.CmpOp.Eq, BO.CaseInequality: ir.CmpOp.NotEq,   # 2-state: same
    BO.LessThan: ir.CmpOp.Lt, BO.LessThanEqual: ir.CmpOp.LtE,
    BO.GreaterThan: ir.CmpOp.Gt, BO.GreaterThanEqual: ir.CmpOp.GtE,
}


def _implements(cls, name: str) -> bool:
    """Does *cls*, or a class it derives from, implement interface class *name*
    (or an interface class that extends it)?"""
    ct = cls
    while ct is not None and getattr(ct, "kind", None) == ast.SymbolKind.ClassType:
        todo = list(getattr(ct, "implementedInterfaces", None) or [])
        while todo:
            i = todo.pop()
            i = getattr(i, "canonicalType", i)
            g = getattr(i, "genericClass", None)
            if (g.name if g is not None else getattr(i, "name", None)) == name:
                return True
            todo += list(getattr(i, "implementedInterfaces", None) or [])
        b = ct.baseClass
        ct = b.canonicalType if b is not None else None
    return False


def _atomic_state(cls):
    """The state property ``s`` of an all-or-nothing step (a class derived
    from fw_atomic_step), or None."""
    b = cls.baseClass
    ct = b.canonicalType if b is not None else None
    while ct is not None and getattr(ct, "kind", None) == ast.SymbolKind.ClassType:
        g = getattr(ct, "genericClass", None)
        if g is not None and g.name == "fw_atomic_step":
            return ct.find("s")
        b = ct.baseClass
        ct = b.canonicalType if b is not None else None
    return None


def find_behavior(cls) -> Tuple[Optional[str], Optional[object]]:
    """The behavior *cls* declares itself: ``("run", task)``, ``("step",
    function)`` for an ``fw_steppable``, or ``(None, None)`` for a structural
    class. Both may come from user bases; raises ValueError (with the more
derived of the two) when it has both."""
    run = step = None
    depth, run_d, step_d = 0, 0, 0
    # The class and its user bases, most derived first; the library roots
    # declare neither.
    ct = cls
    while ct is not None and getattr(ct, "kind", None) == ast.SymbolKind.ClassType:
        g = getattr(ct, "genericClass", None)
        if (g.name if g is not None else ct.name) in ("fw_component", "fw_component_param",
                                                      "fw_atomic_step"):
            break
        for m in ct:
            if m.kind != ast.SymbolKind.Subroutine or m.body is None:
                continue
            if m.name == "run" and run is None:
                run, run_d = m, depth
            elif m.name == "step" and step is None and _implements(cls, "fw_steppable"):
                step, step_d = m, depth
        depth += 1
        b = ct.baseClass
        ct = b.canonicalType if b is not None else None
    if run is not None and step is not None:
        # Located at the one the most derived class declares.
        raise ValueError(step if step_d <= run_d else run)
    if run is not None:
        return "run", run
    if step is not None:
        return "step", step
    return None, None


class StaticMapper:
    """Maps one runnable component class (and the functions it calls)."""

    def __init__(self, config: FlowConfig, reporter: ErrorReporter, source_manager):
        self.config = config
        self.reporter = reporter
        self.sm = source_manager
        self.port_arrays: Dict[str, int] = {}     # port-array property -> N
        self.unroll_vals: Dict[str, int] = {}     # unrolled loop variable -> value
        # Per-body scopes
        self.fields: Dict[str, int] = {}
        self.locals: Dict[str, str] = {}          # symbol key -> IR local name
        self.local_names: set = set()
        self.params: Dict[str, str] = {}          # symbol key -> IR param name
        self.ret_var: Optional[str] = None        # symbol key of the function's return var
        self.in_function: Optional[str] = None
        self.lvalue: List[ir.Expr] = []
        self.port_dirs: Dict[str, str] = {}       # port name -> "get" | "put"
        self.port_nb: set = set()                 # get ports that may poll (fw_get_nb_if)
        self.port_stall: set = set()              # put ports that may stall (fw_put_step_if)
        self.behavior: Optional[str] = None       # "run", "step" or "atomic" (fw_atomic_step)
        self.port_flow: Dict[str, str] = {}       # port name -> "valid" | "level"
        self.cls_name: Optional[str] = None
        self.cls_spelling: Optional[str] = None
        # Functions reached by calls, mapped on demand.
        self.functions: Dict[str, ir.Function] = {}
        self._fn_queue: List[object] = []
        self._fn_names: Dict[str, str] = {}       # symbol key -> IR function name
        # fw_component_param: the instance's parameter-object fields, read as
        # constants (`m_params.<field>`); set per map_component call.
        self.param_values: Dict[str, object] = {}

    # ------------------------------------------------------------------
    # Diagnostics and locations
    # ------------------------------------------------------------------
    def loc(self, node) -> Optional[ir.Loc]:
        try:
            if hasattr(node, "sourceRange"):
                sl = node.sourceRange.start
            else:
                sl = node.location
            return ir.Loc(file=str(self.sm.getFileName(sl)),
                          line=int(self.sm.getLineNumber(sl)),
                          pos=int(self.sm.getColumnNumber(sl)))
        except Exception:
            return None

    def fail(self, msg: str, node=None, suggestion: Optional[str] = None) -> FwHdlError:
        loc = self.loc(node) if node is not None else None
        d = Diagnostic(Severity.ERROR, msg,
                       file=loc.file if loc else None,
                       line=loc.line if loc else None,
                       column=loc.pos if loc else None,
                       suggestion=suggestion)
        self.reporter.diagnostics.append(d)
        return FwHdlError(d)

    @staticmethod
    def key(sym) -> str:
        return f"{sym.name}@{sym.location}"

    @staticmethod
    def fn_key(sub) -> str:
        """A function's identity. The hierarchical path tells apart the copies
        of a static function in two specializations of one parameterized class
        (`lfsr_c#(7)::lfsr`, `lfsr_c#(8)::lfsr`), which share a location."""
        return f"{sub.hierarchicalPath}@{sub.location}"

    # ------------------------------------------------------------------
    # Types
    # ------------------------------------------------------------------
    def dtype(self, t, node, what: str = "value", decl: bool = False) -> ir.DataType:
        """The IR type of SV type *t*.

        ``decl`` marks a declaration (variable, argument, property, payload):
        those must be 2-state. Expression types are not checked, because SV
        literals are 4-state (``8'd0`` is ``logic [7:0]``); a constant's actual
        x/z bits are rejected where it is read.
        """
        ct = t.canonicalType
        if t.isIntegral:
            if decl and t.isFourState and t.bitWidth != 1:
                raise self.fail(f"4-state type {t} for {what}: the static subset is "
                                f"2-state; use `bit`", node, suggestion="bit [N-1:0]")
            if ct.kind == ast.SymbolKind.PackedArrayType:
                r = ct.range
                if r.left < r.right:
                    raise self.fail(f"ascending packed range [{r.left}:{r.right}] on {what} "
                                    f"is not supported in X0; use [{r.right}:{r.left}]", node)
            return _int_dt(int(t.bitWidth), bool(t.isSigned))
        if t.isUnpackedArray and ct.kind == ast.SymbolKind.FixedSizeUnpackedArrayType:
            r = ct.range
            if r.left > r.right or r.left != 0:
                raise self.fail(f"unpacked array {what} must be declared [N] or [0:N-1] in X0 "
                                f"(has [{r.left}:{r.right}])", node)
            return ir.DataTypeArray(element_type=self.dtype(ct.elementType, node, what, decl),
                                    size=r.right - r.left + 1)
        raise self.fail(f"type {t} of {what} is not in the static subset", node)

    # ------------------------------------------------------------------
    # Constants
    # ------------------------------------------------------------------
    @staticmethod
    def svint_value(v) -> Optional[int]:
        """The exact value of a pyslang SVInt (signed values come out negative),
        or None if it has x/z bits.

        Not ``str(v)``: slang abbreviates wide values there
        (``146'd892029...e6``), which loses digits."""
        unknown = v.hasUnknown
        if callable(unknown):
            unknown = unknown()
        if unknown:
            return None
        s = v.toString(pyslang.LiteralBase.Hex, False).strip().replace("_", "")
        neg = s.startswith("-")
        mag = int(s[1:] if neg else s, 16)
        return -mag if neg else mag

    def svint(self, v, width: int, node) -> int:
        """SVInt *v* as an unsigned *width*-bit value."""
        x = self.svint_value(v)
        if x is None:
            raise self.fail(f"constant {v} has x/z bits; the static subset is 2-state", node)
        return x & ((1 << width) - 1)

    def const_value(self, cv, t, node) -> ir.Expr:
        """A pyslang ConstantValue of SV type *t* as a typed IR constant."""
        dt = self.dtype(t, node)
        if isinstance(dt, ir.DataTypeArray):
            elems = list(cv.value)
            et = t.canonicalType.elementType
            return ir.ExprList(elts=[self.const_value(e, et, node) for e in elems],
                               loc=self.loc(node))
        if cv.hasUnknown():
            raise self.fail("constant has x/z bits; the static subset is 2-state", node)
        v = self.svint(cv.value, dt.bits, node)
        return _synth(ir.ExprCast(target_type=dt, value=ir.ExprConstant(value=v),
                                  loc=self.loc(node)), "literal-type")

    def _param_ref(self, e) -> Optional[object]:
        """The value of ``m_params.<field>`` for this instance, or None."""
        if e.kind != EK.MemberAccess or not self.param_values:
            return None
        v = e.value
        while v.kind == EK.Conversion:
            v = v.operand
        if v.kind == EK.NamedValue and v.symbol.kind == ast.SymbolKind.ClassProperty \
                and v.symbol.name == "m_params":
            return self.param_values.get(e.member.name)
        return None

    def const_int(self, e) -> Optional[int]:
        """The value of an elaboration-time constant expression, or None."""
        pv = self._param_ref(e)
        if isinstance(pv, int):
            return pv
        cv = getattr(e, "constant", None)
        if cv is None and e.kind == EK.NamedValue \
                and e.symbol.kind in (ast.SymbolKind.Parameter, ast.SymbolKind.EnumValue):
            # Inside a function body a parameter reference carries no constant.
            cv = getattr(e.symbol, "value", None)
        if cv is None or cv.isContainer() or cv.hasUnknown():
            return None
        return self.svint_value(cv.value)

    # ------------------------------------------------------------------
    # Expressions
    # ------------------------------------------------------------------
    def expr(self, e) -> ir.Expr:
        out = self._expr(e)
        if out.loc is None:
            out.loc = self.loc(e)
        return out

    def cast(self, e, width: int, signed: bool, user: bool = False) -> ir.Expr:
        """A width/sign conversion. Unless the user wrote it (`T'(x)`,
        `$signed`), it is synthesized and takes no anchor ordinal."""
        c = ir.ExprCast(target_type=_int_dt(width, signed), value=e, loc=e.loc)
        return c if user else _synth(c, "cast")

    def _expr(self, e) -> ir.Expr:
        k = e.kind
        t = e.type
        # Fold elaboration-time constants (literals, parameters, enum values).
        if k != EK.LValueReference and getattr(e, "constant", None) is not None \
                and (t.isIntegral or t.isUnpackedArray):
            return self.const_value(e.constant, t, e)
        if k == EK.IntegerLiteral:
            # Not every literal carries e.constant (case items, for one).
            dt = self.dtype(t, e)
            return _synth(ir.ExprCast(target_type=dt, value=ir.ExprConstant(
                value=self.svint(e.value, dt.bits, e))), "literal-type")
        if k == EK.UnbasedUnsizedIntegerLiteral:
            # '0 / '1: pyslang gives the value already filled to the context
            # width, as an SVInt.
            dt = self.dtype(t, e)
            return _synth(ir.ExprCast(target_type=dt, value=ir.ExprConstant(
                value=self.svint(e.value, dt.bits, e))), "literal-type")
        if k == EK.NamedValue:
            return self.named(e)
        if k == EK.LValueReference:
            if not self.lvalue:
                raise self.fail("compound assignment outside an assignment", e)
            return self.lvalue[-1]
        if k == EK.Conversion:
            inner = self.expr(e.operand)
            if not t.isIntegral:
                if t.isEquivalent(e.operand.type):
                    return inner
                raise self.fail(f"conversion to {t} is not supported", e)
            ot = e.operand.type
            if ot.isIntegral and ot.bitWidth == t.bitWidth and bool(ot.isSigned) == bool(t.isSigned):
                return inner
            if e.conversionKind == ast.ConversionKind.Propagated and ot.isIntegral \
                    and bool(ot.isSigned) != bool(t.isSigned):
                # LRM 11.8.2: a context-determined operand takes the propagated
                # type, and is sign-extended only if that type is signed. Retag
                # first, so the extension below follows the target, not the
                # source (ExprCast extends by its operand's signedness).
                # E.g. signed a * unsigned b: a is zero-extended.
                inner = self.cast(inner, int(ot.bitWidth), bool(t.isSigned))
            return self.cast(inner, int(t.bitWidth), bool(t.isSigned),
                             user=e.conversionKind == ast.ConversionKind.Explicit)
        if k == EK.UnaryOp:
            return self.unary(e)
        if k == EK.BinaryOp:
            return self.binary(e)
        if k == EK.ConditionalOp:
            if len(e.conditions) != 1 or getattr(e.conditions[0], "pattern", None) is not None:
                raise self.fail("pattern-matching conditional is not supported", e)
            return ir.ExprIfExp(test=self.expr(e.conditions[0].expr),
                                body=self.expr(e.left), orelse=self.expr(e.right))
        if k == EK.Concatenation:
            ops = [o for o in e.operands if o.type.bitWidth > 0]
            return ir.ExprConcat(values=[self.expr(o) for o in ops])
        if k == EK.Replication:
            n = self.const_int(e.count)
            if n is None or n <= 0:
                raise self.fail("replication count must be a positive constant", e)
            return ir.ExprReplicate(count=n, value=self.expr(e.concat))
        if k == EK.ElementSelect:
            return self.element_select(e)
        if k == EK.RangeSelect:
            return self.range_select(e)
        if k == EK.MemberAccess:
            pv = self._param_ref(e)
            if isinstance(pv, int) and t.isIntegral:
                dt = self.dtype(t, e)
                return _synth(ir.ExprCast(target_type=dt, value=ir.ExprConstant(
                    value=pv & ((1 << dt.bits) - 1))), "literal-type")
            return self.member(e)
        if k == EK.Call:
            return self.call(e)
        if k in (EK.SimpleAssignmentPattern, EK.StructuredAssignmentPattern):
            return self.pattern(e)
        raise self.fail(f"expression kind {k.name} is not in the static subset", e)

    def named(self, e) -> ir.Expr:
        sym = e.symbol
        sk = sym.kind
        key = self.key(sym)
        if sk == ast.SymbolKind.ClassProperty:
            if self.in_function is not None:
                raise self.fail(f"function {self.in_function!r} reads class property "
                                f"{sym.name!r}: functions in the static subset are pure "
                                f"(arguments only)", e)
            if sym.name not in self.fields:
                raise self.fail(f"unknown class property {sym.name!r}", e)
            return ir.ExprRefField(base=ir.TypeExprRefSelf(), index=self.fields[sym.name])
        if sk == ast.SymbolKind.FormalArgument:
            if key not in self.params:
                raise self.fail(f"unknown argument {sym.name!r}", e)
            return ir.ExprRefParam(name=self.params[key])
        if sk == ast.SymbolKind.Variable:
            if key in self.unroll_vals:
                return _synth(ir.ExprCast(target_type=self.dtype(sym.type, e),
                                          value=ir.ExprConstant(value=self.unroll_vals[key] &
                                                                ((1 << int(sym.type.bitWidth)) - 1))),
                              "unroll")
            if key not in self.locals:
                raise self.fail(f"variable {sym.name!r} is used outside the scope it was "
                                f"declared in, or is not a local", e)
            return ir.ExprRefLocal(name=self.locals[key])
        if sk in (ast.SymbolKind.Parameter, ast.SymbolKind.EnumValue):
            # An unpacked-array parameter has no e.constant; read the symbol's value.
            cv = getattr(sym, "value", None)
            if cv is None:
                raise self.fail(f"parameter {sym.name!r} has no constant value", e)
            return self.const_value(cv, sym.type, e)
        raise self.fail(f"reference to {sk.name} {sym.name!r} is not supported", e)

    def unary(self, e) -> ir.Expr:
        op = e.op
        x = self.expr(e.operand)
        simple = {UO.Plus: ir.UnaryOp.UAdd, UO.Minus: ir.UnaryOp.USub,
                  UO.BitwiseNot: ir.UnaryOp.Invert, UO.LogicalNot: ir.UnaryOp.Not,
                  UO.BitwiseAnd: ir.UnaryOp.AndReduce, UO.BitwiseOr: ir.UnaryOp.OrReduce,
                  UO.BitwiseXor: ir.UnaryOp.XorReduce}
        if op in simple:
            return ir.ExprUnary(op=simple[op], operand=x)
        negated = {UO.BitwiseNand: ir.UnaryOp.AndReduce, UO.BitwiseNor: ir.UnaryOp.OrReduce,
                   UO.BitwiseXnor: ir.UnaryOp.XorReduce}
        if op in negated:
            return ir.ExprUnary(op=ir.UnaryOp.Invert,
                                operand=ir.ExprUnary(op=negated[op], operand=x))
        raise self.fail(f"unary operator {op.name} in an expression is not supported "
                        f"(use ++/-- as statements)", e)

    def binary(self, e) -> ir.Expr:
        op = e.op
        if op in _CMP:
            return ir.ExprCompare(left=self.expr(e.left), ops=[_CMP[op]],
                                  comparators=[self.expr(e.right)])
        if op in (BO.LogicalAnd, BO.LogicalOr):
            return ir.ExprBool(op=ir.BoolOp.And if op == BO.LogicalAnd else ir.BoolOp.Or,
                               values=[self.expr(e.left), self.expr(e.right)])
        if op == BO.BinaryXnor:
            return ir.ExprUnary(op=ir.UnaryOp.Invert, operand=ir.ExprBin(
                lhs=self.expr(e.left), op=ir.BinOp.BitXor, rhs=self.expr(e.right)))
        if op in _BIN:
            return ir.ExprBin(lhs=self.expr(e.left), op=_BIN[op], rhs=self.expr(e.right))
        raise self.fail(f"binary operator {op.name} is not in the static subset", e)

    # -- selects ----------------------------------------------------------
    def _offset_expr(self, idx_e, lo_bound: int, scale: int, descending: bool, node) -> ir.Expr:
        """``(idx - lo_bound) * scale`` (or ``(lo_bound - idx) * scale`` for an
        ascending range) as a signed IR expression wide enough not to wrap."""
        c = self.const_int(idx_e)
        if c is not None:
            off = ((c - lo_bound) if descending else (lo_bound - c)) * scale
            w = max(32, off.bit_length() + 2)
            return _synth(ir.ExprCast(target_type=_int_dt(w, True), value=_synth(
                ir.ExprConstant(value=off & ((1 << w) - 1)), "index")), "index")
        it = idx_e.type
        w = max(int(it.bitWidth), abs(lo_bound).bit_length(), 1) + scale.bit_length() + 2
        # ExprCast extends by the source's signedness, so an unsigned index is
        # zero-extended and a signed one sign-extended before the arithmetic.
        i = self.cast(self.expr(idx_e), w, True)
        # The offset arithmetic is the front end's, not the user's.
        lo = _synth(ir.ExprCast(target_type=_int_dt(w, True), value=_synth(ir.ExprConstant(
            value=lo_bound & ((1 << w) - 1)), "index")), "index")
        diff = _synth(ir.ExprBin(lhs=i, op=ir.BinOp.Sub, rhs=lo) if descending else
                      ir.ExprBin(lhs=lo, op=ir.BinOp.Sub, rhs=i), "index")
        if scale == 1:
            return diff
        return _synth(ir.ExprBin(lhs=diff, op=ir.BinOp.Mult, rhs=_synth(ir.ExprCast(
            target_type=_int_dt(w, True), value=_synth(ir.ExprConstant(value=scale), "index")),
            "index")), "index")

    def element_select(self, e) -> ir.Expr:
        vt = e.value.type
        ct = vt.canonicalType
        if vt.isUnpackedArray:
            r = ct.range
            if r.left != 0 or r.left > r.right:
                raise self.fail("unpacked arrays must be [N] or [0:N-1] in X0", e)
            return ir.ExprSubscript(value=self.expr(e.value), slice=self.expr(e.selector))
        if not vt.isIntegral:
            raise self.fail(f"element select on {vt} is not supported", e)
        base = self.expr(e.value)
        w = int(e.type.bitWidth)
        if ct.kind == ast.SymbolKind.PackedArrayType:
            r = ct.range
            if r.left < r.right:
                raise self.fail("select on an ascending packed range is not supported", e)
            off = self._offset_expr(e.selector, r.right, w, True, e)
        else:
            # A bit select of a scalar-bit type, or a packed struct: [w-1:0].
            off = self._offset_expr(e.selector, 0, w, True, e)
        return ir.ExprPartSelect(value=base, base=off, width=w)

    def range_select(self, e) -> ir.Expr:
        vt = e.value.type
        if not vt.isIntegral:
            raise self.fail("part select of an unpacked array is not supported in X0", e)
        ct = vt.canonicalType
        if ct.kind == ast.SymbolKind.PackedArrayType:
            r = ct.range
            if r.left < r.right:
                raise self.fail("part select of an ascending packed range is not supported", e)
            lsb = r.right
            ew = int(ct.elementType.bitWidth)
        else:
            lsb, ew = 0, 1
        width = int(e.type.bitWidth)
        kind = e.selectionKind
        base = self.expr(e.value)
        if kind == ast.RangeSelectionKind.Simple:
            hi, lo = self.const_int(e.left), self.const_int(e.right)
            if hi is None or lo is None:
                raise self.fail("simple part-select bounds must be constant", e)
            off = self._offset_expr(e.right, lsb, ew, True, e)
        elif kind == ast.RangeSelectionKind.IndexedUp:
            off = self._offset_expr(e.left, lsb, ew, True, e)
        elif kind == ast.RangeSelectionKind.IndexedDown:
            n = self.const_int(e.right)
            if n is None:
                raise self.fail("indexed part-select width must be a constant", e)
            # x[b -: n] is x[b-n+1 +: n]: offset (b - (lsb + n - 1)) * ew
            off = self._offset_expr(e.left, lsb + n - 1, ew, True, e)
        else:
            raise self.fail(f"range select kind {kind} is not supported", e)
        return ir.ExprPartSelect(value=base, base=off, width=width)

    def member(self, e) -> ir.Expr:
        vt = e.value.type
        if not (vt.isIntegral and vt.isStruct):
            raise self.fail(f"member access on {vt} is not supported (packed structs only)", e)
        f = e.member
        off = int(f.bitOffset)
        return ir.ExprPartSelect(value=self.expr(e.value), base=ir.ExprConstant(value=off),
                                 width=int(f.type.bitWidth))

    def pattern(self, e) -> ir.Expr:
        t = e.type
        elems = list(e.elements)
        if t.isIntegral and t.isStruct:
            # Packed struct: elements are in member order; the first is the MSB.
            return ir.ExprConcat(values=[self.expr(x) for x in elems])
        if t.isUnpackedArray:
            return ir.ExprList(elts=[self.expr(x) for x in elems])
        raise self.fail(f"assignment pattern of type {t} is not supported", e)

    # -- calls -------------------------------------------------------------
    def _level_get(self, e) -> Optional[ir.Expr]:
        """`v = <level>.t.get()`: an awaited get on a single_value channel."""
        e0 = e
        while e.kind == EK.Conversion:
            e = e.operand
        if e.kind != EK.Call or e.isSystemCall or e.subroutineName != "get":
            return None
        port = self._port_of(e.thisClass, e)
        if port is None or self.port_flow.get(port[1]) != "level":
            return None
        if self.in_function is not None:
            raise self.fail("channel operations are only allowed in run()", e0)
        ref = ir.ExprRefField(base=ir.TypeExprRefSelf(), index=port[0])
        return ir.ExprAwait(value=ir.ExprCall(func=ir.ExprAttribute(value=ref, attr="get"),
                                              args=[]))

    def call(self, e) -> ir.Expr:
        port = None if e.isSystemCall else self._port_of(e.thisClass, e)
        if port is not None:
            raise self.fail(f"{port[1]}.t.{e.subroutineName}() used as a value; read a level "
                            f"on its own: `v = {port[1]}.t.get();`", e)
        if e.isSystemCall:
            name = e.subroutineName
            if name in ("$signed", "$unsigned") and len(e.arguments) == 1:
                a = e.arguments[0]
                return self.cast(self.expr(a), int(a.type.bitWidth), name == "$signed",
                                 user=True)
            if name == "$clog2" and len(e.arguments) == 1:
                # Of an elaboration-time constant only (a loop bound, say):
                # the value is a constant of the call's type.
                v = self.const_int(e.arguments[0])
                if v is None:
                    raise self.fail("$clog2 of a value that is not an elaboration-time "
                                    "constant is not in the static subset", e)
                dt = self.dtype(e.type, e)
                return _synth(ir.ExprCast(target_type=dt, value=ir.ExprConstant(
                    value=(max(v, 1) - 1).bit_length())), "literal-type")
            raise self.fail(f"system call {name} is not in the static subset", e)
        if e.subroutineKind == ast.SubroutineKind.Task:
            raise self.fail(f"task {e.subroutineName!r} called in an expression", e)
        sub = e.subroutine
        name = self.request_function(sub, e)
        args = []
        for a in e.arguments:
            if a.kind == EK.Assignment:
                raise self.fail(f"function {e.subroutineName!r} has an output argument; "
                                f"static-subset functions take inputs only", e)
            args.append(self.expr(a))
        return ir.ExprCall(func=ir.ExprAttribute(value=ir.TypeExprRefSelf(), attr=name),
                           args=args)

    def request_function(self, sub, node, name: Optional[str] = None) -> str:
        key = self.fn_key(sub)
        if key not in self._fn_names:
            name = name or sub.name
            used = set(self._fn_names.values())
            n, i = name, 0
            while n in used:
                i += 1
                n = f"{name}__{i}"
            self._fn_names[key] = n
            self._fn_queue.append(sub)
        return self._fn_names[key]

    # ------------------------------------------------------------------
    # Statements
    # ------------------------------------------------------------------
    def stmts_of(self, s) -> List:
        if s is None:
            return []
        if s.kind == SK.List:
            out = []
            for x in s.list:
                out.extend(self.stmts_of(x))
            return out
        if s.kind == SK.Block:
            return self.stmts_of(s.body)
        if s.kind == SK.Empty:
            return []
        return [s]

    def body(self, s) -> List[ir.Stmt]:
        out: List[ir.Stmt] = []
        for x in self.stmts_of(s):
            out.extend(self.stmt(x))
        return out

    def new_local(self, sym) -> str:
        key = self.key(sym)
        if key in self.locals:
            return self.locals[key]
        n, i = sym.name, 0
        while n in self.local_names:
            i += 1
            n = f"{sym.name}__{i}"
        self.local_names.add(n)
        self.locals[key] = n
        return n

    def declare(self, sym, node) -> ir.Stmt:
        if str(sym.lifetime) != "VariableLifetime.Automatic":
            raise self.fail(f"static variable {sym.name!r}: locals must be automatic", node)
        name = self.new_local(sym)
        dt = self.dtype(sym.type, node, f"local {sym.name!r}", decl=True)
        value = self.expr(sym.initializer) if sym.initializer is not None else None
        return ir.StmtAnnAssign(target=ir.ExprRefLocal(name=name),
                                annotation=ir.ExprConstant(value=str(sym.type)),
                                ir_type=dt, value=value, loc=self.loc(node))

    def stmt(self, s) -> List[ir.Stmt]:
        out = self._stmt(s)
        for x in out:
            if x.loc is None:
                x.loc = self.loc(s)
        return out

    def _stmt(self, s) -> List[ir.Stmt]:
        k = s.kind
        if k in (SK.List, SK.Block):
            return self.body(s)
        if k == SK.Empty:
            return []
        if k == SK.VariableDeclaration:
            return [self.declare(s.symbol, s)]
        if k == SK.ExpressionStatement:
            return self.expr_stmt(s.expr)
        if k == SK.Conditional:
            if len(s.conditions) != 1 or getattr(s.conditions[0], "pattern", None) is not None:
                raise self.fail("`if` with a pattern or `&&&` is not supported", s)
            polled = self.polled_if(s)
            if polled is not None:
                return polled
            return [ir.StmtIf(test=self.expr(s.conditions[0].expr), body=self.body(s.ifTrue),
                              orelse=self.body(s.ifFalse) if s.ifFalse is not None else [])]
        if k == SK.Case:
            return [self.case(s)]
        if k == SK.ForLoop:
            return self.for_loop(s)
        if k == SK.RepeatLoop:
            n = self.const_int(s.count)
            if n is None:
                raise self.fail("repeat count must be a constant", s)
            return [ir.StmtRepeat(count=ir.ExprConstant(value=n), body=self.body(s.body))]
        if k == SK.ForeverLoop:
            return [ir.StmtWhile(test=_synth(ir.ExprConstant(value=True), "forever"),
                                 body=self.body(s.body))]
        if k == SK.Return:
            if s.expr is None:
                raise self.fail("`return` without a value", s)
            return [ir.StmtReturn(value=self.expr(s.expr))]
        if k == SK.ImmediateAssertion:
            return [self.assertion(s)]
        if k in (SK.Break, SK.Continue):
            raise self.fail("break/continue are not supported in the static subset (X0)", s)
        if k in (SK.Timed, SK.Wait, SK.EventTrigger, SK.WaitFork, SK.WaitOrder):
            raise self.fail("timing controls (#, @, wait) are not allowed in the static "
                            "subset: XLS procs have no time", s)
        raise self.fail(f"statement kind {k.name} is not in the static subset", s)

    def expr_stmt(self, e) -> List[ir.Stmt]:
        k = e.kind
        if k == EK.Assignment:
            if e.isNonBlocking:
                raise self.fail("non-blocking assignment in a class method", e)
            target = self.lvalue_expr(e.left)
            nb = self.try_get(e.right)
            if nb is not None:
                return [ir.StmtAssign(targets=[target], value=nb)]
            lv = self._level_get(e.right)
            if lv is not None:
                return [ir.StmtAssign(targets=[target], value=lv)]
            self.lvalue.append(target)
            try:
                value = self.expr(e.right)
            finally:
                self.lvalue.pop()
            return [ir.StmtAssign(targets=[target], value=value)]
        if k == EK.Call:
            return self.call_stmt(e)
        if k == EK.UnaryOp and e.op in (UO.Postincrement, UO.Preincrement,
                                        UO.Postdecrement, UO.Predecrement):
            target = self.lvalue_expr(e.operand)
            t = e.operand.type
            one = _synth(ir.ExprCast(target_type=_int_dt(int(t.bitWidth), bool(t.isSigned)),
                                     value=_synth(ir.ExprConstant(value=1), "incr")), "incr")
            op = ir.BinOp.Add if e.op in (UO.Postincrement, UO.Preincrement) else ir.BinOp.Sub
            return [ir.StmtAssign(targets=[target],
                                  value=ir.ExprBin(lhs=self.expr(e.operand), op=op, rhs=one))]
        raise self.fail(f"expression statement {k.name} has no effect or is not supported", e)

    def lvalue_expr(self, e) -> ir.Expr:
        k = e.kind
        if k == EK.NamedValue:
            return self.named(e)
        if k == EK.ElementSelect:
            return self.element_select(e)
        if k == EK.RangeSelect:
            return self.range_select(e)
        if k == EK.MemberAccess:
            return self.member(e)
        if k == EK.Concatenation:
            return ir.ExprConcat(values=[self.lvalue_expr(o) for o in e.operands])
        raise self.fail(f"cannot assign to {k.name}", e)

    @staticmethod
    def _port_array_len(m) -> Optional[int]:
        """N for a property declared ``fw_port #(..) p[N]``, else None."""
        ct = m.type.canonicalType
        if not m.type.isUnpackedArray or ct.kind != ast.SymbolKind.FixedSizeUnpackedArrayType:
            return None
        et = ct.elementType.canonicalType
        if et.kind != ast.SymbolKind.ClassType or et.genericClass is None \
                or et.genericClass.name != "fw_port":
            return None
        return int(ct.range.width)

    def _const_index(self, e) -> Optional[int]:
        """The value of index expression *e*: a constant, or a loop variable
        of a loop being unrolled."""
        while e.kind == EK.Conversion:
            e = e.operand
        cv = getattr(e, "constant", None)
        if cv is not None:
            return self.svint_value(cv.value)
        if e.kind == EK.IntegerLiteral:
            return self.svint_value(e.value)
        if e.kind == EK.NamedValue and e.symbol.kind == ast.SymbolKind.Parameter:
            cv = getattr(e.symbol, "value", None)
            return None if cv is None else self.svint_value(cv.value)
        if e.kind == EK.NamedValue:
            return self.unroll_vals.get(self.key(e.symbol))
        return None

    def _uses_port_array(self, s) -> bool:
        """Statement *s* indexes an array of ports."""
        names = self.port_arrays
        hit = []

        def f(x):
            if not hit and isinstance(x, ast.ElementSelectExpression) \
                    and x.value.kind == EK.NamedValue and x.value.symbol.name in names:
                hit.append(x)
            return True
        if names:
            s.visit(f)
        return bool(hit)

    def unrolled_for(self, s) -> List[ir.Stmt]:
        """A loop that indexes an array of ports, unrolled here so each
        iteration names one port: ``for (int k = A; k < B; k++)`` (or ``<=``,
        ``k += 1``) with constant A and B."""
        bad = "a loop over an array of ports must be `for (int k = A; k < B; k++)` with " \
              "constant A and B"
        if len(s.loopVars) != 1 or s.loopVars[0].initializer is None or len(s.steps) != 1:
            raise self.fail(bad, s)
        var = s.loopVars[0]
        a = self._const_index(var.initializer)
        c = s.stopExpr
        while c is not None and c.kind == EK.Conversion:
            c = c.operand
        if a is None or c is None or c.kind != EK.BinaryOp \
                or c.op not in (BO.LessThan, BO.LessThanEqual):
            raise self.fail(bad, s)
        lhs = c.left
        while lhs.kind == EK.Conversion:
            lhs = lhs.operand
        b = self._const_index(c.right)
        if lhs.kind != EK.NamedValue or self.key(lhs.symbol) != self.key(var) or b is None:
            raise self.fail(bad, s)
        st = s.steps[0]
        if not (st.kind == EK.UnaryOp and str(st.op).lower().endswith("increment")) and \
                not (st.kind == EK.Assignment and st.isCompound() and
                     self._const_index(st.right) == 1):
            raise self.fail(bad, s)
        out: List[ir.Stmt] = []
        key = self.key(var)
        for k in range(a, b + 1 if c.op == BO.LessThanEqual else b):
            self.unroll_vals[key] = k
            try:
                out.extend(self.body(s.body))
            finally:
                del self.unroll_vals[key]
        return out

    def _port_of(self, this, e) -> Optional[Tuple[int, str]]:
        """``<port>.t`` -> (field index, port name) for a channel port."""
        if this is None or this.kind != EK.MemberAccess or this.member.name != "t":
            return None
        v = this.value
        if v.kind == EK.ElementSelect and v.value.kind == EK.NamedValue \
                and v.value.symbol.name in self.port_arrays:
            k = self._const_index(v.selector)
            n = self.port_arrays[v.value.symbol.name]
            if k is None:
                raise self.fail(f"{v.value.symbol.name}[...]: a port array is indexed by a "
                                f"constant or a constant-bound loop variable", v)
            if not 0 <= k < n:
                raise self.fail(f"{v.value.symbol.name}[{k}] is out of range [0:{n - 1}]", v)
            name = f"{v.value.symbol.name}_{k}"
            return self.fields[name], name
        if v.kind != EK.NamedValue or v.symbol.kind != ast.SymbolKind.ClassProperty:
            return None
        name = v.symbol.name
        if name not in self.fields or name not in self.port_dirs:
            return None
        return self.fields[name], name

    def try_get(self, e) -> Optional[ir.Expr]:
        """`<port>.t.try_get(x)` on an fw_get_nb_if port: an awaited call
        whose argument is the output x and whose value is the valid bit
        (GAP-3; lowered to XLS's non-blocking receive). None otherwise."""
        if e.kind != EK.Call or e.isSystemCall or e.subroutineName != "try_get":
            return None
        port = self._port_of(e.thisClass, e)
        if port is None:
            return None
        idx, pname = port
        if self.in_function is not None:
            raise self.fail("channel operations are only allowed in run()", e)
        if pname not in self.port_nb:
            raise self.fail(f"{pname}.t.try_get(): the port must be an fw_get_nb_if to poll",
                            e)
        if len(e.arguments) != 1 or e.arguments[0].kind != EK.Assignment:
            raise self.fail(f"expected `v = {pname}.t.try_get(x)`", e)
        x = self.lvalue_expr(e.arguments[0].left)
        ref = ir.ExprRefField(base=ir.TypeExprRefSelf(), index=idx)
        return ir.ExprAwait(value=ir.ExprCall(func=ir.ExprAttribute(value=ref, attr="try_get"),
                                              args=[x]))

    def polled_if(self, s) -> Optional[List[ir.Stmt]]:
        """``if (p.t.try_get(x)) ...`` and, without an else, ``if (a &&
        p.t.try_get(x)) ...``: the poll goes into a temporary first, and in
        the second form only when ``a`` holds (SV's short-circuit order).
        None for any other condition."""
        c = s.conditions[0].expr
        guard = None
        nb = self.try_get(c)
        if nb is None and c.kind == EK.BinaryOp and c.op == BO.LogicalAnd:
            nb = self.try_get(c.right)
            if nb is not None:
                if s.ifFalse is not None:
                    raise self.fail("`if (a && p.t.try_get(x)) ... else`: write the poll in "
                                    "its own `if` inside `if (a)`", s)
                guard = self.expr(c.left)
        if nb is None:
            return None
        n, i = "ok", 0
        while n in self.local_names:
            i += 1
            n = f"ok__{i}"
        self.local_names.add(n)
        poll = [_synth(ir.StmtAnnAssign(target=ir.ExprRefLocal(name=n),
                                        annotation=ir.ExprConstant(value="bit"),
                                        ir_type=_int_dt(1, False), value=None,
                                        loc=self.loc(c)), "poll"),
                ir.StmtAssign(targets=[ir.ExprRefLocal(name=n)], value=nb, loc=self.loc(c)),
                ir.StmtIf(test=ir.ExprRefLocal(name=n), body=self.body(s.ifTrue),
                          orelse=self.body(s.ifFalse) if s.ifFalse is not None else [])]
        if guard is None:
            return poll
        return [ir.StmtIf(test=guard, body=poll, orelse=[])]

    def call_stmt(self, e) -> List[ir.Stmt]:
        if e.isSystemCall:
            raise self.fail(f"system task {e.subroutineName} is not in the static subset", e)
        port = self._port_of(e.thisClass, e)
        if port is not None:
            idx, pname = port
            ref = ir.ExprRefField(base=ir.TypeExprRefSelf(), index=idx)
            method = e.subroutineName
            level = self.port_flow.get(pname) == "level"
            if self.in_function is not None:
                raise self.fail("channel operations are only allowed in run()", e)
            if method == "get" and self.port_dirs[pname] == "get" and level:
                raise self.fail(f"{pname} is a level: read it as `v = {pname}.t.get();`", e)
            if method == "get" and self.port_dirs[pname] == "get":
                if len(e.arguments) != 1 or e.arguments[0].kind != EK.Assignment:
                    raise self.fail(f"expected `{pname}.t.get(x)`", e)
                target = self.lvalue_expr(e.arguments[0].left)
                call = ir.ExprCall(func=ir.ExprAttribute(value=ref, attr="get"), args=[])
                return [ir.StmtAssign(targets=[target], value=ir.ExprAwait(value=call))]
            if method == "set" and level and self.port_dirs[pname] == "put":
                if len(e.arguments) != 1:
                    raise self.fail(f"expected `{pname}.t.set(v)`", e)
                call = ir.ExprCall(func=ir.ExprAttribute(value=ref, attr="put"),
                                   args=[self.expr(e.arguments[0])])
                return [ir.StmtExpr(expr=ir.ExprAwait(value=call))]
            if method == "put_or_stall" and pname in self.port_stall:
                if self.behavior != "atomic":
                    raise self.fail(f"{pname}.t.put_or_stall() stalls the whole step, so it "
                                    f"needs an all-or-nothing step (a class derived from "
                                    f"fw_atomic_step)", e)
                if len(e.arguments) != 1:
                    raise self.fail(f"expected `{pname}.t.put_or_stall(v)`", e)
                call = ir.ExprCall(func=ir.ExprAttribute(value=ref, attr="put"),
                                   args=[self.expr(e.arguments[0])])
                return [ir.StmtExpr(expr=ir.ExprAwait(value=call))]
            if method == "put" and self.port_dirs[pname] == "put" and not level:
                if len(e.arguments) != 1:
                    raise self.fail(f"expected `{pname}.t.put(v)`", e)
                if self.behavior in ("step", "atomic") and \
                        self.port_flow.get(pname) != "valid":
                    raise self.fail(f"{pname}.t.put() waits for ready, and a step cannot "
                                    f"wait: use put_or_stall in an fw_atomic_step, or a "
                                    f"valid-only port (fw_valid_put_if)", e)
                call = ir.ExprCall(func=ir.ExprAttribute(value=ref, attr="put"),
                                   args=[self.expr(e.arguments[0])])
                return [ir.StmtExpr(expr=ir.ExprAwait(value=call))]
            raise self.fail(f"{pname}.t.{method}() is not a channel operation of this port", e)
        if e.subroutineKind == ast.SubroutineKind.Task:
            name = e.subroutineName
            raise self.fail(f"call to task {name!r}: an XLS proc has no time-consuming calls "
                            f"other than port get/put", e)
        return [ir.StmtExpr(expr=self.call(e))]

    def case(self, s) -> ir.StmtMatch:
        if str(s.condition) != "CaseStatementCondition.Normal":
            raise self.fail("casez/casex/case-inside are not supported in X0", s)
        items = [(list(it.expressions), it.stmt) for it in s.items]
        all_exprs = [s.expr] + [x for xs, _ in items for x in xs]
        w = max(int(x.type.bitWidth) for x in all_exprs)

        def sized(x) -> ir.Expr:
            m = self.expr(x)
            if int(x.type.bitWidth) != w:
                m = self.cast(m, w, False)   # extends by x's own signedness
            return m

        subject = sized(s.expr)
        cases = []
        for xs, body in items:
            pats = [ir.PatternValue(value=sized(x)) for x in xs]
            pat = pats[0] if len(pats) == 1 else ir.PatternOr(patterns=pats)
            cases.append(ir.StmtMatchCase(pattern=pat, body=self.body(body), loc=self.loc(body)))
        if s.defaultCase is not None:
            cases.append(ir.StmtMatchCase(pattern=ir.PatternAs(), body=self.body(s.defaultCase)))
        return ir.StmtMatch(subject=subject, cases=cases)

    def for_loop(self, s) -> List[ir.Stmt]:
        if self._uses_port_array(s.body):
            return self.unrolled_for(s)
        out: List[ir.Stmt] = []
        for v in s.loopVars:
            if self.key(v) not in self.locals:
                out.append(self.declare(v, s))
        for init in s.initializers:
            out.extend(self.expr_stmt(init))
        if s.stopExpr is None:
            raise self.fail("a `for` loop needs a stop condition", s)
        body = self.body(s.body)
        for step in s.steps:
            body.extend(self.expr_stmt(step))
        out.append(ir.StmtWhile(test=self.expr(s.stopExpr), body=body))
        return out

    def assertion(self, s) -> ir.Stmt:
        if str(s.assertionKind) != "AssertionKind.Assert":
            raise self.fail("only immediate `assert` is supported", s)
        msg = "assertion failed"
        fail = s.ifFalse
        if fail is not None:
            for x in self.stmts_of(fail):
                if x.kind == SK.ExpressionStatement and x.expr.kind == EK.Call \
                        and x.expr.isSystemCall and x.expr.arguments:
                    a = x.expr.arguments[0]
                    if a.kind == EK.StringLiteral:
                        msg = str(a.value)
                    elif getattr(a, "constant", None) is not None:
                        msg = str(a.constant).strip('"')
        return ir.StmtAssert(test=self.expr(s.cond), msg=ir.ExprConstant(value=msg))

    # ------------------------------------------------------------------
    # Functions and components
    # ------------------------------------------------------------------
    def map_function(self, sub) -> ir.Function:
        if sub.subroutineKind != ast.SubroutineKind.Function:
            raise self.fail(f"{sub.name!r} is a task; only functions can be called", sub)
        name = self._fn_names[self.fn_key(sub)]
        saved = (self.locals, self.local_names, self.params, self.ret_var, self.in_function)
        self.locals, self.local_names, self.params = {}, set(), {}
        self.in_function = sub.name
        try:
            args = []
            for a in sub.arguments:
                if str(a.direction) != "ArgumentDirection.In":
                    raise self.fail(f"argument {a.name!r} of {sub.name!r} is not an input", a)
                self.params[self.key(a)] = a.name
                self.local_names.add(a.name)
                args.append(ir.Arg(arg=a.name, datatype=self.dtype(a.type, a, f"argument {a.name!r}", decl=True),
                                   loc=self.loc(a)))
            if sub.returnType is None or str(sub.returnType) == "void":
                raise self.fail(f"function {sub.name!r} must return a value", sub)
            ret_t = self.dtype(sub.returnType, sub, f"return value of {sub.name!r}", decl=True)
            body: List[ir.Stmt] = []
            rv = sub.returnValVar
            if rv is not None:
                self.ret_var = self.key(rv)
                rname = self.new_local(rv)
                body.append(_synth(ir.StmtAnnAssign(target=ir.ExprRefLocal(name=rname),
                                                    annotation=ir.ExprConstant(value=None),
                                                    ir_type=ret_t, value=None,
                                                    loc=self.loc(sub)), "retvar"))
            body.extend(self.body(sub.body))
            if rv is not None:
                # Falling off the end returns the function-name variable.
                body.append(_synth(ir.StmtReturn(
                    value=ir.ExprRefLocal(name=self.locals[self.ret_var])), "return"))
            return ir.Function(name=name, args=ir.Arguments(args=args), returns=ret_t,
                               body=body, loc=self.loc(sub))
        finally:
            (self.locals, self.local_names, self.params, self.ret_var,
             self.in_function) = saved

    def port_field(self, m, name: Optional[str] = None, ctype=None) -> Optional[ir.Field]:
        """The port field for property *m*; *name* and *ctype* override its
        name and type (one element of an array of ports)."""
        ct = (ctype or m.type).canonicalType
        pname = name or m.name
        if ct.kind != ast.SymbolKind.ClassType or ct.genericClass is None \
                or ct.genericClass.name != "fw_port":
            return None
        inner = None
        for x in ct:
            if x.kind == ast.SymbolKind.TypeParameter and x.name == "T":
                inner = x.targetType.type.canonicalType
        if inner is None or inner.kind != ast.SymbolKind.ClassType or inner.genericClass is None:
            raise self.fail(f"port {pname!r}: cannot read its interface type", m)
        api = inner.genericClass.name
        # Port APIs and their flow control are registry entries (fw.hdl.lib).
        from ..lib.registry import port_apis
        apis = port_apis()
        if api not in apis:
            raise self.fail(f"port {pname!r} uses {api}; the static subset has channel "
                            f"ports only ({' / '.join(sorted(apis))})", m)
        api_name = api
        nb = apis[api].polls
        flow = apis[api].flow
        api = "fw_get_if" if apis[api].direction == "get" else "fw_put_if"
        elem = None
        for x in inner:
            if x.kind == ast.SymbolKind.TypeParameter and x.name == "T":
                elem = x.targetType.type
        et = self.dtype(elem, m, f"payload of port {pname!r}", decl=True)
        self.port_dirs[pname] = "get" if api == "fw_get_if" else "put"
        if nb:
            self.port_nb.add(pname)
        if apis[api_name].stalls:
            self.port_stall.add(pname)
        dt = ir.DataTypeGetIF(element_type=et) if api == "fw_get_if" else \
            ir.DataTypePutIF(element_type=et)
        # The payload type as SV spells it from outside the class, for
        # generated harnesses and glue. A typedef inside the class is reached
        # through the class (or its specialization's typedef).
        sv_type = str(elem)
        ct_e = elem.canonicalType
        if elem.isAlias and sv_type.count("::") >= 2 and \
                (ct_e.isSimpleBitVector or ct_e.isScalar):
            # Declared in a class (a type parameter, or a class typedef): a
            # plain vector is spelled as itself.
            sv_type = str(ct_e)
        elif elem.isAlias and f"::{self.cls_name}::" in sv_type:
            sv_type = f"{self.cls_spelling}::{elem.name}"
        if flow != "ready_valid":
            self.port_flow[pname] = flow
        return ir.Field(name=pname, datatype=dt, kind=ir.FieldKind.Port, loc=self.loc(m),
                        pragmas={"sv_type": sv_type, **({"get_nb": True} if nb else {}),
                                 **({"put_step": True} if pname in self.port_stall else {}),
                                 **({"fw_flow": flow} if flow != "ready_valid" else {})})

    def map_component(self, cls, spelling: Optional[str] = None,
                      param_values: Optional[Dict[str, object]] = None) -> ir.DataTypeComponent:
        """Map component class *cls*. ``spelling`` is how SV names it from
        outside: the class name, or a typedef of a parameterized class's
        specialization; it names the component and its class-scoped types.
        ``param_values`` are this instance's ``m_params`` fields (an
        ``fw_component_param``), which the body reads as constants."""
        self.fields, self.port_dirs, self.port_nb = {}, {}, set()
        self.port_stall, self.port_flow = set(), {}
        self.param_values = dict(param_values or {})
        self.cls_name, self.cls_spelling = cls.name, spelling or cls.name
        fields: List[ir.Field] = []
        self.port_arrays, self.unroll_vals = {}, {}
        st = _atomic_state(cls)
        if st is not None:
            # fw_atomic_step's state: one packed struct, zero at reset.
            dt = self.dtype(st.type, st, "the step state 's'", decl=True)
            self.fields["s"] = 0
            fields.append(ir.Field(name="s", datatype=dt, loc=self.loc(st)))
        for m in cls:
            if m.kind == ast.SymbolKind.ClassProperty:
                n = self._port_array_len(m)
                if n is not None:
                    # An array of ports: one port per element (`in[2]` -> `in_2`).
                    et = m.type.canonicalType.elementType
                    self.port_arrays[m.name] = n
                    for k in range(n):
                        f = self.port_field(m, name=f"{m.name}_{k}", ctype=et)
                        f.pragmas["sv_name"] = f"{m.name}[{k}]"
                        self.fields[f.name] = len(fields)
                        fields.append(f)
                    continue
                f = self.port_field(m)
                if f is None:
                    dt = self.dtype(m.type, m, f"property {m.name!r}", decl=True)
                    f = ir.Field(name=m.name, datatype=dt, loc=self.loc(m))
                    init = getattr(m, "initializer", None)
                    if init is not None:
                        f.initial_value = self.expr(init)
                self.fields[m.name] = len(fields)
                fields.append(f)
        try:
            kind, run = find_behavior(cls)
        except ValueError as e:
            raise self.fail(f"class {cls.name!r} has both run() and step(); a component is a "
                            f"process (run) or a cycle step (step), not both", e.args[0]) from None
        if run is None:
            raise self.fail(f"class {cls.name!r} has no run() task or step() function", cls)
        if kind == "step" and _implements(cls, "fw_atomic_steppable"):
            kind = "atomic"
        self.behavior = kind
        self.locals, self.local_names, self.params = {}, set(), {}
        self.ret_var, self.in_function = None, None
        if kind in ("step", "atomic"):
            # One step() is one activation: the body of an implicit forever.
            # Its locals are declared inside it, so they are temporaries.
            run_body = [ir.StmtWhile(test=_synth(ir.ExprConstant(value=True), "step"),
                                     body=self.body(run.body))]
        else:
            run_body = self.body(run.body)
        run_fn = ir.Function(name="run", body=run_body, is_async=True, loc=self.loc(run),
                             metadata={"fw_step": True} if kind == "step" else
                             {"fw_step": True, "fw_stall": True} if kind == "atomic" else {})
        while self._fn_queue:
            sub = self._fn_queue.pop(0)
            fn = self.map_function(sub)
            self.functions[fn.name] = fn
        comp = ir.DataTypeComponent(name=self.cls_spelling, super=None, fields=fields,
                                    functions=list(self.functions.values()), loc=self.loc(cls))
        comp.proc_processes = [run_fn]
        return comp

    def map_functions(self, subs, names=None) -> List[ir.Function]:
        """Map free-standing functions (and what they call): the function corpus.

        *names*, if given, holds an IR name for each of *subs* (None keeps the
        SV name)."""
        self.fields, self.port_dirs, self.port_nb = {}, {}, set()
        for s, n in zip(subs, names or [None] * len(subs)):
            self.request_function(s, s, n)
        while self._fn_queue:
            sub = self._fn_queue.pop(0)
            fn = self.map_function(sub)
            self.functions[fn.name] = fn
        return list(self.functions.values())
