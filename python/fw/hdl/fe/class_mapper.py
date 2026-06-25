"""Map an fw-hdl component class to an SPL-level ``DataTypeComponent``.

P1 scope (DESIGN §5, "class only — no binding"): one runnable ``fw_component``
with own data/port fields plus a ``run`` task.  Process locals declared in
``run`` are **hoisted to component fields** (they are process state), so the
mapped process body is just the (forever) statement sequence and refers to those
fields by index.

The class->module boundary (synthesizing clock/reset/<pin> ports and giving the
``put``/``tick`` beats hardware meaning) is the job of ``fe/bind`` at P2; here a
port property like ``out`` is kept as a ``FieldKind.Port`` placeholder.
"""
from __future__ import annotations

from typing import Dict, Iterator, List, Optional

import zuspec.ir.core as ir
from pyslang import ast

from .. import ir_build
from ..config import FlowConfig
from ..errors import ErrorReporter
from .expr_mapper import ExprMapper, const_to_int
from .func_mapper import FuncMapper
from .stmt_mapper import StmtMapper
from .type_mapper import TypeMapper


class ClassMapper:
    def __init__(self, config: FlowConfig, reporter: ErrorReporter):
        self.config = config
        self.reporter = reporter
        self.type_mapper = TypeMapper(config, reporter)
        self.expr_mapper = ExprMapper(config, reporter)
        self.stmt_mapper = StmtMapper(config, reporter, self.expr_mapper)
        self.func_mapper = FuncMapper(config, reporter)

    # -- discovery -------------------------------------------------------
    def find_run(self, class_sym) -> Optional[object]:
        """Return the class's own ``run`` task (with a body), or ``None``."""
        for m in class_sym:
            if (m.kind == ast.SymbolKind.Subroutine
                    and getattr(m, "name", None) == "run"
                    and getattr(m, "subroutineKind", None) == ast.SubroutineKind.Task
                    and getattr(m, "body", None) is not None):
                return m
        return None

    def is_runnable(self, class_sym) -> bool:
        return self.find_run(class_sym) is not None

    # -- mapping ---------------------------------------------------------
    def map_component(self, class_sym) -> ir.DataTypeComponent:
        fields: List[ir.Field] = []
        scope: Dict[str, int] = {}

        def add(field: ir.Field) -> None:
            scope[field.name] = len(fields)
            fields.append(field)

        # 1. own ClassProperty fields (ports + data)
        for m in class_sym:
            if m.kind == ast.SymbolKind.ClassProperty:
                add(self._map_property(m))

        run = self.find_run(class_sym)
        if run is None:
            raise self.reporter.fail(f"component {class_sym.name!r} has no run() task")

        # 2. hoist run-local variables to component (state) fields
        for vdecl in self._iter_var_decls(run.body):
            add(self._map_local(vdecl))

        # 3. map the run body against the field scope
        self.expr_mapper.set_scope(scope)
        run_fn = self.func_mapper.map_run(run, self.stmt_mapper)

        return ir_build.component(class_sym.name, fields, proc_processes=[run_fn])

    # -- fields ----------------------------------------------------------
    def _map_property(self, m) -> ir.Field:
        t = m.type
        if getattr(t, "isIntegral", False):
            dt = self.type_mapper.map_type(t, what=f"field {m.name!r}")
            return ir.Field(name=m.name, datatype=dt or ir_build.int_t(1))
        # Non-integral property (e.g. fw_port#(fw_put_if#(T))): a port placeholder.
        elem = self._port_element_type(t) or ir_build.int_t(1)
        return ir.Field(name=m.name, datatype=elem, kind=ir.FieldKind.Port)

    def _map_local(self, vdecl) -> ir.Field:
        sym = vdecl.symbol
        dt = self.type_mapper.map_type(sym.type, what=f"local {sym.name!r}")
        field = ir.Field(name=sym.name, datatype=dt or ir_build.int_t(1), is_reg=True)
        init = getattr(sym, "initializer", None)
        if init is not None:
            value = const_to_int(getattr(init, "constant", None))
            if value is not None:
                field.initial_value = ir.ExprConstant(value=value)
        return field

    def _port_element_type(self, t) -> Optional[ir.DataTypeInt]:
        """Best-effort extraction of the element type from a parameterized port
        type (e.g. ``fw_port#(fw_put_if#(led_t))`` -> ``led_t``).  Returns None on
        failure; the P2 binding stage derives the authoritative pin type."""
        try:
            for arg in getattr(t, "typeArguments", []) or []:
                inner = getattr(arg, "isIntegral", False) and arg
                if inner:
                    return ir.DataTypeInt(bits=int(arg.bitWidth),
                                          signed=bool(getattr(arg, "isSigned", False)))
        except Exception:
            pass
        return None

    # -- local-variable collection ---------------------------------------
    def _iter_var_decls(self, body) -> Iterator[object]:
        for stmt in self._iter_statements(body):
            if stmt.kind == ast.StatementKind.VariableDeclaration:
                yield stmt

    def _iter_statements(self, s) -> Iterator[object]:
        """Yield every statement under *s* (recursively through bodies)."""
        if s is None:
            return
        k = s.kind
        if k == ast.StatementKind.List:
            for sub in s.list:
                yield from self._iter_statements(sub)
        elif k == ast.StatementKind.Block:
            yield from self._iter_statements(s.body)
        elif k == ast.StatementKind.ForeverLoop:
            yield from self._iter_statements(s.body)
        elif k == ast.StatementKind.Conditional:
            yield from self._iter_statements(s.ifTrue)
            if s.ifFalse is not None:
                yield from self._iter_statements(s.ifFalse)
        else:
            yield s
