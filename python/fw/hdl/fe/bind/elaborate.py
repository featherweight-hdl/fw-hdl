"""Elaborate the ``fw_root`` binding in a ``*_top`` module into a BoundDesign.

Reads, structurally (not from a hard-coded pin table):
  - the top module's pins (clock/reset/<data>) and their widths;
  - the ``fw_root`` instance's clock/reset connections (identifies which pins are
    clock and reset);
  - the generated ``<top>_bind`` class's ``connect()`` body, which carries each
    ``port.connect(bridge)`` binding (the ``fw_root_bind_port`` macro expansion).

The *protocol meaning* of each bridge (e.g. ``fw_put_xtor_bridge`` -> registered
output ``put`` beat) comes from the Option-B table in :mod:`.protocols` — the one
hard-coded piece (DESIGN §3 debt).
"""
from __future__ import annotations

import dataclasses as dc
from typing import Dict, List, Optional

from pyslang import ast

from ...errors import ErrorReporter
from . import protocols

_FW_ROOT_DEF = "fw_root"


@dc.dataclass
class PortBinding:
    class_port: str      # the component class port, e.g. 'out'
    protocol: str        # 'put'
    pin: str             # the module pin the data lands on, e.g. 'led'
    width: int           # pin width
    pin_dir: str         # 'output' / 'input'
    registered: bool     # put: 1-cycle registered beat


@dc.dataclass
class BoundDesign:
    component: str                       # the root component class, e.g. 'blinky'
    clock_pin: Optional[str]
    reset_pin: Optional[str]
    bindings: List[PortBinding] = dc.field(default_factory=list)


def _sym_name(expr) -> Optional[str]:
    """Resolve the referenced symbol name, unwrapping implicit Conversions."""
    if expr is None:
        return None
    try:
        ref = expr.getSymbolReference()
        if ref is not None and getattr(ref, "name", None):
            return ref.name
    except Exception:
        pass
    sym = getattr(expr, "symbol", None)
    return getattr(sym, "name", None) if sym is not None else None


def _module_ports(body) -> Dict[str, dict]:
    """name -> {dir, width}."""
    ports: Dict[str, dict] = {}
    for m in body:
        if m.kind == ast.SymbolKind.Port:
            t = getattr(m, "type", None)
            ports[m.name] = {
                "dir": str(getattr(m, "direction", "")),
                "width": int(getattr(t, "bitWidth", 1)) if t is not None else 1,
            }
    return ports


def _instances(body) -> Dict[str, object]:
    return {m.name: m for m in body
            if m.kind == ast.SymbolKind.Instance}


def _conn_map(instance) -> Dict[str, Optional[str]]:
    """transactor formal-port name -> connected signal name."""
    out: Dict[str, Optional[str]] = {}
    for c in instance.portConnections:
        expr = getattr(c, "expression", None)
        out[c.port.name] = _sym_name(expr) if expr is not None else None
    return out


def _find_bind_class(body):
    for m in body:
        if m.kind == ast.SymbolKind.ClassType and m.name.endswith("_bind"):
            return m
    return None


def _iter_statements(s):
    if s is None:
        return
    k = s.kind
    if k == ast.StatementKind.List:
        for sub in s.list:
            yield from _iter_statements(sub)
    elif k == ast.StatementKind.Block:
        yield from _iter_statements(s.body)
    else:
        yield s


def _collect_connect_bindings(connect_sym, reporter: ErrorReporter):
    """Return list of (class_port, bridge_name, xtor_instance) from connect()."""
    bridge_vars: Dict[str, tuple] = {}   # var_name -> (bridge_name, xtor_instance)
    connects: List[tuple] = []           # (class_port, bridge_var)

    for s in _iter_statements(connect_sym.body):
        if s.kind == ast.StatementKind.VariableDeclaration:
            sym = s.symbol
            bname = getattr(sym.type, "name", None)
            if bname in protocols.STD_TRANSACTORS:
                xtor = _new_xtor_instance(getattr(sym, "initializer", None))
                bridge_vars[sym.name] = (bname, xtor)
        elif s.kind == ast.StatementKind.ExpressionStatement:
            e = s.expr
            if (e.kind == ast.ExpressionKind.Call
                    and getattr(e, "subroutineName", None) == "connect"
                    and e.thisClass is not None
                    and e.arguments):
                port = _sym_name(e.thisClass)
                var = _sym_name(e.arguments[0])
                if port and var:
                    connects.append((port, var))

    out = []
    for port, var in connects:
        if var in bridge_vars:
            bridge_name, xtor = bridge_vars[var]
            out.append((port, bridge_name, xtor))
    return out


def _new_xtor_instance(new_expr) -> Optional[str]:
    """The transactor instance passed to a bridge's ``new(name, parent, vif)``."""
    if new_expr is None:
        return None
    cc = getattr(new_expr, "constructorCall", None)
    if cc is None:
        return None
    # The vif is the instance-typed argument (last positional in the std bridges).
    for arg in reversed(list(cc.arguments)):
        name = _sym_name(arg)
        if name is not None:
            return name
    return None


