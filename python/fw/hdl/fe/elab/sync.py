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
- a fixed-size array of ports (``fw_rv_sp_in #(T) in[N]``) is one port per
  element, ``in_<i>`` (``in_0_valid``, ``in_0_ready``, ...);
- outputs are driven by the process that writes them: ``SYNC`` for
  ``step()``, ``COMB`` for ``comb()``; a class may have both (a field written
  by both is an error). Sync outputs keep the holder's reset-force;
- integral class properties are state: registers of ``step()``; a
  fixed-size array of them is one register per element (``mem_0``,
  ``mem_1``). ``no_reset`` is set on state that the ``if (in_reset())``
  branch of ``step()`` does not assign;
- ``step()`` becomes a sync process (metadata ``clock``/``reset`` refer to
  the ``clock`` and ``reset`` input ports, reset active high) and ``comb()``
  a comb process.

Process bodies are translated by symbolic execution (:class:`_Body`):
``p.set_x(v)`` assigns field ``p_x``, ``p.get_x()`` reads it, ``in_reset()``
reads ``reset`` and class properties read and write their state field. All
field references are ``ExprRefField(TypeExprRefSelf(), index)``. State reads
in ``step()`` are in SSA form, so the body means the same with nonblocking
registers. Locals, ``for``/``foreach`` with static bounds (unrolled),
``return``, functions of the class (inlined), element selects with a
computed index (``?:`` chains) and packed struct members are supported; the
value of a local is a named comb wire, driven from a third process,
``wires``. Each process also keeps the pyslang subroutine in
``metadata['sv']``.

Static checks (:func:`_check`): a process writes only fields it drives
(never an input); ``comb()`` writes no state and assigns every output on
every path (no latch); calls other than port accessors, ``in_reset()`` and
functions of the class are rejected by :class:`_Body`. A ``step()`` marked ``(* fw_ported *)``
that reads state after writing it gets a :class:`SyncLintWarning` (also in
``metadata['lint']``). ``metadata['reads']``/``['writes']`` hold each
process's read and write sets as frozensets of field indices (after SSA).
"""
from __future__ import annotations

import dataclasses as dc
import operator
import warnings
from typing import Dict, List, Optional, Tuple

from pyslang import ast

from zuspec.ir.core.data_type import (DataTypeComponent, DataTypeInt, Function,
                                      ProcessKind)
from zuspec.ir.core.expr import (BinOp, BoolOp, CmpOp, Expr, ExprBin, ExprBool,
                                 ExprCompare, ExprConstant, ExprIfExp,
                                 ExprRefField, ExprSlice, ExprSubscript, ExprUnary,
                                 TypeExprRefSelf, UnaryOp)
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
    """Names of class properties assigned (whole, or an element) in
    ``if (in_reset()) ...``."""
    names: set = set()

    def in_branch(n):
        if isinstance(n, ast.AssignmentExpression):
            left = _unwrap(n.left)
            while left.kind == ast.ExpressionKind.ElementSelect:
                left = _unwrap(left.value)
            if left.kind == ast.ExpressionKind.NamedValue \
                    and left.symbol.kind == ast.SymbolKind.ClassProperty:
                names.add(left.symbol.name)
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


def _elems(p) -> List[Tuple[Optional[int], object]]:
    """``(index, type)`` for class property ``p``: ``[(None, type)]`` for a
    scalar, one entry per element (SV index, left to right) for a fixed-size
    unpacked array. Element ``i`` of ``in`` is lowered as ``in_<i>``."""
    t = p.type.canonicalType
    if t.isUnpackedArray and not (t.isDynamicallySizedArray or t.isQueue
                                  or t.isAssociativeArray):
        r = t.fixedRange
        lft, rgt = int(r.left), int(r.right)
        step = 1 if rgt >= lft else -1
        return [(i, t.arrayElementType.canonicalType) for i in range(lft, rgt + step, step)]
    return [(None, t)]


def _ename(name: str, i: Optional[int]) -> str:
    return name if i is None else f"{name}_{i}"


_BOOL = {ast.BinaryOperator.LogicalAnd: BoolOp.And,
         ast.BinaryOperator.LogicalOr: BoolOp.Or}
_BIN = {ast.BinaryOperator.BinaryAnd: BinOp.BitAnd,
        ast.BinaryOperator.BinaryOr: BinOp.BitOr,
        ast.BinaryOperator.BinaryXor: BinOp.BitXor,
        ast.BinaryOperator.Add: BinOp.Add,
        ast.BinaryOperator.Subtract: BinOp.Sub,
        ast.BinaryOperator.Multiply: BinOp.Mult,
        ast.BinaryOperator.Mod: BinOp.Mod,
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
_INC = {ast.UnaryOperator.Preincrement: BinOp.Add,
        ast.UnaryOperator.Postincrement: BinOp.Add,
        ast.UnaryOperator.Predecrement: BinOp.Sub,
        ast.UnaryOperator.Postdecrement: BinOp.Sub}

# Constant folding: only when every operand is a constant (loop bounds and
# indices after unrolling); widths are not modeled.
_PY_BIN = {BinOp.BitAnd: operator.and_, BinOp.BitOr: operator.or_,
           BinOp.BitXor: operator.xor, BinOp.Add: operator.add,
           BinOp.Sub: operator.sub, BinOp.Mult: operator.mul,
           BinOp.Mod: lambda a, b: a % b if b else None,
           BinOp.LShift: operator.lshift, BinOp.RShift: operator.rshift}
_PY_CMP = {CmpOp.Eq: operator.eq, CmpOp.NotEq: operator.ne, CmpOp.Lt: operator.lt,
           CmpOp.LtE: operator.le, CmpOp.Gt: operator.gt, CmpOp.GtE: operator.ge}

#: Symbols ``env`` holds: locals, formal arguments, foreach loop variables.
_LOCALS = (ast.SymbolKind.Variable, ast.SymbolKind.FormalArgument, ast.SymbolKind.Iterator)

#: The unroll limit of one loop.
_MAX_ITER = 4096


def _fold(e) -> Optional[int]:
    """The value of ``e`` if it is an integer constant."""
    if isinstance(e, ExprConstant) and isinstance(e.value, int):
        return e.value
    return None


def _const_of(v: Optional[int], e):
    return ExprConstant(value=int(v)) if v is not None else e


def _bin(l, op, r):
    a, b = _fold(l), _fold(r)
    if a is not None and b is not None:
        return _const_of(_PY_BIN[op](a, b), ExprBin(lhs=l, op=op, rhs=r))
    if b == 0 and op in (BinOp.Add, BinOp.Sub, BinOp.BitOr, BinOp.BitXor,
                         BinOp.LShift, BinOp.RShift) or b == 1 and op == BinOp.Mult:
        return l
    if a == 0 and op in (BinOp.Add, BinOp.BitOr, BinOp.BitXor) or a == 1 and op == BinOp.Mult:
        return r
    return ExprBin(lhs=l, op=op, rhs=r)


def _cmp(l, op, r):
    a, b = _fold(l), _fold(r)
    if a is not None and b is not None:
        return ExprConstant(value=int(_PY_CMP[op](a, b)))
    return ExprCompare(left=l, ops=[op], comparators=[r])


def _ifexp(test, a, b):
    c = _fold(test)
    if c is not None:
        return a if c else b
    if a is b or a == b:
        return a
    return ExprIfExp(test=test, body=a, orelse=b)


def _mux(sel, alts: List[Tuple[int, object]]):
    """``alts[k][1]`` where ``sel == alts[k][0]``: a chain of ``?:`` (the
    last alternative is the default)."""
    c = _fold(sel)
    if c is not None:
        for i, x in alts:
            if i == c:
                return x
        raise SyncElabError(f"index {c} is out of range")
    e = alts[-1][1]
    for i, x in reversed(alts[:-1]):
        e = _ifexp(_cmp(sel, CmpOp.Eq, ExprConstant(value=i)), x, e)
    return e


def _slice(e, lo: int, w: int):
    """Bits ``[lo +: w]`` of ``e`` (a packed struct member)."""
    if isinstance(e, ExprIfExp):
        return ExprIfExp(test=e.test, body=_slice(e.body, lo, w), orelse=_slice(e.orelse, lo, w))
    if isinstance(e, ExprRefField):
        sl = ExprConstant(value=lo) if w == 1 else \
            ExprSlice(lower=ExprConstant(value=lo + w - 1), upper=ExprConstant(value=lo),
                      is_bit_slice=True)
        return ExprSubscript(value=e, slice=sl)
    v = _fold(e)
    if v is not None:
        return ExprConstant(value=(v >> lo) & ((1 << w) - 1))
    sh = _bin(e, BinOp.RShift, ExprConstant(value=lo)) if lo else e
    return ExprBin(lhs=sh, op=BinOp.BitAnd, rhs=ExprConstant(value=(1 << w) - 1))


def _local(sym):
    """The ``env`` key of a local variable or formal argument."""
    loc = sym.location
    return ("local", sym.name, getattr(loc.buffer, "id", 0), loc.offset)


def _returns(s) -> bool:
    """Whether statement ``s`` holds a ``return``."""
    found = []

    def v(n):
        if isinstance(n, ast.ReturnStatement):
            found.append(n)
        return ast.VisitAction.Advance
    s.visit(v)
    return bool(found)


def _trivial(e) -> bool:
    """Whether ``e`` is cheap enough to copy into each use: a constant, a
    field or a bit select of one."""
    return isinstance(e, (ExprConstant, ExprRefField)) or (
        isinstance(e, ExprSubscript) and isinstance(e.value, ExprRefField))


class _Wires:
    """The named comb signals of a component's locals (one per distinct
    value), shared by its processes; driven from one comb process,
    ``wires``, in the order they are made (each after what it reads)."""

    def __init__(self, comp: DataTypeComponent):
        self.comp = comp
        self.stmts: list = []
        self.made: List[Tuple[object, ExprRefField]] = []
        self.indices: set = set()

    def wire(self, name: str, width: int, v):
        """``v`` itself if trivial, else a reference to the wire that carries
        it (named ``name``, made unless one already carries ``v``)."""
        if _trivial(v):
            return v
        for e, r in self.made:
            if e == v:
                return r
        names = {f.name for f in self.comp.fields}
        n, k = name, 1
        while n in names:
            n, k = f"{name}_{k}", k + 1
        i = len(self.comp.fields)
        self.comp.fields.append(Field(name=n, datatype=_int(max(width, 1)),
                                      drive=ProcessKind.COMB))
        r = ExprRefField(base=TypeExprRefSelf(), index=i)
        self.stmts.append(StmtAssign(targets=[r], value=v))
        self.made.append((v, r))
        self.indices.add(i)
        return r


class _Body:
    """Translates one process body to IR statements over ``comp.fields``, by
    symbolic execution of the body along each path.

    ``env`` maps what has a value on the current path to its IR expression:
    locals and formal arguments (keyed by declaration) and, in ``step()``,
    the state fields written so far on the path (keyed by field index;
    ``state``). A read of either is replaced by that expression, so locals
    leave no trace in the IR, and state reads are in SSA form (plan S5.2b): in
    the class a state write is immediate, so a later read in the same
    ``step()`` sees the new value, while as a nonblocking register it would
    see the old one. Writes stay where they are: with nonblocking semantics
    the last write on a path wins, as in the class. Port reads are not
    rewritten: ``set_x`` is deferred to the edge in the class too. After an
    ``if``, a value set in either branch reads ``test ? then : else``.

    Loops with static bounds (``for``, ``foreach``) are unrolled; functions
    of the class are inlined; a ``return`` ends its path, and the statements
    after an ``if`` that may return are moved into both of its branches. An
    element select with a non-constant index reads a ``?:`` chain over the
    elements (a port array ``in[g].get_x()`` or a state array ``mem[rd]``) and
    writes one guarded assignment per element (``mem[wr] = v``). A packed
    struct member reads its bits.

    The value of a local (and of a call of a function of the class) that is
    not trivial is carried by a named comb wire (:class:`_Wires`), so a value
    used in several places is computed once and the RTL keeps the names of
    the class code."""

    def __init__(self, comp: DataTypeComponent, where: str, state=frozenset(),
                 wires: Optional[_Wires] = None):
        self.index = {f.name: i for i, f in enumerate(comp.fields)}
        self.where = where
        self.state = set(state)
        self.wires = wires
        #: Bit width of each local, by env key.
        self.width: Dict[object, int] = {}
        #: State fields read after a write on the path (before SSA).
        self.raw: set = set()
        self.depth = 0

    def err(self, n, what: str):
        raise SyncElabError(f"{self.where}: {what}: {n.syntax or n.kind.name}")

    def ref(self, n, name: str) -> ExprRefField:
        if name not in self.index:
            self.err(n, f"no field '{name}'")
        return ExprRefField(base=TypeExprRefSelf(), index=self.index[name])

    def read(self, n, name: str, env: dict):
        r = self.ref(n, name)
        if r.index in self.state and r.index in env:
            self.raw.add(r.index)
            return env[r.index]
        return r

    def elems(self, n, sym) -> List[Tuple[int, str]]:
        el = _elems(sym)
        if el[0][0] is None:
            self.err(n, f"'{sym.name}' is not an array")
        return [(i, _ename(sym.name, i)) for i, _ in el]

    def set_local(self, sym, v, env: dict):
        key = _local(sym)
        w = sym.type.canonicalType.bitWidth if sym.type.canonicalType.isIntegral else 0
        self.width[key] = w
        env[key] = self.wires.wire(sym.name, w, v) if self.wires is not None and w else v

    def process(self, body) -> list:
        return self.run([body], {})

    # -- statements ---------------------------------------------------------

    def run(self, items: list, env: dict) -> list:
        """IR statements for the work list ``items`` (statements and loop
        continuations); updates ``env`` to the values at the end."""
        out: list = []
        items = list(items)
        while items:
            s = items.pop(0)
            if isinstance(s, tuple):
                if s[0] == "for":
                    st, n = s[1], s[2]
                    c = _fold(self.expr(st.stopExpr, env)) if st.stopExpr is not None else None
                    if c is None:
                        self.err(st, "loop bound is not static")
                    if n >= _MAX_ITER:
                        self.err(st, f"loop runs more than {_MAX_ITER} times")
                    if c:
                        items[:0] = [st.body, ("step", st), ("for", st, n + 1)]
                elif s[0] == "step":
                    for e in s[1].steps:
                        self.effect(_unwrap(e), env, out)
                else:                               # ("bind", key, value)
                    env[s[1]] = ExprConstant(value=s[2])
                continue
            k = s.kind
            if k == ast.StatementKind.List:
                items[:0] = list(s.list)
            elif k == ast.StatementKind.Block:
                items[:0] = [s.body]
            elif k == ast.StatementKind.Empty:
                pass
            elif k == ast.StatementKind.VariableDeclaration:
                sym = s.symbol
                self.set_local(sym, self.expr(sym.initializer, env)
                               if sym.initializer is not None else ExprConstant(value=0), env)
            elif k == ast.StatementKind.ExpressionStatement:
                self.effect(_unwrap(s.expr), env, out)
            elif k == ast.StatementKind.Return:
                if s.expr is not None:
                    env[("ret", self.depth)] = self.expr(s.expr, env)
                return out                          # the rest of the path is not reached
            elif k == ast.StatementKind.Conditional:
                if len(s.conditions) != 1 or s.conditions[0].pattern is not None:
                    self.err(s, "unsupported condition")
                test = self.expr(s.conditions[0].expr, env)
                then = [s.ifTrue]
                other = [s.ifFalse] if s.ifFalse is not None else []
                c = _fold(test)
                if c is not None:
                    items[:0] = then if c else other
                    continue
                final = _returns(s)
                if final:
                    then, other, items = then + items, other + items, []
                e_then, e_else = dict(env), dict(env)
                body = self.run(then, e_then)
                orelse = self.run(other, e_else)
                if body:
                    out.append(StmtIf(test=test, body=body, orelse=orelse))
                elif orelse:
                    out.append(StmtIf(test=ExprUnary(op=UnaryOp.Not, operand=test),
                                      body=orelse, orelse=[]))
                self.merge(env, test, e_then, e_else, final)
            elif k == ast.StatementKind.ForLoop:
                for v in s.loopVars:
                    self.set_local(v, self.expr(v.initializer, env)
                                   if v.initializer is not None else ExprConstant(value=0), env)
                for e in s.initializers:
                    self.effect(_unwrap(e), env, out)
                items[:0] = [("for", s, 0)]
            elif k == ast.StatementKind.ForeachLoop:
                if len(s.loopDims) != 1 or s.loopDims[0].loopVar is None:
                    self.err(s, "foreach over more than one dimension")
                r, var = s.loopDims[0].range, s.loopDims[0].loopVar
                lft, rgt = int(r.left), int(r.right)
                d = 1 if rgt >= lft else -1
                seq: list = []
                for i in range(lft, rgt + d, d):
                    seq += [("bind", _local(var), i), s.body]
                items[:0] = seq
            else:
                self.err(s, f"unsupported statement {k.name}")
        return out

    def merge(self, env: dict, test, e_then: dict, e_else: dict, final: bool = False):
        """``env`` after an ``if``. With ``final`` (the rest of the body ran
        in the branches), the locals are dead: only state and return values
        are merged."""
        for key in set(e_then) | set(e_else):
            if final and isinstance(key, tuple) and key[0] == "local":
                continue
            old = env.get(key)
            if old is None and isinstance(key, int):
                old = ExprRefField(base=TypeExprRefSelf(), index=key)
            a, b = e_then.get(key, old), e_else.get(key, old)
            if a is None or b is None:              # set on one path only
                env[key] = a if b is None else b
            else:
                env[key] = _ifexp(test, a, b)
                if self.wires is not None and self.width.get(key):
                    env[key] = self.wires.wire(key[1], self.width[key], env[key])

    def effect(self, e, env: dict, out: list):
        if isinstance(e, ast.AssignmentExpression):
            if e.isCompound or e.isNonBlocking:
                self.err(e, "only plain '=' assignment")
            self.assign(e, _unwrap(e.left), self.expr(e.right, env), env, out)
            return
        if e.kind == ast.ExpressionKind.UnaryOp and e.op in _INC:
            t = _unwrap(e.operand)
            self.assign(e, t, _bin(self.expr(t, env), _INC[e.op], ExprConstant(value=1)),
                        env, out)
            return
        if isinstance(e, ast.CallExpression):
            if self.user_fn(e):
                self.inline(e, env, out)
                return
            port, op, args = self.port_call(e, env)
            if op == "set" and len(args) == 1:
                if not isinstance(port, str):
                    self.err(e, "a port write needs a constant index")
                out.append(StmtAssign(targets=[self.ref(e, port)],
                                      value=self.expr(args[0], env)))
                return
        self.err(e, "unsupported statement expression")

    def assign(self, n, left, v, env: dict, out: list):
        if left.kind == ast.ExpressionKind.NamedValue:
            sym = left.symbol
            if sym.kind == ast.SymbolKind.ClassProperty:
                r = self.ref(n, sym.name)
                out.append(StmtAssign(targets=[r], value=v))
                if r.index in self.state:
                    env[r.index] = v
                return
            if sym.kind in _LOCALS:
                self.set_local(sym, v, env)
                return
        elif left.kind == ast.ExpressionKind.ElementSelect:
            arr = _unwrap(left.value)
            if arr.kind == ast.ExpressionKind.NamedValue \
                    and arr.symbol.kind == ast.SymbolKind.ClassProperty:
                names = self.elems(n, arr.symbol)
                sel = self.expr(left.selector, env)
                c = _fold(sel)
                if c is not None:
                    name = dict(names).get(c)
                    if name is None:
                        self.err(n, f"index {c} is out of range")
                    r = self.ref(n, name)
                    out.append(StmtAssign(targets=[r], value=v))
                    if r.index in self.state:
                        env[r.index] = v
                    return
                for i, name in names:
                    r = self.ref(n, name)
                    test = _cmp(sel, CmpOp.Eq, ExprConstant(value=i))
                    out.append(StmtIf(test=test, body=[StmtAssign(targets=[r], value=v)],
                                      orelse=[]))
                    if r.index in self.state:
                        env[r.index] = _ifexp(test, v, env.get(r.index, r))
                return
        self.err(n, "assignment target is not a state property")

    # -- calls --------------------------------------------------------------

    @staticmethod
    def user_fn(e) -> bool:
        """A call of a function of the class (not of fw-hdl's base classes)."""
        if e.isSystemCall or e.thisClass is not None:
            return False
        sub = e.subroutine
        return sub.body is not None and not sub.lexicalPath.startswith("fw_hdl_pkg::")

    def inline(self, e, env: dict, out: Optional[list]):
        """Inlines the call ``e``; returns the value it returns. With ``out``
        None (a call in an expression), the function must not write fields."""
        sub = e.subroutine
        if self.depth >= 16:
            self.err(e, "calls nest too deep (recursion?)")
        inner = dict(env)
        for f, a in zip(sub.arguments, e.arguments):
            if f.direction != ast.ArgumentDirection.In:
                self.err(e, f"argument '{f.name}' is not an input")
            self.set_local(f, self.expr(a, env), inner)
        self.depth += 1
        key = ("ret", self.depth)
        inner.pop(key, None)
        try:
            stmts = self.run([sub.body], inner)
        finally:
            self.depth -= 1
        for k, v in inner.items():
            if isinstance(k, int):
                env[k] = v
        if stmts:
            if out is None:
                self.err(e, "a function called in an expression writes fields")
            out.extend(stmts)
        ret = inner.get(key)
        if out is None and ret is None:
            self.err(e, "the function returns no value")
        rt = sub.returnType.canonicalType
        if ret is not None and self.wires is not None and rt.isIntegral:
            ret = self.wires.wire(sub.name, rt.bitWidth, ret)
        return ret

    def port_call(self, e, env: dict):
        """``p.set_x(v)``/``p.get_x()`` as ``("p_x", "set"|"get", args)``;
        on a role port's channel ``p.ch.set_x(v)`` is ``"p_chx"``; on an
        element of a port array ``p[i].get_x()`` is ``"p_<i>_x"``, or, for a
        non-constant ``i``, ``(i, [(index, "p_<index>_x")])``."""
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
        if obj is not None and obj.kind == ast.ExpressionKind.ElementSelect \
                and name[:4] in ("set_", "get_"):
            arr = _unwrap(obj.value)
            if arr.kind == ast.ExpressionKind.NamedValue \
                    and arr.symbol.kind == ast.SymbolKind.ClassProperty:
                alts = [(i, f"{n}_{name[4:]}") for i, n in self.elems(e, arr.symbol)]
                sel = self.expr(obj.selector, env)
                c = _fold(sel)
                if c is not None:
                    port = dict(alts).get(c)
                    if port is None:
                        self.err(e, f"index {c} is out of range")
                    return port, name[:3], list(e.arguments)
                return (sel, alts), name[:3], list(e.arguments)
        if obj is None or obj.kind != ast.ExpressionKind.NamedValue \
                or obj.symbol.kind != ast.SymbolKind.ClassProperty \
                or name[:4] not in ("set_", "get_"):
            self.err(e, "unsupported call")
        return f"{obj.symbol.name}_{name[4:]}", name[:3], list(e.arguments)

    # -- expressions --------------------------------------------------------

    def expr(self, e, env: dict):
        e = _unwrap(e)
        k = e.kind
        if k == ast.ExpressionKind.IntegerLiteral:
            return ExprConstant(value=int(e.value))
        cv = e.constant if k != ast.ExpressionKind.Call else None
        if cv is not None and not cv.empty:
            try:
                return ExprConstant(value=int(cv.value))
            except (TypeError, ValueError):
                pass
        if k == ast.ExpressionKind.NamedValue:
            sym = e.symbol
            if sym.kind == ast.SymbolKind.ClassProperty:
                return self.read(e, sym.name, env)
            if sym.kind in _LOCALS:
                key = _local(sym)
                if key not in env:
                    self.err(e, f"'{sym.name}' is read before it is set")
                return env[key]
            if sym.kind == ast.SymbolKind.Parameter:
                try:
                    return ExprConstant(value=int(sym.value.value))
                except (TypeError, ValueError):
                    pass
        elif k == ast.ExpressionKind.Call:
            if not e.isSystemCall and e.thisClass is None \
                    and e.subroutine.name == "in_reset":
                return self.ref(e, "reset")
            if self.user_fn(e):
                return self.inline(e, env, None)
            port, op, args = self.port_call(e, env)
            if op == "get" and not args:
                if isinstance(port, str):
                    return self.ref(e, port)
                sel, alts = port
                return _mux(sel, [(i, self.ref(e, p)) for i, p in alts])
        elif k == ast.ExpressionKind.ElementSelect:
            arr = _unwrap(e.value)
            if arr.kind == ast.ExpressionKind.NamedValue \
                    and arr.symbol.kind == ast.SymbolKind.ClassProperty:
                sel = self.expr(e.selector, env)
                try:
                    return _mux(sel, [(i, self.read(e, n, env))
                                      for i, n in self.elems(e, arr.symbol)])
                except SyncElabError as x:
                    self.err(e, str(x))
        elif k == ast.ExpressionKind.MemberAccess and e.member.kind == ast.SymbolKind.Field:
            return _slice(self.expr(e.value, env), int(e.member.bitOffset),
                          e.member.type.canonicalType.bitWidth)
        elif k == ast.ExpressionKind.UnaryOp and e.op in _UN:
            v = self.expr(e.operand, env)
            c = _fold(v)
            if c is not None and e.op == ast.UnaryOperator.LogicalNot:
                return ExprConstant(value=int(not c))
            return ExprUnary(op=_UN[e.op], operand=v)
        elif k == ast.ExpressionKind.BinaryOp:
            l, r = self.expr(e.left, env), self.expr(e.right, env)
            if e.op in _BOOL:
                return ExprBool(op=_BOOL[e.op], values=[l, r])
            if e.op in _BIN:
                return _bin(l, _BIN[e.op], r)
            if e.op in _CMP:
                return _cmp(l, _CMP[e.op], r)
        elif k == ast.ExpressionKind.ConditionalOp:
            if len(e.conditions) == 1 and e.conditions[0].pattern is None:
                return _ifexp(self.expr(e.conditions[0].expr, env),
                              self.expr(e.left, env), self.expr(e.right, env))
        self.err(e, "unsupported expression")


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
    # What a field nobody writes is driven by (the class's only process, or
    # step() when it has both).
    kind = ProcessKind.SYNC if step is not None else ProcessKind.COMB

    comp = DataTypeComponent(name=name or ct.name, super=None)
    fields = comp.fields
    if step is not None:
        fields.append(FieldInOut(name="clock", datatype=_int(1), is_out=False))
        fields.append(FieldInOut(name="reset", datatype=_int(1), is_out=False))

    # Outputs and state get their drive (and outputs their reset-force) once
    # the bodies say which process writes them.
    force: Dict[int, Optional[int]] = {}

    def port_field(fname: str, w: int, out: bool, f_force):
        if out:
            force[len(fields)] = f_force
        fields.append(FieldInOut(name=fname, datatype=_int(w), is_out=out))

    reset_set = _reset_assigned(step) if step is not None else set()
    for p in _members(ct, ast.SymbolKind.ClassProperty):
        for ix, t in _elems(p):
            pname = _ename(p.name, ix)
            where = f"{ct.name}.{p.name}" + (f"[{ix}]" if ix is not None else "")
            if t.kind == ast.SymbolKind.ClassType and not _derives(t, "fw_sync_port") \
                    and _role_holders(t):
                role, dirs = _role_port(where, t)
                for ch, ht in _role_holders(t):
                    if dirs.get(ch) not in ("FW_FWD", "FW_REV"):
                        raise SyncElabError(f"{where}: channel '{ch}' has no "
                                            f"add_ctl direction in {t.name}")
                    # Role 0 drives the FWD fields of a forward channel.
                    drives = "FW_SYNC_FWD" if (dirs[ch] == "FW_FWD") == (role == 0) \
                        else "FW_SYNC_BWD"
                    for fname, w, d, fo in _holder_fields(ht):
                        port_field(f"{pname}_{ch}{fname}", w, d == drives, fo)
            elif t.kind == ast.SymbolKind.ClassType:
                if not _derives(t, "fw_sync_port"):
                    raise SyncElabError(f"{where}: class property is not a sync port "
                                        f"({t.name})")
                view = _generic_name(t)
                if view.endswith("_sp_out"):
                    drives = "FW_SYNC_FWD"
                elif view.endswith("_sp_in"):
                    drives = "FW_SYNC_BWD"
                else:
                    raise SyncElabError(f"{where}: view {view} is neither *_sp_in nor "
                                        f"*_sp_out")
                sig = _prop(t, "sig")
                if sig is None:
                    raise SyncElabError(f"{view}: no 'sig' holder")
                for fname, w, d, fo in _holder_fields(sig.type.canonicalType):
                    port_field(f"{pname}_{fname}", w, d == drives, fo)
            elif t.isIntegral:
                fields.append(Field(name=pname, datatype=_int(t.bitWidth),
                                    no_reset=(step is not None
                                              and p.name not in reset_set)))
            else:
                raise SyncElabError(f"{where}: unsupported state type {t}")

    state = {i for i, f in enumerate(fields) if not isinstance(f, FieldInOut)}
    wires = _Wires(comp)
    procs: List[Tuple[Function, list]] = []
    if comb is not None:
        b = _Body(comp, f"{ct.name}.comb", wires=wires)
        fn = Function(name="comb", process_kind=ProcessKind.COMB, body=[],
                      metadata={"sv": comb, "lint": []})
        procs.append((fn, b.process(comb.body)))
    raw: set = set()
    if step is not None:
        b = _Body(comp, f"{ct.name}.step", state, wires)
        fn = Function(name="step", process_kind=ProcessKind.SYNC, body=[],
                      metadata={"sv": step, "lint": [],
                                "clock": ExprRefField(base=TypeExprRefSelf(), index=0),
                                "reset": ExprRefField(base=TypeExprRefSelf(), index=1)})
        procs.append((fn, b.process(step.body)))
        raw = b.raw

    # Drive: the process that writes the field.
    writer: Dict[int, Function] = {}
    for fn, body in procs:
        reads, writes = set(), set()
        _rw(body, reads, writes)
        for i in writes:
            if i in writer:
                raise SyncElabError(f"{ct.name}: '{fields[i].name}' is written by both "
                                    f"{writer[i].name}() and {fn.name}()")
            writer[i] = fn
    for i, f in enumerate(fields):
        if (isinstance(f, FieldInOut) and not f.is_out) or i in wires.indices:
            continue                        # inputs, clock, reset; wires
        f.drive = writer[i].process_kind if i in writer else kind
        if i in force and f.drive == ProcessKind.SYNC:
            f.reset_force = force[i]

    if wires.stmts:
        procs.insert(0, (Function(name="wires", process_kind=ProcessKind.COMB, body=[],
                                  metadata={"sv": None, "lint": []}), wires.stmts))
    for fn, body in procs:
        if fn.name != "wires":
            _check(ct, comp, fn, body)
        fn.body = body
        if fn.process_kind == ProcessKind.SYNC:
            if raw and _ported(step):
                msg = (f"{ct.name}.step: (* fw_ported *) reads state after writing it: "
                       f"{', '.join(fields[i].name for i in sorted(raw))} (reads the new "
                       f"value, not the register)")
                fn.metadata["lint"].append(msg)
                warnings.warn(msg, SyncLintWarning, stacklevel=2)
            comp.sync_processes.append(fn)
        else:
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
