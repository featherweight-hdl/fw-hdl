"""fw-hdl's recognized classes, as name-keyed entries in the zuspec
lowering registry (``zuspec.ir.core.LoweringRegistry.register_external``).

A leaf child whose generic class has an entry is not mapped from its body:
Partition takes the entry's lowering instead. Each entry names the class
parameters it accepts; a parameter value it does not take is an error at the
child's SV line, not a fallback to mapping the body.

======================  ========  ===========================================
class                   target    lowering
======================  ========  ===========================================
``fw_credit_tx``        xls       :func:`.xls_ir.credit_tx`
``fw_arbiter``          xls       :func:`.xls_ir.rr_arb` (``FW_ARB_RR`` only)
``fw_reg_component``    native    :mod:`fw.hdl.native` (regblock core)
``fw_channel`` and      elab      :class:`ChannelKind`: the channel's kind
the other channels
``fw_get_if`` and the   elab      :class:`PortApi`: the port's direction and
other port APIs                   flow control
======================  ========  ===========================================

The entries load through the ``zuspec.lowering`` entry point (``register``)
and, for an install that predates it, on first use (:func:`registry`).

Parameters reach a lowering as Python values: an ``int`` parameter as an
int, an enum parameter as its enumerator's name, and a type parameter as its
width in bits (a class type as its name).

A class is recognized by its own generic class or by the nearest base that
has an entry (a register-block child extends ``fw_reg_component #(BLK)``). A
subclass of a recognized class may not define ``run()``: its body would be
replaced by the lowering.
"""
from __future__ import annotations

import dataclasses as dc
from typing import Any, Callable, Dict, List, Optional

from zuspec.ir.core import global_registry

from . import xls_ir

ORIGIN = "fw.hdl.lib"


@dc.dataclass(frozen=True)
class XlsLowering:
    """``text(params, name)`` is the IR package for one block named *name*;
    ``ports`` are the class's port names in the order the IR declares them."""
    text: Callable[[Dict[str, Any], str], str]
    ports: Callable[[Dict[str, Any]], List[str]]


@dc.dataclass(frozen=True)
class NativeLowering:
    kind: str


@dc.dataclass(frozen=True)
class ChannelKind:
    """A channel class: ``ready_valid``, ``valid`` or ``level``."""
    kind: str


@dc.dataclass(frozen=True)
class PortApi:
    """A port API: ``get`` or ``put``, its flow control, and whether a get
    may poll (``try_get``)."""
    direction: str
    flow: str
    polls: bool = False


def _clog2(n: int) -> int:
    return max(1, (n - 1).bit_length())


def _credit_tx(p: Dict[str, Any], name: str) -> str:
    return xls_ir.package(name, xls_ir.credit_tx(
        width=p["T"], credits=p["CREDITS"], cbits=(p["CREDITS"]).bit_length() or 1, name=name,
        ports=("in", "cr", "out")))


def _arbiter(p: Dict[str, Any], name: str) -> str:
    n = p["N"]
    return xls_ir.package(name, xls_ir.rr_arb(n=n, width=p["T"], name=name,
                                              ins=[f"in_{k}" for k in range(n)], out="out"))


