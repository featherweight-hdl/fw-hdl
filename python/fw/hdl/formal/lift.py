"""Lift an SVUnit test body to one static-subset IR function (F0/F1).

``formal-svunit.md`` §3. The test task ``SVTEST_<name>`` becomes

    function bit [K+1:0] __prove_<name>(<one argument per randomized value>);

and the result packs, LSB first, ``assume``, ``failed`` and one bit per
obligation:

* ``std::randomize(v...) with {C}`` and ``obj.randomize() with {C}`` assign
  each randomized value a fresh argument and AND their constraints into
  ``assume``. The call returns 1. A constraint only counts while no failure
  has been reported: after a failure the dynamic test has given up.
* each reached ``svunit_pkg::current_tc.fail(kind, cond, ...)`` -- every
  ``FAIL_*`` macro expands to one -- is an obligation: if ``assume`` holds, no
  earlier obligation failed, and ``cond`` is true, it sets ``failed`` and its
  own bit. ``$error``/``$fatal`` are obligations with ``cond`` = 1.
* ``api.f(args, out)`` on the generated call API is devirtualized through the
  model binding: ``out = <path of f>(args)``.
* ``repeat (N)`` is one iteration, provided the iterations are independent:
  no value written in the body is read before the body writes it.

The model functions are mapped by :class:`StaticMapper` as for the XLS flow,
so the test body and the design share the static subset and its 2-state
semantics.
"""
from __future__ import annotations

import dataclasses as dc
import os
from typing import Callable, Dict, List, Optional, Set, Tuple

import zuspec.ir.core as ir
from pyslang import ast

from ..fe.static_mapper import EK, SK, UO, StaticMapper, _int_dt
from ..fn_api import FnApi

_IGNORED_SYSTASKS = {"$display", "$write", "$info", "$warning", "$monitor", "$strobe",
                     "$displayb", "$displayh", "$displayo"}
_FAILING_SYSTASKS = {"$error", "$fatal"}


@dc.dataclass
class Obligation:
    index: int
    kind: str            # fail_if, fail_unless_equal, $fatal, ...
    expr: str            # the macro's expression text
    file: str
    line: int


@dc.dataclass
class RandVar:
    name: str            # as written: `a`, `s.m`
    param: str           # the IR / SMT argument
    width: int
    signed: bool


@dc.dataclass
class RandSite:
    index: int           # the order in which a dynamic run reaches it
    file: str
    line: int
    text: str
    vars: List[RandVar]
    #: the call's text in *file*, ``with`` clause included, as offsets
    #: (``-1`` when it is not all in the file); a replay replaces it.
    start: int = -1
    end: int = -1


@dc.dataclass
class LiftedTest:
    name: str
    function: str                     # the IR function's name
    functions: List[ir.Function]      # it, and the model functions it calls
    sites: List[RandSite]
    obligations: List[Obligation]
    #: API function path (`crc32_pkg::main`) -> the IR function its calls map to
    api_functions: Dict[str, str] = dc.field(default_factory=dict)

    @property
    def params(self) -> List[RandVar]:
        return [v for s in self.sites for v in s.vars]


@dc.dataclass
class _Obj:
    """A class object of the test: one local per property."""
    cls: object
    fields: Dict[str, str]            # property name -> IR local
    props: Dict[str, object]          # property name -> ClassProperty symbol
    name: str


def _bit(v: int) -> ir.Expr:
    return ir.ExprCast(target_type=_int_dt(1, False), value=ir.ExprConstant(value=v))


def _ref(name: str) -> ir.Expr:
    return ir.ExprRefLocal(name=name)


def _not(x: ir.Expr) -> ir.Expr:
    return ir.ExprUnary(op=ir.UnaryOp.Not, operand=x)


def _and(*xs: ir.Expr) -> ir.Expr:
    return ir.ExprBool(op=ir.BoolOp.And, values=list(xs))


def _or(*xs: ir.Expr) -> ir.Expr:
    return ir.ExprBool(op=ir.BoolOp.Or, values=list(xs))


def _const_str(e) -> str:
    c = getattr(e, "constant", None)
    if c is not None:
        return str(c).strip('"')
    if e.kind == EK.Conversion:
        return _const_str(e.operand)
    if e.kind == EK.StringLiteral:
        return str(e.value)
    return ""


