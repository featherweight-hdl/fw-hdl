"""Synchronous classes to *parameterized* Zuspec IR components.

:func:`sync_component_param` is the structure-preserving counterpart of
:func:`fw.hdl.fe.elab.sync.sync_component`: one IR component per class, with
the class's parameters as the component's ``template_params``, so the emitted
module can be used at any parameter value (``examples/rr_merge/LOWERING.md``,
L9). Nothing is unrolled or flattened:

- a value parameter (``int DEPTH = 2``) is a ``TemplateParamValue``, read as
  ``ExprRefParam("DEPTH")``; a type parameter (``type T = rr_beat_t``) is a
  ``TemplateParamType``, used as ``DataTypeRef("T")``. Defaults are the class
  declaration's;
- widths and sizes written from parameters stay expressions
  (``DataTypeInt.width_expr``, ``DataTypeArray.size_expr``), translated from
  the declaration syntax: ``bit [$clog2(DEPTH)-1:0]`` is width
  ``clog2(DEPTH)``. A port's field types follow the parameter arguments of the
  view and holder declarations (``fw_rv_sp_in #(T)`` → ``fw_rv_sig #(T)`` →
  ``T data_cur``). Packed structs from packages become ``DataTypeStruct``
  types named ``<types_pkg>::<name>`` (:attr:`_Types.structs`);
- a port array (``fw_rv_sp_in #(T) in[N]``) is one array field per holder
  field (``in_valid``: N bits, ``in_data``: N of T); a state array is an array
  field;
- process bodies keep their statements: ``for``/``foreach`` are ``StmtFor``
  over ``range(lo, hi)``, element and member selects are ``ExprSubscript`` and
  ``ExprAttribute``, locals are ``ExprRefLocal`` (declared in
  ``metadata["locals"]``), a ``return`` that ends a process path moves the
  rest of the body into the other branch. Functions of the class become
  ``Function`` entries of ``comp.functions``, called as
  ``ExprCall(ExprAttribute(self, name))``; they may not write fields;
- ``step()`` keeps the class's blocking order: its process has
  ``metadata["order"] = "blocking"`` (it reads state it wrote earlier in the
  same call). The back end maps it to next-state logic.

:func:`composite_param` lowers a statically elaborated composite to one
module that instantiates its children with the parameter arguments of their
declarations.
"""
from __future__ import annotations

import dataclasses as dc
from typing import Dict, List, Optional, Tuple

from pyslang import ast

from zuspec.ir.core.connection import ModuleInstance, PortConnection
from zuspec.ir.core.data_type import (DataType, DataTypeArray, DataTypeComponent,
                                      DataTypeInt, DataTypeRef, DataTypeStruct, Function,
                                      ProcessKind, TemplateParamKind, TemplateParamType,
                                      TemplateParamValue)
from zuspec.ir.core.expr import (BinOp, Expr, ExprAttribute, ExprBin, ExprBool, ExprCall,
                                 ExprCast, ExprCompare, ExprConstant, ExprIfExp,
                                 ExprRefField, ExprRefLocal, ExprRefParam, ExprRefUnresolved,
                                 ExprSubscript, ExprUnary, TypeExprRefSelf, UnaryOp)
from zuspec.ir.core.fields import Field, FieldInOut
from zuspec.ir.core.stmt import Arg, Arguments, StmtAssign, StmtFor, StmtIf, StmtReturn

from . import hier
from .sync import (_BIN, _BOOL, _CMP, _INC, _LOCALS, _UN, SyncElabError, _derives,
                   _generic_name, _holder_fields, _members, _prop, _returns, _role_holders,
                   _sub, _unwrap)

_SYN_BIN = {"AddExpression": BinOp.Add, "SubtractExpression": BinOp.Sub,
            "MultiplyExpression": BinOp.Mult, "DivideExpression": BinOp.Div,
            "ModExpression": BinOp.Mod}
_INT_KW = {"IntType": (32, True), "IntegerType": (32, True), "ByteType": (8, True),
           "ShortIntType": (16, True), "LongIntType": (64, True)}
_BIT_KW = ("BitType", "LogicType", "RegType")


def _c(v: int) -> ExprConstant:
    return ExprConstant(value=v)


def _cv(e: Expr) -> Optional[int]:
    return e.value if isinstance(e, ExprConstant) and isinstance(e.value, int) else None


