"""Spike (micro-pipelining D0, F5b): recognize a map shape in sync IR.

Throwaway-quality code, judged by what it shows
(docs/design/micro-pipelining-feasibility.md F5b). It reads a parameterized
sync component (``fw.hdl.fe.elab.sync_param``) whose port fields carry
channel pragmas (F5a: ``channel``, ``channel_role``, ``channel_side``) and
answers: is this component a *map*, ``out.data = f(in.data)`` with
``out.valid = in.valid`` and ``in.ready = out.ready`` and nothing else, and
if so what is ``f``; if not, why not.

A component of N lanes (port arrays, one ``for`` per field over the lanes,
each lane reading only its own elements) is a map of N lanes.
"""
from __future__ import annotations

import dataclasses as dc
from typing import Dict, List, Optional, Set, Tuple, Union

import zuspec.ir.core as ir
from zuspec.ir.core.data_type import DataTypeArray, DataTypeComponent
from zuspec.ir.core.fields import FieldInOut


@dc.dataclass
class Channel:
    """A ready/valid port: its field indices in the component."""
    name: str
    side: str                      # "in" or "out" (the component's view)
    valid: int
    ready: int
    data: int
    lanes: Optional[object] = None  # array size (int or Expr) or None


@dc.dataclass
class MapMatch:
    comp: DataTypeComponent
    inp: Channel
    out: Channel
    #: out.data's value, over the input's data (``ExprRefField`` of
    #: ``inp.data``, subscripted by the lane variable when there are lanes)
    data: ir.Expr
    #: the lane variable's name when the map has lanes
    lane: Optional[str]
    #: the component's functions that ``data`` calls (pure: they read only
    #: their arguments)
    calls: List[str]


@dc.dataclass
class NoMatch:
    comp: DataTypeComponent
    reason: str


def channels(comp: DataTypeComponent) -> Dict[str, Channel]:
    """The ready/valid channels of ``comp`` from its fields' pragmas."""
    acc: Dict[str, Dict[str, object]] = {}
    for i, f in enumerate(comp.fields):
        p = f.pragmas or {}
        if p.get("channel_kind") != "rv":
            continue
        c = acc.setdefault(p["channel"], {"side": p["channel_side"]})
        c[p["channel_role"]] = i
        if isinstance(f.datatype, DataTypeArray):
            c["lanes"] = f.datatype.size_expr if f.datatype.size_expr is not None \
                else f.datatype.size
    return {n: Channel(name=n, side=c["side"], valid=c["valid"], ready=c["ready"],
                       data=c["data"], lanes=c.get("lanes")) for n, c in acc.items()}


# -- expression walking -------------------------------------------------------

def _walk(x, fn):
    """Call fn on every IR node under x (x included)."""
    fn(x)
    if dc.is_dataclass(x) and not isinstance(x, type):
        for f in dc.fields(x):
            v = getattr(x, f.name)
            if isinstance(v, list):
                for e in v:
                    if dc.is_dataclass(e):
                        _walk(e, fn)
            elif dc.is_dataclass(v) and not isinstance(v, type):
                _walk(v, fn)


def _field_reads(e) -> Set[int]:
    out: Set[int] = set()

    def fn(n):
        if isinstance(n, ir.ExprRefField) and isinstance(n.base, ir.TypeExprRefSelf):
            out.add(n.index)
    _walk(e, fn)
    return out


def _calls(e) -> List[str]:
    out: List[str] = []

    def fn(n):
        if isinstance(n, ir.ExprCall) and isinstance(n.func, ir.ExprAttribute) \
                and isinstance(n.func.value, ir.TypeExprRefSelf):
            out.append(n.func.attr)
    _walk(e, fn)
    return out


def _locals(e) -> Set[str]:
    out: Set[str] = set()

    def fn(n):
        if isinstance(n, ir.ExprRefLocal):
            out.add(n.name)
    _walk(e, fn)
    return out


# -- the comb body as per-field assignments -----------------------------------

