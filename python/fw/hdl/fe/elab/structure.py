"""The module side of the elaborate-then-lower path.

Rebuilds the top module's hierarchy around the translated processes:

  - an interface instance that the class side reaches (its variables are
    process state or inputs) is absorbed: its port connections become
    continuous assignments to and from those variables;
  - a module on the path to such an interface (a transactor wrapper, the top
    itself, ``fw_root``) is flattened: its nets become netlist nets, its
    continuous assignments carry over. It must be structural: procedural code
    in it is an error, except ``fw_root``'s, whose elaboration the front end
    has already done;
  - every other module instance is a leaf, kept as an instance with its
    parameter values.

The design's clock and reset are the signals ``fw_root`` is connected to.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Set

from pyslang import ast

from zuspec.synth.proc import ir as P
from zuspec.synth.proc import term as T

from .entry import ElabResult
from .interp import ElabError
from .values import const_to_py, width_of

EK = ast.ExpressionKind


class StructureError(ElabError):
    pass


def _safe(name: str) -> str:
    return "".join(c if (c.isalnum() or c == "_") else "_" for c in name).strip("_")


class Structure:
    def __init__(self, elab: ElabResult, d: P.Design):
        self.elab = elab
        self.d = d
        self.top = elab.top
        self.byname: Dict[str, P.Var] = {v.name: v for v in d.vars}
        self.leaf_defs: Dict[str, object] = {}
        # interfaces the class side uses: those whose variables appear in the design
        self.bound: Set[str] = set()
        for path in elab.ifaces:
            stem = _safe(self._rel(path)) + "_"
            if any(v.name.startswith(stem) for v in d.vars) or \
                    any(p.origin.startswith(path + ".") for p in d.procs):
                self.bound.add(path)

    def _rel(self, path: str) -> str:
        pre = self.top.name + "."
        return path[len(pre):] if path.startswith(pre) else path

    def _contains_bound(self, inst) -> bool:
        p = inst.hierarchicalPath
        return any(b == p or b.startswith(p + ".") for b in self.bound)

    def var_for(self, sym, kind: str = "net") -> P.Var:
        """The netlist var of a module-scope net/variable/port symbol."""
        name = _safe(self._rel(sym.hierarchicalPath))
        v = self.byname.get(name)
        if v is None:
            w = width_of(sym.type)
            if w is None:
                raise StructureError(f"{sym.hierarchicalPath}: not a bit vector")
            v = P.Var(name=name, w=w, kind=kind, origin=sym.hierarchicalPath)
            self.byname[name] = v
            self.d.vars.append(v)
        return v

    def build(self) -> P.Design:
        d = self.d
        # top ports
        for m in self.top.body:
            if m.kind == ast.SymbolKind.Port:
                isym = m.internalSymbol
                if m.direction == ast.ArgumentDirection.In:
                    v = self.var_for(isym, "in")
                    v.kind = "in"
                    d.ports.append(P.Port(m.name, v.w, "in", v))
                elif m.direction == ast.ArgumentDirection.Out:
                    v = self.var_for(isym, "net")
                    d.ports.append(P.Port(m.name, v.w, "out", v))
                else:
                    raise StructureError(f"port {m.name}: inout is not supported")
        self._flatten(self.top)
        # clock / reset: what fw_root is connected to
        root = self.elab.root_inst
        clk = rst = None
        for c in root.portConnections:
            e = c.expression
            if e is None:
                continue
            t = self.term(e)
            if c.port.name == "clock":
                clk = t
            elif c.port.name == "reset":
                rst = t
        if clk is None or clk.op != "var":
            raise StructureError("fw_root's clock must be a plain signal")
        old_clk, old_rst = d.clock, d.reset
        d.clock = self.byname[clk.name]
        d.reset = self.byname[rst.name] if rst is not None and rst.op == "var" else None
        if rst is not None and rst.op != "var":
            rv = P.Var(name="_reset", w=1, kind="net", origin="fw_root reset")
            d.vars.append(rv)
            d.assigns.append(P.Assign(rv, rst))
            d.reset = rv
        # the translator's placeholder clock/reset vars: alias them
        for old, new in ((old_clk, d.clock), (old_rst, d.reset)):
            if old is not None and new is not None and old is not new and old in d.vars:
                old.kind = "net"
                d.assigns.append(P.Assign(old, T.var(new.name, new.w)))
        # nets nobody drives inside the generated module are an error later;
        # leaf outputs and assigns drive them
        return d

    # ------------------------------------------------------------ hierarchy
    def _flatten(self, inst) -> None:
        for m in inst.body:
            k = m.kind
            if k == ast.SymbolKind.ContinuousAssign:
                a = m.assignment
                lhs, rhs = a.left, a.right
                self._drive(lhs, self.term(rhs))
            elif k == ast.SymbolKind.ProceduralBlock:
                if inst.definition.name == "fw_root":
                    continue        # fw_root's elaboration: done by the front end
                if inst.isInterface:
                    continue        # interface processes are translated
                raise StructureError(f"{inst.hierarchicalPath}: procedural code in a module "
                                     "on the path to the class side (it must be structural)")
            elif k == ast.SymbolKind.Instance:
                self._instance(m)

    def _instance(self, m) -> None:
        path = m.hierarchicalPath
        if m.isInterface:
            if path not in self.bound:
                raise StructureError(f"{path}: an interface the class side does not use")
            self._connect_ports(m, absorb=True)
            self._flatten(m)
            return
        if m.definition.name == "fw_root" or self._contains_bound(m):
            self._connect_ports(m, absorb=True)
            self._flatten(m)
            return
        self._leaf(m)

    def _connect_ports(self, m, absorb: bool) -> None:
        """A flattened instance: its port nets are the connected expressions."""
        for c in m.portConnections:
            port = c.port
            e = c.expression
            isym = port.internalSymbol
            if isym is None:
                continue
            if port.direction == ast.ArgumentDirection.In:
                if e is None:
                    continue
                v = self.var_for(isym, "net")
                if v.kind == "reg":
                    raise StructureError(f"{port.name}: an input written by the class side")
                if v.kind == "in":
                    v.kind = "net"
                self.d.assigns.append(P.Assign(v, T.resize(self.term(e), v.w)))
            elif port.direction == ast.ArgumentDirection.Out:
                v = self.var_for(isym, "net")
                if e is None:
                    continue
                lhs = e.left if e.kind == EK.Assignment else e
                self._drive(lhs, T.var(v.name, v.w))
            else:
                raise StructureError(f"{port.name}: inout is not supported")

    def _leaf(self, m) -> None:
        params: Dict[str, object] = {}
        for s in m.body:
            if s.kind == ast.SymbolKind.Parameter and s.isPortParam:
                v = const_to_py(s.value)
                if isinstance(v, int):
                    params[s.name] = v
        inst = P.Instance(module=m.definition.name, name=_safe(self._rel(m.hierarchicalPath)),
                          params=params)
        self.leaf_defs[m.definition.name] = m.definition
        for c in m.portConnections:
            port = c.port
            e = c.expression
            if port.direction == ast.ArgumentDirection.In:
                inst.conns.append(P.Conn(port.name, term=(self.term(e) if e is not None else None),
                                         direction="in"))
            elif port.direction == ast.ArgumentDirection.Out:
                w = width_of(port.type)
                nv = P.Var(name=f"{inst.name}__{port.name}", w=w, kind="net",
                           origin=f"{m.hierarchicalPath}.{port.name}")
                self.d.vars.append(nv)
                self.byname[nv.name] = nv
                inst.conns.append(P.Conn(port.name, var=nv, direction="out"))
                if e is not None:
                    lhs = e.left if e.kind == EK.Assignment else e
                    self._drive(lhs, T.var(nv.name, nv.w))
            else:
                raise StructureError(f"{m.hierarchicalPath}.{port.name}: inout is not supported")
        self.d.instances.append(inst)

    def _drive(self, lhs, value: T.Term) -> None:
        if lhs.kind in (EK.NamedValue, EK.HierarchicalValue):
            v = self.var_for(lhs.symbol, "net")
            if v.kind == "reg":
                raise StructureError(f"{v.name}: driven by both a process and the structure")
            if v.kind == "in":
                raise StructureError(f"{v.name}: an input is driven")
            self.d.assigns.append(P.Assign(v, T.resize(value, v.w)))
            return
        if lhs.kind == EK.Concatenation:
            pos = 0
            for x in reversed(list(lhs.operands)):
                w = width_of(x.type)
                self._drive(x, T.slice_(value, pos, w))
                pos += w
            return
        if lhs.kind == EK.Conversion:
            self._drive(lhs.operand, value)
            return
        raise StructureError(f"unsupported connection target {lhs.kind.name}")

    # ----------------------------------------------------------- expressions
    def term(self, e) -> T.Term:
        k = e.kind
        w = width_of(e.type)
        if e.constant is not None and k not in (EK.NamedValue, EK.HierarchicalValue):
            v = const_to_py(e.constant)
            if isinstance(v, int):
                return T.const(v, w)
        if k in (EK.NamedValue, EK.HierarchicalValue):
            sym = e.symbol
            if sym.kind in (ast.SymbolKind.Parameter, ast.SymbolKind.EnumValue):
                return T.const(const_to_py(sym.value), w)
            v = self.var_for(sym, "net")
            return T.var(v.name, v.w)
        if k in (EK.IntegerLiteral, EK.UnbasedUnsizedIntegerLiteral):
            if k == EK.UnbasedUnsizedIntegerLiteral:
                return T.const(-1 if str(e.syntax).strip().endswith("1") else 0, w)
            return T.const(const_to_py(e.constant) or 0, w)
        if k == EK.Conversion:
            x = self.term(e.operand)
            ft = e.operand.type.canonicalType
            return T.resize(x, w, bool(ft.isIntegral and ft.isSigned))
        if k == EK.Concatenation:
            return T.concat(*[self.term(x) for x in e.operands if (width_of(x.type) or 0) > 0])
        if k == EK.Replication:
            n = const_to_py(e.count.constant)
            return T.concat(*([self.term(e.concat)] * n))
        if k == EK.ElementSelect:
            base = self.term(e.value)
            idx = const_to_py(e.selector.constant)
            if idx is None:
                raise StructureError("run-time select in a connection")
            t = e.value.type.canonicalType
            r = t.fixedRange
            lo = (idx - int(r.right)) if int(r.left) >= int(r.right) else (int(r.right) - idx)
            return T.slice_(base, lo * w, w)
        if k == EK.RangeSelect:
            base = self.term(e.value)
            a = const_to_py(e.left.constant)
            b = const_to_py(e.right.constant)
            t = e.value.type.canonicalType
            r = t.fixedRange
            sk = e.selectionKind
            if sk == ast.RangeSelectionKind.Simple:
                lo_idx = min(a, b)
            elif sk == ast.RangeSelectionKind.IndexedUp:
                lo_idx = a
            else:
                lo_idx = a - b + 1
            return T.slice_(base, lo_idx - min(int(r.left), int(r.right)), w)
        if k == EK.UnaryOp:
            x = self.term(e.operand)
            op = e.op.name
            return {"LogicalNot": lambda: T.not_(T.bool_(x)), "BitwiseNot": lambda: T.not_(x),
                    "BitwiseAnd": lambda: T.redand(x), "BitwiseOr": lambda: T.redor(x),
                    "BitwiseXor": lambda: T.redxor(x), "Plus": lambda: x,
                    "Minus": lambda: T.neg(x)}[op]()
        if k == EK.BinaryOp:
            op = e.op.name
            a = self.term(e.left)
            b = self.term(e.right)
            if op == "LogicalAnd":
                return T.and_(T.bool_(a), T.bool_(b))
            if op == "LogicalOr":
                return T.or_(T.bool_(a), T.bool_(b))
            if op in ("Equality", "CaseEquality"):
                return T.eq(a, b)
            if op in ("Inequality", "CaseInequality"):
                return T.ne(a, b)
            f = {"BinaryAnd": T.and_, "BinaryOr": T.or_, "BinaryXor": T.xor,
                 "Add": T.add, "Subtract": T.sub}.get(op)
            if f is None:
                raise StructureError(f"unsupported operator {op} in a connection")
            return f(a, b)
        if k == EK.ConditionalOp:
            c = T.bool_(self.term(e.conditions[0].expr))
            return T.ite(c, self.term(e.left), self.term(e.right))
        raise StructureError(f"unsupported expression {k.name} in a connection")


def build_structure(elab: ElabResult, d: P.Design) -> P.Design:
    s = Structure(elab, d)
    s.build()
    d.leaf_defs = s.leaf_defs          # module definitions to synthesize with
    return d
