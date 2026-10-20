"""Elaboration entry: the ``fw_root`` contract.

``fw_root`` is the synthesis root of an fw-hdl design. When reset is released it
does::

    root = new(path);                                   // Tbind
    clk_dom = new("clock", root, u_clk);                // fw_clock_xtor_bridge
    root.clock.connect(clk_dom);
    fork root.start(); join_none

:func:`elaborate` does the same through the interpreter, and also starts the
procedural blocks of every interface instance (their ``initial`` blocks give
reset values; their ``always`` blocks are processes). Then it runs every thread
until all are blocked.
"""
from __future__ import annotations

import dataclasses as dc
from typing import Dict, List, Optional

from pyslang import ast

from .interp import ElabError, Frame, Interpreter, Thread, ThreadRoot, Val
from .values import Iface, Obj

FW_ROOT = "fw_root"


@dc.dataclass
class ElabResult:
    interp: Interpreter
    top: object                       # the top InstanceSymbol
    root_inst: object                 # the fw_root InstanceSymbol
    root: Obj                         # the root component object
    threads: List[Thread]             # live (blocked) threads

    @property
    def objects(self) -> List[Obj]:
        return self.interp.objects

    @property
    def ifaces(self) -> Dict[str, Iface]:
        return self.interp.ifaces


def find_instances(inst, pred, out=None) -> list:
    out = [] if out is None else out
    for m in inst.body:
        if m.kind == ast.SymbolKind.Instance:
            if pred(m):
                out.append(m)
            find_instances(m, pred, out)
    return out


def elaborate(compilation, top_name: Optional[str] = None) -> ElabResult:
    root_syms = compilation.getRoot().topInstances
    tops = [t for t in root_syms if top_name is None or t.name == top_name]
    if not tops:
        raise ElabError(f"top module {top_name!r} not found")
    top = tops[0]
    roots = find_instances(top, lambda m: m.definition.name == FW_ROOT)
    if len(roots) != 1:
        raise ElabError(f"expected one {FW_ROOT} instance under {top.name}, found {len(roots)}")
    root_inst = roots[0]

    it = Interpreter(compilation, top)

    # Interface procedural blocks start at time 0 alongside the root.
    for inst in find_instances(top, lambda m: m.isInterface):
        f = it.iface_of(inst)
        for m in inst.body:
            if m.kind != ast.SymbolKind.ProceduralBlock:
                continue
            pk = m.procedureKind
            if pk == ast.ProceduralBlockKind.Initial:
                it.spawn(ThreadRoot("stmt", stmt=m.body, frame=Frame(None, None, f),
                                    label=f"{f.path}.initial"))
            elif pk in (ast.ProceduralBlockKind.Always, ast.ProceduralBlockKind.AlwaysFF):
                it.spawn(ThreadRoot("stmt", stmt=m.body, frame=Frame(None, None, f),
                                    label=f"{f.path}.always", forever=True))
            # always_comb / always_latch are combinational: the structure stage

    # The fw_root contract.
    tbind = next((m.type.canonicalType for m in root_inst.body
                  if m.kind == ast.SymbolKind.Variable and m.name == "root"), None)
    if tbind is None or not tbind.isClass:
        raise ElabError(f"{root_inst.hierarchicalPath}: no Tbind root variable")
    u_clk = next(m for m in root_inst.body
                 if m.kind == ast.SymbolKind.Instance and m.name == "u_clk")
    clk_if = it.iface_of(u_clk)
    hdl_pkg = compilation.getPackage("fw_hdl_pkg")
    bridge_t = hdl_pkg.find("fw_clock_xtor_bridge")

    top_fr = Frame(None, None, None)
    root = _new(it, tbind, [root_inst.hierarchicalPath], top_fr)
    clk = _new(it, bridge_t, ["clock", root, clk_if], top_fr)
    clock_port = root.fields[_prop(tbind, "clock")]
    it.run_sync(it.call_sub(clock_port.cls.find("connect"), clock_port, None,
                            [Val(clk)], top_fr, None))
    start = it._dispatch(root.cls, tbind.find("start") or _find_up(it, tbind, "start"))
    it.spawn(ThreadRoot("call", sub=start, this=root, label=f"{tbind.name}.start"))
    it.run()
    return ElabResult(interp=it, top=top, root_inst=root_inst, root=root,
                      threads=it.blocked_threads())


def _new(it: Interpreter, cls, args, fr) -> Obj:
    o = it.new_object(cls)
    ctor = _find_up(it, cls, "new")
    it.run_sync(it.call_sub(ctor, o, None, [Val(a) for a in args], fr, None))
    return o


def _find_up(it: Interpreter, cls, name):
    c = cls
    while c is not None:
        m = c.find(name)
        if m is not None and m.kind == ast.SymbolKind.Subroutine:
            return m
        c = it._base(c)
    raise ElabError(f"{cls.name} has no {name}")


def _prop(cls, name):
    c = cls
    while c is not None:
        m = c.find(name)
        if m is not None and m.kind == ast.SymbolKind.ClassProperty:
            return m
        b = c.baseClass
        c = b.canonicalType if b is not None else None
    raise ElabError(f"{cls.name} has no property {name}")
