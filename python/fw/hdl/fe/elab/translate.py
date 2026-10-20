"""Translate blocked threads into processes: partial evaluation over the heap.

Each live thread of the elaboration becomes a :class:`zuspec.synth.proc.Proc`.
Its body is the thread's outermost infinite loop, partially evaluated against
the frozen heap:

  - values known at elaboration (object handles, masks, offsets, queue
    contents, anything no process writes) are *static* and are folded away;
  - object fields and interface variables that a process writes are *state*:
    a register each (:class:`~zuspec.synth.proc.Var`, reset to the elaborated
    value). Interface inputs driven by RTL are nets;
  - a dynamic local is a Var too, written with blocking assignments, so a value
    captured into a local keeps its meaning when state changes later;
  - every call is inlined. A handle whose value depends on run-time data is a
    guarded union of the objects it can hold (:class:`HU`); a call on it is an
    if-chain over those objects;
  - ``return``/``break``/``continue`` under a run-time condition become flags
    that guard the statements after them.

The await at which the thread blocked during elaboration is the process's
initial state.

Which fields are state is found by iteration: translate everything, and if a
process wrote a field that was taken as static, mark it and translate again.
"""
from __future__ import annotations

import dataclasses as dc
from typing import Any, Dict, List, Optional, Set, Tuple

from pyslang import ast

from zuspec.synth.proc import ir as P
from zuspec.synth.proc import term as T

from .entry import ElabResult
from .interp import ElabError, Frame, Thread
from .values import (Event, Iface, Obj, Opaque, const_to_py, default_value, mask, skey,
                     width_of)

SK = ast.StatementKind
EK = ast.ExpressionKind


class TranslateError(ElabError):
    pass


@dc.dataclass(eq=False)
class HU:
    """A handle that is one of several objects, by run-time condition.
    ``alts`` are (cond, obj) with disjoint conditions; where none holds the
    handle is null."""
    alts: List[Tuple[T.Term, Any]]


class _Restart(Exception):
    """A field taken as static was written: translate again."""


class Act:
    """An inlined activation: one subroutine (or a loop frame) in a process."""

    def __init__(self, sub, this, iface, path: tuple, name: str):
        self.sub = sub
        self.this = this
        self.iface = iface
        self.path = path            # call-expression keys from the process root
        self.name = name            # for var names
        self.locals: Dict[Any, Any] = {}
        self.ret = T.ZERO           # returned (static 0/1 or a flag var term)