ENTRIES = [
    ("fw_credit_tx", {"T": int, "CREDITS": range(1, 1 << 16)}, "xls",
     XlsLowering(_credit_tx, lambda p: ["in", "cr", "out"])),
    ("fw_arbiter", {"T": int, "N": range(2, 65), "POLICY": ("FW_ARB_RR",)}, "xls",
     XlsLowering(_arbiter, lambda p: [f"in_{k}" for k in range(p["N"])] + ["out"])),
    ("fw_reg_component", {"BLK": str, "W": (8, 16, 32, 64), "AW": range(1, 65)}, "native",
     NativeLowering("regblock")),
    ("fw_channel", {"T": object, "DEPTH": int}, "elab", ChannelKind("ready_valid")),
    ("fw_valid_channel", {"T": object, "DEPTH": int}, "elab", ChannelKind("valid")),
    ("fw_level_channel", {"T": object}, "elab", ChannelKind("level")),
    ("fw_get_if", {"T": object}, "elab", PortApi("get", "ready_valid")),
    ("fw_get_nb_if", {"T": object}, "elab", PortApi("get", "ready_valid", polls=True)),
    ("fw_put_if", {"T": object}, "elab", PortApi("put", "ready_valid")),
    ("fw_valid_put_if", {"T": object}, "elab", PortApi("put", "valid")),
    ("fw_level_if", {"T": object}, "elab", PortApi("get", "level")),
    ("fw_level_set_if", {"T": object}, "elab", PortApi("put", "level")),
]


def register(reg) -> None:
    """The ``zuspec.lowering`` entry point. Idempotent for fw-hdl's own entries."""
    have = {(e.name, e.target) for e in reg.externals() if e.origin == ORIGIN}
    for name, params, target, lowering in ENTRIES:
        if (name, target) not in have:
            reg.register_external(name, params, target, lowering, origin=ORIGIN)


def registry():
    """The global registry, with fw-hdl's entries in it."""
    reg = global_registry()
    register(reg)
    return reg


def channel_kinds() -> Dict[str, str]:
    """Channel class name -> kind, from the registry."""
    return {e.name: e.lowering.kind for e in registry().externals("elab")
            if isinstance(e.lowering, ChannelKind)}


def port_apis() -> Dict[str, PortApi]:
    """Port API name -> :class:`PortApi`, from the registry."""
    return {e.name: e.lowering for e in registry().externals("elab")
            if isinstance(e.lowering, PortApi)}


def class_params(cls) -> Dict[str, Any]:
    """The parameters of a pyslang class specialization, as lowerings take them."""
    from pyslang import ast
    from ..fe.elab.values import const_to_py
    out: Dict[str, Any] = {}
    for x in cls:
        if x.kind == ast.SymbolKind.TypeParameter:
            t = x.targetType.type.canonicalType
            out[x.name] = t.name if t.kind == ast.SymbolKind.ClassType \
                else int(t.bitWidth)
        elif x.kind == ast.SymbolKind.Parameter and not x.isLocalParam:
            v = const_to_py(x.value)
            t = x.type.canonicalType
            if t.kind == ast.SymbolKind.EnumType:
                names = [m.name for m in t if m.kind == ast.SymbolKind.EnumValue
                         and int(const_to_py(m.value)) == int(v)]
                v = names[0] if names else v
            out[x.name] = int(v) if isinstance(v, (int, bool)) and not isinstance(v, str) else v
    return out


class SubclassError(Exception):
    """A subclass of a recognized class defines run()."""

    def __init__(self, msg: str, node=None):
        super().__init__(msg)
        self.node = node


def recognize(cls, target: str):
    """The registry hit for class *cls* on *target*, or None. Raises
    ``RecognitionError`` for parameters the entry does not take and
    :class:`SubclassError` for a subclass that defines ``run()``."""
    from pyslang import ast
    reg = registry()
    ct, own_run = cls, None
    while ct is not None and ct.kind == ast.SymbolKind.ClassType:
        g = getattr(ct, "genericClass", None)
        name = g.name if g is not None else ct.name
        if any(e.name == name for e in reg.externals(target)):
            if own_run is not None:
                raise SubclassError(f"{cls.name} extends {name}, which the registry lowers "
                                    f"({target}); it may not define run() or step()", own_run)
            return reg.lookup(name, class_params(ct), target)
        m = next((x for x in ct if x.kind == ast.SymbolKind.Subroutine
                  and x.name in ("run", "step")), None)          # declared here, not inherited
        if m is not None and own_run is None:
            own_run = m
        b = ct.baseClass
        ct = b.canonicalType if b is not None else None
    return None
