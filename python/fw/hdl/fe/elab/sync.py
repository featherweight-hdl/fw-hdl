"""Synchronous components (``step()``/``comb()``) to a Zuspec IR component.

:func:`sync_component` takes a specialized class type (a pyslang ``ClassType``
such as ``fw_rv_slice #(bit [7:0])``) and builds one flattened
``DataTypeComponent``:

- each struct port (a class property whose type is an ``fw_sync_port`` view,
  e.g. ``fw_rv_sp_in``) becomes one ``FieldInOut`` per holder field, named
  ``<port>_<field>`` (``in_valid``, ``out_data``). The view's suffix gives
  the side: ``*_sp_out`` drives the FWD fields, ``*_sp_in`` the BWD ones.
  The fields, their direction and reset-force come from the holder's
  ``new()`` (``f_x = add_field("x", w, DIR)``, ``f_x.set_force(V)``); a
  field's width is that of the holder's ``<field>_cur`` property;
- each fw_proto role port (a class property whose class has ``fw_rv_sig``
  channel holders, e.g. the generated ``axi4_sub_sp``) becomes one
  ``FieldInOut`` per channel and holder field, named ``<port>_<ch><field>``
  (``s_awvalid``, ``m_rdata``). The role is the second argument of the
  ``super.new(name, role, owner)`` call in the port's ``new()`` (role 0, the
  manager, drives the forward channels); each channel's direction is the
  ``FW_FWD``/``FW_REV`` of its ``fw_rv_ch #(T)::add_ctl(this, "<ch>", DIR)``
  call in a base class method (fw_proto: ``build_fields()``). The body reads and writes them as
  ``p.<ch>.get_x()``/``p.<ch>.set_x(v)``;
- outputs are driven by the class's process: ``SYNC`` for ``step()``,
  ``COMB`` for ``comb()``. Sync outputs keep the holder's reset-force;
- integral class properties are state: registers of ``step()``.
  ``no_reset`` is set on state that the ``if (in_reset())`` branch of
  ``step()`` does not assign;
- ``step()`` becomes a sync process (metadata ``clock``/``reset`` refer to
  the ``clock`` and ``reset`` input ports, reset active high) and ``comb()``
  a comb process.

Process bodies are translated statement for statement (:class:`_Body`):
``p.set_x(v)`` assigns field ``p_x``, ``p.get_x()`` reads it, ``in_reset()``
reads ``reset`` and class properties read and write their state field. All
field references are ``ExprRefField(TypeExprRefSelf(), index)``. The
``step()`` body is then put in SSA form (:func:`_ssa`) so that it means the
same with nonblocking registers. Each process also keeps the pyslang
subroutine in ``metadata['sv']``.

Static checks (:func:`_check`): a process writes only fields it drives
(never an input); ``comb()`` writes no state and assigns every output on
every path (no latch); calls other than port accessors and ``in_reset()``
are rejected by :class:`_Body`. A ``step()`` marked ``(* fw_ported *)``
that reads state after writing it gets a :class:`SyncLintWarning` (also in
``metadata['lint']``). ``metadata['reads']``/``['writes']`` hold each
process's read and write sets as frozensets of field indices (after SSA).
"""
from __future__ import annotations

import copy
import dataclasses as dc
import warnings
from typing import Dict, List, Optional, Tuple

from pyslang import ast

from zuspec.ir.core.data_type import (DataTypeComponent, DataTypeInt, Function,
                                      ProcessKind)
from zuspec.ir.core.expr import (BinOp, BoolOp, CmpOp, Expr, ExprBin, ExprBool,
                                 ExprCompare, ExprConstant, ExprIfExp,
                                 ExprRefField, ExprUnary, TypeExprRefSelf,
                                 UnaryOp)
from zuspec.ir.core.fields import Field, FieldInOut
from zuspec.ir.core.stmt import StmtAssign, StmtIf

from .interp import ElabError


class SyncElabError(ElabError):
    pass


def _members(ct, kind) -> list:
    return [m for m in ct if m.kind == kind]


def _sub(ct, name):
    for m in _members(ct, ast.SymbolKind.Subroutine):
        if m.name == name:
            return m
    return None


def _prop(ct, name):
    for m in _members(ct, ast.SymbolKind.ClassProperty):
        if m.name == name:
            return m
    return None


def _generic_name(t) -> Optional[str]:
    t = t.canonicalType
    if t.kind != ast.SymbolKind.ClassType:
        return None
    g = t.genericClass
    return g.name if g is not None else t.name


