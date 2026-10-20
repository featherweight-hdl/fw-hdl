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

An RTL module (any module with procedural code, other than ``fw_root``: the
transactor cores) is lowered with the rest. Its ``always``/``always_ff``
blocks are processes like an interface's. One whose body is
``if (reset) R else B``, with ``reset`` an input port, is a register block
with a reset: ``R`` runs once at elaboration and gives the reset values, and
the process is ``B`` (the translator skips ``R``); the structure stage checks
that the port is the design's reset (an asynchronous reset becomes
synchronous). Its ``always_comb`` blocks, continuous assignments and net
initializers are combinational processes (:attr:`ElabResult.comb`).
"""
from __future__ import annotations

import dataclasses as dc
from typing import Dict, List, Optional

from pyslang import ast

from .interp import ElabError, Frame, Interpreter, Thread, ThreadRoot, Val
from .values import Iface, Obj, skey

EK = ast.ExpressionKind
SK = ast.StatementKind

FW_ROOT = "fw_root"


@dc.dataclass
class ElabResult:
    interp: Interpreter
    top: object                       # the top InstanceSymbol
    root_inst: object                 # the fw_root InstanceSymbol
    root: Obj                         # the root component object
    threads: List[Thread]             # live (blocked) threads
    # RTL modules lowered with the design (instance paths)
    rtl_modules: List[str] = dc.field(default_factory=list)
    # combinational code of RTL modules: (iface, kind, node, label) with kind
    # 'always' (an always_comb body), 'assign' (a continuous assignment's
    # Assignment expression) or 'init' (a net with an initializer: the net)
    comb: List[tuple] = dc.field(default_factory=list)
    # reset branches of RTL register blocks, by skey of the if statement
    reset_ifs: Dict[tuple, str] = dc.field(default_factory=dict)
    # (instance path, port name, role, active high): the clock and reset
    # ports RTL blocks are sensitive to; they must be the design's
    rtl_ports: List[tuple] = dc.field(default_factory=list)

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

    rtl_modules: List[str] = []
    comb: List[tuple] = []
    reset_ifs: Dict[tuple, str] = {}
    rtl_ports: List[tuple] = []
    for inst in find_instances(top, _is_rtl_module):
        f = it.iface_of(inst)
        rtl_modules.append(inst.hierarchicalPath)
        for m in inst.body:
            k = m.kind
            if k == ast.SymbolKind.Instance:
                raise ElabError(f"{m.hierarchicalPath}: an instance inside an RTL module "
                                "is not supported yet")
            if k == ast.SymbolKind.ContinuousAssign:
                comb.append((f, "assign", m.assignment, f"{f.path}.assign"))
            elif k == ast.SymbolKind.Net and m.initializer is not None:
                comb.append((f, "init", m, f"{f.path}.{m.name}"))
            elif k == ast.SymbolKind.ProceduralBlock:
                pk = m.procedureKind
                if pk == ast.ProceduralBlockKind.AlwaysComb:
                    comb.append((f, "always", m.body, f"{f.path}.always_comb"))
                elif pk in (ast.ProceduralBlockKind.Always, ast.ProceduralBlockKind.AlwaysFF):
                    _rtl_block(it, inst, f, m, reset_ifs, rtl_ports)
                elif pk == ast.ProceduralBlockKind.Initial:
                    it.spawn(ThreadRoot("stmt", stmt=m.body, frame=Frame(None, None, f),
                                        label=f"{f.path}.initial"))
                else:
                    raise ElabError(f"{inst.hierarchicalPath}: {pk.name} block "
                                    "(level-sensitive latches are not supported)")

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
                      threads=it.blocked_threads(), rtl_modules=rtl_modules, comb=comb,
                      reset_ifs=reset_ifs, rtl_ports=rtl_ports)


def _has_procedural(inst) -> bool:
    return any(m.kind == ast.SymbolKind.ProceduralBlock for m in inst.body)


def _is_rtl_module(m) -> bool:
    return (not m.isInterface and m.definition.name != FW_ROOT and _has_procedural(m))


def _input_port(inst, sym) -> Optional[str]:
    """The name of the input port whose internal symbol is *sym*."""
    for m in inst.body:
        if m.kind == ast.SymbolKind.Port and m.direction == ast.ArgumentDirection.In \
                and m.internalSymbol is not None and m.internalSymbol.name == sym.name:
            return m.name
    return None


def _port_ref(inst, e):
    """(port name, active high) if *e* is an input port or its negation."""
    hi = True
    while e.kind == EK.UnaryOp and e.op.name in ("LogicalNot", "BitwiseNot"):
        hi = not hi
        e = e.operand
    if e.kind != EK.NamedValue:
        return None
    p = _input_port(inst, e.symbol)
    return (p, hi) if p is not None else None


def _const_writes(s) -> bool:
    k = s.kind
    if k == SK.List:
        return all(_const_writes(x) for x in s.list)
    if k == SK.Block:
        return _const_writes(s.body)
    if k == SK.ExpressionStatement and s.expr.kind == EK.Assignment:
        r = s.expr.right
        return r.constant is not None or r.kind in (EK.IntegerLiteral,
                                                     EK.UnbasedUnsizedIntegerLiteral)
    return k == SK.Empty


def _rtl_block(it: Interpreter, inst, f: Iface, m, reset_ifs, rtl_ports) -> None:
    """An RTL always/always_ff block: a process; a reset branch gives reset values."""
    body = m.body
    path = inst.hierarchicalPath
    edges = []
    if body.kind == SK.Timed:
        tc = body.timing
        evs = list(tc.events) if tc.kind == ast.TimingControlKind.EventList else [tc]
        for ev in evs:
            if ev.kind != ast.TimingControlKind.SignalEvent:
                raise ElabError(f"{path}: unsupported sensitivity in an always block")
            pr = _port_ref(inst, ev.expr)
            if pr is None:
                raise ElabError(f"{path}: an always block sensitive to something other "
                                "than an input port")
            edges.append((pr[0], ev.edge == ast.EdgeKind.PosEdge))
        stmt = body.stmt
    else:
        stmt = body
    while True:
        if stmt.kind == SK.Block and stmt.blockKind == ast.StatementBlockKind.Sequential:
            stmt = stmt.body
        elif stmt.kind == SK.List and len(stmt.list) == 1:
            stmt = stmt.list[0]
        else:
            break
    if not edges:
        raise ElabError(f"{path}: an always block without an edge (use always_comb)")
    rst = None
    if stmt.kind == SK.Conditional and stmt.ifFalse is not None:
        rst = _port_ref(inst, stmt.conditions[0].expr)
        # a synchronous reset branch writes constants only (else: an enable)
        if rst is not None and rst[0] not in dict(edges) and not _const_writes(stmt.ifTrue):
            rst = None
    clocks = [(p, pos) for p, pos in edges if rst is None or p != rst[0]]
    if len(clocks) != 1 or not clocks[0][1]:
        raise ElabError(f"{path}: an always block must be clocked by one rising edge")
    rtl_ports.append((path, clocks[0][0], "clock", True))
    if rst is not None:
        if len(edges) == 2 and dict(edges).get(rst[0]) != rst[1]:
            raise ElabError(f"{path}: reset edge and level disagree")
        reset_ifs[skey(stmt)] = path
        rtl_ports.append((path, rst[0], "reset", rst[1]))
        it.spawn(ThreadRoot("stmt", stmt=stmt.ifTrue, frame=Frame(None, None, f),
                            label=f"{f.path}.reset"))
    elif len(edges) != 1:
        raise ElabError(f"{path}: an asynchronous event without a reset branch")
    it.spawn(ThreadRoot("stmt", stmt=m.body, frame=Frame(None, None, f),
                        label=f"{f.path}.always", forever=True))


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
