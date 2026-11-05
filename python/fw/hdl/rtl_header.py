"""Read a Verilog module's header: its parameters and ports, with widths
resolved for given parameter values.

The module is elaborated by pyslang as the only top, with the values applied
as parameter overrides, so a width written in terms of parameters
(``[W*2-1:0]``) comes back as a number. ANSI and non-ANSI headers both work.
"""
from __future__ import annotations

import dataclasses as dc
from typing import Dict, Iterable, List, Mapping, Optional, Union

Value = Union[int, str]


class HeaderError(Exception):
    pass


@dc.dataclass(frozen=True)
class HeaderPort:
    name: str
    direction: str              # "in" | "out" | "inout"
    width: int                  # bits; 0 for an interface port
    sv_type: str                # as slang prints it, e.g. "logic[36:0]"
    signed: bool = False
    interface: bool = False


@dc.dataclass(frozen=True)
class Header:
    module: str
    params: Dict[str, Value]            # every overridable value parameter
    localparams: Dict[str, Value]
    type_params: List[str]
    ports: List[HeaderPort]

    def port(self, name: str) -> Optional[HeaderPort]:
        return next((p for p in self.ports if p.name == name), None)


_DIR = {"In": "in", "Out": "out", "InOut": "inout", "Ref": "ref"}


def _value(cv) -> Value:
    s = str(cv)
    if s.startswith('"') and s.endswith('"'):
        return s[1:-1]
    try:
        return int(s)
    except ValueError:
        pass
    # Sized literals print as e.g. 8'd5 / 4'b1010.
    if "'" in s:
        size, _, rest = s.partition("'")
        rest = rest.lstrip("sS")
        base = {"d": 10, "h": 16, "b": 2, "o": 8}.get(rest[:1].lower())
        if base is not None:
            try:
                return int(rest[1:].replace("_", ""), base)
            except ValueError:
                pass
    return s


def _literal(v: Value) -> str:
    if isinstance(v, bool):
        return str(int(v))
    if isinstance(v, int):
        return str(v)
    return '"' + str(v).replace('"', '\\"') + '"'


def read_header(files: Iterable[str], module: str,
                params: Optional[Mapping[str, Value]] = None,
                defines: Optional[Mapping[str, str]] = None,
                include_dirs: Iterable[str] = ()) -> Header:
    """The header of *module* in *files*, elaborated with *params*.

    Raises :class:`HeaderError` if the module is not found, a value names no
    parameter of the module (or a localparam), or elaboration reports errors.
    """
    import pyslang
    from pyslang import ast, syntax

    params = dict(params or {})
    co = ast.CompilationOptions()
    co.topModules = {module}
    co.paramOverrides = [f"{k}={_literal(v)}" for k, v in params.items()]
    opts = [co]
    if defines or include_dirs:
        po = pyslang.parsing.PreprocessorOptions()
        if defines:
            po.predefines = [f"{k}={v}" for k, v in defines.items()]
        if include_dirs:
            po.additionalIncludePaths = [str(d) for d in include_dirs]
        opts.append(po)
    bag = pyslang.Bag(opts)
    sm = pyslang.SourceManager()
    comp = ast.Compilation(bag)
    for f in files:
        comp.addSyntaxTree(syntax.SyntaxTree.fromFile(str(f), sm, bag))
    tops = [i for i in comp.getRoot().topInstances if i.name == module]
    if not tops:
        raise HeaderError(f"module {module!r} not found in {[str(f) for f in files]}")
    errors = [d for d in comp.getAllDiagnostics() if d.isError()]
    if errors:
        text = pyslang.DiagnosticEngine.reportAll(sm, errors)
        raise HeaderError(f"module {module!r}: elaboration errors:\n{text}")
    body = tops[0].body

    values: Dict[str, Value] = {}
    local: Dict[str, Value] = {}
    types: List[str] = []
    for p in body.parameters:
        if getattr(p, "isType", False) or type(p).__name__ == "TypeParameterSymbol":
            types.append(p.name)
        elif p.isLocalParam:
            local[p.name] = _value(p.value)
        else:
            values[p.name] = _value(p.value)
    unknown = sorted(set(params) - set(values) - set(types))
    if unknown:
        bad = [n for n in unknown if n in local]
        why = (f"{', '.join(bad)} {'is a localparam' if len(bad) == 1 else 'are localparams'}"
               if bad else f"module parameters are {sorted(values) or 'none'}")
        raise HeaderError(f"module {module!r}: no parameter {', '.join(unknown)} ({why})")

    ports: List[HeaderPort] = []
    for p in body.portList:
        kind = type(p).__name__
        if kind == "InterfacePortSymbol":
            ports.append(HeaderPort(p.name, "inout", 0, "interface", interface=True))
            continue
        if kind != "PortSymbol":
            raise HeaderError(f"module {module!r}: port {p.name!r} of kind {kind} "
                              f"is not supported")
        t = p.type
        ports.append(HeaderPort(p.name, _DIR.get(str(p.direction).split(".")[-1], "inout"),
                                int(t.bitWidth), str(t), bool(t.isSigned)))
    return Header(module, values, local, types, ports)