def _derives(t, base: str) -> bool:
    t = t.canonicalType
    while t is not None and t.kind == ast.SymbolKind.ClassType:
        if t.name == base or _generic_name(t) == base:
            return True
        t = t.baseClass
    return False


def _unwrap(e):
    while e.kind == ast.ExpressionKind.Conversion:
        e = e.operand
    return e


def _const(e):
    e = _unwrap(e)
    if e.kind == ast.ExpressionKind.StringLiteral:
        return e.value
    if e.kind == ast.ExpressionKind.IntegerLiteral:
        return int(e.value)
    if e.kind == ast.ExpressionKind.NamedValue:
        return e.symbol.name
    raise SyncElabError(f"not a constant: {e.syntax}")


def _holder_fields(ht) -> List[Tuple[str, int, str, Optional[int]]]:
    """``(name, width, dir, force)`` for each field the holder ``ht`` adds in
    its ``new()``."""
    new = _sub(ht, "new")
    if new is None or new.body is None:
        raise SyncElabError(f"{ht.name}: no new()")
    fields: Dict[str, list] = {}
    by_var: Dict[str, str] = {}
    order: List[str] = []

    def v(n):
        if isinstance(n, ast.AssignmentExpression):
            r = _unwrap(n.right)
            if isinstance(r, ast.CallExpression) and r.subroutine.name == "add_field":
                args = list(r.arguments)
                fname = _const(args[0])
                d = _const(args[2]) if len(args) > 2 else "FW_SYNC_FWD"
                fields[fname] = [d, None]
                order.append(fname)
                by_var[n.left.symbol.name] = fname
        elif isinstance(n, ast.CallExpression) and not n.isSystemCall \
                and n.subroutine.name == "set_force":
            obj = n.thisClass
            if obj is not None and obj.kind == ast.ExpressionKind.NamedValue \
                    and obj.symbol.name in by_var:
                fields[by_var[obj.symbol.name]][1] = _const(list(n.arguments)[0])
        return ast.VisitAction.Advance
    new.body.visit(v)

    out = []
    for fname in order:
        cur = _prop(ht, f"{fname}_cur")
        if cur is None:
            raise SyncElabError(f"{ht.name}: field '{fname}' has no {fname}_cur")
        d, force = fields[fname]
        out.append((fname, cur.type.canonicalType.bitWidth, d, force))
    return out


def _role_holders(t) -> List[Tuple[str, object]]:
    """``(name, holder type)`` of the ``fw_rv_sig`` channel holders of role
    port class ``t`` (empty if ``t`` is not a role port)."""
    return [(m.name, m.type.canonicalType) for m in _members(t, ast.SymbolKind.ClassProperty)
            if _generic_name(m.type) == "fw_rv_sig"]


def _calls(sub, name: str) -> list:
    """Argument lists of the calls to ``name`` in the body of ``sub``."""
    out = []

    def v(n):
        if isinstance(n, ast.CallExpression) and not n.isSystemCall \
                and n.subroutine.name == name:
            out.append(list(n.arguments))
        return ast.VisitAction.Advance
    if sub is not None and sub.body is not None:
        sub.body.visit(v)
    return out


def _role_port(owner: str, t) -> Tuple[int, Dict[str, str]]:
    """``(role, {channel: "FW_FWD"|"FW_REV"})`` of role port class ``t``."""
    roles = [a for a in _calls(_sub(t, "new"), "new") if len(a) >= 2]
    if len(roles) != 1:
        raise SyncElabError(f"{owner}: {t.name}.new() has no super.new(name, role, ..)")
    role = _const(roles[0][1])
    dirs: Dict[str, str] = {}
    b = t.baseClass
    while b is not None and b.kind == ast.SymbolKind.ClassType:
        for sub in _members(b, ast.SymbolKind.Subroutine):
            for a in _calls(sub, "add_ctl"):
                if len(a) >= 3:
                    dirs.setdefault(_const(a[1]), _const(a[2]))
        b = b.baseClass
    return role, dirs


