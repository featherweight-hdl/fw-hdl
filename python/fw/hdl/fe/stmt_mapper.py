"""Map pyslang statements to :mod:`zuspec.ir.core` ``Stmt`` nodes.

Body containers in pyslang normalize three ways — a ``StatementList`` (``.list``),
a ``BlockStatement`` (``.body``, which may itself be a single statement), or a
bare single statement.  :meth:`StmtMapper.stmts_of` flattens all three.

``forever`` becomes ``StmtWhile(True, ...)``.  A *task* call (e.g. ``put``,
``tick``) is a time-consuming **beat**: it maps to ``StmtExpr(ExprAwait(call))``.
``VariableDeclaration`` is dropped here — the class mapper hoists process locals
to component fields and captures their initializers.  Unsupported statements are
hard errors (``sv2ir`` is strict).
"""
from __future__ import annotations

from typing import List

import zuspec.ir.core as ir
from pyslang import ast

from ..config import FlowConfig
from ..errors import ErrorReporter
from .expr_mapper import ExprMapper


class StmtMapper:
    def __init__(self, config: FlowConfig, reporter: ErrorReporter,
                 expr_mapper: ExprMapper):
        self.config = config
        self.reporter = reporter
        self.expr = expr_mapper

    # -- body normalization ----------------------------------------------
    def stmts_of(self, s) -> List:
        """Flatten a body container into a list of leaf statements."""
        if s is None:
            return []
        if s.kind == ast.StatementKind.List:
            return list(s.list)
        if s.kind == ast.StatementKind.Block:
            return self.stmts_of(s.body)
        return [s]

    def map_body(self, s) -> List[ir.Stmt]:
        out: List[ir.Stmt] = []
        for stmt in self.stmts_of(s):
            out.extend(self.map(stmt))
        return out

    # -- dispatch --------------------------------------------------------
    def map(self, s) -> List[ir.Stmt]:
        k = s.kind
        if k in (ast.StatementKind.List, ast.StatementKind.Block):
            return self.map_body(s)
        if k == ast.StatementKind.VariableDeclaration:
            return []  # hoisted to a field by the class mapper
        if k == ast.StatementKind.ForeverLoop:
            return [ir.StmtWhile(test=ir.ExprConstant(value=True),
                                 body=self.map_body(s.body), orelse=[])]
        if k == ast.StatementKind.Conditional:
            return [self._conditional(s)]
        if k == ast.StatementKind.ExpressionStatement:
            return self._expr_stmt(s)
        raise self.reporter.fail(f"unsupported statement: {k.name}")

    # -- specific kinds --------------------------------------------------
    def _conditional(self, s) -> ir.StmtIf:
        if len(s.conditions) != 1:
            raise self.reporter.fail(
                "unsupported multi-condition if (pattern/&&-in-condition)")
        test = self.expr.map(s.conditions[0].expr)
        body = self.map_body(s.ifTrue)
        orelse = self.map_body(s.ifFalse) if s.ifFalse is not None else []
        return ir.StmtIf(test=test, body=body, orelse=orelse)

    def _expr_stmt(self, s) -> List[ir.Stmt]:
        e = s.expr
        k = e.kind
        if k == ast.ExpressionKind.Assignment:
            return [self._assign(e)]
        if k == ast.ExpressionKind.Call:
            return [self._call_stmt(e)]
        if k == ast.ExpressionKind.UnaryOp:
            return [self._unary_stmt(e)]
        raise self.reporter.fail(f"unsupported expression-statement: {k.name}")

    def _assign(self, e) -> ir.StmtAssign:
        target = self.expr.map(e.left)
        # ``e.right`` is already the full RHS, including pyslang's expansion of a
        # compound ``x op= y`` to ``x = LValueReference op y``; resolve the
        # LValueReference back to ``target`` while mapping it.
        self.expr.push_lvalue(target)
        try:
            value = self.expr.map(e.right)
        finally:
            self.expr.pop_lvalue()
        return ir.StmtAssign(targets=[target], value=value)

    def _call_stmt(self, e) -> ir.StmtExpr:
        call = self.expr.map_call(e)
        # A task call consumes time -> it is an awaited beat.
        if e.subroutineKind == ast.SubroutineKind.Task:
            return ir.StmtExpr(expr=ir.ExprAwait(value=call))
        return ir.StmtExpr(expr=call)

    def _unary_stmt(self, e) -> ir.StmtAssign:
        """``x++`` / ``x--`` (and pre- forms) as statements -> ``x = x +/- 1``."""
        incr = {ast.UnaryOperator.Postincrement, ast.UnaryOperator.Preincrement}
        decr = {ast.UnaryOperator.Postdecrement, ast.UnaryOperator.Predecrement}
        if e.op in incr:
            op = ir.BinOp.Add
        elif e.op in decr:
            op = ir.BinOp.Sub
        else:
            raise self.reporter.fail(f"unsupported unary statement: {e.op}")
        target = self.expr.map(e.operand)
        value = ir.ExprBin(lhs=self.expr.map(e.operand), op=op, rhs=ir.ExprConstant(value=1))
        return ir.StmtAssign(targets=[target], value=value)
