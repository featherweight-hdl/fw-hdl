"""The elaboration interpreter: runs SV class code over the pyslang AST.

Elaboration of an fw-hdl design is ordinary SV execution at time 0:
constructors, build/connect, binds and bridge set-up, and the start of every
thread. This interpreter runs that code, and each thread runs until it blocks
(on a clock edge, a false ``wait``, an event, or a delay). The result is the
object heap plus a set of blocked threads; the translator turns each blocked
thread into a hardware process whose reset state is the point it blocked at.

Threads are Python generators. A statement executes as a generator and yields
a :class:`Block` when its thread must wait; expressions evaluate synchronously
(functions cannot block). Calls push a :class:`Frame` on the thread's stack, so
a blocked thread's stack says exactly where it is: the chain of call sites from
the thread's root and every local variable's value.
"""
from __future__ import annotations

import dataclasses as dc
from typing import Any, Callable, Dict, List, Optional, Tuple

from pyslang import ast

from .values import (Event, Iface, Obj, Opaque, const_to_py, copy_value, default_value,
                     fmt_sv, mask, to_signed, truthy, width_of)

SK = ast.StatementKind
EK = ast.ExpressionKind


class Val:
    """An already-evaluated argument, for calls made from Python."""
    kind = None

    def __init__(self, v):
        self.v = v


class ElabError(Exception):
    """The design cannot be elaborated (a $fatal, or an unsupported construct)."""


class _Break(Exception):
    pass


class _Continue(Exception):
    pass


class _Return(Exception):
    pass


@dc.dataclass
class Block:
    """Why a thread is waiting."""
    kind: str                       # 'edge' | 'time' | 'event' | 'wait' | 'delay0' | 'join'
    stmt: Any = None                # the statement that blocks
    cond: Optional[Callable[[], bool]] = None   # 'wait': resume when true
    event: Optional[Event] = None   # 'event'
    children: Optional[List["Thread"]] = None   # 'join'
    join_any: bool = False


class Frame:
    """One activation: a subroutine (or a thread root) with its locals."""

    def __init__(self, sub, this: Optional[Obj], iface: Optional[Iface],
                 call: Any = None, parent: Optional["Frame"] = None):
        self.sub = sub                  # SubroutineSymbol, or None for a root block
        self.this = this
        self.iface = iface              # interface instance context (interface code)
        self.call = call                # the CallExpression that made this frame
        self.locals: Dict[Any, Any] = {}
        self.loop_state: Dict[Any, Any] = {}   # implicit loop counters (repeat)
        self.parent = parent            # lexical parent for fork-branch frames
        self.pos: List[Any] = []        # statements being executed, outermost first

    def lookup(self, sym) -> Tuple[bool, Any]:
        f: Optional[Frame] = self
        while f is not None:
            if sym in f.locals:
                return True, f
            f = f.parent
        return False, None


@dc.dataclass
class ThreadRoot:
    """Where a thread starts: a fork branch (``stmt`` in ``frame``), an interface
    procedural block, or a call made by the elaboration entry."""
    kind: str                        # 'stmt' | 'call'
    stmt: Any = None
    frame: Optional[Frame] = None
    sub: Any = None                  # 'call': the subroutine and its receiver
    this: Optional[Obj] = None
    label: str = ""
    forever: bool = False            # an `always` block
    args: List[Any] = dc.field(default_factory=list)


class Thread:
    _next = 0

    def __init__(self, root: ThreadRoot):
        Thread._next += 1
        self.tid = Thread._next
        self.root = root
        self.gen = None
        self.block: Optional[Block] = None
        self.done = False
        self.stack: List[Frame] = []     # active frames, outermost first
        self.parent: Optional[Thread] = None

    def __repr__(self) -> str:
        return f"<thread {self.tid} {self.root.label}>"