def _target(t, lane: Optional[str]) -> Optional[int]:
    """The field a statement's target is: ``field`` (no lanes) or
    ``field[lane]``; None for anything else."""
    if lane is None and isinstance(t, ir.ExprRefField) and isinstance(t.base, ir.TypeExprRefSelf):
        return t.index
    if lane is not None and isinstance(t, ir.ExprSubscript) \
            and isinstance(t.value, ir.ExprRefField) \
            and isinstance(t.slice, ir.ExprRefLocal) and t.slice.name == lane:
        return t.value.index
    return None


def _lane_loop(s) -> Optional[Tuple[str, object]]:
    """``(var, upper bound)`` of ``for var in range(0, hi)``, else None."""
    if not isinstance(s, ir.StmtFor) or s.orelse:
        return None
    it = s.iter
    if not (isinstance(s.target, ir.ExprRefLocal) and isinstance(it, ir.ExprCall)
            and isinstance(it.func, ir.ExprRefUnresolved) and it.func.name == "range"
            and len(it.args) == 2 and isinstance(it.args[0], ir.ExprConstant)
            and it.args[0].value == 0):
        return None
    return s.target.name, it.args[1]


def _assigns(body: list) -> Union[str, Tuple[Optional[str], List[Tuple[int, ir.Expr]]]]:
    """``(lane var or None, [(field, value)])`` for a comb body made of plain
    field assignments, or one-assignment loops over the lanes; a reason
    string for anything else."""
    out: List[Tuple[int, ir.Expr]] = []
    lane: Optional[str] = None
    mode: Optional[str] = None          # "scalar" or "lanes"
    for s in body:
        ll = _lane_loop(s)
        if ll is not None:
            if mode == "scalar":
                return "mixes per-lane loops with scalar assignments"
            mode = "lanes"
            var = ll[0]
            for b in s.body:
                if not isinstance(b, ir.StmtAssign) or len(b.targets) != 1:
                    return "a lane loop holds something other than field assignments"
                f = _target(b.targets[0], var)
                if f is None:
                    return "a lane loop assigns something other than this lane's field"
                # one lane variable name for the map: rename later loops' vars
                v = b.value if lane is None or var == lane else _rename(b.value, var, lane)
                out.append((f, v))
            lane = lane or var
            continue
        if isinstance(s, ir.StmtAssign) and len(s.targets) == 1:
            if mode == "lanes":
                return "mixes per-lane loops with scalar assignments"
            mode = "scalar"
            f = _target(s.targets[0], None)
            if f is None:
                return "assigns something other than a port field"
            out.append((f, s.value))
            continue
        return f"comb() has a {type(s).__name__} (only field assignments are a map)"
    return lane, out


def _rename(e, old: str, new: str):
    if isinstance(e, ir.ExprRefLocal) and e.name == old:
        return dc.replace(e, name=new)
    if dc.is_dataclass(e) and not isinstance(e, type):
        ch = {}
        for f in dc.fields(e):
            v = getattr(e, f.name)
            if isinstance(v, list):
                nv = [_rename(x, old, new) for x in v]
                if any(a is not b for a, b in zip(nv, v)):
                    ch[f.name] = nv
            elif dc.is_dataclass(v) and not isinstance(v, type):
                nv = _rename(v, old, new)
                if nv is not v:
                    ch[f.name] = nv
        if ch:
            return dc.replace(e, **ch)
    return e


def _own_lane(e, field: int, lane: str) -> bool:
    """Every read of ``field`` in ``e`` is ``field[lane]``."""
    ok = [True]

    def fn(n):
        if isinstance(n, ir.ExprSubscript) and isinstance(n.value, ir.ExprRefField) \
                and n.value.index == field and not (
                    isinstance(n.slice, ir.ExprRefLocal) and n.slice.name == lane):
            ok[0] = False
    _walk(e, fn)
    bare = [0]

    def count(n):
        if isinstance(n, ir.ExprRefField) and n.index == field:
            bare[0] += 1
    _walk(e, count)
    subs = [0]

    def count_sub(n):
        if isinstance(n, ir.ExprSubscript) and isinstance(n.value, ir.ExprRefField) \
                and n.value.index == field:
            subs[0] += 1
    _walk(e, count_sub)
    return ok[0] and bare[0] == subs[0]       # no whole-array read either


