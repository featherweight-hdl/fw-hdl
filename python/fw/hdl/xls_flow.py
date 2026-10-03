"""SV (fw-hdl static subset) -> zuspec IR -> XLS IR.

The X0 path of ``xls-phase0.md``: parse with the fw-hdl library, map one
component class (or a set of functions) with :mod:`fw.hdl.fe.static_mapper`,
and lower with ``zuspec-be-xls``.
"""
from __future__ import annotations

from typing import List, Optional, Sequence

import zuspec.ir.core as ir
from pyslang import ast

from .config import FlowConfig
from .errors import ErrorReporter, FwHdlError
from .fe.astdump import collect_user_classes
from .fe.parser import Parser
from .fe.static_mapper import StaticMapper
from .fe.structure import Structure, StructureMapper


class XlsFlowError(Exception):
    pass


def _parse(files: Sequence[str], config: FlowConfig, reporter: ErrorReporter) -> Parser:
    parser = Parser(config, reporter)
    if not parser.parse(list(files), include_root=False):
        raise XlsFlowError("SV parse failed:\n" + "\n".join(str(d) for d in reporter.diagnostics))
    return parser


def _find_class(parser: Parser, top: str):
    """The class *top*: a class name, or a typedef of a class specialization."""
    classes = [c for c in collect_user_classes(parser.get_root()) if c.name == top]
    if not classes:
        # A parameterized class is chosen by a typedef of one specialization
        # (T7, FE-11): `typedef rle_enc #(8) rle_enc8_t;`.
        found = []

        def visit(sym):
            if sym.kind == ast.SymbolKind.TypeAlias and sym.name == top:
                ct = sym.targetType.type.canonicalType
                if ct.kind == ast.SymbolKind.ClassType:
                    found.append(ct)
            return True

        parser.get_root().visit(visit)
        classes = found[:1]
    if not classes:
        raise XlsFlowError(f"class {top!r} not found (a class name, or a typedef of a "
                           f"class specialization)")
    return classes[0]


def sv_to_component(files: Sequence[str], top: str,
                    config: Optional[FlowConfig] = None,
                    reporter: Optional[ErrorReporter] = None) -> ir.DataTypeComponent:
    """Map the component class *top* to static-subset IR."""
    config = config or FlowConfig()
    reporter = reporter or ErrorReporter()
    parser = _parse(files, config, reporter)
    return StaticMapper(config, reporter, parser.source_manager).map_component(
        _find_class(parser, top), spelling=top)


def sv_to_structure(files: Sequence[str], top: str,
                    config: Optional[FlowConfig] = None,
                    reporter: Optional[ErrorReporter] = None) -> Structure:
    """Map the structural component class *top*: its ports, children, channels
    and binds (``xls-phase2.md`` ST-2)."""
    config = config or FlowConfig()
    reporter = reporter or ErrorReporter()
    parser = _parse(files, config, reporter)
    return StructureMapper(config, reporter, parser.source_manager).map_structure(
        _find_class(parser, top), spelling=top)


def sv_to_functions(files: Sequence[str], names: Sequence[str],
                    config: Optional[FlowConfig] = None,
                    reporter: Optional[ErrorReporter] = None) -> List[ir.Function]:
    """Map the named package-level (or static class) functions, and their callees."""
    config = config or FlowConfig()
    reporter = reporter or ErrorReporter()
    parser = _parse(files, config, reporter)
    found = {}

    def visit(sym):
        if sym.kind == ast.SymbolKind.Subroutine and getattr(sym, "name", None) in names \
                and sym.subroutineKind == ast.SubroutineKind.Function \
                and sym.body is not None and sym.name not in found:
            found[sym.name] = sym
        return True

    parser.get_root().visit(visit)
    missing = [n for n in names if n not in found]
    if missing:
        raise XlsFlowError(f"function(s) not found: {missing}")
    return StaticMapper(config, reporter, parser.source_manager).map_functions(
        [found[n] for n in names])


def sv_to_xls(files: Sequence[str], top: str, config: Optional[FlowConfig] = None,
              reporter: Optional[ErrorReporter] = None):
    """The XLS package (``zuspec.be.xls.xir.Package``) for component *top*."""
    from zuspec.be.xls.lower_proc import lower_component
    return lower_component(sv_to_component(files, top, config, reporter))


def sv_functions_to_xls(files: Sequence[str], names: Sequence[str], top: Optional[str] = None,
                        config: Optional[FlowConfig] = None,
                        reporter: Optional[ErrorReporter] = None):
    """The XLS package for the named functions (top: *top* or the first name)."""
    from zuspec.be.xls import xir
    from zuspec.be.xls.lower_fn import lower_functions
    fns = sv_to_functions(files, names, config, reporter)
    pkg = xir.Package(name=(top or names[0]))
    lower_functions(pkg, fns)
    pkg.top = top or names[0]
    return pkg


__all__ = ["XlsFlowError", "FwHdlError", "sv_to_component", "sv_to_structure", "sv_to_functions",
           "sv_to_xls", "sv_functions_to_xls"]