class Interpreter:
    def __init__(self, compilation, top_inst):
        self.comp = compilation
        self.top = top_inst
        self.objects: List[Obj] = []
        self.ifaces: Dict[str, Iface] = {}
        self.statics: Dict[Any, Any] = {}      # static class properties
        self.threads: List[Thread] = []
        self.ready: List[Thread] = []
        self.nba: List[Tuple[Callable[[Any], None], Any]] = []
        self.cur: Optional[Thread] = None
        self.warnings: List[str] = []
        self._oid = 0

    # ------------------------------------------------------------------ heap
    def new_object(self, cls) -> Obj:
        self._oid += 1
        o = Obj(cls, self._oid)
        self.objects.append(o)
        c = cls
        while c is not None:
            for m in c:
                if m.kind == ast.SymbolKind.ClassProperty and not self._is_static(m):
                    o.fields[m] = default_value(m.type, m.name)
            c = self._base(c)
        return o

    @staticmethod
    def _base(cls):
        b = cls.baseClass
        if b is None:
            return None
        b = b.canonicalType
        return b if b.kind == ast.SymbolKind.ClassType else None

    @staticmethod
    def _is_static(prop) -> bool:
        return prop.lifetime == ast.VariableLifetime.Static

    def iface_of(self, inst) -> Iface:
        path = inst.hierarchicalPath
        f = self.ifaces.get(path)
        if f is None:
            f = Iface(inst, path)
            for m in inst.body:
                if m.kind in (ast.SymbolKind.Variable, ast.SymbolKind.Net):
                    f.vars[m.name] = default_value(m.type, m.name)
            self.ifaces[path] = f
            for m in inst.body:
                if m.kind == ast.SymbolKind.Variable and m.initializer is not None:
                    f.vars[m.name] = self.eval(m.initializer, Frame(None, None, f))
        return f

    # ------------------------------------------------------------ scheduling
    def spawn(self, root: ThreadRoot, parent: Optional[Thread] = None) -> Thread:
        t = Thread(root)
        t.parent = parent
        if root.kind == "stmt":
            t.gen = self._run_root_stmt(t, root)
        else:
            t.gen = self._run_root_call(t, root)
        self.threads.append(t)
        self.ready.append(t)
        return t

    def _run_root_stmt(self, t: Thread, root: ThreadRoot):
        t.stack.append(root.frame)
        if root.forever:
            while True:
                yield from self.exec(root.stmt, root.frame)
        yield from self.exec(root.stmt, root.frame)

    def _run_root_call(self, t: Thread, root: ThreadRoot):
        yield from self.call_sub(root.sub, root.this, None, list(root.args), None, None)

    def run(self) -> None:
        """Run every thread until all are blocked on something that needs time."""
        while True:
            while self.ready:
                t = self.ready.pop(0)
                self._step(t)
            if self._wake():
                continue
            if self.nba:
                pending, self.nba = self.nba, []
                for setter, v in pending:
                    setter(v)
                self._wake()
                if self.ready:
                    continue
            break

    def _step(self, t: Thread) -> None:
        self.cur = t
        try:
            t.block = next(t.gen)
        except StopIteration:
            t.done = True
            t.block = None
        finally:
            self.cur = None

    def _wake(self) -> bool:
        woke = False
        for t in self.threads:
            if t.done or t in self.ready or t.block is None:
                continue
            b = t.block
            if b.kind == "delay0":
                self.ready.append(t)
                woke = True
            elif b.kind == "wait" and b.cond():
                self.ready.append(t)
                woke = True
            elif b.kind == "join":
                done = [c.done for c in b.children]
                if (any(done) if b.join_any else all(done)):
                    self.ready.append(t)
                    woke = True
        return woke

    def trigger(self, ev: Event) -> None:
        for t in self.threads:
            if not t.done and t.block is not None and t.block.kind == "event" \
                    and t.block.event is ev and t not in self.ready:
                self.ready.append(t)

    def blocked_threads(self) -> List[Thread]:
        return [t for t in self.threads if not t.done]

    # ------------------------------------------------------------ statements
    def exec(self, s, fr: Frame):
        fr.pos.append(s)
        try:
            yield from self._exec(s, fr)
        finally:
            fr.pos.pop()

    def _exec(self, s, fr: Frame):
        k = s.kind
        if k == SK.List:
            for x in s.list:
                yield from self.exec(x, fr)
        elif k == SK.Block:
            if s.blockKind == ast.StatementBlockKind.Sequential:
                yield from self.exec(s.body, fr)
            else:
                yield from self._fork(s, fr)
        elif k == SK.VariableDeclaration:
            sym = s.symbol
            v = (self.eval(sym.initializer, fr) if sym.initializer is not None
                 else default_value(sym.type, sym.name))
            fr.locals[sym] = self._coerce(copy_value(v), sym.type)
        elif k == SK.ExpressionStatement:
            e = s.expr
            if e.kind == EK.Call and not e.isSystemCall \
                    and e.subroutine.subroutineKind == ast.SubroutineKind.Task:
                yield from self._call_expr(e, fr)
            else:
                self.eval(e, fr)
        elif k == SK.Conditional:
            if truthy(self.eval(s.conditions[0].expr, fr)):
                yield from self.exec(s.ifTrue, fr)
            elif s.ifFalse is not None:
                yield from self.exec(s.ifFalse, fr)
        elif k == SK.Case:
            v = self.eval(s.expr, fr)
            for item in s.items:
                if any(self._case_match(v, self.eval(x, fr), s) for x in item.expressions):
                    yield from self.exec(item.stmt, fr)
                    break
            else:
                if s.defaultCase is not None:
                    yield from self.exec(s.defaultCase, fr)
        elif k == SK.ForLoop:
            for sym in (s.loopVars or []):
                fr.locals[sym] = (self.eval(sym.initializer, fr) if sym.initializer is not None
                                  else default_value(sym.type))
            for init in (s.initializers or []):
                self.eval(init, fr)
            while s.stopExpr is None or truthy(self.eval(s.stopExpr, fr)):
                try:
                    yield from self.exec(s.body, fr)
                except _Break:
                    break
                except _Continue:
                    pass
                for st in s.steps:
                    self.eval(st, fr)
        elif k == SK.ForeachLoop:
            yield from self._foreach(s, fr)
        elif k == SK.RepeatLoop:
            n = self.eval(s.count, fr)
            fr.loop_state[s] = n
            while fr.loop_state[s] > 0:
                fr.loop_state[s] -= 1
                try:
                    yield from self.exec(s.body, fr)
                except _Break:
                    break
                except _Continue:
                    pass
            fr.loop_state.pop(s, None)
        elif k == SK.WhileLoop:
            while truthy(self.eval(s.cond, fr)):
                try:
                    yield from self.exec(s.body, fr)
                except _Break:
                    break
                except _Continue:
                    pass
        elif k == SK.DoWhileLoop:
            while True:
                try:
                    yield from self.exec(s.body, fr)
                except _Break:
                    break
                except _Continue:
                    pass
                if not truthy(self.eval(s.cond, fr)):
                    break
        elif k == SK.ForeverLoop:
            while True:
                try:
                    yield from self.exec(s.body, fr)
                except _Break:
                    break
                except _Continue:
                    pass
        elif k == SK.Return:
            if s.expr is not None and fr.sub is not None and fr.sub.returnValVar is not None:
                fr.locals[fr.sub.returnValVar] = self._coerce(
                    self.eval(s.expr, fr), fr.sub.returnValVar.type)
            raise _Return()
        elif k == SK.Break:
            raise _Break()
        elif k == SK.Continue:
            raise _Continue()
        elif k == SK.Timed:
            yield from self._timed(s, fr)
            yield from self.exec(s.stmt, fr)
        elif k == SK.Wait:
            while not truthy(self.eval(s.cond, fr)):
                yield Block("wait", stmt=s, cond=lambda s=s, fr=fr: truthy(self.eval(s.cond, fr)))
            yield from self.exec(s.stmt, fr)
        elif k == SK.EventTrigger:
            ev = self.eval(s.target, fr)
            if isinstance(ev, Event):
                self.trigger(ev)
        elif k in (SK.Empty, SK.WaitFork, SK.DisableFork, SK.Disable):
            pass
        elif k == SK.ImmediateAssertion:
            if not truthy(self.eval(s.cond, fr)):
                self.warn(f"assertion failed at {s.sourceRange}")
        else:
            raise ElabError(f"unsupported statement {k.name} during elaboration")

    def _case_match(self, v, item, s) -> bool:
        return v == item

    def _foreach(self, s, fr: Frame):
        arr = self.eval(s.arrayRef, fr)
        dim = s.loopDims[0]
        var = dim.loopVar
        if isinstance(arr, dict):
            keys = sorted(arr.keys())
        elif isinstance(arr, list):
            keys = list(range(len(arr)))
        elif isinstance(arr, int):          # foreach over a packed vector
            w = width_of(s.arrayRef.type) or 0
            keys = list(range(w))
        else:
            keys = []
        for key in keys:
            if var is not None:
                fr.locals[var] = key
            try:
                yield from self.exec(s.body, fr)
            except _Break:
                break
            except _Continue:
                pass

    def _fork(self, s, fr: Frame):
        body = s.body
        stmts = list(body.list) if body.kind == SK.List else [body]
        branches = []
        for x in stmts:
            if x.kind == SK.VariableDeclaration:
                yield from self.exec(x, fr)
            else:
                branches.append(x)
        children = []
        for b in branches:
            bf = Frame(fr.sub, fr.this, fr.iface, call=None, parent=fr)
            # A fork branch sees the automatic variables as they are when it
            # starts: copy them (the per-iteration `automatic` idiom).
            f: Optional[Frame] = fr
            while f is not None:
                for sym, v in f.locals.items():
                    bf.locals.setdefault(sym, v)
                f = f.parent
            bf.parent = None
            children.append(self.spawn(ThreadRoot("stmt", stmt=b, frame=bf,
                                                  label=self._label(fr, b)),
                                       parent=self.cur))
        if s.blockKind == ast.StatementBlockKind.JoinNone:
            return
        yield Block("join", stmt=s, children=children,
                    join_any=(s.blockKind == ast.StatementBlockKind.JoinAny))

    def _label(self, fr: Frame, stmt) -> str:
        who = fr.this.cls.name if fr.this is not None else (fr.iface.path if fr.iface else "")
        sub = fr.sub.name if fr.sub is not None else "block"
        return f"{who}.{sub}"

    def _timed(self, s, fr: Frame):
        tc = s.timing
        tk = tc.kind
        if tk == ast.TimingControlKind.Delay:
            d = self.eval(tc.expr, fr)
            yield Block("delay0" if not d else "time", stmt=s)
            return
        if tk == ast.TimingControlKind.SignalEvent:
            yield from self._signal_event(tc, s, fr)
            return
        if tk == ast.TimingControlKind.EventList:
            evs = list(tc.events)
            if all(e.kind == ast.TimingControlKind.SignalEvent for e in evs):
                # @(posedge clock or posedge reset): a clock edge at elaboration
                yield Block("edge", stmt=s)
                return
        raise ElabError(f"unsupported timing control {tk.name}")

    def _signal_event(self, tc, s, fr: Frame):
        t = tc.expr.type.canonicalType
        if t.isEvent:
            ev = self.eval(tc.expr, fr)
            yield Block("event", stmt=s, event=ev)
            return
        yield Block("edge", stmt=s)

    # ------------------------------------------------------------------ calls
    def _call_expr(self, e, fr: Frame):
        """A task call statement (may block)."""
        sub, this, iface = self._resolve_call(e, fr)
        yield from self.call_sub(sub, this, iface, list(e.arguments), fr, e)

    def _resolve_call(self, e, fr: Frame):
        sub = e.subroutine
        this: Optional[Obj] = None
        iface: Optional[Iface] = None
        scope = sub.parentScope
        if e.thisClass is not None:
            recv = self.eval(e.thisClass, fr)
            if isinstance(recv, Iface):
                iface = recv
            elif isinstance(recv, Obj):
                this = recv
            elif recv is None:
                raise ElabError(f"null object access calling {sub.name} at {e.sourceRange}")
            else:
                raise ElabError(f"call {sub.name} on {recv!r}")
        else:
            owner = self._owner_class(sub)
            if owner is not None:
                this = fr.this
            else:
                iface = fr.iface
        if this is not None and self._is_virtual(sub) and not self._is_super_call(e):
            sub = self._dispatch(this.cls, sub)
        return sub, this, iface

    @staticmethod
    def _owner_class(sub):
        """The class a (non-static) method belongs to, from its ``this`` variable."""
        tv = sub.thisVar
        if tv is None:
            return None
        t = tv.type.canonicalType
        return t if t.kind == ast.SymbolKind.ClassType else None

    @staticmethod
    def _is_virtual(sub) -> bool:
        # (pyslang cannot convert combined MethodFlags values; isVirtual covers
        # virtual, pure and interface-class methods)
        return sub.kind == ast.SymbolKind.MethodPrototype or bool(sub.isVirtual)

    @staticmethod
    def _is_super_call(e) -> bool:
        syn = e.syntax
        txt = str(syn).strip() if syn is not None else ""
        return txt.startswith("super.") or txt.startswith("super ")

    def _dispatch(self, cls, sub):
        name = sub.name
        c = cls
        while c is not None:
            m = c.find(name)
            if m is not None and m.kind == ast.SymbolKind.Subroutine and m.body is not None:
                return m
            c = self._base(c)
        return sub

    def call_sub(self, sub, this, iface, args, caller: Optional[Frame], call_expr):
        """Execute *sub* (generator). *args* are the actual argument expressions,
        evaluated in *caller*."""
        if sub.kind == ast.SymbolKind.MethodPrototype or sub.body is None:
            raise ElabError(f"call to {sub.name} has no body")
        fr = Frame(sub, this, iface, call=call_expr)
        outs: List[Tuple[Any, Any]] = []
        formals = list(sub.arguments)
        for i, fa in enumerate(formals):
            a = args[i] if i < len(args) else None
            d = fa.direction
            if a is None or a.kind == EK.EmptyArgument:
                dv = fa.defaultValue if hasattr(fa, "defaultValue") else None
                v = self.eval(dv, fr) if dv is not None else default_value(fa.type)
                fr.locals[fa] = self._coerce(v, fa.type)
                continue
            if d == ast.ArgumentDirection.In:
                fr.locals[fa] = self._coerce(copy_value(self.eval(a, caller)), fa.type)
            else:
                lhs = a.left if a.kind == EK.Assignment else a
                if d in (ast.ArgumentDirection.InOut, ast.ArgumentDirection.Ref):
                    fr.locals[fa] = self._coerce(self.eval(lhs, caller), fa.type)
                else:
                    fr.locals[fa] = default_value(fa.type)
                outs.append((fa, lhs))
        if sub.returnValVar is not None:
            fr.locals[sub.returnValVar] = default_value(sub.returnValVar.type)
        t = self.cur
        if t is not None:
            t.stack.append(fr)
        try:
            if sub.name == "new" and this is not None:
                yield from self._ctor_body(sub, this, fr)
            else:
                try:
                    yield from self.exec(sub.body, fr)
                except _Return:
                    pass
        finally:
            if t is not None:
                t.stack.pop()
        for fa, lhs in outs:
            self.assign(lhs, caller, fr.locals[fa])
        if sub.returnValVar is not None:
            return fr.locals[sub.returnValVar]
        return None

    def run_sync(self, gen):
        """Run a generator that must not block (a function)."""
        try:
            b = next(gen)
        except StopIteration as stop:
            return stop.value
        raise ElabError(f"blocking ({b.kind}) inside a function")

    # ------------------------------------------------------------ construction
    def construct(self, cls, call_expr, caller: Frame):
        """``new``: allocate, then run the constructor chain."""
        o = self.new_object(cls)
        ctor = cls.find("new") if call_expr is None else call_expr.subroutine
        args = list(call_expr.arguments) if call_expr is not None else []
        if ctor is None or ctor.kind != ast.SymbolKind.Subroutine:
            self._implicit_ctor(cls, o, caller)
        else:
            self.run_sync(self.call_sub(ctor, o, None, args, caller, call_expr))
        return o

    def _implicit_ctor(self, cls, o: Obj, caller):
        base = self._base(cls)
        if base is not None:
            bctor = base.find("new")
            bcall = cls.baseConstructorCall
            if bcall is not None and bcall.kind == EK.Call:
                self.run_sync(self.call_sub(bcall.subroutine, o, None, list(bcall.arguments),
                                            Frame(None, o, None), bcall))
            elif bctor is not None and bctor.kind == ast.SymbolKind.Subroutine:
                self.run_sync(self.call_sub(bctor, o, None, [], caller, None))
            else:
                self._implicit_ctor(base, o, caller)
        self._init_props(cls, o)

    def _init_props(self, cls, o: Obj):
        fr = Frame(None, o, None)
        for m in cls:
            if m.kind == ast.SymbolKind.ClassProperty and not self._is_static(m) \
                    and m.initializer is not None:
                o.fields[m] = self._coerce(self.eval(m.initializer, fr), m.type)

    def _ctor_body(self, sub, o: Obj, fr: Frame):
        cls = self._owner_class(sub)
        stmts = self._flat(sub.body)
        first = stmts[0] if stmts else None
        explicit_super = (first is not None and first.kind == SK.ExpressionStatement
                          and first.expr.kind == EK.NewClass and first.expr.isSuperClass)
        if not explicit_super:
            base = self._base(cls)
            if base is not None:
                bcall = cls.baseConstructorCall
                if bcall is not None and bcall.kind == EK.Call:
                    self.run_sync(self.call_sub(bcall.subroutine, o, None,
                                                list(bcall.arguments), fr, bcall))
                else:
                    bctor = base.find("new")
                    if bctor is not None and bctor.kind == ast.SymbolKind.Subroutine:
                        self.run_sync(self.call_sub(bctor, o, None, [], fr, None))
                    else:
                        self._implicit_ctor(base, o, fr)
            self._init_props(cls, o)
            rest = stmts
        else:
            self._super_new(first.expr, o, fr)
            self._init_props(cls, o)
            rest = stmts[1:]
        try:
            for x in rest:
                yield from self.exec(x, fr)
        except _Return:
            pass

    def _super_new(self, e, o: Obj, fr: Frame) -> None:
        """``super.new(...)``: the base constructor on the object being built."""
        cc = e.constructorCall
        if cc is not None and cc.kind == EK.Call:
            self.run_sync(self.call_sub(cc.subroutine, o, None, list(cc.arguments), fr, cc))
            return
        base = self._base(self._owner_class(fr.sub)) if fr.sub is not None else None
        if base is not None:
            self._implicit_ctor(base, o, fr)

    @staticmethod
    def _flat(s) -> list:
        if s is None:
            return []
        if s.kind == SK.List:
            out = []
            for x in s.list:
                out += Interpreter._flat(x) if x.kind == SK.List else [x]
            return out
        if s.kind == SK.Block and s.blockKind == ast.StatementBlockKind.Sequential:
            return Interpreter._flat(s.body)
        return [s]

    # ------------------------------------------------------------ expressions
    def eval(self, e, fr: Frame):
        if isinstance(e, Val):
            return e.v
        k = e.kind
        if k in (EK.IntegerLiteral, EK.UnbasedUnsizedIntegerLiteral, EK.RealLiteral,
                 EK.StringLiteral, EK.TimeLiteral):
            if k == EK.UnbasedUnsizedIntegerLiteral:
                # '0 / '1 / 'x / 'z fill the context width
                bit = str(e.syntax).strip()[-1:]
                w = width_of(e.type) or 1
                return mask(-1, w) if bit == "1" else 0
            v = const_to_py(e.constant) if e.constant is not None else None
            if v is None and k == EK.StringLiteral:
                return str(e.syntax).strip().strip('"')
            if v is None and k == EK.IntegerLiteral:
                v = int(e.value) if hasattr(e, "value") else 0
            return v if v is not None else 0
        if k == EK.NullLiteral:
            return None
        if k == EK.NamedValue or k == EK.HierarchicalValue:
            return self._named(e, fr)
        if k == EK.ArbitrarySymbol:
            sym = e.symbol
            if sym.kind == ast.SymbolKind.Instance and sym.isInterface:
                return self.iface_of(sym)
            raise ElabError(f"unsupported symbol reference {sym.name}")
        if k == EK.MemberAccess:
            return self._member(e, fr)
        if k == EK.ElementSelect:
            return self._elem(e, fr)
        if k == EK.RangeSelect:
            return self._range(e, fr)
        if k == EK.Conversion:
            return self._convert(e, fr)
        if k == EK.UnaryOp:
            return self._unary(e, fr)
        if k == EK.BinaryOp:
            return self._binary(e, fr)
        if k == EK.ConditionalOp:
            c = truthy(self.eval(e.conditions[0].expr, fr))
            return self.eval(e.left if c else e.right, fr)
        if k == EK.Assignment:
            return self._assign_expr(e, fr)
        if k == EK.Call:
            return self._call_value(e, fr)
        if k == EK.NewClass:
            if e.isSuperClass:
                self._super_new(e, fr.this, fr)
                return None
            t = e.type.canonicalType
            if not t.isClass:
                raise ElabError(f"new of non-class type {t} at {e.syntax}")
            return self.construct(t, e.constructorCall, fr)
        if k == EK.Concatenation:
            return self._concat(e, fr)
        if k == EK.Replication:
            n = self.eval(e.count, fr)
            w = width_of(e.concat.type) or 0
            v = self.eval(e.concat, fr)
            out = 0
            for _ in range(n):
                out = (out << w) | v
            return out
        if k in (EK.SimpleAssignmentPattern, EK.StructuredAssignmentPattern,
                 EK.ReplicatedAssignmentPattern):
            return self._pattern(e, fr)
        if k == EK.Inside:
            v = self.eval(e.left, fr)
            for r in e.rangeList:
                if r.kind == EK.ValueRange:
                    if self.eval(r.left, fr) <= v <= self.eval(r.right, fr):
                        return 1
                elif self.eval(r, fr) == v:
                    return 1
            return 0
        if k == EK.LValueReference:
            return self._lvref
        if k == EK.TypeReference or k == EK.DataType:
            return e.type
        if e.constant is not None:
            return const_to_py(e.constant)
        raise ElabError(f"unsupported expression {k.name} at {e.sourceRange}")

    def _named(self, e, fr: Frame):
        sym = e.symbol
        sk = sym.kind
        if sk in (ast.SymbolKind.Variable, ast.SymbolKind.FormalArgument, ast.SymbolKind.Iterator):
            found, f = fr.lookup(sym)
            if found:
                return f.locals[sym]
            if sym.name == "this" and sk == ast.SymbolKind.Variable:
                return fr.this
            if fr.iface is not None and sym.name in fr.iface.vars:
                return fr.iface.vars[sym.name]
            if sym.lifetime == ast.VariableLifetime.Static:
                if sym not in self.statics:
                    self.statics[sym] = (self.eval(sym.initializer, fr)
                                         if sym.initializer is not None
                                         else default_value(sym.type, sym.name))
                return self.statics[sym]
            raise ElabError(f"variable {sym.name} has no value")
        if sk == ast.SymbolKind.ClassProperty:
            if self._is_static(sym):
                if sym not in self.statics:
                    self.statics[sym] = (self.eval(sym.initializer, Frame(None, None, None))
                                         if sym.initializer is not None
                                         else default_value(sym.type, sym.name))
                return self.statics[sym]
            if fr.this is None:
                raise ElabError(f"property {sym.name} without an object")
            return fr.this.fields[sym]
        if sk == ast.SymbolKind.Net:
            if fr.iface is not None and sym.name in fr.iface.vars:
                return fr.iface.vars[sym.name]
            self.warn(f"read of net {sym.hierarchicalPath} during elaboration (0)")
            return 0
        if sk in (ast.SymbolKind.Parameter, ast.SymbolKind.EnumValue):
            return const_to_py(sym.value)
        if sk == ast.SymbolKind.Instance and sym.isInterface:
            return self.iface_of(sym)
        if e.constant is not None:
            return const_to_py(e.constant)
        raise ElabError(f"unsupported named value {sym.name} ({sk.name})")

    def _member(self, e, fr: Frame):
        base_t = e.value.type.canonicalType
        m = e.member
        if base_t.isClass:
            if m.kind == ast.SymbolKind.ClassProperty and self._is_static(m):
                return self._named_static(m)
            o = self.eval(e.value, fr)
            if o is None:
                raise ElabError(f"null object access .{m.name} at {e.sourceRange}")
            return o.fields[m]
        if base_t.isVirtualInterface or base_t.kind == ast.SymbolKind.VirtualInterfaceType:
            f = self.eval(e.value, fr)
            if f is None:
                raise ElabError(f"null virtual interface .{m.name}")
            if m.kind == ast.SymbolKind.Instance and m.isInterface:
                return self.iface_of(self._child_inst(f.inst, m.name))
            return f.vars.get(m.name, 0)
        if base_t.isIntegral:            # packed struct field
            v = self.eval(e.value, fr)
            w = width_of(m.type)
            return mask(v >> int(m.bitOffset), w)
        if base_t.isUnpackedStruct:
            return self.eval(e.value, fr)[m.name]
        if m.kind == ast.SymbolKind.Instance and m.isInterface:
            return self.iface_of(m)
        raise ElabError(f"unsupported member access .{m.name} on {base_t}")

    def _named_static(self, sym):
        if sym not in self.statics:
            self.statics[sym] = (self.eval(sym.initializer, Frame(None, None, None))
                                 if sym.initializer is not None
                                 else default_value(sym.type, sym.name))
        return self.statics[sym]

    @staticmethod
    def _child_inst(inst, name):
        for m in inst.body:
            if m.kind == ast.SymbolKind.Instance and m.name == name:
                return m
        raise ElabError(f"no instance {name} in {inst.hierarchicalPath}")

    def _elem(self, e, fr: Frame):
        t = e.value.type.canonicalType
        base = self.eval(e.value, fr)
        idx = self.eval(e.selector, fr)
        if t.isAssociativeArray:
            if idx not in base:
                self.warn(f"read of a missing associative-array key {idx!r}")
                return default_value(t.arrayElementType)
            return base[idx]
        if t.isQueue or (t.isUnpackedArray and t.isDynamicallySizedArray):
            return base[idx] if 0 <= idx < len(base) else default_value(t.arrayElementType)
        if t.isUnpackedArray:
            return base[self._fixed_index(t, idx)]
        if t.isIntegral:
            ew = width_of(e.type)
            lo = self._bit_offset(t, idx, ew)
            return mask(base >> lo, ew)
        if t.isString:
            return ord(base[idx]) if 0 <= idx < len(base) else 0
        raise ElabError(f"unsupported element select on {t}")

    @staticmethod
    def _fixed_index(t, idx):
        r = t.fixedRange
        left, right = int(r.left), int(r.right)
        return abs(idx - left)

    @staticmethod
    def _bit_offset(t, idx, ew) -> int:
        """Bit position of element *idx* of a packed vector/array type."""
        r = t.fixedRange
        left, right = int(r.left), int(r.right)
        pos = (idx - right) if left >= right else (right - idx)
        return pos * ew

    def _range(self, e, fr: Frame):
        t = e.value.type.canonicalType
        base = self.eval(e.value, fr)
        w = width_of(e.type)
        if isinstance(base, list):
            lft = self.eval(e.left, fr)
            return base[lft:lft + w]
        lo = self._range_lo(e, t, fr)
        return mask(base >> lo, w)

    def _range_lo(self, e, t, fr) -> int:
        r = t.fixedRange
        left, right = int(r.left), int(r.right)
        a = self.eval(e.left, fr)
        b = self.eval(e.right, fr)
        sk = e.selectionKind
        if sk == ast.RangeSelectionKind.Simple:
            lo_idx = min(a, b) if left >= right else max(a, b)
        elif sk == ast.RangeSelectionKind.IndexedUp:
            lo_idx = a if left >= right else a + b - 1
        else:
            lo_idx = a - b + 1 if left >= right else a
        ew = (width_of(t) or 1) // (abs(left - right) + 1)
        return self._bit_offset(t, lo_idx, ew)

    def _convert(self, e, fr: Frame):
        v = self.eval(e.operand, fr)
        to_t = e.type.canonicalType
        from_t = e.operand.type.canonicalType
        if to_t.isIntegral:
            if isinstance(v, float):
                v = int(round(v))
            if isinstance(v, str):
                n = 0
                for ch in v:
                    n = (n << 8) | ord(ch)
                v = n
            if not isinstance(v, int):
                return v
            w = width_of(to_t)
            fw = width_of(from_t) if from_t.isIntegral else None
            if fw is not None and from_t.isSigned and w > fw:
                v = to_signed(v, fw)
            return mask(v, w)
        if to_t.isFloating:
            if isinstance(v, int) and from_t.isIntegral and from_t.isSigned:
                v = to_signed(v, width_of(from_t))
            return float(v) if v is not None else 0.0
        if to_t.isString and isinstance(v, int):
            from .values import _int_to_str
            return _int_to_str(v)
        return v

    def _coerce(self, v, t):
        t = t.canonicalType
        if t.isIntegral and isinstance(v, int):
            return mask(v, width_of(t))
        if t.isIntegral and isinstance(v, float):
            return mask(int(round(v)), width_of(t))
        return v

    def _unary(self, e, fr: Frame):
        op = e.op.name
        if op in ("Preincrement", "Predecrement", "Postincrement", "Postdecrement"):
            old = self.eval(e.operand, fr)
            new = old + (1 if "increment" in op else -1)
            w = width_of(e.operand.type)
            new = mask(new, w) if w else new
            self.assign(e.operand, fr, new)
            return new if op.startswith("Pre") else old
        v = self.eval(e.operand, fr)
        w = width_of(e.type) or 0
        ow = width_of(e.operand.type) or 0
        if op == "LogicalNot":
            return 0 if truthy(v) else 1
        if op == "BitwiseNot":
            return mask(~v, w)
        if op == "Minus":
            return mask(-v, w) if isinstance(v, int) else -v
        if op == "Plus":
            return v
        ones = (1 << ow) - 1
        if op == "BitwiseAnd":
            return int(mask(v, ow) == ones)
        if op == "BitwiseNand":
            return int(mask(v, ow) != ones)
        if op == "BitwiseOr":
            return int(v != 0)
        if op == "BitwiseNor":
            return int(v == 0)
        if op == "BitwiseXor":
            return bin(mask(v, ow)).count("1") & 1
        if op == "BitwiseXnor":
            return 1 - (bin(mask(v, ow)).count("1") & 1)
        raise ElabError(f"unsupported unary {op}")

    def _binary(self, e, fr: Frame):
        op = e.op.name
        if op == "LogicalAnd":
            return int(truthy(self.eval(e.left, fr)) and truthy(self.eval(e.right, fr)))
        if op == "LogicalOr":
            return int(truthy(self.eval(e.left, fr)) or truthy(self.eval(e.right, fr)))
        a = self.eval(e.left, fr)
        b = self.eval(e.right, fr)
        lt = e.left.type.canonicalType
        if op in ("Equality", "CaseEquality", "WildcardEquality"):
            return int(a == b)
        if op in ("Inequality", "CaseInequality", "WildcardInequality"):
            return int(a != b)
        if op == "LogicalImplication":
            return int((not truthy(a)) or truthy(b))
        if op == "LogicalEquivalence":
            return int(truthy(a) == truthy(b))
        if isinstance(a, str) or isinstance(b, str):
            cmp = {"LessThan": a < b, "LessThanEqual": a <= b,
                   "GreaterThan": a > b, "GreaterThanEqual": a >= b}
            if op in cmp:
                return int(cmp[op])
        w = width_of(e.type)
        if isinstance(a, float) or isinstance(b, float):
            r = {"Add": lambda: a + b, "Subtract": lambda: a - b, "Multiply": lambda: a * b,
                 "Divide": lambda: a / b if b else 0.0,
                 "LessThan": lambda: int(a < b), "LessThanEqual": lambda: int(a <= b),
                 "GreaterThan": lambda: int(a > b),
                 "GreaterThanEqual": lambda: int(a >= b)}[op]()
            return r
        if op in ("LessThan", "LessThanEqual", "GreaterThan", "GreaterThanEqual"):
            if lt.isIntegral and lt.isSigned:
                lw = width_of(lt)
                a, b = to_signed(a, lw), to_signed(b, lw)
            return int({"LessThan": a < b, "LessThanEqual": a <= b,
                        "GreaterThan": a > b, "GreaterThanEqual": a >= b}[op])
        signed = lt.isIntegral and lt.isSigned
        if signed and op in ("Divide", "Mod", "ArithmeticShiftRight"):
            a = to_signed(a, width_of(lt))
            if op != "ArithmeticShiftRight":
                b = to_signed(b, width_of(e.right.type.canonicalType))
        if op == "Add":
            r = a + b
        elif op == "Subtract":
            r = a - b
        elif op == "Multiply":
            r = a * b
        elif op == "Divide":
            r = int(a / b) if b else 0
        elif op == "Mod":
            r = (abs(a) % abs(b)) * (1 if a >= 0 else -1) if b else 0
        elif op == "BinaryAnd":
            r = a & b
        elif op == "BinaryOr":
            r = a | b
        elif op == "BinaryXor":
            r = a ^ b
        elif op == "BinaryXnor":
            r = ~(a ^ b)
        elif op in ("LogicalShiftLeft", "ArithmeticShiftLeft"):
            r = a << b
        elif op == "LogicalShiftRight":
            r = a >> b
        elif op == "ArithmeticShiftRight":
            r = a >> b
        elif op == "Power":
            r = a ** b
        else:
            raise ElabError(f"unsupported binary {op}")
        return mask(r, w) if w else r

    def _concat(self, e, fr: Frame):
        if e.type.canonicalType.isString:
            return "".join(str(self.eval(x, fr)) for x in e.operands)
        if e.type.canonicalType.isQueue or e.type.canonicalType.isUnpackedArray:
            out = []
            for x in e.operands:
                v = self.eval(x, fr)
                out += v if isinstance(v, list) else [v]
            return out
        out = 0
        for x in e.operands:
            w = width_of(x.type) or 0
            out = (out << w) | mask(self.eval(x, fr), w)
        return out

    def _pattern(self, e, fr: Frame):
        t = e.type.canonicalType
        elems = [self.eval(x, fr) for x in e.elements]
        if t.isIntegral:
            out = 0
            for x, v in zip(e.elements, elems):
                w = width_of(x.type) or 0
                out = (out << w) | mask(v, w)
            return mask(out, width_of(t))
        if t.isUnpackedStruct:
            names = [m.name for m in t if m.kind == ast.SymbolKind.Field]
            return dict(zip(names, elems))
        return elems

    def _assign_expr(self, e, fr: Frame):
        if e.isCompound:
            self._lvref = self.eval(e.left, fr)
        v = self.eval(e.right, fr)
        v = self._coerce(copy_value(v), e.left.type)
        if e.isNonBlocking:
            self.nba.append((lambda val, lhs=e.left, f=fr: self.assign(lhs, f, val), v))
        else:
            self.assign(e.left, fr, v)
        return v

    # ------------------------------------------------------------- l-values
    def assign(self, lhs, fr: Frame, v) -> None:
        k = lhs.kind
        if k == EK.NamedValue or k == EK.HierarchicalValue:
            sym = lhs.symbol
            sk = sym.kind
            v = self._coerce(v, sym.type)
            if sk in (ast.SymbolKind.Variable, ast.SymbolKind.FormalArgument, ast.SymbolKind.Iterator):
                found, f = fr.lookup(sym)
                if found:
                    f.locals[sym] = v
                    return
                if fr.iface is not None and sym.name in fr.iface.vars:
                    fr.iface.vars[sym.name] = v
                    return
                if sym.lifetime == ast.VariableLifetime.Static:
                    self.statics[sym] = v
                    return
                fr.locals[sym] = v
                return
            if sk == ast.SymbolKind.ClassProperty:
                if self._is_static(sym):
                    self.statics[sym] = v
                else:
                    fr.this.fields[sym] = v
                return
            if sk == ast.SymbolKind.Net and fr.iface is not None:
                fr.iface.vars[sym.name] = v
                return
            raise ElabError(f"cannot assign {sym.name} ({sk.name})")
        if k == EK.MemberAccess:
            base_t = lhs.value.type.canonicalType
            m = lhs.member
            if base_t.isClass:
                if self._is_static(m):
                    self.statics[m] = self._coerce(v, m.type)
                    return
                o = self.eval(lhs.value, fr)
                if o is None:
                    raise ElabError(f"null object write .{m.name}")
                o.fields[m] = self._coerce(v, m.type)
                return
            if base_t.isVirtualInterface or base_t.kind == ast.SymbolKind.VirtualInterfaceType:
                f = self.eval(lhs.value, fr)
                f.vars[m.name] = self._coerce(v, m.type)
                return
            if base_t.isIntegral:
                old = self.eval(lhs.value, fr)
                w = width_of(m.type)
                off = int(m.bitOffset)
                fm = ((1 << w) - 1) << off
                self.assign(lhs.value, fr, (old & ~fm) | ((mask(v, w) << off) & fm))
                return
            if base_t.isUnpackedStruct:
                d = self.eval(lhs.value, fr)
                d[m.name] = v
                return
        if k == EK.ElementSelect:
            t = lhs.value.type.canonicalType
            idx = self.eval(lhs.selector, fr)
            if t.isAssociativeArray:
                self.eval(lhs.value, fr)[idx] = v
                return
            if t.isQueue or t.isUnpackedArray:
                arr = self.eval(lhs.value, fr)
                i = idx if (t.isQueue or t.isDynamicallySizedArray) else self._fixed_index(t, idx)
                if 0 <= i < len(arr):
                    arr[i] = v
                return
            if t.isIntegral:
                ew = width_of(lhs.type)
                lo = self._bit_offset(t, idx, ew)
                old = self.eval(lhs.value, fr)
                fm = ((1 << ew) - 1) << lo
                self.assign(lhs.value, fr, (old & ~fm) | ((mask(v, ew) << lo) & fm))
                return
        if k == EK.RangeSelect:
            t = lhs.value.type.canonicalType
            w = width_of(lhs.type)
            lo = self._range_lo(lhs, t, fr)
            old = self.eval(lhs.value, fr)
            fm = ((1 << w) - 1) << lo
            self.assign(lhs.value, fr, (old & ~fm) | ((mask(v, w) << lo) & fm))
            return
        if k == EK.Concatenation:
            pos = 0
            parts = list(lhs.operands)
            for x in reversed(parts):
                w = width_of(x.type) or 0
                self.assign(x, fr, mask(v >> pos, w))
                pos += w
            return
        if k == EK.Conversion:
            self.assign(lhs.operand, fr, v)
            return
        if k == EK.Assignment:              # an output-argument wrapper
            self.assign(lhs.left, fr, v)
            return
        raise ElabError(f"unsupported assignment target {k.name} at {lhs.sourceRange}")

    # ----------------------------------------------------------- call values
    def _call_value(self, e, fr: Frame):
        if e.isSystemCall:
            return self._system_call(e, fr)
        sub, this, iface = self._resolve_call(e, fr)
        if self._is_std_process(sub):
            return Opaque("process")
        gen = self.call_sub(sub, this, iface, list(e.arguments), fr, e)
        if sub.subroutineKind == ast.SubroutineKind.Task:
            raise ElabError(f"task {sub.name} called as an expression")
        return self.run_sync(gen)

    @staticmethod
    def _is_std_process(sub) -> bool:
        return "process::" in (sub.lexicalPath or "")

    def _system_call(self, e, fr: Frame):
        name = e.subroutineName
        args = list(e.arguments)
        if name in ("$display", "$write", "$info", "$warning", "$fdisplay", "$fwrite",
                    "$fclose", "$fflush", "$monitor", "$strobe"):
            return 0
        if name == "$error":
            self.warn("$error during elaboration")
            return 0
        if name == "$fatal":
            msg = self._fmt_args(args[1:], fr) if len(args) > 1 else ""
            raise ElabError(f"$fatal during elaboration: {msg}")
        if name in ("$sformatf", "$psprintf"):
            return self._fmt_args(args, fr)
        if name == "$sformat":
            self.assign(args[0], fr, self._fmt_args(args[1:], fr))
            return 0
        if name in ("$test$plusargs",):
            return 0
        if name == "$value$plusargs":
            return 0
        if name == "$bits":
            t = args[0].type
            return int(t.bitWidth)
        if name == "$clog2":
            v = self.eval(args[0], fr)
            return max(0, (v - 1).bit_length())
        if name in ("$signed", "$unsigned"):
            return self.eval(args[0], fr)
        if name in ("$time", "$realtime", "$stime"):
            return 0
        if name == "$fopen":
            return 0
        if name == "$isunknown":
            return 0
        if name == "$cast":
            src = self.eval(args[1], fr)
            dst = args[0].left if args[0].kind == EK.Assignment else args[0]
            dst_t = dst.type.canonicalType
            if src is None:
                self.assign(args[0], fr, None)
                return 1
            if isinstance(src, Obj):
                if dst_t.isAssignmentCompatible(src.cls):
                    self.assign(args[0], fr, src)
                    return 1
                return 0
            self.assign(args[0], fr, src)
            return 1
        if name == "$typename":
            return str(args[0].type)
        # built-in methods: the receiver is the first argument
        if args:
            return self._builtin_method(name, args, fr, e)
        raise ElabError(f"unsupported system call {name}")

    def _fmt_args(self, args, fr) -> str:
        if not args:
            return ""
        fmt = self.eval(args[0], fr)
        vals = [self.eval(a, fr) for a in args[1:]]
        return fmt_sv(str(fmt), vals, self.top.name)

    def _builtin_method(self, name, args, fr, e):
        recv_t = args[0].type.canonicalType
        recv = self.eval(args[0], fr)
        rest = args[1:]
        if isinstance(recv, list):
            if name == "size":
                return len(recv)
            if name == "push_back":
                recv.append(copy_value(self.eval(rest[0], fr)))
                return 0
            if name == "push_front":
                recv.insert(0, copy_value(self.eval(rest[0], fr)))
                return 0
            if name == "pop_front":
                return recv.pop(0) if recv else default_value(recv_t.arrayElementType)
            if name == "pop_back":
                return recv.pop() if recv else default_value(recv_t.arrayElementType)
            if name == "delete":
                if rest:
                    i = self.eval(rest[0], fr)
                    if 0 <= i < len(recv):
                        recv.pop(i)
                else:
                    recv.clear()
                return 0
            if name == "insert":
                recv.insert(self.eval(rest[0], fr), copy_value(self.eval(rest[1], fr)))
                return 0
        if isinstance(recv, dict):
            if name == "exists":
                return int(self.eval(rest[0], fr) in recv)
            if name in ("num", "size"):
                return len(recv)
            if name == "delete":
                if rest:
                    recv.pop(self.eval(rest[0], fr), None)
                else:
                    recv.clear()
                return 0
            if name in ("first", "last", "next", "prev"):
                keys = sorted(recv.keys())
                if not keys:
                    return 0
                if name in ("first", "last"):
                    self.assign(rest[0], fr, keys[0] if name == "first" else keys[-1])
                    return 1
                cur = self.eval(rest[0], fr)
                cand = [x for x in keys if (x > cur if name == "next" else x < cur)]
                if not cand:
                    return 0
                self.assign(rest[0], fr, cand[0] if name == "next" else cand[-1])
                return 1
        if isinstance(recv, str):
            if name == "len":
                return len(recv)
            if name == "substr":
                i, j = self.eval(rest[0], fr), self.eval(rest[1], fr)
                return recv[i:j + 1]
            if name == "toupper":
                return recv.upper()
            if name == "tolower":
                return recv.lower()
            if name == "compare":
                o = self.eval(rest[0], fr)
                return (recv > o) - (recv < o)
            if name == "atoi":
                try:
                    return int(recv)
                except ValueError:
                    return 0
        if name == "name" and recv_t.isEnum:
            for m in recv_t:
                if m.kind == ast.SymbolKind.EnumValue and const_to_py(m.value) == recv:
                    return m.name
            return ""
        if name == "triggered":
            return 0
        raise ElabError(f"unsupported built-in method {name} on {recv_t}")

    # ---------------------------------------------------------------- misc
    def warn(self, msg: str) -> None:
        self.warnings.append(msg)
