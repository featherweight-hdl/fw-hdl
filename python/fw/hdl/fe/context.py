"""sv2ir orchestration: parse fw-hdl SystemVerilog and build an SPL ``Context``.

Top-level entry point for the front end.  Parses the design (plus the fw-hdl
library) and maps each runnable component class to a ``DataTypeComponent`` keyed
into an :class:`zuspec.ir.core.Context`.
"""
from __future__ import annotations

from typing import List, Optional

import zuspec.ir.core as ir

from .. import ir_build
from ..config import FlowConfig
from ..errors import ErrorReporter
from .astdump import collect_user_classes
from .bind.elaborate import apply_binding, elaborate_binding
from .class_mapper import ClassMapper
from .parser import Parser


def build_spl_context(files: List[str],
                      config: FlowConfig,
                      reporter: ErrorReporter) -> Optional[ir.Context]:
    """Return the SPL-level IR ``Context`` for *files*, or ``None`` on error.

    Each runnable component is mapped (class -> SPL ``DataTypeComponent``) and,
    when its ``*_top`` ``fw_root`` binding is available, elaborated into concrete
    clock/reset/<pin> ports (DESIGN §3/§5).
    """
    parser = Parser(config, reporter)
    if not parser.parse(files):
        return None

    root = parser.get_root()
    classes = collect_user_classes(root)
    if config.top is not None:
        classes = [c for c in classes if c.name == config.top]
        if not classes:
            reporter.error(f"top component {config.top!r} not found")
            return None

    mapper = ClassMapper(config, reporter)
    components = []
    for cls in classes:
        if not mapper.is_runnable(cls):
            continue  # only runnable components are mapped
        comp = mapper.map_component(cls)
        bound = elaborate_binding(root, cls.name, reporter,
                                  top_module=config.top_module)
        if bound is not None and not reporter.has_errors():
            apply_binding(comp, bound, reporter)
        components.append(comp)

    if not components:
        reporter.error("no runnable component found to map")
        return None

    if reporter.has_errors():
        return None

    return ir_build.context(components)
