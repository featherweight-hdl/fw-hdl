"""Map pyslang expressions to :mod:`zuspec.ir.core` ``Expr`` nodes.

References to component fields / hoisted process locals resolve to
``ExprRefField(self, index)`` via a name->index *scope* installed by the class
mapper.  Relational operators map to ``ExprCompare`` (never ``ExprBin`` — the
spike trap; see ``ir_build``).  Method calls become ``ExprCall``; the statement
mapper decides whether to wrap a *task* call in ``ExprAwait`` (a time-consuming
beat).
"""
from __future__ import annotations

from typing import Dict, Optional

import zuspec.ir.core as ir
from pyslang import ast

from ..config import FlowConfig
from ..errors import ErrorReporter


_UNARY = {
    ast.UnaryOperator.BitwiseNot: ir.UnaryOp.Invert,
    ast.UnaryOperator.LogicalNot: ir.UnaryOp.Not,
    ast.UnaryOperator.Minus: ir.UnaryOp.USub,
    ast.UnaryOperator.Plus: ir.UnaryOp.UAdd,
}

# Relational operators -> CmpOp (rendered via ExprCompare).
_CMP = {
    ast.BinaryOperator.Equality: ir.CmpOp.Eq,
    ast.BinaryOperator.Inequality: ir.CmpOp.NotEq,
    ast.BinaryOperator.LessThan: ir.CmpOp.Lt,
    ast.BinaryOperator.LessThanEqual: ir.CmpOp.LtE,
    ast.BinaryOperator.GreaterThan: ir.CmpOp.Gt,
    ast.BinaryOperator.GreaterThanEqual: ir.CmpOp.GtE,
}

# Arithmetic / bitwise / shift operators -> BinOp.
_BIN = {
    ast.BinaryOperator.Add: ir.BinOp.Add,
    ast.BinaryOperator.Subtract: ir.BinOp.Sub,
    ast.BinaryOperator.Multiply: ir.BinOp.Mult,
    ast.BinaryOperator.Divide: ir.BinOp.Div,
    ast.BinaryOperator.Mod: ir.BinOp.Mod,
    ast.BinaryOperator.BinaryAnd: ir.BinOp.BitAnd,
    ast.BinaryOperator.BinaryOr: ir.BinOp.BitOr,
    ast.BinaryOperator.BinaryXor: ir.BinOp.BitXor,
    ast.BinaryOperator.LogicalShiftLeft: ir.BinOp.LShift,
    ast.BinaryOperator.LogicalShiftRight: ir.BinOp.RShift,
}


def parse_int_token(s) -> Optional[int]:
    """Parse an SV integer rendering to a Python int, or ``None``.

    Handles plain ints (``"100"``) and sized literals (``"32'd100"``,
    ``"8'hFF"``, ``"1'b0"``, signed ``"32'sd1"``).
    """
    if s is None:
        return None
    s = str(s).strip()
    if "'" in s:
        _, _, rest = s.partition("'")
        if not rest:
            return None
        if rest[0].lower() == "s":   # signed marker, e.g. 32'sd1
            rest = rest[1:]
        if not rest:
            return None
        base_ch, digits = rest[0].lower(), rest[1:].replace("_", "")
        base = {"b": 2, "o": 8, "d": 10, "h": 16}.get(base_ch)
        if base is None:
            return None
        try:
            return int(digits, base)
        except ValueError:
            return None
    try:
        return int(s)
    except ValueError:
        return None


def const_to_int(cv) -> Optional[int]:
    """Convert a pyslang ``ConstantValue`` to a Python int, or ``None``.

    ``expr.constant is None`` is the reliable "not constant" signal; note
    ``hasUnknown``/``empty`` are *methods* and ``empty()`` is unreliable (returns
    True even for a real value).
    """
    if cv is None:
        return None
    try:
        if cv.hasUnknown():   # x/z bits -> not a synthesizable constant
            return None
    except Exception:
        return None
    return parse_int_token(str(cv))