def _bin(l: Expr, op: BinOp, r: Expr) -> Expr:
    """``l op r``, folded when both are constants; ``x - 1 + 1`` is ``x``."""
    a, b = _cv(l), _cv(r)
    if a is not None and b is not None:
        f = {BinOp.Add: a + b, BinOp.Sub: a - b, BinOp.Mult: a * b,
             BinOp.Div: a // b if b else None, BinOp.Mod: a % b if b else None}[op]
        if f is not None:
            return _c(f)
    if op == BinOp.Add and b is not None and isinstance(l, ExprBin) \
            and l.op == BinOp.Sub and _cv(l.rhs) == b:
        return l.lhs
    if op in (BinOp.Add, BinOp.Sub) and b == 0:
        return l
    return ExprBin(lhs=l, op=op, rhs=r)


def _clog2(v: int) -> int:
    return max(0, (v - 1).bit_length())


def _tok(n) -> str:
    return n.valueText if hasattr(n, "valueText") else str(n).strip()


def _kind(n) -> str:
    return n.kind.name


class _Types:
    """Packed structs the components use, by qualified name."""

    def __init__(self, pkg: str):
        self.pkg = pkg
        self.structs: Dict[str, DataTypeStruct] = {}

    def struct(self, t) -> DataType:
        """The IR type of a semantic (non-parameter) type ``t``."""
        name = t.name if t.kind == ast.SymbolKind.TypeAlias else None
        c = t.canonicalType
        if c.kind == ast.SymbolKind.PackedStructType:
            if not name:
                raise SyncElabError(f"anonymous struct type {c}: give it a typedef")
            q = f"{self.pkg}::{name}"
            if q not in self.structs:
                fields = [Field(name=m.name, datatype=self.struct(m.type))
                          for m in c if m.kind == ast.SymbolKind.Field]
                self.structs[q] = DataTypeStruct(name=q, super=None, fields=fields)
            return DataTypeRef(ref_name=q)
        if c.isIntegral:
            return DataTypeInt(bits=c.bitWidth, signed=c.isSigned)
        raise SyncElabError(f"unsupported type {t}")


class _Scope:
    """The names of a (specialized) class in the terms of the lowered class:
    ``env`` maps each parameter of ``ct`` to its IR value (a ``DataType`` for a
    type parameter, an ``Expr`` for a value parameter)."""

    def __init__(self, ct, env: Dict[str, object], types: _Types):
        self.ct, self.env, self.types = ct, env, types

    def err(self, what: str):
        raise SyncElabError(f"{self.ct.name}: {what}")

    # -- constant expressions (widths, sizes, parameter arguments) ----------

    def cexpr(self, s) -> Expr:
        k = _kind(s)
        if k in ("SimplePropertyExpr", "SimpleSequenceExpr"):
            return self.cexpr(s.expr)
        if k == "ParenthesizedExpression":
            return self.cexpr(s.expression)
        if k == "IntegerLiteralExpression":
            return _c(int(s.literal.value))
        if k == "IdentifierName":
            name = _tok(s.identifier)
            v = self.env.get(name)
            if isinstance(v, Expr):
                return v
            sym = self.ct.lookupName(name)
            if sym is not None and sym.kind == ast.SymbolKind.Parameter:
                return _c(int(sym.value.value))     # a localparam
            self.err(f"'{name}' is not a value parameter")
        if k in _SYN_BIN:
            return _bin(self.cexpr(s.left), _SYN_BIN[k], self.cexpr(s.right))
        if k == "InvocationExpression" and _kind(s.left) == "SystemName":
            fn = _tok(s.left.systemIdentifier)
            args = [a for a in s.arguments.parameters if _kind(a) == "OrderedArgument"]
            if fn == "$clog2" and len(args) == 1:
                a = self.cexpr(args[0].expr)
                if _cv(a) is not None:
                    return _c(_clog2(_cv(a)))
                return ExprCall(func=ExprRefUnresolved(name="clog2"), args=[a])
        self.err(f"unsupported constant expression '{str(s).strip()}'")

    def width(self, dim) -> Expr:
        """The width of packed dimension syntax ``[hi:lo]``."""
        sel = dim.specifier.selector
        if _kind(sel) != "SimpleRangeSelect":
            self.err(f"unsupported packed dimension '{str(dim).strip()}'")
        hi, lo = self.cexpr(sel.left), self.cexpr(sel.right)
        if _cv(lo) != 0:
            self.err(f"packed dimension '{str(dim).strip()}' is not [w-1:0]")
        return _bin(hi, BinOp.Add, _c(1))

    def size(self, dim) -> Expr:
        """The size of unpacked dimension syntax ``[N]``."""
        sel = dim.specifier.selector if _kind(dim.specifier) == "RangeDimensionSpecifier" \
            else None
        if sel is None or _kind(sel) != "BitSelect":
            self.err(f"unsupported unpacked dimension '{str(dim).strip()}' (write [N])")
        return self.cexpr(sel.expr)

    # -- types --------------------------------------------------------------

    def dtype(self, ts, sem) -> DataType:
        """The IR type of type syntax ``ts``; ``sem`` is its semantic type."""
        k = _kind(ts)
        if k in _BIT_KW:
            dims = list(ts.dimensions)
            signed = ts.signing is not None and _tok(ts.signing) == "signed"
            if not dims:
                return DataTypeInt(bits=1, signed=signed)
            if len(dims) != 1:
                self.err(f"more than one packed dimension: '{str(ts).strip()}'")
            w = self.width(dims[0])
            bits = sem.canonicalType.bitWidth if sem is not None else _cv(w)
            return DataTypeInt(bits=bits, signed=signed,
                               width_expr=None if _cv(w) is not None else w)
        if k in _INT_KW:
            bits, signed = _INT_KW[k]
            return DataTypeInt(bits=bits, signed=signed)
        if k == "NamedType":
            n = ts.name
            if _kind(n) == "IdentifierName":
                name = _tok(n.identifier)
                v = self.env.get(name)
                if isinstance(v, DataType):
                    return v
                sym = self.ct.lookupName(name)
                if sym is not None and sym.kind == ast.SymbolKind.TypeAlias \
                        and sym.parentScope is not None \
                        and _members(self.ct, ast.SymbolKind.TypeAlias).count(sym):
                    return self.dtype(sym.targetType.typeSyntax, sym.targetType.type)
            if sem is None:
                sym = self.ct.lookupName(str(n).strip())
                if sym is None or not sym.isType:
                    self.err(f"cannot resolve type '{str(ts).strip()}'")
                sem = sym
            return self.types.struct(sem)
        self.err(f"unsupported type '{str(ts).strip()}'")

    def arg_type(self, s, sem) -> DataType:
        """A type parameter's argument (expression syntax naming a type)."""
        k = _kind(s)
        if k == "IdentifierName":
            name = _tok(s.identifier)
            v = self.env.get(name)
            if isinstance(v, DataType):
                return v
            sym = self.ct.lookupName(name)
            if sym is not None and sym.kind == ast.SymbolKind.TypeAlias \
                    and sym in _members(self.ct, ast.SymbolKind.TypeAlias):
                return self.dtype(sym.targetType.typeSyntax, sym.targetType.type)
            return self.types.struct(sem)
        if k in _BIT_KW or k in _INT_KW or k == "NamedType":
            return self.dtype(s, sem)
        if k == "ScopedName":
            return self.types.struct(sem)
        self.err(f"unsupported type argument '{str(s).strip()}'")

    # -- the scope of a member's class ---------------------------------------

    def sub(self, ts, t) -> "_Scope":
        """The scope of class type ``t``, declared as ``ts`` (``cls #(args)``) here."""
        name = ts.name if _kind(ts) == "NamedType" else ts
        if _kind(name) == "ScopedName":
            name = name.right
        args = []
        if _kind(name) == "ClassName" and name.parameters is not None:
            args = [a for a in name.parameters.parameters
                    if _kind(a) in ("OrderedParamAssignment", "NamedParamAssignment")]
        params = _params(t)
        env: Dict[str, object] = {}
        named = {_tok(a.name): a.expr for a in args if _kind(a) == "NamedParamAssignment"}
        ordered = [a.expr for a in args if _kind(a) == "OrderedParamAssignment"]
        for i, p in enumerate(params):
            s = ordered[i] if i < len(ordered) else named.get(p.name)
            if p.kind == ast.SymbolKind.TypeParameter:
                env[p.name] = self.arg_type(s, p.targetType.type) if s is not None \
                    else _Scope(t, env, self.types).default_type(p)
            else:
                env[p.name] = self.cexpr(s) if s is not None \
                    else _c(int(p.value.value))
        return _Scope(t, env, self.types)

    def default_type(self, p) -> DataType:
        return self.types.struct(p.targetType.type)

    def prop_type(self, prop) -> Tuple[DataType, Optional[Expr], Optional[int]]:
        """``(element type, size expr, size)`` of class property ``prop``;
        size None for a scalar."""
        dims = list(prop.syntax.dimensions) if prop.syntax is not None else []
        t = prop.type.canonicalType
        if not dims:
            if t.kind == ast.SymbolKind.ClassType:
                return None, None, None
            return self.dtype(prop.declaredType.typeSyntax, prop.type), None, None
        if len(dims) != 1 or not t.isUnpackedArray:
            self.err(f"'{prop.name}': only one unpacked dimension")
        el = t.arrayElementType
        et = None if el.canonicalType.kind == ast.SymbolKind.ClassType \
            else self.dtype(prop.declaredType.typeSyntax, el)
        return et, self.size(dims[0]), int(t.fixedRange.width)


def _params(t) -> list:
    """The (port) parameters of class type ``t``, in declaration order."""
    return [m for m in t if m.kind in (ast.SymbolKind.Parameter, ast.SymbolKind.TypeParameter)
            and m.isPortParam]


def _root_scope(ct, types: _Types) -> Tuple[_Scope, list]:
    """The scope of the lowered class ``ct`` and its template parameters."""
    env: Dict[str, object] = {}
    tps = []
    scope = _Scope(ct, env, types)
    # The defaults as declared (a specialization's parameters have no syntax).
    decls = {}
    g = ct.genericClass
    if g is not None and g.syntax is not None and g.syntax.parameters is not None:
        for d in g.syntax.parameters.declarations:
            for x in getattr(d, "declarators", []):
                if _kind(x) in ("TypeAssignment", "Declarator"):
                    decls[_tok(x.name)] = x
    dscope = _Scope(ct, {}, types)          # earlier parameters, by their defaults
    for p in _params(ct):
        decl = decls.get(p.name)
        if p.kind == ast.SymbolKind.TypeParameter:
            env[p.name] = DataTypeRef(ref_name=p.name)
            dflt = dscope.dtype(decl.assignment.type, None) \
                if decl is not None and decl.assignment is not None \
                else types.struct(p.targetType.type)
            dscope.env[p.name] = dflt
            tps.append(TemplateParamType(name=p.name, kind=TemplateParamKind.TYPE,
                                         default_value=dflt))
        else:
            env[p.name] = ExprRefParam(name=p.name)
            dflt = dscope.cexpr(decl.initializer.expr) \
                if decl is not None and decl.initializer is not None \
                else _c(int(p.value.value))
            dscope.env[p.name] = dflt
            vt = p.declaredType.typeSyntax
            tps.append(TemplateParamValue(
                name=p.name, kind=TemplateParamKind.VALUE,
                value_type=scope.dtype(vt, p.type) if vt is not None
                else DataTypeInt(bits=32, signed=True),
                default_value=dflt))
    return scope, tps


def _arr(et: DataType, size_expr: Optional[Expr], size: Optional[int]) -> DataType:
    if size is None:
        return et
    return DataTypeArray(element_type=et, size=size,
                         size_expr=None if _cv(size_expr) is not None else size_expr)


def _sync_ports(scope: _Scope, ct) -> Dict[str, Tuple[bool, list, Optional[Expr],
                                                      Optional[int]]]:
    """``{port: (is_out_view, [(field, type, dir, force)], size_expr, size)}``
    for the sync ports of class ``ct`` (size None for a scalar port)."""
    out = {}
    for p in _members(ct, ast.SymbolKind.ClassProperty):
        t = p.type.canonicalType
        el = t.arrayElementType.canonicalType if t.isUnpackedArray else t
        if el.kind != ast.SymbolKind.ClassType or _derives(el, "fw_component"):
            continue                        # state; a composite's children
        if not _derives(el, "fw_sync_port"):
            if _role_holders(el):
                raise SyncElabError(f"{ct.name}.{p.name}: role ports are not lowered "
                                    f"parameterized yet")
            raise SyncElabError(f"{ct.name}.{p.name}: class property is not a sync port "
                                f"({el.name})")
        view = _generic_name(el)
        if not (view.endswith("_sp_out") or view.endswith("_sp_in")):
            raise SyncElabError(f"{ct.name}.{p.name}: view {view} is neither *_sp_in "
                                f"nor *_sp_out")
        _, size_expr, size = scope.prop_type(p)
        vscope = scope.sub(p.declaredType.typeSyntax, el)
        sig = _prop(el, "sig")
        if sig is None:
            raise SyncElabError(f"{view}: no 'sig' holder")
        ht = sig.type.canonicalType
        hscope = vscope.sub(sig.declaredType.typeSyntax, ht)
        fields = []
        for fname, _, d, force in _holder_fields(ht):
            cur = _prop(ht, f"{fname}_cur")
            fields.append((fname, hscope.dtype(cur.declaredType.typeSyntax, cur.type), d,
                           force))
        out[p.name] = (view.endswith("_sp_out"), fields, size_expr, size)
    return out


class _Proc:
    """One process or function body as IR statements."""

    def __init__(self, low: "_Lower", kind: str):
        self.low, self.kind = low, kind     # kind: "comb", "step" or "fn"
        self.locals: List[Tuple[str, DataType]] = []
        self.names: Dict[object, str] = {}
        self.loop = 0

    def err(self, n, what: str):
        at = str(n.syntax).strip() if getattr(n, "syntax", None) is not None else ""
        raise SyncElabError(f"{self.low.ct.name}.{self.kind}: {what}"
                            + (f": '{at[:60]}'" if at else ""))

    # -- locals -------------------------------------------------------------

    @staticmethod
    def _key(sym):
        loc = sym.location
        return (sym.name, getattr(loc.buffer, "id", 0), loc.offset)

    def declare(self, sym, hoist: bool = True) -> str:
        used = set(self.names.values())
        name, i = sym.name, 0
        while name in used or name in self.low.field_ix:
            i += 1
            name = f"{sym.name}_{i}"
        self.names[self._key(sym)] = name
        if hoist:
            ts = sym.declaredType.typeSyntax
            self.locals.append((name, self.low.scope.dtype(ts, sym.type) if ts is not None
                                else self.low.types.struct(sym.type)))
        return name

    def local(self, n, sym) -> ExprRefLocal:
        name = self.names.get(self._key(sym))
        if name is None:
            self.err(n, f"'{sym.name}' is not declared in this process")
        return ExprRefLocal(name=name)

    # -- statements ---------------------------------------------------------

    def body(self, s) -> list:
        return self.run([s])

    def run(self, items: list) -> list:
        out: list = []
        items = list(items)
        while items:
            s = items.pop(0)
            k = s.kind
            if k == ast.StatementKind.List:
                items[:0] = list(s.list)
            elif k == ast.StatementKind.Block:
                items[:0] = [s.body]
            elif k == ast.StatementKind.Empty:
                pass
            elif k == ast.StatementKind.VariableDeclaration:
                sym = s.symbol
                if items and items[0].kind == ast.StatementKind.ForLoop \
                        and any(v == sym for v in items[0].loopVars):
                    continue                        # declared by the loop
                v = ExprRefLocal(name=self.declare(sym))
                if sym.initializer is not None:
                    out.append(StmtAssign(targets=[v], value=self.expr(sym.initializer)))
                elif self.loop:
                    out.append(StmtAssign(targets=[v], value=_c(0)))
            elif k == ast.StatementKind.ExpressionStatement:
                out.extend(self.effect(_unwrap(s.expr)))
            elif k == ast.StatementKind.Return:
                if self.kind == "fn":
                    out.append(StmtReturn(value=self.expr(s.expr) if s.expr is not None
                                          else None))
                elif self.loop:
                    self.err(s, "a return inside a loop of a process")
                return out                          # the rest of the path is not reached
            elif k == ast.StatementKind.Conditional:
                if len(s.conditions) != 1 or s.conditions[0].pattern is not None:
                    self.err(s, "unsupported condition")
                test = self.expr(s.conditions[0].expr)
                then = [s.ifTrue]
                other = [s.ifFalse] if s.ifFalse is not None else []
                if self.kind != "fn" and _returns(s):
                    then, other, items = then + items, other + items, []
                body, orelse = self.run(then), self.run(other)
                if body:
                    out.append(StmtIf(test=test, body=body, orelse=orelse))
                elif orelse:
                    out.append(StmtIf(test=ExprUnary(op=UnaryOp.Not, operand=test),
                                      body=orelse, orelse=[]))
            elif k == ast.StatementKind.ForLoop:
                out.append(self.for_loop(s))
            elif k == ast.StatementKind.ForeachLoop:
                out.append(self.foreach(s))
            else:
                self.err(s, f"unsupported statement {k.name}")
        return out

    def for_loop(self, s):
        """``for (int k = a; k < b; k++)`` as ``StmtFor(k, range(a, b))``."""
        bad = "only 'for (int k = a; k < b; k++)' loops"
        if len(s.loopVars) != 1 or s.initializers or len(s.steps) != 1 \
                or s.stopExpr is None:
            self.err(s, bad)
        var = s.loopVars[0]
        if var.initializer is None:
            self.err(s, bad)
        lo = self.expr(var.initializer)
        stop = _unwrap(s.stopExpr)
        st = _unwrap(s.steps[0])
        if stop.kind != ast.ExpressionKind.BinaryOp \
                or stop.op not in (ast.BinaryOperator.LessThan,
                                   ast.BinaryOperator.LessThanEqual) \
                or _unwrap(stop.left).kind != ast.ExpressionKind.NamedValue \
                or _unwrap(stop.left).symbol != var:
            self.err(s, bad)
        if st.kind != ast.ExpressionKind.UnaryOp or st.op not in (
                ast.UnaryOperator.Postincrement, ast.UnaryOperator.Preincrement) \
                or _unwrap(st.operand).symbol != var:
            self.err(s, bad)
        hi = self.expr(stop.right)
        if stop.op == ast.BinaryOperator.LessThanEqual:
            hi = _bin(hi, BinOp.Add, _c(1))
        return self.loop_stmt(var, lo, hi, s.body)

    def foreach(self, s):
        if len(s.loopDims) != 1 or s.loopDims[0].loopVar is None:
            self.err(s, "foreach over more than one dimension")
        arr = _unwrap(s.arrayRef)
        if arr.kind != ast.ExpressionKind.NamedValue \
                or arr.symbol.kind != ast.SymbolKind.ClassProperty:
            self.err(s, "foreach over something other than a class property")
        _, size_expr, size = self.low.scope.prop_type(arr.symbol)
        if size is None:
            self.err(s, "foreach over a scalar")
        return self.loop_stmt(s.loopDims[0].loopVar, _c(0), size_expr, s.body)

    def loop_stmt(self, var, lo: Expr, hi: Expr, body):
        name = self.declare(var, hoist=False)
        self.loop += 1
        try:
            stmts = self.body(body)
        finally:
            self.loop -= 1
        return StmtFor(target=ExprRefLocal(name=name),
                       iter=ExprCall(func=ExprRefUnresolved(name="range"), args=[lo, hi]),
                       body=stmts)

    def effect(self, e) -> list:
        if isinstance(e, ast.AssignmentExpression):
            if e.isNonBlocking:
                self.err(e, "a nonblocking assignment")
            left = _unwrap(e.left)
            v = self.expr(e.right)
            t = self.target(e, left)
            if e.isCompound:
                op = e.op
                if op not in _BIN:
                    self.err(e, "unsupported compound assignment")
                v = ExprBin(lhs=self.expr(left), op=_BIN[op], rhs=v)
            return [StmtAssign(targets=[t], value=v)]
        if e.kind == ast.ExpressionKind.UnaryOp and e.op in _INC:
            t = _unwrap(e.operand)
            return [StmtAssign(targets=[self.target(e, t)],
                               value=ExprBin(lhs=self.expr(t), op=_INC[e.op], rhs=_c(1)))]
        if isinstance(e, ast.CallExpression):
            pc = self.port_call(e)
            if pc is not None and pc[1] == "set" and len(pc[2]) == 1:
                ref, _, args = pc
                self.check_write(e, ref)
                return [StmtAssign(targets=[ref], value=self.expr(args[0]))]
            if self.user_fn(e):
                self.err(e, "a function called as a statement (it would write fields)")
        self.err(e, "unsupported statement expression")

    def target(self, n, left) -> Expr:
        if left.kind == ast.ExpressionKind.NamedValue:
            sym = left.symbol
            if sym.kind == ast.SymbolKind.ClassProperty:
                r = self.low.ref(n, sym.name)
                self.check_write(n, r)
                return r
            if sym.kind in _LOCALS:
                return self.local(n, sym)
        elif left.kind == ast.ExpressionKind.ElementSelect:
            return ExprSubscript(value=self.target(n, _unwrap(left.value)),
                                 slice=self.expr(left.selector))
        elif left.kind == ast.ExpressionKind.MemberAccess \
                and left.member.kind == ast.SymbolKind.Field:
            return ExprAttribute(value=self.target(n, _unwrap(left.value)),
                                 attr=left.member.name)
        self.err(n, "unsupported assignment target")

    def check_write(self, n, r: Expr):
        while isinstance(r, ExprSubscript):
            r = r.value
        f = self.low.comp.fields[r.index]
        if isinstance(f, FieldInOut) and not f.is_out:
            self.err(n, f"writes input '{f.name}' (driven outside the component)")
        if self.kind == "fn":
            self.err(n, f"a function writes '{f.name}' (only read-only functions are "
                        f"lowered parameterized)")
        if self.kind == "comb" and not isinstance(f, FieldInOut):
            self.err(n, f"writes state '{f.name}' (comb() has no state)")
        self.low.writes.setdefault(r.index, set()).add(self.kind)

    # -- calls --------------------------------------------------------------

    @staticmethod
    def user_fn(e) -> bool:
        if e.isSystemCall or e.thisClass is not None:
            return False
        sub = e.subroutine
        return sub.body is not None and not sub.lexicalPath.startswith("fw_hdl_pkg::")

    def port_call(self, e):
        """``p.set_x(v)``/``p[i].get_x()`` as ``(field ref, "set"|"get", args)``,
        or None."""
        if e.isSystemCall:
            return None
        name = e.subroutine.name
        obj = e.thisClass
        if obj is None or name[:4] not in ("set_", "get_"):
            return None
        obj = _unwrap(obj)
        idx = None
        if obj.kind == ast.ExpressionKind.ElementSelect:
            idx = self.expr(obj.selector)
            obj = _unwrap(obj.value)
        if obj.kind != ast.ExpressionKind.NamedValue \
                or obj.symbol.kind != ast.SymbolKind.ClassProperty:
            return None
        ref = self.low.ref(e, f"{obj.symbol.name}_{name[4:]}")
        if idx is not None:
            ref = ExprSubscript(value=ref, slice=idx)
        al = getattr(e.syntax, "arguments", None)
        nargs = len([a for a in al.parameters if a is not None]) if al is not None else 0
        return ref, name[:3], list(e.arguments)[:nargs]

    # -- expressions --------------------------------------------------------

    def expr(self, e) -> Expr:
        k = e.kind
        if k == ast.ExpressionKind.Conversion:
            if e.isImplicit:
                return self.expr(e.operand)
            ts = getattr(e.syntax, "left", None)
            if ts is None:
                return self.expr(e.operand)
            return ExprCast(target_type=self.low.scope.dtype(ts, e.type),
                            value=self.expr(e.operand))
        if k == ast.ExpressionKind.IntegerLiteral:
            return _c(int(e.value))
        if k == ast.ExpressionKind.UnbasedUnsizedIntegerLiteral:
            v = str(e.syntax).strip()
            if v in ("'0", "0"):
                return _c(0)
            self.err(e, f"unsupported literal {v}")
        if k == ast.ExpressionKind.NamedValue:
            sym = e.symbol
            if sym.kind == ast.SymbolKind.ClassProperty:
                return self.low.ref(e, sym.name)
            if sym.kind in _LOCALS:
                return self.local(e, sym)
            if sym.kind == ast.SymbolKind.Parameter:
                if sym.isPortParam and sym.name in self.low.scope.env:
                    return ExprRefParam(name=sym.name)
                return _c(int(sym.value.value))
        elif k == ast.ExpressionKind.Call:
            if e.isSystemCall:
                if e.subroutine.name == "$clog2":
                    return ExprCall(func=ExprRefUnresolved(name="clog2"),
                                    args=[self.expr(a) for a in e.arguments])
                self.err(e, f"unsupported system call {e.subroutine.name}")
            if e.thisClass is None and e.subroutine.name == "in_reset":
                return self.low.ref(e, "reset")
            if self.user_fn(e):
                name = self.low.function(e.subroutine)
                return ExprCall(func=ExprAttribute(value=TypeExprRefSelf(), attr=name),
                                args=[self.expr(a) for a in e.arguments])
            pc = self.port_call(e)
            if pc is not None and pc[1] == "get" and not pc[2]:
                return pc[0]
        elif k == ast.ExpressionKind.ElementSelect:
            return ExprSubscript(value=self.expr(e.value), slice=self.expr(e.selector))
        elif k == ast.ExpressionKind.MemberAccess and e.member.kind == ast.SymbolKind.Field:
            return ExprAttribute(value=self.expr(e.value), attr=e.member.name)
        elif k == ast.ExpressionKind.UnaryOp:
            if e.op in _UN:
                return ExprUnary(op=_UN[e.op], operand=self.expr(e.operand))
            if e.op == ast.UnaryOperator.Minus:
                return ExprUnary(op=UnaryOp.USub, operand=self.expr(e.operand))
        elif k == ast.ExpressionKind.BinaryOp:
            l, r = self.expr(e.left), self.expr(e.right)
            if e.op in _BOOL:
                return ExprBool(op=_BOOL[e.op], values=[l, r])
            if e.op in _BIN:
                return ExprBin(lhs=l, op=_BIN[e.op], rhs=r)
            if e.op == ast.BinaryOperator.Divide:
                return ExprBin(lhs=l, op=BinOp.Div, rhs=r)
            if e.op in _CMP:
                return ExprCompare(left=l, ops=[_CMP[e.op]], comparators=[r])
        elif k == ast.ExpressionKind.ConditionalOp:
            if len(e.conditions) == 1 and e.conditions[0].pattern is None:
                return ExprIfExp(test=self.expr(e.conditions[0].expr),
                                 body=self.expr(e.left), orelse=self.expr(e.right))
        self.err(e, f"unsupported expression '{str(e.syntax).strip() if e.syntax else k}'")


class _Lower:
    """State of lowering one class."""

    def __init__(self, ct, name: str, types: _Types):
        self.ct, self.types = ct, types
        self.scope, tps = _root_scope(ct, types)
        self.comp = DataTypeComponent(name=name, super=None, template_params=tps)
        self.field_ix: Dict[str, int] = {}
        self.writes: Dict[int, set] = {}
        self.fns: Dict[str, Function] = {}

    def add(self, f: Field) -> int:
        self.field_ix[f.name] = len(self.comp.fields)
        self.comp.fields.append(f)
        return self.field_ix[f.name]

    def ref(self, n, name: str) -> ExprRefField:
        if name not in self.field_ix:
            raise SyncElabError(f"{self.ct.name}: no field '{name}'")
        return ExprRefField(base=TypeExprRefSelf(), index=self.field_ix[name])

    def function(self, sub) -> str:
        """Lowers function ``sub`` of the class (once); returns its name."""
        if sub.name in self.fns:
            return sub.name
        fn = Function(name=sub.name, body=[])
        self.fns[sub.name] = fn                 # before the body: recursion
        p = _Proc(self, "fn")
        args = []
        for a in sub.arguments:
            if a.direction != ast.ArgumentDirection.In:
                raise SyncElabError(f"{self.ct.name}.{sub.name}: argument '{a.name}' is "
                                    f"not an input")
            n = p.declare(a, hoist=False)
            ts = a.declaredType.typeSyntax
            args.append(Arg(arg=n, datatype=self.scope.dtype(ts, a.type) if ts is not None
                            else self.types.struct(a.type)))
        fn.args = Arguments(args=args)
        proto = getattr(sub.syntax, "prototype", None) if sub.syntax is not None else None
        rts = getattr(proto, "returnType", None)
        rt = sub.returnType
        fn.returns = self.scope.dtype(rts, rt) if rts is not None \
            else self.types.struct(rt)
        fn.body = p.body(sub.body)
        fn.metadata["locals"] = p.locals
        fn.metadata["sv"] = sub
        return sub.name


def sync_component_param(ct, name: Optional[str] = None,
                         types: Optional[_Types] = None) -> DataTypeComponent:
    """The parameterized IR component of the class of specialization ``ct``."""
    step = _sub(ct, "step")
    comb = _sub(ct, "comb")
    if step is None and comb is None:
        raise SyncElabError(f"{ct.name}: neither step() nor comb()")
    kind = ProcessKind.SYNC if step is not None else ProcessKind.COMB
    types = types or _Types("fw_types")
    low = _Lower(ct, name or _generic_name(ct), types)
    if step is not None:
        low.add(FieldInOut(name="clock", datatype=DataTypeInt(bits=1, signed=False),
                           is_out=False))
        low.add(FieldInOut(name="reset", datatype=DataTypeInt(bits=1, signed=False),
                           is_out=False))
    force: Dict[int, Optional[int]] = {}
    ports = _sync_ports(low.scope, ct)
    for p in _members(ct, ast.SymbolKind.ClassProperty):
        if p.name in ports:
            is_out, fields, size_expr, size = ports[p.name]
            drives = "FW_SYNC_FWD" if is_out else "FW_SYNC_BWD"
            for fname, dt, d, fo in fields:
                i = low.add(FieldInOut(name=f"{p.name}_{fname}",
                                       datatype=_arr(dt, size_expr, size),
                                       is_out=(d == drives)))
                if d == drives:
                    force[i] = fo
            continue
        et, size_expr, size = low.scope.prop_type(p)
        if et is None:
            raise SyncElabError(f"{ct.name}.{p.name}: unsupported state type {p.type}")
        low.add(Field(name=p.name, datatype=_arr(et, size_expr, size)))

    procs: List[Tuple[Function, _Proc]] = []
    if comb is not None:
        pr = _Proc(low, "comb")
        fn = Function(name="comb", process_kind=ProcessKind.COMB, body=pr.body(comb.body),
                      metadata={"sv": comb})
        procs.append((fn, pr))
    if step is not None:
        pr = _Proc(low, "step")
        fn = Function(name="step", process_kind=ProcessKind.SYNC, body=pr.body(step.body),
                      metadata={"sv": step, "order": "blocking",
                                "clock": low.ref(None, "clock"),
                                "reset": low.ref(None, "reset")})
        procs.append((fn, pr))
    comp = low.comp
    for i, ks in low.writes.items():
        if len(ks) > 1:
            raise SyncElabError(f"{ct.name}: '{comp.fields[i].name}' is written by both "
                                f"comb() and step()")
    for i, f in enumerate(comp.fields):
        if isinstance(f, FieldInOut) and not f.is_out:
            continue
        ks = low.writes.get(i)
        f.drive = (ProcessKind.COMB if "comb" in ks else ProcessKind.SYNC) if ks else kind
        if i in force and f.drive == ProcessKind.SYNC:
            f.reset_force = force[i]
    for fn, pr in procs:
        fn.metadata["locals"] = pr.locals
        if fn.process_kind == ProcessKind.COMB:
            missed = [f.name for i, f in enumerate(comp.fields)
                      if f.drive == ProcessKind.COMB and isinstance(f, FieldInOut)
                      and f.is_out and i not in _always(fn.body, comp)]
            if missed:
                raise SyncElabError(f"{ct.name}.comb: output(s) {', '.join(missed)} not "
                                    f"assigned on every path (latch)")
            comp.comb_processes.append(fn)
        else:
            comp.sync_processes.append(fn)
    comp.functions.extend(low.fns.values())
    return comp


def _always(stmts: list, comp: DataTypeComponent) -> set:
    """Fields assigned (whole) on every path through ``stmts``. A loop over
    ``range(0, size)`` that assigns ``f[k]`` on every path assigns all of an
    array field ``f`` of that size."""
    out: set = set()
    for s in stmts:
        if isinstance(s, StmtAssign):
            t = s.targets[0]
            if isinstance(t, ExprRefField):
                out.add(t.index)
        elif isinstance(s, StmtIf):
            out |= _always(s.body, comp) & _always(s.orelse, comp)
        elif isinstance(s, StmtFor):
            lo, hi = s.iter.args
            if _cv(lo) != 0:
                continue
            k = s.target.name
            for x in _elem_writes(s.body, k):
                dt = comp.fields[x].datatype
                if isinstance(dt, DataTypeArray) and (
                        (dt.size_expr is not None and dt.size_expr == hi)
                        or (dt.size_expr is None and _cv(hi) == dt.size)):
                    out.add(x)
    return out


def _elem_writes(stmts: list, k: str) -> set:
    """Array fields ``f`` with ``f[k]`` assigned on every path through ``stmts``."""
    out: set = set()
    for s in stmts:
        if isinstance(s, StmtAssign):
            t = s.targets[0]
            if isinstance(t, ExprSubscript) and isinstance(t.value, ExprRefField) \
                    and isinstance(t.slice, ExprRefLocal) and t.slice.name == k:
                out.add(t.value.index)
        elif isinstance(s, StmtIf):
            out |= _elem_writes(s.body, k) & _elem_writes(s.orelse, k)
    return out


# -- composites ----------------------------------------------------------------

def _subst(x, env: Dict[str, object]):
    """``x`` (an IR type or expression of a child) with the child's parameters
    replaced by their arguments ``env``."""
    if isinstance(x, ExprRefParam) and x.name in env:
        return env[x.name]
    if isinstance(x, DataTypeRef) and x.ref_name in env:
        return env[x.ref_name]
    if dc.is_dataclass(x) and not isinstance(x, type):
        ch = {}
        for f in dc.fields(x):
            v = getattr(x, f.name)
            if isinstance(v, (Expr, DataType)):
                nv = _subst(v, env)
                if nv is not v:
                    ch[f.name] = nv
            elif isinstance(v, list) and v and all(isinstance(e, Expr) for e in v):
                nl = [_subst(e, env) for e in v]
                if any(a is not b for a, b in zip(nl, v)):
                    ch[f.name] = nl
        if ch:
            return dc.replace(x, **ch)
    return x


def composite_param(top: hier.Node, types: Optional[_Types] = None
                    ) -> Dict[str, DataTypeComponent]:
    """Parameterized IR components for composite ``top``: ``{module: component}``
    with one component per child class and the composite (``top.name``) last."""
    types = types or _Types(f"{top.name}_types")
    scope, tps = _root_scope(top.cls, types)
    out: Dict[str, DataTypeComponent] = {}
    kids: Dict[str, Tuple[DataTypeComponent, Dict[str, object]]] = {}
    kid_ports: Dict[str, Dict[str, List[str]]] = {}
    for cname, n in top.children.items():
        if n.children:
            raise SyncElabError(f"{n.path}: nested composites are not lowered yet")
        mod = _generic_name(n.cls)
        if mod not in out:
            out[mod] = sync_component_param(n.cls, mod, types)
        prop = _prop(top.cls, cname)
        if prop is None:
            raise SyncElabError(f"{top.path}: child '{cname}' is not held in a class "
                                f"property of the same name")
        env = scope.sub(prop.declaredType.typeSyntax, n.cls).env
        kids[cname] = (out[mod], env)
        kscope, _ = _root_scope(n.cls, types)
        kid_ports[cname] = {p: [f[0] for f in v[1]]
                            for p, v in _sync_ports(kscope, n.cls).items()}

    comp = DataTypeComponent(name=top.name, super=None, template_params=tps)
    own = _port_fields(_sync_ports(scope, top.cls))

    # Ports: "<child>.<port>" / ".<port>" with (element) index or None.
    def port_of(path: str):
        rel = path[len(top.path) + 1:] if path.startswith(top.path + ".") else ""
        parts = rel.split(".")
        name = parts[-1]
        idx = None
        if name.endswith("]"):
            name, ix = name[:-1].split("[")
            idx = int(ix)
        if len(parts) == 1:
            return "", name, idx
        if len(parts) == 2 and parts[0] in kids:
            return parts[0], name, idx
        raise SyncElabError(f"{top.path}: {path} is not a sync port of the composite or of "
                            f"a direct child")

    pairs: Dict[Tuple, List[Tuple]] = {}
    for method, recv, args in top.sync_connects:
        if method not in ("connect", "connect_up"):
            raise SyncElabError(f"{recv}.{method}: not lowered yet")
        a, b = port_of(recv), port_of(args[0])
        pairs.setdefault((a[:2], b[:2]), []).append((a[2], b[2]))

    # Fields of each side: {field: (type in top's terms, is_out from the side's view)}
    def side_fields(side) -> Dict[str, Tuple[DataType, bool]]:
        c, p = side
        if c == "":
            return {f: (dt, o) for (pp, f), (dt, o) in own.items() if pp == p}
        kc, env = kids[c]
        by_name = {f.name: f for f in kc.fields}
        return {f: (_subst(by_name[f"{p}_{f}"].datatype, env), by_name[f"{p}_{f}"].is_out)
                for f in kid_ports[c][p]}

    parent: Dict[Tuple, Tuple] = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            x = parent[x]
        return x

    for (sa, sb), idxs in pairs.items():
        fa, fb = side_fields(sa), side_fields(sb)
        if set(fa) != set(fb):
            raise SyncElabError(f"{top.path}: {sa} and {sb} have different fields")
        whole = all(i is None and j is None for i, j in idxs)
        if not whole:
            ta, tb = next(iter(fa.values()))[0], next(iter(fb.values()))[0]
            if not (isinstance(ta, DataTypeArray) and isinstance(tb, DataTypeArray)
                    and ta.size == tb.size and ta.size_expr == tb.size_expr
                    and sorted(idxs) == [(i, i) for i in range(ta.size)]):
                raise SyncElabError(
                    f"{top.path}: {'.'.join(x for x in sa if x)} and "
                    f"{'.'.join(x for x in sb if x)} are joined element by element in a "
                    f"way other than in[i] to in[i] for every i (not lowered "
                    f"parameterized)")
        for f in fa:
            parent[find((*sa, f))] = find((*sb, f))

    comp.fields.append(FieldInOut(name="clock", datatype=DataTypeInt(bits=1, signed=False),
                                  is_out=False))
    comp.fields.append(FieldInOut(name="reset", datatype=DataTypeInt(bits=1, signed=False),
                                  is_out=False))
    names: Dict[Tuple, str] = {}
    for (p, f), (dt, o) in own.items():
        r = find(("", p, f))
        if r in names:
            raise SyncElabError(f"{top.path}: ports {names[r]} and {p}_{f} are joined")
        names[r] = f"{p}_{f}"
        comp.fields.append(FieldInOut(name=names[r], datatype=dt, is_out=o))
    for cname, (kc, env) in kids.items():
        by_name = {f.name: f for f in kc.fields}
        for p, fs in kid_ports[cname].items():
            for f in fs:
                r = find((cname, p, f))
                if r not in names:
                    names[r] = f"{cname}_{p}_{f}"
                    comp.fields.append(Field(name=names[r],
                                             datatype=_subst(by_name[f"{p}_{f}"].datatype,
                                                             env)))
    for cname, (kc, env) in kids.items():
        conns = [PortConnection(port=f, signal=f) for f in ("clock", "reset")
                 if kc.sync_processes]
        conns += [PortConnection(port=f"{p}_{f}", signal=names[find((cname, p, f))])
                  for p, fs in kid_ports[cname].items() for f in fs]
        comp.module_instances.append(ModuleInstance(
            module=kc.name, name=cname, connections=conns,
            parameters={tp.name: env[tp.name] for tp in kc.template_params}))
    out[top.name] = comp
    return out


def _port_fields(ports) -> Dict[Tuple[str, str], Tuple[DataType, bool]]:
    """``{(port, field): (type, is_out)}`` of the composite's own ports (an
    own port's direction is that of the class's view)."""
    out = {}
    for p, (is_out, fields, size_expr, size) in ports.items():
        drives = "FW_SYNC_FWD" if is_out else "FW_SYNC_BWD"
        for fname, dt, d, _ in fields:
            out[(p, fname)] = (_arr(dt, size_expr, size), d == drives)
    return out