def _reset_assigned(step) -> set:
    """Names of class properties assigned in ``if (in_reset()) ...``."""
    names: set = set()

    def in_branch(n):
        if isinstance(n, ast.AssignmentExpression) \
                and n.left.kind == ast.ExpressionKind.NamedValue \
                and n.left.symbol.kind == ast.SymbolKind.ClassProperty:
            names.add(n.left.symbol.name)
        return ast.VisitAction.Advance

    def v(n):
        if isinstance(n, ast.ConditionalStatement):
            c = _unwrap(n.conditions[0].expr)
            if isinstance(c, ast.CallExpression) and not c.isSystemCall \
                    and c.subroutine.name == "in_reset":
                n.ifTrue.visit(in_branch)
        return ast.VisitAction.Advance
    step.body.visit(v)
    return names


_BOOL = {ast.BinaryOperator.LogicalAnd: BoolOp.And,
         ast.BinaryOperator.LogicalOr: BoolOp.Or}
_BIN = {ast.BinaryOperator.BinaryAnd: BinOp.BitAnd,
        ast.BinaryOperator.BinaryOr: BinOp.BitOr,
        ast.BinaryOperator.BinaryXor: BinOp.BitXor,
        ast.BinaryOperator.Add: BinOp.Add,
        ast.BinaryOperator.Subtract: BinOp.Sub,
        ast.BinaryOperator.LogicalShiftLeft: BinOp.LShift,
        ast.BinaryOperator.LogicalShiftRight: BinOp.RShift}
_CMP = {ast.BinaryOperator.Equality: CmpOp.Eq,
        ast.BinaryOperator.Inequality: CmpOp.NotEq,
        ast.BinaryOperator.LessThan: CmpOp.Lt,
        ast.BinaryOperator.LessThanEqual: CmpOp.LtE,
        ast.BinaryOperator.GreaterThan: CmpOp.Gt,
        ast.BinaryOperator.GreaterThanEqual: CmpOp.GtE}
_UN = {ast.UnaryOperator.LogicalNot: UnaryOp.Not,
       ast.UnaryOperator.BitwiseNot: UnaryOp.Invert}


class _Body:
    """Translates one process body to IR statements over ``comp.fields``."""

    def __init__(self, comp: DataTypeComponent, where: str):
        self.index = {f.name: i for i, f in enumerate(comp.fields)}
        self.where = where

    def err(self, n, what: str):
        raise SyncElabError(f"{self.where}: {what}: {n.syntax or n.kind.name}")

    def ref(self, n, name: str) -> ExprRefField:
        if name not in self.index:
            self.err(n, f"no field '{name}'")
        return ExprRefField(base=TypeExprRefSelf(), index=self.index[name])

    def stmts(self, s) -> list:
        k = s.kind
        if k == ast.StatementKind.List:
            return [x for c in s.list for x in self.stmts(c)]
        if k == ast.StatementKind.Block:
            return self.stmts(s.body)
        if k == ast.StatementKind.Empty:
            return []
        if k == ast.StatementKind.ExpressionStatement:
            return [self.effect(_unwrap(s.expr))]
        if k == ast.StatementKind.Conditional:
            if len(s.conditions) != 1 or s.conditions[0].pattern is not None:
                self.err(s, "unsupported condition")
            return [StmtIf(test=self.expr(s.conditions[0].expr),
                           body=self.stmts(s.ifTrue),
                           orelse=self.stmts(s.ifFalse) if s.ifFalse is not None else [])]
        self.err(s, f"unsupported statement {k.name}")

    def effect(self, e):
        if isinstance(e, ast.AssignmentExpression):
            if e.isCompound or e.isNonBlocking:
                self.err(e, "only plain '=' assignment")
            left = _unwrap(e.left)
            if left.kind != ast.ExpressionKind.NamedValue \
                    or left.symbol.kind != ast.SymbolKind.ClassProperty:
                self.err(e, "assignment target is not a state property")
            return StmtAssign(targets=[self.ref(e, left.symbol.name)],
                              value=self.expr(e.right))
        if isinstance(e, ast.CallExpression):
            port, op, args = self.port_call(e)
            if op == "set" and len(args) == 1:
                return StmtAssign(targets=[self.ref(e, port)], value=self.expr(args[0]))
        self.err(e, "unsupported statement expression")

    def port_call(self, e) -> Tuple[str, str, list]:
        """``p.set_x(v)``/``p.get_x()`` as ``("p_x", "set"|"get", args)``;
        on a role port's channel ``p.ch.set_x(v)`` is ``"p_chx"``."""
        obj = None if e.isSystemCall else e.thisClass
        name = e.subroutine.name if not e.isSystemCall else ""
        if obj is not None and obj.kind == ast.ExpressionKind.MemberAccess \
                and obj.member.kind == ast.SymbolKind.ClassProperty \
                and name[:4] in ("set_", "get_"):
            base = _unwrap(obj.value)
            if base.kind == ast.ExpressionKind.NamedValue \
                    and base.symbol.kind == ast.SymbolKind.ClassProperty:
                # Only the written arguments: fw_rv_sig's get_x(bit peer = 0)
                # has a default that pyslang fills in.
                al = getattr(e.syntax, "arguments", None)
                n = len([a for a in al.parameters if a is not None]) if al is not None else 0
                return (f"{base.symbol.name}_{obj.member.name}{name[4:]}", name[:3],
                        list(e.arguments)[:n])
        if obj is None or obj.kind != ast.ExpressionKind.NamedValue \
                or obj.symbol.kind != ast.SymbolKind.ClassProperty \
                or name[:4] not in ("set_", "get_"):
            self.err(e, "unsupported call")
        return f"{obj.symbol.name}_{name[4:]}", name[:3], list(e.arguments)

    def expr(self, e):
        e = _unwrap(e)
        k = e.kind
        if k == ast.ExpressionKind.IntegerLiteral:
            return ExprConstant(value=int(e.value))
        if k == ast.ExpressionKind.NamedValue \
                and e.symbol.kind == ast.SymbolKind.ClassProperty:
            return self.ref(e, e.symbol.name)
        if k == ast.ExpressionKind.Call:
            if not e.isSystemCall and e.thisClass is None \
                    and e.subroutine.name == "in_reset":
                return self.ref(e, "reset")
            port, op, args = self.port_call(e)
            if op == "get" and not args:
                return self.ref(e, port)
        elif k == ast.ExpressionKind.UnaryOp and e.op in _UN:
            return ExprUnary(op=_UN[e.op], operand=self.expr(e.operand))
        elif k == ast.ExpressionKind.BinaryOp:
            l, r = self.expr(e.left), self.expr(e.right)
            if e.op in _BOOL:
                return ExprBool(op=_BOOL[e.op], values=[l, r])
            if e.op in _BIN:
                return ExprBin(lhs=l, op=_BIN[e.op], rhs=r)
            if e.op in _CMP:
                return ExprCompare(left=l, ops=[_CMP[e.op]], comparators=[r])
        self.err(e, "unsupported expression")