def _class_chain(cls) -> List[object]:
    """*cls* and its bases, most derived first."""
    out = []
    while cls is not None:
        out.append(cls)
        b = cls.baseClass
        cls = b.canonicalType if b is not None else None
    return out


def is_fail_call(e) -> bool:
    """A call of ``svunit_testcase::fail`` (what every FAIL_* macro expands to)."""
    if e is None or e.kind != EK.Call or e.isSystemCall or e.subroutineName != "fail":
        return False
    this = e.thisClass
    return this is not None and "svunit_testcase" in str(this.type)


class TestLifter(StaticMapper):
    """Maps one SVUnit test task, and the model functions it reaches."""

    ASSUME, FAILED = "__assume", "__failed"

    def __init__(self, config, reporter, source_manager, api: Optional[FnApi],
                 resolve: Callable[[str], object]):
        super().__init__(config, reporter, source_manager)
        self.api = api
        self.resolve = resolve        # function path -> pyslang Subroutine
        self._pre: List[List[ir.Stmt]] = []
        self._sites: List[RandSite] = []
        self._obls: List[Obligation] = []
        self._args: List[ir.Arg] = []
        self._objs: Dict[str, _Obj] = {}
        self._this_obj: Optional[_Obj] = None
        self._loop_depth = 0
        self._api_names: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # The test
    # ------------------------------------------------------------------
    def lift_test(self, task, name: str) -> LiftedTest:
        self.fields, self.port_dirs = {}, {}
        self.locals, self.local_names, self.params = {}, set(), {}
        self.ret_var, self.in_function = None, None
        fn_name = f"__prove_{name}"
        self._fn_names["__test__"] = fn_name
        self.local_names.update({self.ASSUME, self.FAILED})
        body = self.body(task.body)
        obl = [f"__ob{o.index}" for o in self._obls]
        decls = [ir.StmtAnnAssign(target=_ref(n), annotation=ir.ExprConstant(value="bit"),
                                  ir_type=_int_dt(1, False), value=_bit(v))
                 for n, v in [(self.ASSUME, 1), (self.FAILED, 0)] + [(o, 0) for o in obl]]
        ret = ir.ExprConcat(values=[_ref(n) for n in reversed(obl)]
                            + [_ref(self.FAILED), _ref(self.ASSUME)])
        fn = ir.Function(name=fn_name, args=ir.Arguments(args=list(self._args)),
                         returns=_int_dt(len(obl) + 2, False),
                         body=decls + body + [ir.StmtReturn(value=ret)], loc=self.loc(task))
        while self._fn_queue:
            sub = self._fn_queue.pop(0)
            f = self.map_function(sub)
            self.functions[f.name] = f
        return LiftedTest(name=name, function=fn_name,
                          functions=[fn] + list(self.functions.values()),
                          sites=list(self._sites), obligations=list(self._obls),
                          api_functions=dict(self._api_names))

    def literal_int(self, e) -> Optional[int]:
        """A constant, or a literal: in a task body slang leaves literals
        without a constant value."""
        v = self.const_int(e)
        if v is None and e.kind == EK.IntegerLiteral:
            v = self.svint_value(e.value)
        if v is None and e.kind == EK.Conversion:
            v = self.literal_int(e.operand)
        return v

    def _original_span(self, e) -> Tuple[int, int]:
        """*e*'s text in the file it was written in (through macro arguments)."""
        try:
            r = self.sm.getFullyOriginalRange(e.sourceRange)
            if (r.start.buffer == r.end.buffer and r.end.offset > r.start.offset
                    and os.path.abspath(str(self.sm.getFileName(r.start))) ==
                    self._where(e)[0]):
                return int(r.start.offset), int(r.end.offset)
        except Exception:                 # no original range: not replayable
            pass
        return -1, -1

    def _where(self, node) -> Tuple[str, int]:
        loc = self.loc(node)
        return (os.path.abspath(loc.file), loc.line) if loc is not None else ("", 0)

    # ------------------------------------------------------------------
    # Statements
    # ------------------------------------------------------------------
    def stmt(self, s) -> List[ir.Stmt]:
        # Expressions with effects (randomize) leave statements in the buffer;
        # they run before the statement that holds the expression.
        self._pre.append([])
        try:
            out = super().stmt(s)
        finally:
            pre = self._pre.pop()
        return pre + out

    def _stmt(self, s) -> List[ir.Stmt]:
        k = s.kind
        if k == SK.Conditional and len(s.conditions) == 1 \
                and is_fail_call(s.conditions[0].expr):
            return self.obligation(s.conditions[0].expr)
        if k == SK.RepeatLoop:
            n = self.literal_int(s.count)
            if n is None or n < 1:
                raise self.fail("formal: the repeat count must be a constant of at least 1", s)
            self.check_independent(s.body)
            return self.body(s.body)
        if k == SK.VariableDeclaration and s.symbol.type.canonicalType.kind \
                == ast.SymbolKind.ClassType:
            return self.declare_object(s.symbol, s)
        if k in (SK.ForLoop, SK.WhileLoop, SK.DoWhileLoop, SK.ForeverLoop, SK.ForeachLoop):
            self._loop_depth += 1
            try:
                return super()._stmt(s)
            finally:
                self._loop_depth -= 1
        return super()._stmt(s)

    def obligation(self, call) -> List[ir.Stmt]:
        a = call.arguments
        file, line = self._where(call)
        o = Obligation(index=len(self._obls), kind=_const_str(a[0]), expr=_const_str(a[2]),
                       file=os.path.abspath(_const_str(a[3])) if _const_str(a[3]) else file,
                       line=int(self.literal_int(a[4]) or line))
        return self._obligation(o, self.expr(a[1]))

    def _obligation(self, o: Obligation, cond: ir.Expr) -> List[ir.Stmt]:
        self._obls.append(o)
        bit = f"__ob{o.index}"
        self.local_names.add(bit)
        return [ir.StmtIf(test=_and(_ref(self.ASSUME), _not(_ref(self.FAILED)), cond),
                          body=[ir.StmtAssign(targets=[_ref(self.FAILED)], value=_bit(1)),
                                ir.StmtAssign(targets=[_ref(bit)], value=_bit(1))],
                          orelse=[])]

    def expr_stmt(self, e) -> List[ir.Stmt]:
        if e.kind == EK.Conversion and str(e.type) == "void":
            self.expr(e.operand)          # void'(std::randomize(...))
            return []
        return super().expr_stmt(e)

    def call_stmt(self, e) -> List[ir.Stmt]:
        if e.isSystemCall:
            name = e.subroutineName
            if name in _IGNORED_SYSTASKS:
                return []
            if name in _FAILING_SYSTASKS:
                file, line = self._where(e)
                o = Obligation(index=len(self._obls), kind=name, expr=name, file=file,
                               line=line)
                return self._obligation(o, _bit(1))
            if name == "randomize":
                self.expr(e)
                return []
        api = self._api_fn(e)
        if api is not None:
            return self.api_call(e, api)
        if e.thisClass is not None and e.subroutineName in ("rand_mode", "constraint_mode",
                                                            "srandom"):
            raise self.fail(f"formal: {e.subroutineName}() is not supported yet", e)
        return super().call_stmt(e)

    # -- the call API ----------------------------------------------------
    def _api_fn(self, e):
        if self.api is None or e.thisClass is None or e.isSystemCall:
            return None
        ct = e.thisClass.type.canonicalType
        if getattr(ct, "name", None) not in (self.api.name, f"{self.api.name}_proxy",
                                             f"{self.api.name}_model"):
            return None
        for f in self.api.functions:
            if f.name == e.subroutineName:
                return f
        raise self.fail(f"{e.subroutineName!r} is not a function of API {self.api.name}", e)

    def api_call(self, e, f) -> List[ir.Stmt]:
        """``api.f(in..., out)`` -> ``out = <f.path>(in...)``: the model binding."""
        args = list(e.arguments)
        if len(args) != len(f.args) + 1 or args[-1].kind != EK.Assignment:
            raise self.fail(f"call of API task {f.name!r}: expected {len(f.args)} inputs and "
                            f"the result", e)
        sub = self.resolve(f.path)
        name = self.request_function(sub, e)
        self._api_names[f.path] = name
        call = ir.ExprCall(func=ir.ExprAttribute(value=ir.TypeExprRefSelf(), attr=name),
                           args=[self.expr(a) for a in args[:-1]])
        out = args[-1].left
        if int(out.type.bitWidth) != f.ret.bits:
            call = self.cast(call, int(out.type.bitWidth), bool(out.type.isSigned))
        return [ir.StmtAssign(targets=[self.lvalue_expr(out)], value=call)]

    # -- class objects -----------------------------------------------------
    def declare_object(self, sym, node) -> List[ir.Stmt]:
        init = sym.initializer
        if init is None or init.kind != EK.NewClass or list(getattr(init, "arguments", []) or []):
            raise self.fail(f"formal: class object {sym.name!r} must be created where it is "
                            f"declared, with `new` and no arguments", node)
        cls = sym.type.canonicalType
        obj = _Obj(cls=cls, fields={}, props={}, name=sym.name)
        out: List[ir.Stmt] = []
        for c in reversed(_class_chain(cls)):
            for m in c:
                if m.kind != ast.SymbolKind.ClassProperty or m.name in obj.props:
                    continue
                if str(m.lifetime) != "VariableLifetime.Automatic":
                    raise self.fail(f"formal: static property {c.name}::{m.name} is not "
                                    f"supported", m)
                local = f"{sym.name}__{m.name}"
                n, i = local, 0
                while n in self.local_names:
                    i += 1
                    n = f"{local}__{i}"
                self.local_names.add(n)
                obj.fields[m.name], obj.props[m.name] = n, m
                dt = self.dtype(m.type, m, f"property {m.name!r}", decl=True)
                value = None
                mi = getattr(m, "initializer", None)
                if mi is not None:
                    if getattr(mi, "constant", None) is None:
                        raise self.fail(f"formal: the initializer of {c.name}::{m.name} must "
                                        f"be a constant", m)
                    value = self.const_value(mi.constant, m.type, mi)
                out.append(ir.StmtAnnAssign(target=_ref(n), annotation=ir.ExprConstant(
                    value=str(m.type)), ir_type=dt, value=value, loc=self.loc(node)))
        self._objs[self.key(sym)] = obj
        return out

    def _obj_of(self, e) -> Optional[_Obj]:
        if e is not None and e.kind == EK.NamedValue:
            return self._objs.get(self.key(e.symbol))
        return None

    def named(self, e) -> ir.Expr:
        sym = e.symbol
        if sym.kind == ast.SymbolKind.ClassProperty and self._this_obj is not None:
            if sym.name not in self._this_obj.fields:
                raise self.fail(f"unknown property {sym.name!r}", e)
            return _ref(self._this_obj.fields[sym.name])
        if sym.kind == ast.SymbolKind.Variable and self.key(sym) in self._objs:
            raise self.fail(f"formal: class object {sym.name!r} is used as a value; only "
                            f"its properties and randomize() are supported", e)
        return super().named(e)

    def member(self, e) -> ir.Expr:
        obj = self._obj_of(e.value)
        if obj is not None:
            return _ref(obj.fields[e.member.name])
        return super().member(e)

    # ------------------------------------------------------------------
    # Expressions
    # ------------------------------------------------------------------
    def _expr(self, e) -> ir.Expr:
        if e.kind == EK.Call and e.isSystemCall and e.subroutineName == "randomize":
            return self.randomize(e)
        if e.kind == EK.Inside:
            return self.inside(e)
        if e.kind == EK.StringLiteral and e.type.isIntegral:
            # A string literal as a packed value ("1" -> 8'h31): in a task body
            # slang gives it no constant value.
            w = int(e.type.bitWidth)
            return ir.ExprCast(target_type=_int_dt(w, False), value=ir.ExprConstant(
                value=self.svint(e.intValue.value, w, e)))
        return super()._expr(e)

    def _cmp(self, op: ir.CmpOp, a, b) -> ir.Expr:
        """``a op b`` at the wider of the two widths (both signed: signed)."""
        w = max(int(a.type.bitWidth), int(b.type.bitWidth))
        s = bool(a.type.isSigned) and bool(b.type.isSigned)
        return ir.ExprCompare(left=self.cast(self.expr(a), w, s), ops=[op],
                              comparators=[self.cast(self.expr(b), w, s)])

    def inside(self, e) -> ir.Expr:
        terms = []
        for r in e.rangeList:
            if r.kind == EK.ValueRange:
                if "+/-" in str(r.syntax) or "+%-" in str(r.syntax):
                    raise self.fail("formal: tolerance ranges in `inside` are not supported", r)
                terms.append(_and(self._cmp(ir.CmpOp.GtE, e.left, r.left),
                                  self._cmp(ir.CmpOp.LtE, e.left, r.right)))
            elif r.type.isUnpackedArray:
                raise self.fail("formal: `inside` an array is not supported", r)
            else:
                terms.append(self._cmp(ir.CmpOp.Eq, e.left, r))
        return _or(*terms) if len(terms) > 1 else terms[0]

    def _truth(self, e) -> ir.Expr:
        x = self.expr(e)
        w = int(e.type.bitWidth)
        if w == 1:
            return x
        return ir.ExprCompare(left=x, ops=[ir.CmpOp.NotEq], comparators=[
            ir.ExprCast(target_type=_int_dt(w, bool(e.type.isSigned)),
                        value=ir.ExprConstant(value=0))])

    # -- randomize -----------------------------------------------------------
    def randomize(self, e) -> ir.Expr:
        if self._loop_depth:
            raise self.fail("formal: randomize() inside a for/while loop is not supported; "
                            "use `repeat`, whose iterations are independent", e)
        if not self._pre:
            raise self.fail("formal: randomize() is only supported in a statement", e)
        info = e.subroutine.extraInfo
        if list(getattr(info, "constraintRestrictions", None) or []):
            raise self.fail("formal: randomize() with a restricted `with (...)` list is not "
                            "supported", e)
        args = list(e.arguments)
        file, line = self._where(e)
        site = RandSite(index=len(self._sites), file=file, line=line,
                        text=str(e.syntax).strip() if e.syntax else "randomize", vars=[])
        site.start, site.end = self._original_span(e)
        pre = self._pre[-1]
        obj = None
        targets = []                      # (name, lvalue IR, type)
        if len(args) == 1 and args[0].type.canonicalType.kind == ast.SymbolKind.ClassType:
            obj = self._obj_of(args[0])
            if obj is None:
                raise self.fail("formal: randomize() of an object not declared in the test", e)
            for c in _class_chain(obj.cls):
                for m in c:
                    if m.kind == ast.SymbolKind.Subroutine and m.name in (
                            "pre_randomize", "post_randomize") and m.syntax is not None:
                        raise self.fail(f"formal: {c.name}::{m.name}() is not supported yet", m)
            for pname, p in obj.props.items():
                mode = str(p.randMode)
                if mode == "RandMode.RandC":
                    raise self.fail(f"formal: randc property {pname!r} is not supported", p)
                if mode == "RandMode.Rand":
                    targets.append((f"{obj.name}.{pname}", _ref(obj.fields[pname]), p.type))
        else:
            for a in args:
                v = a.left if a.kind == EK.Assignment else a
                targets.append((str(v.syntax).strip() if v.syntax else "v",
                                self.lvalue_expr(v), v.type))
        for vname, lv, t in targets:
            safe = "".join(ch if ch.isalnum() else "_" for ch in vname)
            param = f"__r{site.index}_{safe}"
            dt = self.dtype(t, e, f"randomized value {vname!r}", decl=True)
            if not isinstance(dt, ir.DataTypeInt):
                raise self.fail(f"formal: randomized value {vname!r} must be an integral value",
                                e)
            self._args.append(ir.Arg(arg=param, datatype=dt, loc=self.loc(e)))
            pre.append(ir.StmtAssign(targets=[lv], value=ir.ExprRefParam(name=param)))
            site.vars.append(RandVar(name=vname, param=param, width=int(t.bitWidth),
                                     signed=bool(t.isSigned)))
        conds: List[ir.Expr] = []
        saved = self._this_obj
        self._this_obj = obj
        try:
            if obj is not None:
                seen: Set[str] = set()
                for c in _class_chain(obj.cls):
                    for m in c:
                        if m.kind == ast.SymbolKind.ConstraintBlock and m.name not in seen:
                            seen.add(m.name)
                            conds.append(self.constraint(m.constraints))
            ic = getattr(info, "inlineConstraints", None)
            if ic is not None:
                conds.append(self.constraint(ic))
        finally:
            self._this_obj = saved
        if conds:
            c = conds[0] if len(conds) == 1 else _and(*conds)
            pre.append(ir.StmtAssign(targets=[_ref(self.ASSUME)], value=_and(
                _ref(self.ASSUME), _or(_ref(self.FAILED), c))))
        self._sites.append(site)
        return ir.ExprCast(target_type=_int_dt(int(e.type.bitWidth), bool(e.type.isSigned)),
                           value=ir.ExprConstant(value=1))

    def constraint(self, c) -> ir.Expr:
        k = c.kind
        CK = ast.ConstraintKind
        if k == CK.List:
            items = [self.constraint(x) for x in c.list]
            return _bit(1) if not items else items[0] if len(items) == 1 else _and(*items)
        if k == CK.Expression:
            if c.isSoft:
                raise self.fail("formal: soft constraints are not supported", c.expr)
            if c.expr.kind == EK.Dist:
                return self.dist(c.expr)
            return self._truth(c.expr)
        if k == CK.Implication:
            return _or(_not(self._truth(c.predicate)), self.constraint(c.body))
        if k == CK.Conditional:
            other = self.constraint(c.elseBody) if c.elseBody is not None else _bit(1)
            return ir.ExprIfExp(test=self._truth(c.predicate),
                                body=self.constraint(c.ifBody), orelse=other)
        if k == CK.SolveBefore:
            return _bit(1)              # shapes the distribution, not the solutions
        raise self.fail(f"formal: {k.name} constraints are not supported", c)

    def dist(self, e) -> ir.Expr:
        """``x dist {...}`` constrains x to the items of nonzero weight (LRM 18.5.3)."""
        terms = []
        for it in e.items:
            w = it.weight
            if w is not None:
                wv = self.literal_int(w.expr) if hasattr(w, "expr") else None
                if wv is None:
                    raise self.fail("formal: dist weights must be constants", e)
                if wv == 0:
                    continue
            r = it.value
            if r.kind == EK.ValueRange:
                terms.append(_and(self._cmp(ir.CmpOp.GtE, e.left, r.left),
                                  self._cmp(ir.CmpOp.LtE, e.left, r.right)))
            else:
                terms.append(self._cmp(ir.CmpOp.Eq, e.left, r))
        if not terms:
            return _bit(0)
        return _or(*terms) if len(terms) > 1 else terms[0]

    # ------------------------------------------------------------------
    # repeat: are the iterations independent?
    # ------------------------------------------------------------------
    def check_independent(self, body) -> None:
        """Reject a value carried from one iteration to the next: one written in
        the body, declared outside it, and read before the body writes it."""
        inside: Set[str] = set()
        writes: Set[object] = set()
        events: List[Tuple[str, object, int, object]] = []   # (r|w, key, depth, node)
        self._scan_stmt(body, 0, inside, events)
        writes = {k for ev, k, _, _ in events if ev == "w"}
        carried = {k for k in writes if (k[0] if isinstance(k, tuple) else k) not in inside}
        defined: Set[object] = set()
        for ev, k, depth, node in events:
            if ev == "w":
                if depth == 0:
                    defined.add(k)
            elif k in carried and k not in defined:
                name = k[1] if isinstance(k, tuple) else k.split("@")[0]
                raise self.fail(f"formal: {name!r} is carried from one repeat iteration to "
                                f"the next, so the iterations are not independent", node)

    def _scan_stmt(self, s, depth, inside, ev) -> None:
        if s is None:
            return
        k = s.kind
        if k == SK.List:
            for x in s.list:
                self._scan_stmt(x, depth, inside, ev)
        elif k == SK.Block:
            self._scan_stmt(s.body, depth, inside, ev)
        elif k == SK.VariableDeclaration:
            inside.add(self.key(s.symbol))
            if s.symbol.initializer is not None:
                self._scan_expr(s.symbol.initializer, depth, ev)
        elif k == SK.ExpressionStatement:
            self._scan_expr(s.expr, depth, ev)
        elif k == SK.Conditional:
            for c in s.conditions:
                self._scan_expr(c.expr, depth, ev)
            self._scan_stmt(s.ifTrue, depth + 1, inside, ev)
            self._scan_stmt(s.ifFalse, depth + 1, inside, ev)
        elif k == SK.RepeatLoop:
            self._scan_stmt(s.body, depth + 1, inside, ev)
        elif k == SK.ForLoop:
            for v in s.loopVars:
                inside.add(self.key(v))
            for x in list(s.initializers) + ([s.stopExpr] if s.stopExpr else []) \
                    + list(s.steps):
                self._scan_expr(x, depth + 1, ev)
            self._scan_stmt(s.body, depth + 1, inside, ev)
        elif k == SK.Case:
            self._scan_expr(s.expr, depth, ev)
            for it in s.items:
                for x in it.expressions:
                    self._scan_expr(x, depth, ev)
                self._scan_stmt(it.stmt, depth + 1, inside, ev)
            self._scan_stmt(s.defaultCase, depth + 1, inside, ev)
        else:
            for a in ("body", "ifTrue", "stmt"):
                x = getattr(s, a, None)
                if isinstance(x, ast.Statement):
                    self._scan_stmt(x, depth + 1, inside, ev)

    def _lkey(self, e):
        """The storage an lvalue names, and whether it is all of it."""
        if e.kind == EK.NamedValue:
            return self.key(e.symbol), True
        if e.kind == EK.MemberAccess and e.value.kind == EK.NamedValue:
            return (self.key(e.value.symbol), e.member.name), True
        if e.kind in (EK.ElementSelect, EK.RangeSelect, EK.MemberAccess):
            k, _ = self._lkey(e.value)
            return k, False
        return None, False

    def _scan_write(self, lv, depth, ev) -> None:
        if lv.kind == EK.Concatenation:
            for o in lv.operands:
                self._scan_write(o, depth, ev)
            return
        k, whole = self._lkey(lv)
        for a in ("selector", "left", "right"):
            x = getattr(lv, a, None)
            if lv.kind != EK.NamedValue and isinstance(x, ast.Expression):
                self._scan_expr(x, depth, ev)
        if k is None:
            return
        if not whole:
            ev.append(("r", k, depth, lv))        # a partial write keeps the rest
        ev.append(("w", k, depth if whole else depth + 1, lv))

    def _scan_expr(self, e, depth, ev) -> None:
        if e is None:
            return
        k = e.kind
        if k == EK.NamedValue:
            ev.append(("r", self.key(e.symbol), depth, e))
        elif k == EK.MemberAccess and e.value.kind == EK.NamedValue:
            ev.append(("r", (self.key(e.value.symbol), e.member.name), depth, e))
        elif k == EK.Assignment:
            if e.right is not None and e.right.kind != EK.EmptyArgument:
                self._scan_expr(e.right, depth, ev)
            self._scan_write(e.left, depth, ev)
        elif k == EK.UnaryOp and e.op in (UO.Postincrement, UO.Preincrement,
                                          UO.Postdecrement, UO.Predecrement):
            self._scan_expr(e.operand, depth, ev)
            self._scan_write(e.operand, depth, ev)
        elif k == EK.Call:
            if e.isSystemCall and e.subroutineName == "randomize":
                args = list(e.arguments)
                obj = self._obj_of(args[0]) if len(args) == 1 else None
                if obj is not None:
                    okey = self.key(args[0].symbol)
                    for pname, p in obj.props.items():
                        if str(p.randMode) == "RandMode.Rand":
                            ev.append(("w", (okey, pname), depth, e))
                else:
                    for a in args:
                        self._scan_write(a.left if a.kind == EK.Assignment else a, depth, ev)
                ic = getattr(e.subroutine.extraInfo, "inlineConstraints", None)
                if ic is not None:
                    self._scan_constraint(ic, depth, ev)
                return
            for a in e.arguments:
                self._scan_expr(a, depth, ev)
        elif k == EK.ConditionalOp:
            for c in e.conditions:
                self._scan_expr(c.expr, depth, ev)
            self._scan_expr(e.left, depth + 1, ev)
            self._scan_expr(e.right, depth + 1, ev)
        elif k == EK.Inside:
            self._scan_expr(e.left, depth, ev)
            for r in e.rangeList:
                self._scan_expr(r, depth, ev)
        else:
            for a in ("operand", "left", "right", "value", "selector", "concat"):
                x = getattr(e, a, None)
                if isinstance(x, ast.Expression):
                    self._scan_expr(x, depth, ev)
            for x in (getattr(e, "operands", None) or []):
                self._scan_expr(x, depth, ev)

    def _scan_constraint(self, c, depth, ev) -> None:
        CK = ast.ConstraintKind
        if c.kind == CK.List:
            for x in c.list:
                self._scan_constraint(x, depth, ev)
        elif c.kind == CK.Expression:
            self._scan_expr(c.expr, depth, ev)
        elif c.kind in (CK.Implication, CK.Conditional):
            self._scan_expr(c.predicate, depth, ev)
            for a in ("body", "ifBody", "elseBody"):
                x = getattr(c, a, None)
                if x is not None:
                    self._scan_constraint(x, depth, ev)