def elaborate_binding(root, component: str,
                      reporter: ErrorReporter,
                      top_module: Optional[str] = None) -> Optional[BoundDesign]:
    """Build the :class:`BoundDesign` for *component* from its ``*_top`` module.

    Returns ``None`` (no error) when there is simply no top module to elaborate
    (class-only usage); errors only when an explicitly-requested ``top_module``
    is missing or its binding is malformed.
    """
    top = _select_top(root, top_module)
    if top is None:
        if top_module is not None:
            reporter.error(f"top module {top_module!r} not found")
        return None
    body = top.body

    ports = _module_ports(body)
    instances = _instances(body)

    # clock / reset pins from the fw_root instance's connections
    clock_pin = reset_pin = None
    for inst in instances.values():
        if getattr(getattr(inst, "definition", None), "name", None) == _FW_ROOT_DEF:
            conns = _conn_map(inst)
            clock_pin = conns.get("clock")
            reset_pin = conns.get("reset")
            break

    bind_cls = _find_bind_class(body)
    if bind_cls is None:
        reporter.error(f"no *_bind class found in module {top.name!r}")
        return None
    connect_sym = next((m for m in bind_cls
                        if m.kind == ast.SymbolKind.Subroutine and m.name == "connect"), None)
    if connect_sym is None:
        reporter.error(f"bind class {bind_cls.name!r} has no connect()")
        return None

    bindings: List[PortBinding] = []
    for class_port, bridge_name, xtor in _collect_connect_bindings(connect_sym, reporter):
        spec = protocols.lookup(bridge_name)
        if spec is None:                       # unsupported transactor -> hard error
            reporter.error(f"unsupported transactor bridge {bridge_name!r} "
                           f"(no entry in the std-transactor table)")
            continue
        xtor_inst = instances.get(xtor)
        if xtor_inst is None:
            reporter.error(f"transactor instance {xtor!r} not found in {top.name!r}")
            continue
        pin = _conn_map(xtor_inst).get(spec.data_port)
        if pin is None or pin not in ports:
            reporter.error(f"could not resolve pin for {class_port!r} "
                           f"(transactor {xtor!r}.{spec.data_port})")
            continue
        bindings.append(PortBinding(
            class_port=class_port, protocol=spec.protocol, pin=pin,
            width=ports[pin]["width"], pin_dir=spec.pin_dir, registered=spec.registered))

    return BoundDesign(component=component, clock_pin=clock_pin,
                       reset_pin=reset_pin, bindings=bindings)


def apply_binding(component, bound: BoundDesign, reporter: ErrorReporter) -> None:
    """Inject pin fields and tag the bound class ports on *component* in place.

    Pins are **appended** so the existing field indices (referenced by the run
    process) stay valid.  Roles are carried in ``Field.pragmas`` so the IR is
    self-contained for the lowering pass (P3).
    """
    import zuspec.ir.core as ir

    def pin(name: str, width: int, *, is_out: bool, pragmas: dict):
        f = ir.FieldInOut(name=name,
                          datatype=ir.DataTypeInt(bits=width, signed=False),
                          is_out=is_out)
        f.pragmas.update(pragmas)
        return f

    by_name = {f.name: f for f in component.fields}

    # Tag each bound class port so P3 can resolve the protocol beat to its pin.
    for b in bound.bindings:
        port_field = by_name.get(b.class_port)
        if port_field is not None:
            port_field.pragmas.update({
                "fw_protocol": b.protocol,
                "fw_pin": b.pin,
                "fw_registered": b.registered,
            })

    # Inject clock / reset input pins.
    if bound.clock_pin and bound.clock_pin not in by_name:
        component.fields.append(pin(bound.clock_pin, 1, is_out=False,
                                    pragmas={"fw_role": "clock"}))
    if bound.reset_pin and bound.reset_pin not in by_name:
        component.fields.append(pin(bound.reset_pin, 1, is_out=False,
                                    pragmas={"fw_role": "reset"}))

    # Inject the data pins (e.g. the LED output).
    seen = {f.name for f in component.fields}
    for b in bound.bindings:
        if b.pin in seen:
            continue
        seen.add(b.pin)
        component.fields.append(pin(
            b.pin, b.width, is_out=(b.pin_dir == "output"),
            pragmas={"fw_role": "pin", "fw_protocol": b.protocol,
                     "fw_source_port": b.class_port, "fw_registered": b.registered}))


def _select_top(root, top_module: Optional[str]):
    tops = list(getattr(root, "topInstances", []) or [])
    if top_module is not None:
        for t in tops:
            if t.name == top_module or getattr(t.body, "name", None) == top_module:
                return t
        # fall through: maybe not a top-level instance
        return None
    return tops[0] if tops else None