def _subst(e, env: Dict[int, object]):
    """``e`` with each state read ``ExprRefField(self, i)``, ``i`` in ``env``,
    replaced by a copy of ``env[i]``."""
    if isinstance(e, ExprRefField):
        if isinstance(e.base, TypeExprRefSelf) and e.index in env:
            return copy.deepcopy(env[e.index])
        return e
    if not dc.is_dataclass(e):
        return e
    ch = {}
    for f in dc.fields(e):
        v = getattr(e, f.name)
        if isinstance(v, Expr):
            ch[f.name] = _subst(v, env)
        elif isinstance(v, list) and any(isinstance(x, Expr) for x in v):
            ch[f.name] = [_subst(x, env) if isinstance(x, Expr) else x for x in v]
    return dc.replace(e, **ch) if ch else e


def _ssa(stmts: list, state: set, env: Dict[int, object]) -> list:
    """SSA of a ``step()`` body (plan S5.2b), in place of local temps.

    In the class a state write is immediate, so a later read in the same
    ``step()`` sees the new value; as a nonblocking register it would see the
    old one. Each read of state field ``i`` written earlier on the path is
    replaced by the expression last written to it (``env[i]``); after an
    ``if``, a field written in either branch reads
    ``test ? then_value : else_value``. The writes stay where they are: with
    nonblocking semantics the last write on a path wins, as in the class.
    Port reads are not rewritten: ``set_x`` is deferred to the edge in the
    class too. ``env`` is updated to the values at the end of ``stmts``."""
    out = []
    for s in stmts:
        if isinstance(s, StmtAssign):
            v = _subst(s.value, env)
            out.append(StmtAssign(targets=s.targets, value=v))
            t = s.targets[0]
            if t.index in state:
                env[t.index] = v
        else:
            test = _subst(s.test, env)
            e_then, e_else = dict(env), dict(env)
            body = _ssa(s.body, state, e_then)
            orelse = _ssa(s.orelse, state, e_else)
            out.append(StmtIf(test=test, body=body, orelse=orelse))
            for i in set(e_then) | set(e_else):
                old = env.get(i, ExprRefField(base=TypeExprRefSelf(), index=i))
                a, b = e_then.get(i, old), e_else.get(i, old)
                env[i] = a if a is b else ExprIfExp(test=copy.deepcopy(test),
                                                     body=a, orelse=b)
    return out


