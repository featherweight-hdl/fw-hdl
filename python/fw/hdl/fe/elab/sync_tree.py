"""Lower a statically elaborated sync composite to IR (plan-sync-rtl E10, S6.2s2).

:func:`fw.hdl.fe.elab.hier.elaborate_tree` runs the composite's
``new()``/``build()``/``connect()`` at compile time; the resulting
:class:`~fw.hdl.fe.elab.hier.Node` holds the children and the sync wiring
(``Node.sync_connects``). :func:`composite_components` turns that into one IR
component per distinct leaf class (:func:`~fw.hdl.fe.elab.sync.sync_component`,
named by ``Node.spelling()``) and a composite component that instantiates
them (``module_instances``) and joins their port fields with nets.

A ``connect`` or ``connect_up`` joins two sync ports field by field; every
joined set of fields is one net. A net that holds a field of the composite's
own port is that port; any other net is a wire named after its first child
field (``<child>_<port>_<field>``). Children with a ``step()`` get the
composite's ``clock`` and ``reset``.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from pyslang import ast

from zuspec.ir.core.connection import ModuleInstance, PortConnection
from zuspec.ir.core.data_type import DataTypeComponent
from zuspec.ir.core.fields import Field, FieldInOut

from . import hier
from .sync import (SyncElabError, _derives, _generic_name, _holder_fields, _int,
                   _members, _prop, sync_component)

_JOIN = ("connect", "connect_up")


def _sync_ports(ct) -> Dict[str, Tuple[bool, list]]:
    """``{prop: (is_out_view, [(field, width, dir, force)])}`` for the sync
    ports of class ``ct``."""
    out = {}
    for p in _members(ct, ast.SymbolKind.ClassProperty):
        t = p.type.canonicalType
        if t.kind != ast.SymbolKind.ClassType or not _derives(t, "fw_sync_port"):
            continue
        view = _generic_name(t)
        if not (view.endswith("_sp_out") or view.endswith("_sp_in")):
            raise SyncElabError(f"{ct.name}.{p.name}: view {view} is neither "
                                f"*_sp_in nor *_sp_out")
        sig = _prop(t, "sig")
        if sig is None:
            raise SyncElabError(f"{view}: no 'sig' holder")
        out[p.name] = (view.endswith("_sp_out"), _holder_fields(sig.type.canonicalType))
    return out


def composite_components(top: hier.Node) -> Dict[str, DataTypeComponent]:
    """IR components for composite ``top``: ``{module name: component}``, the
    composite (named ``top.name``) last."""
    out: Dict[str, DataTypeComponent] = {}
    mods: Dict[str, str] = {}           # node key -> module name
    child_ports: Dict[str, Dict[str, Tuple[bool, list]]] = {}
    for cname, n in top.children.items():
        if n.children:
            raise SyncElabError(f"{n.path}: nested composites are not lowered yet")
        if n.key() not in mods:
            mods[n.key()] = n.spelling()
            out[n.spelling()] = sync_component(n.cls, n.spelling())
        child_ports[cname] = _sync_ports(n.cls)
    own = _sync_ports(top.cls)

    # Union-find over "<child>.<port>.<field>" / ".<port>.<field>" (own port).
    parent: Dict[str, str] = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            x = parent[x]
        return x

    def port_of(path: str) -> Tuple[str, str, list]:
        rel = path[len(top.path) + 1:] if path.startswith(top.path + ".") else None
        parts = rel.split(".") if rel else []
        if len(parts) == 1 and parts[0] in own:
            return "", parts[0], own[parts[0]][1]
        if len(parts) == 2 and parts[1] in child_ports.get(parts[0], {}):
            return parts[0], parts[1], child_ports[parts[0]][parts[1]][1]
        raise SyncElabError(f"{top.path}: {path} is not a sync port of the composite "
                            f"or of a direct child")

    for method, recv, args in top.sync_connects:
        if method not in _JOIN:
            raise SyncElabError(f"{recv}.{method}: not lowered yet")
        ra, rp, rf = port_of(recv)
        aa, ap, af = port_of(args[0])
        if [f[:2] for f in rf] != [f[:2] for f in af]:
            raise SyncElabError(f"{recv}.{method}({args[0]}): field lists differ")
        for fname, *_ in rf:
            parent[find(f"{ra}.{rp}.{fname}")] = find(f"{aa}.{ap}.{fname}")

    comp = DataTypeComponent(name=top.name, super=None)
    clocked = any(m.sync_processes for m in out.values())
    if clocked:
        comp.fields.append(FieldInOut(name="clock", datatype=_int(1), is_out=False))
        comp.fields.append(FieldInOut(name="reset", datatype=_int(1), is_out=False))
    names: Dict[str, str] = {}          # net root -> signal name
    for pname, (is_out, fields) in own.items():
        drives = "FW_SYNC_FWD" if is_out else "FW_SYNC_BWD"
        for fname, w, d, _ in fields:
            r = find(f".{pname}.{fname}")
            if r in names:
                raise SyncElabError(f"{top.path}: ports {names[r]} and "
                                    f"{pname}_{fname} are joined")
            names[r] = f"{pname}_{fname}"
            comp.fields.append(FieldInOut(name=names[r], datatype=_int(w),
                                          is_out=(d == drives)))
    for cname, ports in child_ports.items():
        for pname, (_, fields) in ports.items():
            for fname, w, _, _ in fields:
                r = find(f"{cname}.{pname}.{fname}")
                if r not in names:
                    names[r] = f"{cname}_{pname}_{fname}"
                    comp.fields.append(Field(name=names[r], datatype=_int(w)))
    for cname, n in top.children.items():
        leaf = out[mods[n.key()]]
        conns = [PortConnection(port=f, signal=f) for f in ("clock", "reset")
                 if leaf.sync_processes]
        conns += [PortConnection(port=f"{p}_{fname}",
                                 signal=names[find(f"{cname}.{p}.{fname}")])
                  for p, (_, fields) in child_ports[cname].items() for fname, *_ in fields]
        comp.module_instances.append(ModuleInstance(module=mods[n.key()], name=cname,
                                                    connections=conns))
    out[top.name] = comp
    return out