class Translator:
    def __init__(self, elab: ElabResult):
        self.elab = elab
        self.it = elab.interp
        self.dyn_fields: Set[Tuple[int, Any]] = set()     # (oid, prop)
        self.dyn_ifvars: Set[Tuple[str, str]] = set()     # (iface path, name)
        self.warnings: List[str] = []
        self.awaited_events: Set[int] = set()
        self._obj_names = self._name_objects()
        # variables of RTL modules that combinational code writes: nets
        self.comb_vars: Set[Tuple[str, str]] = set()
        for f, kind, node, _label in elab.comb:
            for sym in _written_roots(node if kind != "init" else None, kind):
                self.comb_vars.add((f.path, sym.name))
            if kind == "init":
                self.comb_vars.add((f.path, node.name))
        self._in_comb = False
        # what RTL modules' clocked blocks and tasks write is state: known up
        # front (no rediscovery round per variable)
        for path in elab.rtl_modules:
            f = self.it.ifaces[path]
            mvars = {m.name for m in f.inst.body if m.kind == ast.SymbolKind.Variable}
            for m in f.inst.body:
                body = None
                if m.kind == ast.SymbolKind.ProceduralBlock and m.procedureKind in (
                        ast.ProceduralBlockKind.Always, ast.ProceduralBlockKind.AlwaysFF):
                    body = m.body
                elif m.kind == ast.SymbolKind.Subroutine:
                    body = m.body
                if body is None:
                    continue
                for sym in _written_roots(body, "always"):
                    key = (path, sym.name)
                    if sym.name in mvars and key not in self.comb_vars:
                        self.dyn_ifvars.add(key)

    # ================================================================ driver
    def translate(self) -> P.Design:
        for _ in range(50):
            try:
                return self._translate_once()
            except _Restart:
                continue
        raise TranslateError("state discovery did not converge")

    def _translate_once(self) -> P.Design:
        self.vars: Dict[tuple, P.Var] = {}
        self.var_list: List[P.Var] = []
        self._names: Set[str] = set()
        self._tmp = 0
        procs: List[P.Proc] = []
        for th in self.elab.threads:
            p = self._thread(th)
            if p is not None:
                procs.append(p)
        for f, kind, node, label in self.elab.comb:
            procs.append(self._comb(f, kind, node, label))
        clock = self._mk_var(("clock",), "clock", 1, kind="in", origin="clock")
        reset = self._mk_var(("reset",), "reset", 1, kind="in", origin="reset")
        return P.Design(name=self.elab.top.name, clock=clock, reset=reset,
                        vars=list(self.var_list), procs=procs)

    # ---------------------------------------------------------------- threads
    def _thread(self, th: Thread) -> Optional[P.Proc]:
        b = th.block
        frames = th.stack
        loop_fi, loop_stmt = self._outer_loop(th)
        if loop_fi is None:
            if b.kind == "join":
                self.note(f"{th.root.label}: blocked in a fork/join that never completes; "
                          "no process")
                return None
            if b.kind == "wait":
                # one-shot thread waiting on a condition nothing makes true
                fr = frames[-1]
                act = self._act_from_frame(fr, frames, len(frames) - 1)
                c = self._bool(self.ev(b.stmt.cond, act))
                if c.is_const and not c.val:
                    self.note(f"{th.root.label}: waits on a condition no process sets; no process")
                    return None
            raise TranslateError(f"{th.root.label}: a thread that does not loop forever "
                                 "is not supported yet")
        fr = frames[loop_fi]
        act = self._act_from_frame(fr, frames, loop_fi)
        # the blocking point: call keys below the loop frame, then the stmt
        self._target = (tuple(skey(f.call) for f in frames[loop_fi + 1:] if f.call is not None),
                        skey(b.stmt))
        self._found_initial = False
        self._proc_name = self._proc_label(th, fr)
        self._block_frames = frames[loop_fi:]
        self._act_stack = [act]
        self._loop_flags = []
        self._defined = set()
        out: List[P.Stmt] = []
        self._out = out
        if loop_stmt is None:              # an `always` root: forever over root.stmt
            body: List[P.Stmt] = []
            self._with_out(body, lambda: self.pe_stmt(th.root.stmt, act))
            out.append(P.Loop(body=body))
        else:
            self._residual_loop(loop_stmt, act, forever=True)
        if not self._found_initial:
            raise TranslateError(f"{self._proc_name}: the blocking point was not found "
                                 "while translating its loop")
        return P.Proc(name=self._proc_name, body=out, priority=self._priority(th, fr),
                      origin=th.root.label)

    def _comb(self, f: Iface, kind: str, node, label: str) -> P.Proc:
        """Combinational code of an RTL module -> a combinational process."""
        self._proc_name = self._iface_rel(label).replace(".", "_")
        self._target = ((), None)
        self._found_initial = True
        self._block_frames = []
        act = Act(None, None, f, (), self._proc_name)
        self._act_stack = [act]
        self._loop_flags = []
        self._defined = set()
        out: List[P.Stmt] = []
        self._out = out
        self._in_comb = True
        try:
            if kind == "always":
                self.pe_stmt(node, act)
            elif kind == "assign":
                self._assign_expr(node, act)
            else:
                v = self.ev(node.initializer, act)
                self._write_ifvar(f, node.name, node.type,
                                  self._conv_to(v, node.type, node.initializer), False)
        finally:
            self._in_comb = False
        return P.Proc(name=self._proc_name, body=out, origin=label, comb=True)

    def _outer_loop(self, th: Thread):
        """(frame index, loop stmt) of the outermost infinite loop on the stack;
        (0, None) for an `always` root."""
        if th.root.forever:
            return 0, None
        for fi, fr in enumerate(th.stack):
            for s in fr.pos:
                if s.kind == SK.ForeverLoop:
                    return fi, s
                if s.kind == SK.WhileLoop and s.cond.constant is not None \
                        and const_to_py(s.cond.constant):
                    return fi, s
        return None, None

    def _act_from_frame(self, fr: Frame, frames, fi: int) -> Act:
        path = tuple(skey(f.call) for f in frames[1:fi + 1] if f.call is not None)
        act = Act(fr.sub, fr.this, fr.iface, (), self._fname(fr))
        f: Optional[Frame] = fr
        while f is not None:
            for sym, v in f.locals.items():
                act.locals.setdefault(sym, self._static_val(v, sym.type))
            f = f.parent
        return act

    def _proc_label(self, th: Thread, fr: Frame) -> str:
        if fr.this is not None:
            base = self._obj_names.get(fr.this.oid, fr.this.cls.name)
        elif fr.iface is not None:
            base = self._iface_rel(fr.iface.path)
        else:
            base = "proc"
        sub = fr.sub.name if fr.sub is not None else "always"
        return self._uniq(_safe(f"{base}.{sub}"))

    def _priority(self, th: Thread, fr: Frame) -> int:
        """Bridge threads (a class holding a virtual interface calls into the
        model) first, then interface processes, then the model's own."""
        if fr.this is not None:
            for prop, v in fr.this.fields.items():
                if isinstance(v, Iface):
                    return 2
            return 0
        return 1

    # ============================================================ statements
    def _with_out(self, lst: List[P.Stmt], fn):
        saved = self._out
        self._out = lst
        try:
            return fn()
        finally:
            self._out = saved

    def emit(self, s: P.Stmt) -> None:
        self._out.append(s)
        if isinstance(s, P.Assign) and s.var.origin in ("temporary",) or \
                isinstance(s, P.Assign) and s.var.origin.startswith("local "):
            self._defined.add(s.var)

    def pe_list(self, stmts: list, act: Act, i: int = 0) -> None:
        while i < len(stmts):
            alive = self._alive(act)
            if alive.is_const:
                if not alive.val:
                    return
                self.pe_stmt(stmts[i], act)
                i += 1
                continue
            rest = stmts[i:]

            def live_rest():
                # under `alive` every flag of this activation is 0
                act.ret = T.ZERO
                for fl in self._loop_flags:
                    if fl["act"] is act:
                        act.locals[fl["brk"]] = T.ZERO
                        act.locals[fl["cont"]] = T.ZERO
                self.pe_list(rest, act)
            self._dyn_if(alive, live_rest, lambda: None, act)
            return

    def _alive(self, act: Act) -> T.Term:
        parts = [T.not_(act.ret)]
        for fl in self._loop_flags:
            if fl["act"] is act:
                parts.append(T.not_(self._flag(act, fl["brk"])))
                parts.append(T.not_(self._flag(act, fl["cont"])))
        return T.and_(*parts)

    def _flag(self, act: Act, key) -> T.Term:
        v = act.locals.get(key, T.ZERO)
        return v

    def pe_stmt(self, s, act: Act) -> None:
        k = s.kind
        if k == SK.List:
            self.pe_list(list(s.list), act)
        elif k == SK.Block:
            if s.blockKind != ast.StatementBlockKind.Sequential:
                raise TranslateError("fork inside a process is not supported (anti-pattern A5)")
            self.pe_stmt(s.body, act)
        elif k == SK.VariableDeclaration:
            sym = s.symbol
            if sym.initializer is not None:
                v = self.ev(sym.initializer, act)
            else:
                v = self._default(sym.type)
            self.set_local(act, sym, self._conv_to(v, sym.type, None))
        elif k == SK.ExpressionStatement:
            self.ev(s.expr, act)
        elif k == SK.Conditional and skey(s) in self.elab.reset_ifs:
            # an RTL register block's reset branch: its values are the
            # registers' reset values (entry._rtl_block); the design reset
            # applies them
            self.pe_stmt(s.ifFalse, act)
        elif k == SK.Conditional:
            c = self._bool(self.ev(s.conditions[0].expr, act))
            if c.is_const:
                if c.val:
                    self.pe_stmt(s.ifTrue, act)
                elif s.ifFalse is not None:
                    self.pe_stmt(s.ifFalse, act)
            else:
                self._dyn_if(c, lambda: self.pe_stmt(s.ifTrue, act),
                             (lambda: self.pe_stmt(s.ifFalse, act)) if s.ifFalse is not None
                             else (lambda: None), act)
        elif k == SK.Case:
            self._case(s, act)
        elif k in (SK.ForeverLoop, SK.WhileLoop, SK.DoWhileLoop, SK.ForLoop, SK.RepeatLoop,
                   SK.ForeachLoop):
            self._loop(s, act)
        elif k == SK.Return:
            if s.expr is not None:
                rv = act.sub.returnValVar
                self.set_local(act, rv, self._conv_to(self.ev(s.expr, act), rv.type, s.expr))
            act.ret = T.ONE
        elif k == SK.Break:
            fl = self._innermost_flags(act)
            act.locals[fl["brk"]] = T.ONE
        elif k == SK.Continue:
            fl = self._innermost_flags(act)
            act.locals[fl["cont"]] = T.ONE
        elif k == SK.Timed:
            self._timed(s, act)
            self.pe_stmt(s.stmt, act)
        elif k == SK.Wait:
            c = self._bool(self.ev(s.cond, act))
            if not (c.is_const and c.val):
                self._await(c, s, act)
            self.pe_stmt(s.stmt, act)
        elif k == SK.EventTrigger:
            pass          # nothing in a process waits on an event (checked on await)
        elif k in (SK.Empty, SK.WaitFork, SK.DisableFork):
            pass
        elif k == SK.ImmediateAssertion:
            pass
        else:
            raise TranslateError(f"unsupported statement {k.name} in a process")

    def _innermost_flags(self, act: Act):
        for fl in reversed(self._loop_flags):
            if fl["act"] is act:
                return fl
        raise TranslateError("break/continue outside a loop")

    # ------------------------------------------------------------- if merge
    def _dyn_if(self, c: T.Term, then_fn, else_fn, act: Act) -> None:
        acts = self._acts_live()
        before = self._snapshot(acts)
        def0 = set(self._defined)
        t_out: List[P.Stmt] = []
        e_out: List[P.Stmt] = []
        self._with_out(t_out, then_fn)
        after_t = self._snapshot(acts)
        def_t = set(self._defined)
        self._restore(acts, before)
        self._defined = set(def0)
        self._with_out(e_out, else_fn)
        after_e = self._snapshot(acts)
        def_e = set(self._defined)
        self._merge(acts, c, after_t, after_e, t_out, e_out)
        # definite assignment: a private var first written on one side gets a
        # default on the other, so its old value is never read (no register)
        for v in sorted(def_t - def_e - def0, key=lambda v: v.name):
            e_out.append(P.Assign(v, T.const(0, v.w)))
        for v in sorted(def_e - def_t - def0, key=lambda v: v.name):
            t_out.append(P.Assign(v, T.const(0, v.w)))
        self._defined = def_t | def_e
        if t_out or e_out:
            self.emit(P.If(cond=c, then=t_out, orelse=e_out))

    def _acts_live(self) -> List[Act]:
        return list(self._act_stack)

    def _snapshot(self, acts: List[Act]):
        return [(dict(a.locals), a.ret) for a in acts]

    def _restore(self, acts, snap) -> None:
        for a, (loc, ret) in zip(acts, snap):
            a.locals = dict(loc)
            a.ret = ret

    def _merge(self, acts, c, st, se, t_out, e_out) -> None:
        for a, (lt, rt), (le, re) in zip(acts, st, se):
            merged: Dict[Any, Any] = {}
            for key in set(lt) | set(le):
                vt = lt.get(key, None)
                ve = le.get(key, None)
                merged[key] = self._merge_val(a, key, c, vt, ve, t_out, e_out)
            a.locals = merged
            a.ret = self._merge_flag(a, ("$ret",), c, rt, re, t_out, e_out)

    def _merge_val(self, a, key, c, vt, ve, t_out, e_out):
        if vt is ve:
            return vt
        if vt is None or ve is None:
            # declared on one side only: dead after the if
            return vt if vt is not None else ve
        if isinstance(vt, T.Term) and isinstance(ve, T.Term) and vt.w == ve.w:
            # a local var with the same value term on both sides?
            if vt is ve:
                return vt
            v = self._local_var(a, key, vt.w)
            vref = T.var(v.name, v.w)
            if vt is not vref:
                t_out.append(P.Assign(v, vt))
            if ve is not vref:
                e_out.append(P.Assign(v, ve))
            self._defined.add(v)
            return vref
        if self._is_handle(vt) or self._is_handle(ve):
            cv = self._materialize_bit(c, t_out, e_out)
            alts = []
            for cond, o in self._alts(vt):
                alts.append((T.and_(cv, cond), o))
            for cond, o in self._alts(ve):
                alts.append((T.and_(T.not_(cv), cond), o))
            return self._norm_hu(alts)
        if vt == ve:
            return vt
        raise TranslateError(f"cannot merge values of {key!r} across a run-time condition")

    def _merge_flag(self, a, key, c, ft, fe, t_out, e_out) -> T.Term:
        if ft is fe:
            return ft
        v = self._local_var(a, key, 1)
        vref = T.var(v.name, 1)
        if ft is not vref:
            t_out.append(P.Assign(v, ft))
        if fe is not vref:
            e_out.append(P.Assign(v, fe))
        return vref

    def _materialize_bit(self, c: T.Term, t_out, e_out) -> T.Term:
        if c.is_const or c.op == "var":
            return c
        v = self._temp_var(1, "cond")
        self.emit(P.Assign(v, c))
        return T.var(v.name, 1)

    # ------------------------------------------------------------------ case
    def _case(self, s, act: Act) -> None:
        sel = self.ev(s.expr, act)
        w = width_of(s.expr.type)
        arms = []
        for item in s.items:
            conds = [T.eq(self._term(sel, w, s.expr), self._term(self.ev(x, act), w, x))
                     for x in item.expressions]
            arms.append((T.or_(*conds) if conds else T.ZERO, item.stmt))

        def chain(i):
            if i == len(arms):
                if s.defaultCase is not None:
                    self.pe_stmt(s.defaultCase, act)
                return
            c, st = arms[i]
            if c.is_const:
                if c.val:
                    self.pe_stmt(st, act)
                else:
                    chain(i + 1)
                return
            self._dyn_if(c, lambda: self.pe_stmt(st, act), lambda: chain(i + 1), act)
        chain(0)

    # ----------------------------------------------------------------- loops
    _UNROLL_LIMIT = 4096

    def _loop(self, s, act: Act) -> None:
        k = s.kind
        if k == SK.ForeverLoop:
            self._residual_loop(s, act, forever=True)
            return
        if k == SK.ForeachLoop:
            arr = self.ev(s.arrayRef, act)
            if isinstance(arr, dict):
                keys = sorted(arr.keys())
            elif isinstance(arr, list):
                keys = list(range(len(arr)))
            else:
                raise TranslateError("foreach over a run-time array is not supported")
            var = s.loopDims[0].loopVar
            fl = self._push_flags(act)
            try:
                for key in keys:
                    if var is not None:
                        act.locals[var] = T.const(key, width_of(var.type) or 32) \
                            if isinstance(key, int) else key
                    if not self._iter_alive(act, fl):
                        break
                    self._guarded(act, fl, lambda: self.pe_stmt(s.body, act))
                    act.locals[fl["cont"]] = T.ZERO
            finally:
                self._pop_flags(act, fl)
            return
        if k == SK.RepeatLoop:
            n = self._term(self.ev(s.count, act), width_of(s.count.type) or 32, s.count)
            if n.is_const:
                fl = self._push_flags(act)
                try:
                    for _ in range(n.val):
                        if not self._iter_alive(act, fl):
                            break
                        self._guarded(act, fl, lambda: self.pe_stmt(s.body, act))
                        act.locals[fl["cont"]] = T.ZERO
                finally:
                    self._pop_flags(act, fl)
                return
            raise TranslateError("repeat with a run-time count is not supported yet")
        if k == SK.ForLoop:
            for sym in (s.loopVars or []):
                v = self.ev(sym.initializer, act) if sym.initializer is not None \
                    else self._default(sym.type)
                self.set_local(act, sym, self._conv_to(v, sym.type, None))
            for init in (s.initializers or []):
                self.ev(init, act)
        # while / do-while / for: a body that may wait runs over clock cycles;
        # otherwise unroll while the condition is static
        if self._may_block(s.body):
            self._residual_loop(s, act, forever=False)
            return
        fl = self._push_flags(act)
        try:
            first = True
            for _ in range(self._UNROLL_LIMIT):
                if k == SK.DoWhileLoop and first:
                    c = T.ONE
                else:
                    cexpr = s.stopExpr if k == SK.ForLoop else s.cond
                    c = T.ONE if cexpr is None else self._bool(self.ev(cexpr, act))
                first = False
                if not c.is_const:
                    self._residual_loop(s, act, forever=False)
                    return
                if not c.val:
                    return
                if not self._iter_alive(act, fl):
                    return
                self._guarded(act, fl, lambda: self.pe_stmt(s.body, act))
                act.locals[fl["cont"]] = T.ZERO
                if k == SK.ForLoop:
                    for st in s.steps:
                        self.ev(st, act)
            raise TranslateError("loop did not terminate during unrolling")
        finally:
            self._pop_flags(act, fl)

    def _may_block(self, s) -> bool:
        """Syntactically: can this statement wait (an event control, a wait, or a
        task call)?"""
        found = [False]

        def visit_e(e):
            if e is None or found[0]:
                return
            if e.kind == EK.Call:
                if not e.isSystemCall and e.subroutine.subroutineKind == ast.SubroutineKind.Task:
                    found[0] = True
                    return
                for a in e.arguments:
                    visit_e(a)
            elif e.kind == EK.Assignment:
                visit_e(e.left)
                visit_e(e.right)

        def visit(x):
            if x is None or found[0]:
                return
            k = x.kind
            if k in (SK.Timed, SK.Wait, SK.WaitFork):
                found[0] = True
            elif k == SK.List:
                for y in x.list:
                    visit(y)
            elif k == SK.Block:
                visit(x.body)
            elif k == SK.ExpressionStatement:
                visit_e(x.expr)
            elif k == SK.Conditional:
                visit(x.ifTrue)
                visit(x.ifFalse)
            elif k == SK.Case:
                for it in x.items:
                    visit(it.stmt)
                visit(x.defaultCase)
            elif k in (SK.ForeverLoop, SK.WhileLoop, SK.DoWhileLoop, SK.ForLoop,
                       SK.RepeatLoop, SK.ForeachLoop):
                visit(x.body)
        visit(s)
        return found[0]

    def _iter_alive(self, act, fl) -> bool:
        b = self._flag(act, fl["brk"])
        if b.is_const and b.val:
            return False
        r = act.ret
        if r.is_const and r.val:
            return False
        return True

    def _guarded(self, act, fl, fn) -> None:
        alive = T.and_(T.not_(self._flag(act, fl["brk"])), T.not_(act.ret))
        if alive.is_const:
            if alive.val:
                fn()
            return

        def live():
            act.ret = T.ZERO
            act.locals[fl["brk"]] = T.ZERO
            fn()
        self._dyn_if(alive, live, lambda: None, act)

    def _push_flags(self, act: Act):
        self._loop_id += 1
        fl = {"act": act, "brk": ("$brk", self._loop_id), "cont": ("$cont", self._loop_id)}
        act.locals[fl["brk"]] = T.ZERO
        act.locals[fl["cont"]] = T.ZERO
        self._loop_flags.append(fl)
        return fl

    def _pop_flags(self, act: Act, fl) -> None:
        self._loop_flags.remove(fl)

    def _residual_loop(self, s, act: Act, forever: bool) -> None:
        """A loop that runs over clock cycles: generalize the locals it assigns,
        then translate the body once."""
        k = s.kind
        assigned = self._assigned_locals(s.body, act)
        if k == SK.ForLoop:
            for st in s.steps:
                assigned |= self._assigned_in_expr(st, act)
        for sym in assigned:
            cur = act.locals.get(sym)
            if cur is None or isinstance(cur, T.Term):
                w = width_of(sym.type)
                if w is None:
                    raise TranslateError(f"loop-carried non-integral local {sym.name}")
                v = self._local_var(act, sym, w)
                vref = T.var(v.name, w)
                if cur is not None and cur is not vref:
                    self.emit(P.Assign(v, cur))
                    # the reset value of a loop-carried local in the initial
                    # iteration is its value when elaboration blocked
                    if cur.is_const:
                        v.init = cur.val
                act.locals[sym] = vref
            elif self._is_handle(cur):
                raise TranslateError(f"loop-carried handle {sym.name} is not supported")
        fl = self._push_flags(act)
        body: List[P.Stmt] = []
        try:
            def run_body():
                self.pe_stmt(s.body, act)
                if k == SK.ForLoop:
                    self._guarded(act, fl, lambda: [self.ev(st, act) for st in s.steps])
            self._with_out(body, lambda: self._guarded(act, fl, run_body))
            # flags reset at the end of each iteration
            brk = self._flag(act, fl["brk"])
            cont = self._flag(act, fl["cont"])
            for key, val in ((fl["cont"], cont),):
                if not val.is_const:
                    body.append(P.Assign(self._local_var(act, key, 1), T.ZERO))
            pre = None
            post = None
            if k == SK.WhileLoop:
                pre = self._bool(self.ev(s.cond, act))
            elif k == SK.ForLoop:
                pre = T.ONE if s.stopExpr is None else self._bool(self.ev(s.stopExpr, act))
            elif k == SK.DoWhileLoop:
                post = self._bool(self.ev(s.cond, act))
            stop = T.or_(brk, act.ret) if not forever or not brk.is_const or not act.ret.is_const \
                else T.ZERO
            if not stop.is_const:
                if post is not None:
                    post = T.and_(post, T.not_(stop))
                else:
                    pre = T.and_(pre if pre is not None else T.ONE, T.not_(stop))
            self.emit(P.Loop(body=body, pre=pre, post=post))
            if not brk.is_const:
                v = self._local_var(act, fl["brk"], 1)
                self.emit(P.Assign(v, T.ZERO))
        finally:
            self._pop_flags(act, fl)

    def _assigned_locals(self, s, act: Act) -> Set[Any]:
        """Locals of *act* that a statement may assign (syntactic)."""
        out: Set[Any] = set()

        def visit_stmt(x):
            if x is None:
                return
            k = x.kind
            if k == SK.List:
                for y in x.list:
                    visit_stmt(y)
            elif k == SK.Block:
                visit_stmt(x.body)
            elif k == SK.ExpressionStatement:
                out.update(self._assigned_in_expr(x.expr, act))
            elif k == SK.Conditional:
                visit_stmt(x.ifTrue)
                visit_stmt(x.ifFalse)
            elif k == SK.Case:
                for it in x.items:
                    visit_stmt(it.stmt)
                visit_stmt(x.defaultCase)
            elif k in (SK.ForeverLoop, SK.WhileLoop, SK.DoWhileLoop, SK.ForLoop,
                       SK.RepeatLoop, SK.ForeachLoop):
                visit_stmt(x.body)
                if k == SK.ForLoop:
                    for st in x.steps:
                        out.update(self._assigned_in_expr(st, act))
            elif k in (SK.Timed, SK.Wait):
                visit_stmt(x.stmt)
            elif k == SK.VariableDeclaration:
                pass
        visit_stmt(s)
        return {sym for sym in out if sym in act.locals or self._is_local_sym(sym)}

    def _assigned_in_expr(self, e, act) -> Set[Any]:
        out: Set[Any] = set()

        def root_sym(x):
            while x.kind in (EK.ElementSelect, EK.RangeSelect, EK.MemberAccess, EK.Conversion):
                if x.kind == EK.MemberAccess and x.value.type.canonicalType.isClass:
                    return None
                x = x.operand if x.kind == EK.Conversion else x.value
            if x.kind == EK.NamedValue and x.symbol.kind in (
                    ast.SymbolKind.Variable, ast.SymbolKind.FormalArgument, ast.SymbolKind.Iterator):
                return x.symbol
            return None

        def visit(x):
            if x is None:
                return
            k = x.kind
            if k == EK.Assignment:
                s = root_sym(x.left)
                if s is not None:
                    out.add(s)
                visit(x.right)
            elif k == EK.UnaryOp and x.op.name in ("Preincrement", "Predecrement",
                                                   "Postincrement", "Postdecrement"):
                s = root_sym(x.operand)
                if s is not None:
                    out.add(s)
            elif k == EK.Call:
                for a in x.arguments:
                    visit(a)
            elif k in (EK.BinaryOp,):
                visit(x.left)
                visit(x.right)
            elif k == EK.ConditionalOp:
                visit(x.left)
                visit(x.right)
        visit(e)
        return out

    @staticmethod
    def _is_local_sym(sym) -> bool:
        return sym.kind in (ast.SymbolKind.Variable, ast.SymbolKind.FormalArgument) and \
            sym.lifetime == ast.VariableLifetime.Automatic

    # ----------------------------------------------------------------- await
    def _timed(self, s, act: Act) -> None:
        tc = s.timing
        tk = tc.kind
        if tk == ast.TimingControlKind.Delay:
            d = self.ev(tc.expr, act)
            if isinstance(d, T.Term) and d.is_const and d.val == 0:
                return
            if isinstance(d, (int, float)) and d == 0:
                return
            raise TranslateError("a time delay in a process cannot be synthesized")
        if tk == ast.TimingControlKind.SignalEvent:
            if tc.expr.type.canonicalType.isEvent:
                raise TranslateError("waiting on a named event is not supported yet")
            if tc.edge != ast.EdgeKind.PosEdge:
                raise TranslateError("only @(posedge clock) is supported")
            self._await(None, s, act)
            return
        if tk == ast.TimingControlKind.EventList:
            self._await(None, s, act)
            return
        raise TranslateError(f"unsupported timing control {tk.name}")

    def _await(self, cond: Optional[T.Term], s, act: Act) -> None:
        key = (act.path, skey(s))
        initial = key == self._target
        if initial:
            if self._found_initial:
                raise TranslateError(f"{self._proc_name}: the blocking point was reached twice ({act.name})")
            self._found_initial = True
        # <call path>@<source>: copies of one source wait share the part
        # after '@' (zuspec.synth.proc.lower's factored encoding groups them)
        st = s.sourceRange.start
        label = f"{act.name}@{st.buffer.id}:{st.offset}"
        self.emit(P.Await(cond=cond, initial=initial, label=label))

    # ============================================================= calls
    def _call(self, e, act: Act):
        sub = e.subroutine
        if e.thisClass is not None:
            recv = self.ev(e.thisClass, act)
        else:
            recv = None
        owner = self.it._owner_class(sub)
        if e.thisClass is None:
            if owner is not None:
                recv = act.this
            else:
                recv = act.iface
        if isinstance(recv, HU):
            return self._call_union(e, recv, act)
        if recv is None and (owner is not None or e.thisClass is not None):
            raise TranslateError(f"null object calling {sub.name}")
        if isinstance(recv, Obj) and self.it._is_virtual(sub) and not self.it._is_super_call(e):
            sub = self.it._dispatch(recv.cls, sub)
        this = recv if isinstance(recv, Obj) else None
        iface = recv if isinstance(recv, Iface) else None
        return self._inline(sub, this, iface, list(e.arguments), act, e)

    def _call_union(self, e, hu: HU, act: Act):
        res_var = None
        rt = e.type.canonicalType
        w = width_of(rt) if not rt.isVoid else None
        if w is not None:
            res_var = self._temp_var(w, "ret")
        alts = list(hu.alts)

        def chain(i):
            if i == len(alts):
                return
            c, o = alts[i]

            def then():
                sub = e.subroutine
                if self.it._is_virtual(sub):
                    sub = self.it._dispatch(o.cls, sub)
                r = self._inline(sub, o, None, list(e.arguments), act, e)
                if res_var is not None:
                    self.emit(P.Assign(res_var, self._term(r, w, None)))
            if c.is_const:
                if c.val:
                    then()
                else:
                    chain(i + 1)
                return
            self._dyn_if(c, then, lambda: chain(i + 1), act)
        chain(0)
        return T.var(res_var.name, w) if res_var is not None else None

    def _inline(self, sub, this, iface, args, caller: Act, call_e):
        if sub.body is None or sub.kind == ast.SymbolKind.MethodPrototype:
            raise TranslateError(f"call to {sub.name} has no body")
        if len(self._act_stack) > 64:
            raise TranslateError(f"call depth exceeded at {sub.name} (recursion?)")
        path = caller.path + (skey(call_e),)
        a = Act(sub, this, iface, path, _safe(f"{caller.name}.{sub.name}"))
        outs = []
        formals = list(sub.arguments)
        for i, fa in enumerate(formals):
            x = args[i] if i < len(args) else None
            d = fa.direction
            if x is None or x.kind == EK.EmptyArgument:
                dv = getattr(fa, "defaultValue", None)
                v = self.ev(dv, caller) if dv is not None else self._default(fa.type)
                self.set_local(a, fa, self._conv_to(v, fa.type, dv))
                continue
            if d == ast.ArgumentDirection.In:
                self.set_local(a, fa, self._conv_to(self.ev(x, caller), fa.type, x))
            else:
                lhs = x.left if x.kind == EK.Assignment else x
                if d in (ast.ArgumentDirection.InOut, ast.ArgumentDirection.Ref):
                    self.set_local(a, fa, self._conv_to(self.ev(lhs, caller), fa.type, lhs))
                else:
                    self.set_local(a, fa, self._default(fa.type))
                outs.append((fa, lhs))
        if sub.returnValVar is not None:
            self.set_local(a, sub.returnValVar, self._default(sub.returnValVar.type))
        self._act_stack.append(a)
        try:
            if sub.name == "new":
                raise TranslateError("object construction inside a process (anti-pattern A1)")
            self.pe_stmt(sub.body, a)
        finally:
            self._act_stack.pop()
        for fa, lhs in outs:
            self.assign(lhs, caller, a.locals[fa], src_type=fa.type)
        if sub.returnValVar is not None:
            return a.locals[sub.returnValVar]
        return None

    # ========================================================== expressions
    def ev(self, e, act: Act):
        """Evaluate: an integral value is a Term (constant when static); other
        values are Python objects (Obj, Iface, str, None, ...) or HU."""
        k = e.kind
        if k in (EK.IntegerLiteral, EK.UnbasedUnsizedIntegerLiteral, EK.RealLiteral,
                 EK.StringLiteral, EK.TimeLiteral):
            v = self.it.eval(e, Frame(None, None, None))
            return self._static_val(v, e.type)
        if k == EK.NullLiteral:
            return None
        if k in (EK.NamedValue, EK.HierarchicalValue):
            return self._named(e, act)
        if k == EK.ArbitrarySymbol:
            sym = e.symbol
            if sym.kind == ast.SymbolKind.Instance and sym.isInterface:
                return self.it.iface_of(sym)
            raise TranslateError(f"unsupported symbol reference {sym.name}")
        if k == EK.MemberAccess:
            return self._member(e, act)
        if k == EK.ElementSelect:
            return self._elem(e, act)
        if k == EK.RangeSelect:
            return self._range(e, act)
        if k == EK.Conversion:
            v = self.ev(e.operand, act)
            return self._conv_to(v, e.type, e.operand)
        if k == EK.UnaryOp:
            return self._unary(e, act)
        if k == EK.BinaryOp:
            return self._binary(e, act)
        if k == EK.ConditionalOp:
            c = self._bool(self.ev(e.conditions[0].expr, act))
            if c.is_const:
                return self.ev(e.left if c.val else e.right, act)
            a = self.ev(e.left, act)
            b = self.ev(e.right, act)
            if self._is_handle(a) or self._is_handle(b):
                return self._norm_hu([(T.and_(c, x), o) for x, o in self._alts(a)] +
                                     [(T.and_(T.not_(c), x), o) for x, o in self._alts(b)])
            w = width_of(e.type)
            return T.ite(c, self._term(a, w, e.left), self._term(b, w, e.right))
        if k == EK.Assignment:
            return self._assign_expr(e, act)
        if k == EK.Call:
            if e.isSystemCall:
                return self._system(e, act)
            return self._call(e, act)
        if k == EK.Concatenation:
            if e.type.canonicalType.isString:
                raise TranslateError("string concatenation in a process")
            parts = [self._term(self.ev(x, act), width_of(x.type), x) for x in e.operands
                     if (width_of(x.type) or 0) > 0]
            return T.concat(*parts)
        if k == EK.Replication:
            n = self._term(self.ev(e.count, act), 32, e.count)
            if not n.is_const:
                raise TranslateError("replication by a run-time count")
            v = self._term(self.ev(e.concat, act), width_of(e.concat.type), e.concat)
            return T.concat(*([v] * n.val))
        if k in (EK.SimpleAssignmentPattern, EK.StructuredAssignmentPattern,
                 EK.ReplicatedAssignmentPattern):
            t = e.type.canonicalType
            if not t.isIntegral:
                raise TranslateError("unpacked assignment pattern in a process")
            parts = [self._term(self.ev(x, act), width_of(x.type), x) for x in e.elements]
            return T.zext(T.concat(*parts), width_of(t))
        if k == EK.Inside:
            v = self._term(self.ev(e.left, act), width_of(e.left.type), e.left)
            conds = []
            for r in e.rangeList:
                if r.kind == EK.ValueRange:
                    lo = self._term(self.ev(r.left, act), v.w, r.left)
                    hi = self._term(self.ev(r.right, act), v.w, r.right)
                    conds.append(T.and_(T.ule(lo, v), T.ule(v, hi)))
                else:
                    conds.append(T.eq(v, self._term(self.ev(r, act), v.w, r)))
            return T.or_(*conds) if conds else T.ZERO
        if k == EK.LValueReference:
            return self._lvref_val
        if k == EK.NewClass:
            raise TranslateError("object construction inside a process (anti-pattern A1)")
        if e.constant is not None:
            return self._static_val(const_to_py(e.constant), e.type)
        raise TranslateError(f"unsupported expression {k.name} in a process")

    # -- named values / members ------------------------------------------
    def _named(self, e, act: Act):
        sym = e.symbol
        sk = sym.kind
        if sk in (ast.SymbolKind.Variable, ast.SymbolKind.FormalArgument, ast.SymbolKind.Iterator):
            if sym in act.locals:
                return act.locals[sym]
            if sym.name == "this" and sk == ast.SymbolKind.Variable:
                return act.this
            if act.iface is not None and sym.name in act.iface.vars:
                return self._ifvar(act.iface, sym.name, sym.type)
            if sym.lifetime == ast.VariableLifetime.Static and sym in self.it.statics:
                return self._static_val(self.it.statics[sym], sym.type)
            raise TranslateError(f"variable {sym.name} has no value in {act.name}")
        if sk == ast.SymbolKind.ClassProperty:
            if self.it._is_static(sym):
                return self._static_val(self.it._named_static(sym), sym.type)
            return self._field(act.this, sym)
        if sk == ast.SymbolKind.Net:
            if act.iface is not None:
                return self._ifvar(act.iface, sym.name, sym.type)
            raise TranslateError(f"net {sym.name} outside an interface")
        if sk in (ast.SymbolKind.Parameter, ast.SymbolKind.EnumValue):
            return self._static_val(const_to_py(sym.value), sym.type)
        if sk == ast.SymbolKind.Instance and sym.isInterface:
            return self.it.iface_of(sym)
        if e.constant is not None:
            return self._static_val(const_to_py(e.constant), e.type)
        raise TranslateError(f"unsupported named value {sym.name} ({sk.name})")

    def _field(self, o, prop):
        if o is None:
            raise TranslateError(f"null object access .{prop.name}")
        if isinstance(o, HU):
            return self._field_union(o, prop)
        if (o.oid, prop) in self.dyn_fields:
            w = width_of(prop.type)
            if w is None:
                raise TranslateError(f"run-time write to non-integral field {prop.name}")
            v = self._state_var_field(o, prop)
            return T.var(v.name, v.w)
        return self._static_val(o.fields[prop], prop.type)

    def _field_union(self, hu: HU, prop):
        vals = [(c, self._field(o, prop)) for c, o in hu.alts]
        if all(self._is_handle(v) or v is None for _, v in vals):
            alts = []
            for c, v in vals:
                for c2, o2 in self._alts(v):
                    alts.append((T.and_(c, c2), o2))
            return self._norm_hu(alts)
        w = width_of(prop.type)
        out = T.const(0, w)
        for c, v in reversed(vals):
            out = T.ite(c, self._term(v, w, None), out)
        return out

    def _ifvar(self, f: Iface, name: str, t):
        key = (f.path, name)
        w = width_of(t)
        if key in self.comb_vars:
            v = self._net_var(f, name, w)
            return T.var(v.name, v.w)
        if key in self.dyn_ifvars:
            v = self._state_var_if(f, name, t)
            return T.var(v.name, v.w)
        if self._iface_input(f, name):
            v = self._net_var(f, name, w)
            return T.var(v.name, v.w)
        return self._static_val(f.vars.get(name, 0), t)

    def _iface_input(self, f: Iface, name: str) -> bool:
        for m in f.inst.body:
            if m.kind == ast.SymbolKind.Port and m.name == name:
                return m.direction == ast.ArgumentDirection.In
        for m in f.inst.body:
            if m.kind == ast.SymbolKind.Net and m.name == name:
                return True
        return False

    def _member(self, e, act: Act):
        base_t = e.value.type.canonicalType
        m = e.member
        if base_t.isClass:
            if m.kind == ast.SymbolKind.ClassProperty and self.it._is_static(m):
                return self._static_val(self.it._named_static(m), m.type)
            o = self.ev(e.value, act)
            return self._field(o, m)
        if base_t.isVirtualInterface or base_t.kind == ast.SymbolKind.VirtualInterfaceType:
            f = self.ev(e.value, act)
            if not isinstance(f, Iface):
                raise TranslateError(f"virtual interface .{m.name} is not static")
            if m.kind == ast.SymbolKind.Instance and m.isInterface:
                return self.it.iface_of(self.it._child_inst(f.inst, m.name))
            return self._ifvar(f, m.name, m.type)
        if base_t.isIntegral:
            v = self._term(self.ev(e.value, act), width_of(base_t), e.value)
            return T.slice_(v, int(m.bitOffset), width_of(m.type))
        if m.kind == ast.SymbolKind.Instance and m.isInterface:
            return self.it.iface_of(m)
        raise TranslateError(f"unsupported member access .{m.name}")

    def _elem(self, e, act: Act):
        t = e.value.type.canonicalType
        base = self.ev(e.value, act)
        if t.isAssociativeArray or t.isQueue or t.isUnpackedArray:
            if not isinstance(base, (dict, list)):
                raise TranslateError("run-time array in a process")
            idx = self.ev(e.selector, act)
            iw = width_of(e.selector.type) or 32
            it = self._term(idx, iw, e.selector) if not isinstance(idx, str) else idx
            if isinstance(it, str) or (isinstance(it, T.Term) and it.is_const):
                key = it if isinstance(it, str) else it.val
                if isinstance(base, dict):
                    v = base.get(key)
                else:
                    i = key if (t.isQueue or t.isDynamicallySizedArray) \
                        else self.it._fixed_index(t, key)
                    v = base[i] if 0 <= i < len(base) else None
                return self._static_val(v, t.arrayElementType)
            # run-time index into a static container: a select over its entries
            items = (sorted(base.items()) if isinstance(base, dict)
                     else list(enumerate(base)))
            et = t.arrayElementType.canonicalType
            if et.isClass or et.isVirtualInterface:
                alts = [(T.eq(it, T.const(kk, it.w)), o) for kk, o in items if o is not None]
                return self._norm_hu(alts)
            w = width_of(et)
            out = T.const(0, w)
            for kk, vv in reversed(items):
                out = T.ite(T.eq(it, T.const(kk, it.w)), self._term(self._static_val(vv, et), w, None), out)
            return out
        if t.isIntegral:
            v = self._term(base, width_of(t), e.value)
            ew = width_of(e.type)
            idx = self._term(self.ev(e.selector, act), width_of(e.selector.type) or 32, e.selector)
            r = t.fixedRange
            left, right = int(r.left), int(r.right)
            if idx.is_const:
                lo = self.it._bit_offset(t, idx.val, ew)
                return T.slice_(v, lo, ew)
            # run-time bit select: a shifter
            pos = T.sub(idx, T.const(right, idx.w)) if left >= right else \
                T.sub(T.const(right, idx.w), idx)
            sh = T.lshr(v, T.zext(T.mul(T.zext(pos, max(idx.w, v.w)), T.const(ew, max(idx.w, v.w))), v.w)
                        if max(idx.w, v.w) >= v.w else pos)
            return T.slice_(sh, 0, ew)
        raise TranslateError(f"unsupported element select on {t}")

    def _range(self, e, act: Act):
        t = e.value.type.canonicalType
        v = self._term(self.ev(e.value, act), width_of(t), e.value)
        w = width_of(e.type)
        a = self._term(self.ev(e.left, act), 32, e.left)
        b = self._term(self.ev(e.right, act), 32, e.right)
        if not (a.is_const and b.is_const):
            raise TranslateError("run-time part select")
        lo = self._range_lo(e, t, a.val, b.val)
        return T.slice_(v, lo, w)

    def _range_lo(self, e, t, a, b) -> int:
        r = t.fixedRange
        left, right = int(r.left), int(r.right)
        sk = e.selectionKind
        if sk == ast.RangeSelectionKind.Simple:
            lo_idx = min(a, b) if left >= right else max(a, b)
        elif sk == ast.RangeSelectionKind.IndexedUp:
            lo_idx = a if left >= right else a + b - 1
        else:
            lo_idx = a - b + 1 if left >= right else a
        ew = (width_of(t) or 1) // (abs(left - right) + 1)
        return self.it._bit_offset(t, lo_idx, ew)

    # -- operators --------------------------------------------------------
    def _unary(self, e, act: Act):
        op = e.op.name
        if op in ("Preincrement", "Predecrement", "Postincrement", "Postdecrement"):
            w = width_of(e.operand.type)
            old = self._term(self.ev(e.operand, act), w, e.operand)
            new = (T.add if "increment" in op else T.sub)(old, T.const(1, w))
            self.assign(e.operand, act, new)
            return new if op.startswith("Pre") else old
        v = self.ev(e.operand, act)
        if op == "LogicalNot":
            return T.not_(self._bool(v))
        ow = width_of(e.operand.type)
        tv = self._term(v, ow, e.operand)
        w = width_of(e.type)
        if op == "BitwiseNot":
            return T.not_(tv)
        if op == "Minus":
            return T.neg(tv)
        if op == "Plus":
            return tv
        if op == "BitwiseAnd":
            return T.redand(tv)
        if op == "BitwiseNand":
            return T.not_(T.redand(tv))
        if op == "BitwiseOr":
            return T.redor(tv)
        if op == "BitwiseNor":
            return T.not_(T.redor(tv))
        if op == "BitwiseXor":
            return T.redxor(tv)
        if op == "BitwiseXnor":
            return T.not_(T.redxor(tv))
        raise TranslateError(f"unsupported unary {op}")

    def _binary(self, e, act: Act):
        op = e.op.name
        if op == "LogicalAnd":
            a = self._bool(self.ev(e.left, act))
            if a.is_const and not a.val:
                return T.ZERO
            return T.and_(a, self._bool(self.ev(e.right, act)))
        if op == "LogicalOr":
            a = self._bool(self.ev(e.left, act))
            if a.is_const and a.val:
                return T.ONE
            return T.or_(a, self._bool(self.ev(e.right, act)))
        a = self.ev(e.left, act)
        b = self.ev(e.right, act)
        lt = e.left.type.canonicalType
        if op in ("Equality", "Inequality", "CaseEquality", "CaseInequality",
                  "WildcardEquality", "WildcardInequality") and \
                (self._is_handle(a) or self._is_handle(b) or a is None or b is None
                 or isinstance(a, (Obj, Iface, str, Event, Opaque))):
            r = self._handle_eq(a, b)
            return r if "Equality" in op and "In" not in op else T.not_(r)
        if op == "LogicalImplication":
            return T.or_(T.not_(self._bool(a)), self._bool(b))
        if op == "LogicalEquivalence":
            return T.not_(T.xor(self._bool(a), self._bool(b)))
        if op in ("LessThan", "LessThanEqual", "GreaterThan", "GreaterThanEqual",
                  "Equality", "Inequality", "CaseEquality", "CaseInequality",
                  "WildcardEquality", "WildcardInequality"):
            w = max(width_of(lt) or 1, width_of(e.right.type) or 1)
            x = self._term(a, w, e.left)
            y = self._term(b, w, e.right)
            signed = lt.isIntegral and lt.isSigned
            if op in ("Equality", "CaseEquality", "WildcardEquality"):
                return T.eq(x, y)
            if op in ("Inequality", "CaseInequality", "WildcardInequality"):
                return T.ne(x, y)
            lt_f = T.slt if signed else T.ult
            le_f = T.sle if signed else T.ule
            return {"LessThan": lambda: lt_f(x, y), "LessThanEqual": lambda: le_f(x, y),
                    "GreaterThan": lambda: lt_f(y, x),
                    "GreaterThanEqual": lambda: le_f(y, x)}[op]()
        w = width_of(e.type)
        if op in ("LogicalShiftLeft", "ArithmeticShiftLeft", "LogicalShiftRight",
                  "ArithmeticShiftRight"):
            x = self._term(a, w, e.left)
            n = self._term(b, width_of(e.right.type), e.right)
            n = T.zext(n, max(n.w, 1))
            if n.w != x.w:
                n = T.zext(n, x.w) if n.w < x.w else (T.slice_(n, 0, x.w) if n.is_const and
                                                       n.val < (1 << x.w) else n)
            if n.w != x.w:
                if n.is_const:
                    n = T.const(min(n.val, x.w), x.w)
                else:
                    raise TranslateError("wide shift amount")
            f = {"LogicalShiftLeft": T.shl, "ArithmeticShiftLeft": T.shl,
                 "LogicalShiftRight": T.lshr,
                 "ArithmeticShiftRight": T.ashr if lt.isSigned else T.lshr}[op]
            return f(x, n)
        x = self._term(a, w, e.left)
        y = self._term(b, w, e.right)
        if op == "Add":
            return T.add(x, y)
        if op == "Subtract":
            return T.sub(x, y)
        if op == "Multiply":
            return T.mul(x, y)
        if op == "BinaryAnd":
            return T.and_(x, y)
        if op == "BinaryOr":
            return T.or_(x, y)
        if op == "BinaryXor":
            return T.xor(x, y)
        if op == "BinaryXnor":
            return T.not_(T.xor(x, y))
        if op in ("Divide", "Mod", "Power"):
            if x.is_const and y.is_const:
                xv, yv = x.val, y.val
                r = {"Divide": (xv // yv) if yv else 0, "Mod": (xv % yv) if yv else 0,
                     "Power": xv ** yv}[op]
                return T.const(r, w)
            raise TranslateError(f"run-time {op} is not supported")
        raise TranslateError(f"unsupported binary {op}")

    def _handle_eq(self, a, b) -> T.Term:
        if isinstance(a, (Obj, Iface, Event, Opaque, str)) or a is None:
            if isinstance(b, (Obj, Iface, Event, Opaque, str)) or b is None:
                return T.const(int(a is b or (isinstance(a, str) and a == b)), 1)
        if a is None or b is None:
            h = b if a is None else a
            return T.not_(T.or_(*[c for c, o in self._alts(h) if o is not None])) \
                if self._alts(h) else T.ONE
        conds = []
        for ca, oa in self._alts(a):
            for cb, ob in self._alts(b):
                if oa is ob:
                    conds.append(T.and_(ca, cb))
        return T.or_(*conds) if conds else T.ZERO

    # -- system calls -----------------------------------------------------
    def _system(self, e, act: Act):
        name = e.subroutineName
        args = list(e.arguments)
        if name in ("$display", "$write", "$info", "$warning", "$error", "$fatal",
                    "$fdisplay", "$fwrite", "$fclose", "$fflush", "$monitor", "$strobe"):
            if name == "$fatal":
                self.note(f"{self._proc_name}: $fatal on a reachable path is dropped in hardware")
            return None
        if name in ("$sformatf", "$psprintf"):
            return ""
        if name == "$bits":
            return T.const(int(args[0].type.bitWidth), 32)
        if name == "$clog2":
            v = self._term(self.ev(args[0], act), width_of(args[0].type), args[0])
            if not v.is_const:
                raise TranslateError("$clog2 of a run-time value")
            return T.const(max(0, (v.val - 1).bit_length()), 32)
        if name in ("$signed", "$unsigned"):
            return self._term(self.ev(args[0], act), width_of(e.type), args[0])
        if name in ("$time", "$realtime", "$stime", "$test$plusargs", "$value$plusargs",
                    "$isunknown"):
            return T.const(0, width_of(e.type) or 32)
        if name == "$cast":
            src = self.ev(args[1], act)
            dst = args[0].left if args[0].kind == EK.Assignment else args[0]
            dt = dst.type.canonicalType
            if dt.isClass:
                alts = [(c, o) for c, o in self._alts(src)
                        if o is not None and dt.isAssignmentCompatible(o.cls)]
                ok = T.or_(*[c for c, _ in alts]) if alts else T.ZERO
                self.assign(dst, act, self._norm_hu(alts))
                return ok
            self.assign(dst, act, src)
            return T.ONE
        if args:
            return self._builtin(name, args, act)
        raise TranslateError(f"unsupported system call {name} in a process")

    def _builtin(self, name, args, act: Act):
        recv = self.ev(args[0], act)
        rest = args[1:]
        if isinstance(recv, dict):
            if name == "exists":
                k = self.ev(rest[0], act)
                kt = self._term(k, width_of(rest[0].type) or 32, rest[0])
                if kt.is_const:
                    return T.const(int(kt.val in recv), 1)
                return T.or_(*[T.eq(kt, T.const(x, kt.w)) for x in recv]) if recv else T.ZERO
            if name in ("num", "size"):
                return T.const(len(recv), 32)
        if isinstance(recv, list):
            if name == "size":
                return T.const(len(recv), 32)
            if name in ("push_back", "push_front", "pop_front", "pop_back", "delete", "insert"):
                raise TranslateError(f"{name}() on a queue inside a process (anti-pattern A1)")
        if isinstance(recv, str):
            if name == "len":
                return T.const(len(recv), 32)
        if name == "triggered":
            return T.ZERO
        if name == "name":
            return ""
        raise TranslateError(f"unsupported built-in {name} in a process")

    # ============================================================ assignment
    def _assign_expr(self, e, act: Act):
        if e.isCompound:
            self._lvref_val = self.ev(e.left, act)
        v = self.ev(e.right, act)
        v = self._conv_to(v, e.left.type, e.right)
        self.assign(e.left, act, v, nb=bool(e.isNonBlocking))
        return v

    def assign(self, lhs, act: Act, v, nb: bool = False, src_type=None) -> None:
        k = lhs.kind
        if k == EK.Assignment:
            return self.assign(lhs.left, act, v, nb, src_type)
        if k == EK.Conversion:
            return self.assign(lhs.operand, act, v, nb, src_type)
        if src_type is not None:
            v = self._conv_to(v, lhs.type, None, from_type=src_type)
        if k in (EK.NamedValue, EK.HierarchicalValue):
            sym = lhs.symbol
            sk = sym.kind
            if sk in (ast.SymbolKind.Variable, ast.SymbolKind.FormalArgument, ast.SymbolKind.Iterator):
                if sym in act.locals or self._is_local_sym(sym):
                    if nb:
                        raise TranslateError(f"nonblocking write to local {sym.name}")
                    self.set_local(act, sym, v)
                    return
                if act.iface is not None and sym.name in act.iface.vars:
                    self._write_ifvar(act.iface, sym.name, sym.type, v, nb)
                    return
                raise TranslateError(f"write to static variable {sym.name} in a process")
            if sk == ast.SymbolKind.ClassProperty:
                if self.it._is_static(sym):
                    raise TranslateError(f"write to static property {sym.name} in a process")
                self._write_field(act.this, sym, v, nb)
                return
            if sk == ast.SymbolKind.Net and act.iface is not None:
                self._write_ifvar(act.iface, sym.name, sym.type, v, nb)
                return
            raise TranslateError(f"cannot assign {sym.name} ({sk.name})")
        if k == EK.MemberAccess:
            base_t = lhs.value.type.canonicalType
            m = lhs.member
            if base_t.isClass:
                o = self.ev(lhs.value, act)
                self._write_field(o, m, v, nb)
                return
            if base_t.isVirtualInterface or base_t.kind == ast.SymbolKind.VirtualInterfaceType:
                f = self.ev(lhs.value, act)
                self._write_ifvar(f, m.name, m.type, v, nb)
                return
            if base_t.isIntegral:
                cur = self._term(self.ev(lhs.value, act), width_of(base_t), lhs.value)
                new = self._insert(cur, int(m.bitOffset), self._term(v, width_of(m.type), None))
                self.assign(lhs.value, act, new, nb)
                return
        if k == EK.ElementSelect:
            t = lhs.value.type.canonicalType
            if t.isIntegral:
                cur = self._term(self.ev(lhs.value, act), width_of(t), lhs.value)
                idx = self._term(self.ev(lhs.selector, act), width_of(lhs.selector.type) or 32,
                                 lhs.selector)
                ew = width_of(lhs.type)
                if not idx.is_const:
                    self.assign(lhs.value, act, self._dyn_insert(cur, t, idx, self._term(v, ew, None)),
                                nb)
                    return
                lo = self.it._bit_offset(t, idx.val, ew)
                self.assign(lhs.value, act, self._insert(cur, lo, self._term(v, ew, None)), nb)
                return
            raise TranslateError("write to an array element inside a process")
        if k == EK.RangeSelect:
            t = lhs.value.type.canonicalType
            cur = self._term(self.ev(lhs.value, act), width_of(t), lhs.value)
            a = self._term(self.ev(lhs.left, act), 32, lhs.left)
            b = self._term(self.ev(lhs.right, act), 32, lhs.right)
            lo = self._range_lo(lhs, t, a.val, b.val)
            self.assign(lhs.value, act, self._insert(cur, lo, self._term(v, width_of(lhs.type), None)), nb)
            return
        if k == EK.Concatenation:
            vt = self._term(v, width_of(lhs.type), None)
            pos = 0
            for x in reversed(list(lhs.operands)):
                w = width_of(x.type) or 0
                self.assign(x, act, T.slice_(vt, pos, w), nb)
                pos += w
            return
        raise TranslateError(f"unsupported assignment target {k.name}")

    @staticmethod
    def _dyn_insert(cur: T.Term, t, idx: T.Term, val: T.Term) -> T.Term:
        """*cur* with the element at run-time index *idx* replaced by *val*
        (a write out of range changes nothing)."""
        w, ew = cur.w, val.w
        r = t.fixedRange
        left, right = int(r.left), int(r.right)
        iw = max(idx.w, (max(abs(left), abs(right)) * ew + w).bit_length() + 1)
        ix = T.resize(idx, iw)
        # element index -> element number from the least significant end
        num = T.sub(ix, T.const(right, iw)) if left >= right else T.sub(T.const(right, iw), ix)
        off = T.mul(num, T.const(ew, iw)) if ew > 1 else num
        m = T.shl(T.resize(T.ones(ew), w), off)
        return T.or_(T.and_(cur, T.not_(m)), T.and_(T.shl(T.resize(val, w), off), m))

    @staticmethod
    def _insert(cur: T.Term, lo: int, val: T.Term) -> T.Term:
        parts = []
        if lo + val.w < cur.w:
            parts.append(T.slice_(cur, lo + val.w, cur.w - lo - val.w))
        parts.append(val)
        if lo > 0:
            parts.append(T.slice_(cur, 0, lo))
        return T.concat(*parts)

    def set_local(self, act: Act, sym, v) -> None:
        if isinstance(v, T.Term) and not v.is_const:
            var = self._local_var(act, sym, v.w)
            vref = T.var(var.name, var.w)
            if v is not vref:
                self.emit(P.Assign(var, v))
            act.locals[sym] = vref
            return
        if isinstance(v, HU):
            alts = []
            for c, o in v.alts:
                if not (c.is_const or c.op == "var"):
                    tv = self._temp_var(1, "sel")
                    self.emit(P.Assign(tv, c))
                    c = T.var(tv.name, 1)
                alts.append((c, o))
            act.locals[sym] = self._norm_hu(alts)
            return
        act.locals[sym] = v

    def _write_field(self, o, prop, v, nb: bool) -> None:
        if isinstance(o, HU):
            for c, oo in o.alts:
                self._dyn_if(c, lambda oo=oo: self._write_field(oo, prop, v, nb), lambda: None,
                             self._act_stack[-1])
            return
        if o is None:
            raise TranslateError(f"null object write .{prop.name}")
        key = (o.oid, prop)
        if key not in self.dyn_fields:
            self.dyn_fields.add(key)
            raise _Restart()
        var = self._state_var_field(o, prop)
        self.emit(P.Assign(var, self._term(v, var.w, None), nb=nb))

    def _write_ifvar(self, f: Iface, name: str, t, v, nb: bool) -> None:
        key = (f.path, name)
        if key in self.comb_vars:
            if not self._in_comb:
                raise TranslateError(f"{f.path}.{name}: written by both combinational and "
                                     "clocked code")
            var = self._net_var(f, name, width_of(t))
            self.emit(P.Assign(var, self._term(v, var.w, None), nb=False))
            return
        if key not in self.dyn_ifvars:
            self.dyn_ifvars.add(key)
            raise _Restart()
        var = self._state_var_if(f, name, t)
        self.emit(P.Assign(var, self._term(v, var.w, None), nb=nb))

    # ============================================================== values
    def _static_val(self, v, t):
        """An elaboration value as a translator value."""
        tt = t.canonicalType if t is not None else None
        if isinstance(v, bool):
            v = int(v)
        if isinstance(v, int) and tt is not None and tt.isIntegral:
            return T.const(v, width_of(tt))
        if isinstance(v, int) and tt is None:
            return T.const(v, 32)
        return v

    def _default(self, t):
        return self._static_val(default_value(t), t)

    def _term(self, v, w: Optional[int], expr) -> T.Term:
        if isinstance(v, T.Term):
            if w is None or v.w == w:
                return v
            signed = bool(expr is not None and expr.type.canonicalType.isIntegral
                          and expr.type.canonicalType.isSigned)
            return T.resize(v, w, signed)
        if isinstance(v, bool):
            return T.const(int(v), w or 1)
        if isinstance(v, int):
            return T.const(v, w or 32)
        if isinstance(v, float):
            return T.const(int(v), w or 32)
        if v is None:
            return T.const(0, w or 1)
        raise TranslateError(f"value {v!r} used as a bit vector")

    def _bool(self, v) -> T.Term:
        if isinstance(v, T.Term):
            return T.bool_(v)
        if self._is_handle(v):
            return T.or_(*[c for c, o in self._alts(v) if o is not None]) if self._alts(v) else T.ZERO
        if v is None:
            return T.ZERO
        if isinstance(v, (Obj, Iface, Event, Opaque)):
            return T.ONE
        if isinstance(v, str):
            return T.const(int(v != ""), 1)
        if isinstance(v, (int, float)):
            return T.const(int(bool(v)), 1)
        raise TranslateError(f"value {v!r} used as a condition")

    def _conv_to(self, v, to_t, src_expr, from_type=None):
        tt = to_t.canonicalType
        if tt.isIntegral:
            if isinstance(v, (T.Term, int, bool)):
                ft = from_type.canonicalType if from_type is not None else (
                    src_expr.type.canonicalType if src_expr is not None else None)
                signed = bool(ft is not None and ft.isIntegral and ft.isSigned)
                t = self._term(v, None, None) if isinstance(v, T.Term) else T.const(int(v), width_of(tt))
                return T.resize(t, width_of(tt), signed)
            if isinstance(v, float):
                return T.const(int(v), width_of(tt))
            if isinstance(v, str):
                n = 0
                for ch in v:
                    n = (n << 8) | ord(ch)
                return T.const(n, width_of(tt))
            if v is None:
                return T.const(0, width_of(tt))
        return v

    @staticmethod
    def _is_handle(v) -> bool:
        return isinstance(v, HU)

    @staticmethod
    def _alts(v) -> List[Tuple[T.Term, Any]]:
        if isinstance(v, HU):
            return list(v.alts)
        if v is None:
            return []
        return [(T.ONE, v)]

    @staticmethod
    def _norm_hu(alts):
        out = []
        for c, o in alts:
            if c.is_const and not c.val:
                continue
            if o is None:
                continue
            for i, (c2, o2) in enumerate(out):
                if o2 is o:
                    out[i] = (T.or_(c2, c), o)
                    break
            else:
                out.append((c, o))
        if len(out) == 1 and out[0][0].is_const and out[0][0].val:
            return out[0][1]
        if not out:
            return None
        return HU(out)

    # ================================================================ vars
    def _uniq(self, name: str) -> str:
        base = name
        n = 1
        while name in self._names:
            n += 1
            name = f"{base}_{n}"
        self._names.add(name)
        return name

    def _mk_var(self, key, name, w, kind="reg", init=0, origin="") -> P.Var:
        v = self.vars.get(key)
        if v is None:
            v = P.Var(name=self._uniq(_safe(name)), w=w, kind=kind, init=init, origin=origin)
            self.vars[key] = v
            self.var_list.append(v)
        return v

    def _state_var_field(self, o: Obj, prop) -> P.Var:
        key = ("f", o.oid, prop)
        if key in self.vars:
            return self.vars[key]
        w = width_of(prop.type)
        init = o.fields[prop]
        init = init if isinstance(init, int) else 0
        name = f"{self._obj_names.get(o.oid, o.cls.name)}.{prop.name}"
        return self._mk_var(key, name, w, "reg", mask(init, w), origin=f"{o.cls.name}.{prop.name}")

    def _state_var_if(self, f: Iface, name: str, t) -> P.Var:
        key = ("i", f.path, name)
        if key in self.vars:
            return self.vars[key]
        w = width_of(t)
        init = f.vars.get(name, 0)
        init = init if isinstance(init, int) else 0
        return self._mk_var(key, f"{self._iface_rel(f.path)}.{name}", w, "reg", mask(init, w),
                            origin=f"{f.path}.{name}")

    def _net_var(self, f: Iface, name: str, w: int) -> P.Var:
        key = ("i", f.path, name)
        return self._mk_var(key, f"{self._iface_rel(f.path)}.{name}", w, "net",
                            origin=f"{f.path}.{name}")

    def _local_var(self, act: Act, sym, w: int) -> P.Var:
        key = ("l", self._proc_name, act.path, act.name, sym if not isinstance(sym, tuple) else sym)
        if key in self.vars:
            v = self.vars[key]
            if v.w != w:
                raise TranslateError(f"local {getattr(sym, 'name', sym)} changes width")
            return v
        nm = getattr(sym, "name", None) or "_".join(str(x) for x in sym).replace("$", "")
        init = self._block_value(act, sym, w)
        return self._mk_var(key, f"{act.name}.{nm}", w, "reg", init,
                            origin=f"local {nm} in {act.name}")

    def _block_value(self, act: Act, sym, w: int) -> int:
        """A local that is live where the thread blocked resets to the value it had
        there (the process starts at that point)."""
        depth = len(act.path)
        tpath = self._target[0]
        if isinstance(sym, tuple) or act.path != tpath[:depth] or depth >= len(self._block_frames):
            return 0
        fr: Optional[Frame] = self._block_frames[depth]
        while fr is not None:
            if sym in fr.locals:
                v = fr.locals[sym]
                return mask(v, w) if isinstance(v, int) else 0
            fr = fr.parent
        return 0

    def _temp_var(self, w: int, what: str) -> P.Var:
        self._tmp += 1
        return self._mk_var(("t", self._proc_name, self._tmp), f"{self._proc_name}._{what}{self._tmp}",
                            w, "reg", 0, origin="temporary")

    def _iface_rel(self, path: str) -> str:
        top = self.elab.top.name + "."
        return path[len(top):] if path.startswith(top) else path

    @staticmethod
    def _fname(fr: Frame) -> str:
        if fr.sub is not None:
            who = fr.this.cls.name if fr.this is not None else ""
            return _safe(f"{who}.{fr.sub.name}" if who else fr.sub.name)
        return "root"

    def _name_objects(self) -> Dict[int, str]:
        """A readable path for every object reachable from the root."""
        names: Dict[int, str] = {}
        root = self.elab.root
        queue = [(root, "root")]
        names[root.oid] = "root"
        while queue:
            o, path = queue.pop(0)
            for prop, v in sorted(o.fields.items(), key=lambda kv: kv[0].name):
                vals = v if isinstance(v, list) else list(v.values()) if isinstance(v, dict) else [v]
                for i, x in enumerate(vals):
                    if isinstance(x, Obj) and x.oid not in names:
                        nm = prop.name.lstrip("m_") if prop.name.startswith("m_") else prop.name
                        nm = f"{path}.{nm}" + (f"{i}" if len(vals) > 1 else "")
                        names[x.oid] = nm
                        queue.append((x, nm))
        return names

    def note(self, msg: str) -> None:
        # translation restarts (state discovery) repeat the same notes
        if msg not in self.warnings:
            self.warnings.append(msg)

    # state for a translation pass
    _act_stack: List[Act] = []
    _loop_flags: List[dict] = []
    _loop_id = 0
    _lvref_val = None


def _safe(name: str) -> str:
    return "".join(c if (c.isalnum() or c == "_") else "_" for c in name).strip("_")


def translate(elab: ElabResult) -> Tuple[P.Design, List[str]]:
    tr = Translator(elab)
    tr._act_stack = []
    tr._loop_flags = []
    d = tr.translate()
    return d, tr.warnings


def _written_roots(node, kind: str) -> List[Any]:
    """The variables an always_comb body or a continuous assignment writes."""
    out: List[Any] = []
    if node is None:
        return out

    def root(e):
        while True:
            k = e.kind
            if k in (EK.ElementSelect, EK.RangeSelect, EK.MemberAccess):
                e = e.value
            elif k == EK.Conversion:
                e = e.operand
            elif k == EK.Assignment:
                e = e.left
            elif k == EK.Concatenation:
                for x in e.operands:
                    root(x)
                return
            else:
                break
        if k in (EK.NamedValue, EK.HierarchicalValue):
            out.append(e.symbol)

    if kind == "assign":
        root(node.left)
        return out

    def cb(n):
        if isinstance(n, ast.Expression) and n.kind == EK.Assignment:
            root(n.left)
        return True
    node.visit(cb)
    return out
