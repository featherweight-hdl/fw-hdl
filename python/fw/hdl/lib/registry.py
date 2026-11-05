"""fw-hdl's recognized classes, as name-keyed entries in the zuspec
lowering registry (``zuspec.ir.core.LoweringRegistry.register_external``).

A leaf child whose generic class has an entry is not mapped from its body:
Partition takes the entry's lowering instead. Each entry names the class
parameters it accepts; a parameter value it does not take is an error at the
child's SV line, not a fallback to mapping the body.

======================  ========  ===========================================
class                   target    lowering
======================  ========  ===========================================
``fw_reg_component``    native    :mod:`fw.hdl.native` (regblock core)
``fw_channel`` and      elab      :class:`ChannelKind`: the channel's kind
the other channels
``fw_get_if`` and the   elab      :class:`PortApi`: the port's direction and
other port APIs                   flow control
``fw_keyed_table`` and  elab      :class:`StorageKind`: the storage bindings
the other tables                  it allows (flops only), and why
``fw_sp_mem``           elab      :class:`MemoryKind`: a member array in a
                                  RAM (its ports, read latency, bindings)
======================  ========  ===========================================

A channel's :class:`ChannelKind` also lists the storage bindings it allows
(knob ``storage:``, :mod:`fw.hdl.storage`).

A library class written as a cycle step (``fw_credit_tx``, ``fw_arbiter``)
has no entry: its step() is mapped like any other component's.

The entries load through the ``zuspec.lowering`` entry point (``register``)
and, for an install that predates it, on first use (:func:`registry`).

Parameters reach a lowering as Python values: an ``int`` parameter as an
int, an enum parameter as its enumerator's name, and a type parameter as its
width in bits (a class type as its name).

Besides the classes above, an entry may target ``zuspec``
(:class:`ZuspecLowering`): a factory that builds the block as Zuspec IR from
the parameters. The ``xls`` target (:class:`XlsLowering`, IR text) remains
for a user with an existing XLS proc; the library itself does not use it.

A class is recognized by its own generic class or by the nearest base that
has an entry (a register-block child extends ``fw_reg_component #(BLK)``). A
subclass of a recognized class may not define ``run()``: its body would be
replaced by the lowering.
"""
from __future__ import annotations

import dataclasses as dc
from typing import Any, Callable, Dict, List, Optional

from zuspec.ir.core import global_registry


ORIGIN = "fw.hdl.lib"


@dc.dataclass(frozen=True)
class XlsLowering:
    """``text(params, name)`` is the IR package for one block named *name*;
    ``ports`` are the class's port names in the order the IR declares them."""
    text: Callable[[Dict[str, Any], str], str]
    ports: Callable[[Dict[str, Any]], List[str]]


@dc.dataclass(frozen=True)
class ZuspecLowering:
    """``component(params, name, ports)`` builds the block as Zuspec IR: a
    ``DataTypeComponent`` named *name*, whose port fields are taken from
    *ports* (the child's port fields, by name). Partition treats it like a
    class it mapped itself, so any backend can lower it. For a class whose
    model cannot be its implementation (a staged variant, say)."""
    component: Callable[[Dict[str, Any], str, Dict[str, Any]], Any]


@dc.dataclass(frozen=True)
class NativeLowering:
    kind: str


@dc.dataclass(frozen=True)
class ChannelKind:
    """A channel class: ``ready_valid``, ``valid`` or ``level``, and the
    storage bindings (knob ``storage:``) it allows; a level holds no storage."""
    kind: str
    bindings: tuple = ()


@dc.dataclass(frozen=True)
class StorageKind:
    """A class that holds storage in its own state: the bindings it allows,
    and the reason it allows no others."""
    bindings: tuple
    why: str


@dc.dataclass(frozen=True)
class MemoryKind:
    """A memory member of a step class: an array held outside the block in a
    RAM with *ports* access ports and a *read_latency*-cycle read, and the
    storage bindings (knob ``storage:``) it allows. Every binding has that
    timing."""
    ports: int
    read_latency: int
    bindings: tuple


