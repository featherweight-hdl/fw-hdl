"""The pin shell of a lowered sync class: protocol (AMBA) pin names around the
module that :func:`fw.hdl.fe.elab.sync.sync_component` lowers.

A role-port member with a pin preset::

    (* fw_pins = "s_axi_" *) axi4_sub_sp #(P) s;

is lowered to ``s_<ch>valid/ready/data`` (the payload packed in one vector).
The shell module ``<var>_pins`` instantiates ``<var>`` and gives the port one
pin per payload struct member, named ``<preset><ch><member>`` (``s_axi_awaddr``),
plus ``<preset><ch>valid/ready``. A member marked ``(* fw_opt = "NAME" *)`` is
absent when the payload's parameter ``P.NAME`` is 0 (as in the field table of
``<proto>_sp::build_fields()``): an absent input is tied to 0, an absent output
dropped. Ports without a preset, and clock/reset, keep their names.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from pyslang import ast
from zuspec.ir.core.data_type import DataTypeComponent
from zuspec.ir.core.fields import FieldInOut

from fw.hdl.fe.elab.sync import (SyncElabError, _holder_fields, _members, _prop,
                                 _role_holders)


def _attr(comp, sym, name: str) -> Optional[str]:
    for a in comp.getAttributes(sym):
        if a.name == name:
            v = getattr(a.syntax, "value", None)
            return "" if v is None else str(v.expr).strip().strip('"')
    return None


def _param_field(st, name: str, where: str) -> int:
    """The value of member ``name`` of the struct parameter ``P`` of the class
    that declares payload struct ``st``."""
    p = st.parentScope.lookupName("P") if st.parentScope is not None else None
    if p is None or p.kind != ast.SymbolKind.Parameter:
        raise SyncElabError(f"{where}: fw_opt \"{name}\" but no parameter P beside {st}")
    pt = p.type.canonicalType
    for f in _members(pt, ast.SymbolKind.Field):
        if f.name == name:
            return (int(p.value.value) >> f.bitOffset) & ((1 << f.type.bitWidth) - 1)
    raise SyncElabError(f"{where}: fw_opt \"{name}\": P has no member {name}")


def _split(comp, st, where: str) -> List[Tuple[str, int, int, bool]]:
    """``(member, lsb, width, present)`` of payload type ``st``, MSB first; a
    non-struct payload is one member ``data``."""
    if st.kind != ast.SymbolKind.PackedStructType:
        return [("data", 0, st.bitWidth, True)]
    out = []
    for f in _members(st, ast.SymbolKind.Field):
        opt = _attr(comp, f, "fw_opt")
        present = opt is None or _param_field(st, opt, where) != 0
        out.append((f.name, f.bitOffset, f.type.canonicalType.bitWidth, present))
    return out


def _decl(is_out: bool, w: int, name: str) -> str:
    rng = f" [{w - 1}:0]" if w > 1 else ""
    return f"{'output' if is_out else 'input'} logic{rng} {name}"


def pin_shell(ct, lowered: DataTypeComponent, var: str) -> Optional[str]:
    """The shell module text for class ``ct`` lowered as ``lowered`` (module
    ``var``), or None if no member has a pin preset."""
    comp = ct.compilation
    ios: Dict[str, FieldInOut] = {f.name: f for f in lowered.fields
                                  if isinstance(f, FieldInOut)}
    pins: Dict[str, str] = {}       # lowered port -> connection expression
    decls: List[str] = []
    body: List[str] = []
    for p in _members(ct, ast.SymbolKind.ClassProperty):
        pre = _attr(comp, p, "fw_pins")
        if pre is None:
            continue
        where = f"{ct.name}.{p.name}"
        t = p.type.canonicalType
        if t.kind != ast.SymbolKind.ClassType or not _role_holders(t):
            raise SyncElabError(f"{where}: fw_pins on a member that is not a role port")
        for ch, ht in _role_holders(t):
            for fname, w, _d, _f in _holder_fields(ht):
                port = f"{p.name}_{ch}{fname}"
                io = ios[port]
                if fname != "data":
                    decls.append(_decl(io.is_out, w, f"{pre}{ch}{fname}"))
                    pins[port] = f"{pre}{ch}{fname}"
                    continue
                st = _prop(ht, "data_cur").type.canonicalType
                parts = _split(comp, st, where)
                if io.is_out:
                    wire = f"{port}__w"
                    body.append(f"  logic [{w - 1}:0] {wire};")
                    pins[port] = wire
                    for m, lsb, mw, present in parts:
                        if present:
                            decls.append(_decl(True, mw, f"{pre}{ch}{m}"))
                            body.append(f"  assign {pre}{ch}{m} = {wire}[{lsb + mw - 1}:{lsb}];")
                else:
                    cat = []
                    for m, lsb, mw, present in parts:
                        if present:
                            decls.append(_decl(False, mw, f"{pre}{ch}{m}"))
                            cat.append(f"{pre}{ch}{m}")
                        else:
                            cat.append(f"{mw}'d0")
                    pins[port] = "{" + ", ".join(cat) + "}"
    if not pins:
        return None
    for name, io in ios.items():
        if name not in pins:
            decls.append(_decl(io.is_out, io.datatype.bits, name))
            pins[name] = name
    conns = ",\n".join(f"    .{n}({pins[n]})" for n in ios)
    return (f"// Pin shell of {var} (fw.hdl.emit.pins): protocol pin names.\n"
            f"module {var}_pins(\n  " + ",\n  ".join(decls) + "\n);\n"
            + "".join(b + "\n" for b in body)
            + f"  {var} u_{var}(\n{conns}\n  );\nendmodule\n")