def _reads(e) -> set:
    """Indices of the self fields read by expression ``e``."""
    if isinstance(e, ExprRefField):
        return {e.index} if isinstance(e.base, TypeExprRefSelf) else set()
    out: set = set()
    if dc.is_dataclass(e):
        for f in dc.fields(e):
            v = getattr(e, f.name)
            for x in (v if isinstance(v, list) else [v]):
                if isinstance(x, Expr):
                    out |= _reads(x)
    return out


def _rw(stmts: list, reads: set, writes: set):
    """Adds the fields read and written by ``stmts`` to ``reads``/``writes``."""
    for s in stmts:
        if isinstance(s, StmtAssign):
            reads |= _reads(s.value)
            writes.add(s.targets[0].index)
        else:
            reads |= _reads(s.test)
            _rw(s.body, reads, writes)
            _rw(s.orelse, reads, writes)


def _raw(stmts: list, state: set, written: set) -> set:
    """State fields read after a write on some path through ``stmts`` (before
    SSA). ``written`` is updated to the fields written on some path."""
    out: set = set()
    for s in stmts:
        if isinstance(s, StmtAssign):
            out |= _reads(s.value) & written
            if s.targets[0].index in state:
                written.add(s.targets[0].index)
        else:
            out |= _reads(s.test) & written
            w_then, w_else = set(written), set(written)
            out |= _raw(s.body, state, w_then) | _raw(s.orelse, state, w_else)
            written |= w_then | w_else
    return out


def _always(stmts: list) -> set:
    """Fields assigned on every path through ``stmts``."""
    out: set = set()
    for s in stmts:
        if isinstance(s, StmtAssign):
            out.add(s.targets[0].index)
        else:
            out |= _always(s.body) & _always(s.orelse)
    return out


class SyncLintWarning(UserWarning):
    """A lint finding of the sync front end (the class still elaborates)."""


def _check(ct, comp: DataTypeComponent, fn: Function, body: list):
    """Static checks (plan S5.2): one driver per field, comb rules."""
    where = f"{ct.name}.{fn.name}"
    fields = comp.fields
    reads, writes = set(), set()
    _rw(body, reads, writes)
    for i in sorted(writes):
        f = fields[i]
        if isinstance(f, FieldInOut) and not f.is_out:
            raise SyncElabError(f"{where}: writes input '{f.name}' (driven outside "
                                f"the component)")
        if f.drive != fn.process_kind:
            raise SyncElabError(f"{where}: writes '{f.name}', driven by "
                                f"{f.drive.name if f.drive else 'none'}")
        if fn.process_kind == ProcessKind.COMB and not isinstance(f, FieldInOut):
            raise SyncElabError(f"{where}: writes state '{f.name}' (comb() has no "
                                f"state)")
    if fn.process_kind == ProcessKind.COMB:
        missed = [f.name for i, f in enumerate(fields)
                  if f.drive == ProcessKind.COMB and isinstance(f, FieldInOut)
                  and i not in _always(body)]
        if missed:
            raise SyncElabError(f"{where}: output(s) {', '.join(missed)} not "
                                f"assigned on every path (latch)")


def _ported(sub) -> bool:
    """Whether subroutine ``sub`` carries ``(* fw_ported *)``."""
    return any(a.name == "fw_ported" for a in sub.compilation.getAttributes(sub))


def _int(bits: int) -> DataTypeInt:
    return DataTypeInt(bits=bits, signed=False)