def _is_ref(e, field: int, lane: Optional[str]) -> bool:
    return _target(e, lane) == field


def _pure_fn(comp: DataTypeComponent, name: str) -> Optional[str]:
    """None if function ``name`` reads only its arguments and locals; else why."""
    fn = next((f for f in comp.functions if f.name == name), None)
    if fn is None:
        return f"calls '{name}', which is not a function of the component"
    reads = set()
    for s in fn.body:
        reads |= _field_reads(s)
    if reads:
        return f"'{name}' reads {', '.join(comp.fields[i].name for i in sorted(reads))}"
    for s in fn.body:
        for c in _calls(s):
            why = _pure_fn(comp, c)
            if why is not None:
                return why
    return None


def match_map(comp: DataTypeComponent) -> Union[MapMatch, NoMatch]:
    """``comp`` as a map, or why it isn't one."""
    def no(why: str) -> NoMatch:
        return NoMatch(comp, why)

    if comp.module_instances:
        return no("a composite (its children are matched one by one)")
    if comp.sync_processes:
        return no("has step(): state")
    state = [f.name for f in comp.fields if not isinstance(f, FieldInOut)]
    if state:
        return no(f"has state: {', '.join(state)}")
    chans = channels(comp)
    ins = [c for c in chans.values() if c.side == "in"]
    outs = [c for c in chans.values() if c.side == "out"]
    if len(ins) != 1 or len(outs) != 1:
        return no(f"{len(ins)} input and {len(outs)} output channels (a map has 1 and 1)")
    i, o = ins[0], outs[0]
    other = [f.name for f in comp.fields if isinstance(f, FieldInOut)
             and (f.pragmas or {}).get("channel") not in (i.name, o.name)]
    if other:
        return no(f"ports outside the two channels: {', '.join(other)}")
    if (i.lanes is None) != (o.lanes is None) or (i.lanes is not None and i.lanes != o.lanes):
        return no("input and output have different lanes")
    if len(comp.comb_processes) != 1:
        return no("no comb()")
    r = _assigns(comp.comb_processes[0].body)
    if isinstance(r, str):
        return no(r)
    lane, asg = r
    if (lane is None) != (i.lanes is None):
        return no("the lanes are not assigned one loop per field")
    by: Dict[int, ir.Expr] = {}
    for f, v in asg:
        if f in by:
            return no(f"'{comp.fields[f].name}' assigned twice")
        by[f] = v
    want = {o.valid, o.data, i.ready}
    if set(by) != want:
        extra = sorted(set(by) - want)
        if extra:
            return no(f"comb() writes {', '.join(comp.fields[x].name for x in extra)}")
        return no("comb() does not drive out.valid, out.data and in.ready")
    if not _is_ref(by[o.valid], i.valid, lane):
        reads = _field_reads(by[o.valid])
        if i.data in reads:
            return no("out.valid depends on the data: a filter (not a map)")
        return no("out.valid is not in.valid")
    if not _is_ref(by[i.ready], o.ready, lane):
        reads = _field_reads(by[i.ready])
        if i.data in reads or i.valid in reads:
            return no("in.ready depends on the input: a filter or a join (not a map)")
        return no("in.ready is not out.ready")
    d = by[o.data]
    reads = _field_reads(d)
    if reads - {i.data}:
        return no(f"out.data reads {', '.join(comp.fields[x].name for x in sorted(reads - {i.data}))}")
    if lane is not None and _locals(d) - {lane}:
        return no("out.data reads locals other than the lane")
    if lane is not None and not _own_lane(d, i.data, lane):
        return no("out.data reads another lane's input")
    for c in _calls(d):
        why = _pure_fn(comp, c)
        if why is not None:
            return no(why)
    return MapMatch(comp=comp, inp=i, out=o, data=d, lane=lane, calls=_calls(d))