@dc.dataclass(frozen=True)
class PortApi:
    """A port API: ``get`` or ``put``, its flow control, whether a get may
    poll (``try_get``), and whether a put may stall an all-or-nothing step
    (``put_or_stall``)."""
    direction: str
    flow: str
    polls: bool = False
    stalls: bool = False


ENTRIES = [
    ("fw_reg_component", {"BLK": str, "W": (8, 16, 32, 64), "AW": range(1, 65)}, "native",
     NativeLowering("regblock")),
    ("fw_channel", {"T": object, "DEPTH": int}, "elab",
     ChannelKind("ready_valid", ("flops", "wrapper", "xls_fifo", "sram"))),
    ("fw_valid_channel", {"T": object, "DEPTH": int}, "elab",
     ChannelKind("valid", ("flops", "wrapper", "sram"))),
    ("fw_level_channel", {"T": object}, "elab", ChannelKind("level")),
    ("fw_get_if", {"T": object}, "elab", PortApi("get", "ready_valid")),
    ("fw_get_nb_if", {"T": object}, "elab", PortApi("get", "ready_valid", polls=True)),
    ("fw_put_if", {"T": object}, "elab", PortApi("put", "ready_valid")),
    ("fw_put_step_if", {"T": object}, "elab", PortApi("put", "ready_valid", stalls=True)),
    ("fw_valid_put_if", {"T": object}, "elab", PortApi("put", "valid")),
    ("fw_level_if", {"T": object}, "elab", PortApi("get", "level")),
    ("fw_level_set_if", {"T": object}, "elab", PortApi("put", "level")),
    ("fw_sp_mem", {"T": object, "WORDS": int}, "elab",
     MemoryKind(1, 1, ("flops", "wrapper", "sram"))),
] + [
    (name, {}, "elab", StorageKind(("flops",), "it reads every entry each cycle"))
    for name in ("fw_keyed_table", "fw_token_pool", "fw_slot_reserve", "fw_dep_tracker")
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


def channel_bindings() -> Dict[str, tuple]:
    """Channel kind -> the storage bindings it allows, from the registry."""
    return {e.lowering.kind: e.lowering.bindings for e in registry().externals("elab")
            if isinstance(e.lowering, ChannelKind)}


def storage_kind(cls) -> Optional[StorageKind]:
    """The :class:`StorageKind` of class *cls* (by its generic class or the
    nearest base with an entry), or None."""
    from pyslang import ast
    kinds = {e.name: e.lowering for e in registry().externals("elab")
             if isinstance(e.lowering, StorageKind)}
    ct = cls
    while ct is not None and ct.kind == ast.SymbolKind.ClassType:
        g = getattr(ct, "genericClass", None)
        name = g.name if g is not None else ct.name
        if name in kinds:
            return kinds[name]
        b = ct.baseClass
        ct = b.canonicalType if b is not None else None
    return None


def memory_kinds() -> Dict[str, MemoryKind]:
    """Memory class name -> :class:`MemoryKind`, from the registry."""
    return {e.name: e.lowering for e in registry().externals("elab")
            if isinstance(e.lowering, MemoryKind)}


def memories(cls) -> List[Dict[str, Any]]:
    """The memory members of class *cls* (and its bases): one
    ``{name, class, words, bits, addr_bits, bindings}`` each, in declaration
    order."""
    from pyslang import ast
    kinds = memory_kinds()
    out: List[Dict[str, Any]] = []
    ct = cls
    while ct is not None and ct.kind == ast.SymbolKind.ClassType:
        for m in ct:
            if m.kind != ast.SymbolKind.ClassProperty:
                continue
            t = m.type.canonicalType
            g = getattr(t, "genericClass", None) if t.kind == ast.SymbolKind.ClassType else None
            if g is None or g.name not in kinds:
                continue
            p = class_params(t)
            words, bits = int(p["WORDS"]), int(p["T"])
            out.append({"name": m.name, "class": g.name, "words": words, "bits": bits,
                        "addr_bits": max(1, (words - 1).bit_length()),
                        "bindings": list(kinds[g.name].bindings)})
        b = ct.baseClass
        ct = b.canonicalType if b is not None else None
    return out


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