def sync_component(ct, name: Optional[str] = None) -> DataTypeComponent:
    """Build the flattened IR component for the specialized class ``ct``."""
    step = _sub(ct, "step")
    comb = _sub(ct, "comb")
    if step is None and comb is None:
        raise SyncElabError(f"{ct.name}: neither step() nor comb()")
    if step is not None and comb is not None:
        raise SyncElabError(f"{ct.name}: both step() and comb()")
    kind = ProcessKind.SYNC if step is not None else ProcessKind.COMB

    comp = DataTypeComponent(name=name or ct.name, super=None)
    fields = comp.fields
    if kind == ProcessKind.SYNC:
        fields.append(FieldInOut(name="clock", datatype=_int(1), is_out=False))
        fields.append(FieldInOut(name="reset", datatype=_int(1), is_out=False))

    reset_set = _reset_assigned(step) if step is not None else set()
    for p in _members(ct, ast.SymbolKind.ClassProperty):
        t = p.type.canonicalType
        if t.kind == ast.SymbolKind.ClassType and not _derives(t, "fw_sync_port") \
                and _role_holders(t):
            role, dirs = _role_port(f"{ct.name}.{p.name}", t)
            for ch, ht in _role_holders(t):
                if dirs.get(ch) not in ("FW_FWD", "FW_REV"):
                    raise SyncElabError(f"{ct.name}.{p.name}: channel '{ch}' has no "
                                        f"add_ctl direction in {t.name}")
                # Role 0 drives the FWD fields of a forward channel.
                drives = "FW_SYNC_FWD" if (dirs[ch] == "FW_FWD") == (role == 0) \
                    else "FW_SYNC_BWD"
                for fname, w, d, force in _holder_fields(ht):
                    out = d == drives
                    fields.append(FieldInOut(
                        name=f"{p.name}_{ch}{fname}", datatype=_int(w), is_out=out,
                        drive=kind if out else None,
                        reset_force=force if out and kind == ProcessKind.SYNC else None))
        elif t.kind == ast.SymbolKind.ClassType:
            if not _derives(t, "fw_sync_port"):
                raise SyncElabError(f"{ct.name}.{p.name}: class property is not a "
                                    f"sync port ({t.name})")
            view = _generic_name(t)
            if view.endswith("_sp_out"):
                drives = "FW_SYNC_FWD"
            elif view.endswith("_sp_in"):
                drives = "FW_SYNC_BWD"
            else:
                raise SyncElabError(f"{ct.name}.{p.name}: view {view} is neither "
                                    f"*_sp_in nor *_sp_out")
            sig = _prop(t, "sig")
            if sig is None:
                raise SyncElabError(f"{view}: no 'sig' holder")
            for fname, w, d, force in _holder_fields(sig.type.canonicalType):
                out = d == drives
                fields.append(FieldInOut(
                    name=f"{p.name}_{fname}", datatype=_int(w), is_out=out,
                    drive=kind if out else None,
                    reset_force=force if out and kind == ProcessKind.SYNC else None))
        elif t.isIntegral:
            fields.append(Field(name=p.name, datatype=_int(t.bitWidth), drive=kind,
                                no_reset=(kind == ProcessKind.SYNC
                                          and p.name not in reset_set)))
        else:
            raise SyncElabError(f"{ct.name}.{p.name}: unsupported state type {t}")

    if step is not None:
        state = {i for i, f in enumerate(fields) if not isinstance(f, FieldInOut)}
        body = _Body(comp, f"{ct.name}.step").stmts(step.body)
        fn = Function(name="step", process_kind=ProcessKind.SYNC, body=[],
                      metadata={"sv": step, "lint": [],
                                "clock": ExprRefField(base=TypeExprRefSelf(), index=0),
                                "reset": ExprRefField(base=TypeExprRefSelf(), index=1)})
        _check(ct, comp, fn, body)
        raw = _raw(body, state, set())
        if raw and _ported(step):
            msg = (f"{ct.name}.step: (* fw_ported *) reads state after writing it: "
                   f"{', '.join(fields[i].name for i in sorted(raw))} (reads the new "
                   f"value, not the register)")
            fn.metadata["lint"].append(msg)
            warnings.warn(msg, SyncLintWarning, stacklevel=2)
        fn.body = _ssa(body, state, {})
        comp.sync_processes.append(fn)
    else:
        fn = Function(name="comb", process_kind=ProcessKind.COMB,
                      body=_Body(comp, f"{ct.name}.comb").stmts(comb.body),
                      metadata={"sv": comb, "lint": []})
        _check(ct, comp, fn, fn.body)
        comp.comb_processes.append(fn)
    # Per-process read and write sets (field indices), for the C simulator (S9).
    reads, writes = set(), set()
    _rw(fn.body, reads, writes)
    fn.metadata["reads"], fn.metadata["writes"] = frozenset(reads), frozenset(writes)
    return comp


def find_class_var(compilation, module: str, var: str):
    """The specialized class type of variable ``var`` in top module ``module``."""
    for top in compilation.getRoot().topInstances:
        if top.name != module:
            continue
        for m in top.body:
            if m.kind == ast.SymbolKind.Variable and m.name == var:
                return m.type.canonicalType
    raise SyncElabError(f"no variable {module}.{var}")
