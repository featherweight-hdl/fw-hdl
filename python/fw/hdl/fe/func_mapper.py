"""Map an fw-hdl ``run`` task to an async process ``Function``.

The ``run`` task becomes an entry in ``DataTypeComponent.proc_processes`` — a
sequential-process-level (SPL) coroutine whose body is the (possibly
``forever``) statement sequence.  Process locals have already been hoisted to
component fields by the class mapper, so the body refers to them as
``ExprRefField(self, ...)``.
"""
from __future__ import annotations

import zuspec.ir.core as ir

from ..config import FlowConfig
from ..errors import ErrorReporter
from .stmt_mapper import StmtMapper


class FuncMapper:
    def __init__(self, config: FlowConfig, reporter: ErrorReporter):
        self.config = config
        self.reporter = reporter

    def map_run(self, run_sym, stmt_mapper: StmtMapper) -> ir.Function:
        body = stmt_mapper.map_body(run_sym.body)
        return ir.Function(name=run_sym.name, body=body, is_async=True)