class ExprMapper:
    def __init__(self, config: FlowConfig, reporter: ErrorReporter):
        self.config = config
        self.reporter = reporter
        self.scope: Dict[str, int] = {}
        # Stack of the current assignment target(s); pyslang expands a compound
        # assignment ``x op= y`` into ``x = LValueReference op y`` where the
        # ``LValueReference`` resolves to the target.
        self._lvalue_stack: list = []

    def set_scope(self, scope: Dict[str, int]) -> None:
        """Install the name->field-index map for ``self`` references."""
        self.scope = scope

    def push_lvalue(self, target: ir.Expr) -> None:
        self._lvalue_stack.append(target)

    def pop_lvalue(self) -> None:
        self._lvalue_stack.pop()

    # -- dispatch --------------------------------------------------------
    def map(self, e) -> ir.Expr:
        # Fold genuinely-constant expressions (literals, localparams like
        # BLINK_TICKS).  pyslang only folds true constants, so a mutable
        # variable reference stays non-constant and falls through to a ref.
        const = self._maybe_const(e)
        if const is not None:
            return const

        k = e.kind
        if k == ast.ExpressionKind.IntegerLiteral:
            # A wrapping Conversion doesn't always fold; the literal's own SVInt
            # value is authoritative.
            value = parse_int_token(str(e.value))
            if value is None:
                raise self.reporter.fail(f"unsupported integer literal: {e.value}")
            return ir.ExprConstant(value=value)
        if k == ast.ExpressionKind.NamedValue:
            return self._named(e)
        if k == ast.ExpressionKind.LValueReference:
            if not self._lvalue_stack:
                raise self.reporter.fail("LValueReference outside an assignment")
            return self._lvalue_stack[-1]
        if k == ast.ExpressionKind.Conversion:
            return self.map(e.operand)
        if k == ast.ExpressionKind.UnaryOp:
            return self._unary(e)
        if k == ast.ExpressionKind.BinaryOp:
            return self._binary(e)
        if k == ast.ExpressionKind.MemberAccess:
            return ir.ExprAttribute(value=self.map(e.value), attr=e.member.name)
        if k == ast.ExpressionKind.ElementSelect:
            # bit-select, e.g. count[21]
            return ir.ExprSubscript(value=self.map(e.value), slice=self.map(e.selector))
        if k == ast.ExpressionKind.Call:
            return self.map_call(e)
        raise self.reporter.fail(f"unsupported expression: {k.name}")

    def map_call(self, e) -> ir.ExprCall:
        """Map a call to ``ExprCall`` (no await — callers wrap tasks)."""
        recv = self.map(e.thisClass) if e.thisClass is not None else ir.TypeExprRefSelf()
        func = ir.ExprAttribute(value=recv, attr=e.subroutineName)
        args = [self.map(a) for a in e.arguments]
        return ir.ExprCall(func=func, args=args, keywords=[])

    # -- helpers ---------------------------------------------------------
    def _maybe_const(self, e) -> Optional[ir.ExprConstant]:
        value = const_to_int(getattr(e, "constant", None))
        return None if value is None else ir.ExprConstant(value=value)

    def _named(self, e) -> ir.ExprRefField:
        name = e.symbol.name
        idx = self.scope.get(name)
        if idx is None:
            raise self.reporter.fail(f"unresolved reference: {name!r}")
        return ir.ExprRefField(base=ir.TypeExprRefSelf(), index=idx)

    def _unary(self, e) -> ir.ExprUnary:
        op = _UNARY.get(e.op)
        if op is None:
            raise self.reporter.fail(f"unsupported unary operator: {e.op}")
        return ir.ExprUnary(op=op, operand=self.map(e.operand))

    def _binary(self, e) -> ir.Expr:
        if e.op in _CMP:
            return ir.ExprCompare(
                left=self.map(e.left),
                ops=[_CMP[e.op]],
                comparators=[self.map(e.right)],
            )
        op = _BIN.get(e.op)
        if op is None:
            raise self.reporter.fail(f"unsupported binary operator: {e.op}")
        return ir.ExprBin(lhs=self.map(e.left), op=op, rhs=self.map(e.right))
