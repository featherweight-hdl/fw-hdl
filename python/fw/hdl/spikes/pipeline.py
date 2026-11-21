"""Spike (micro-pipelining D0, F6): pipeline a recognized map, IR to IR.

Throwaway-quality code (docs/design/micro-pipelining-feasibility.md F6).
``stall_map`` turns a map (``dataflow.match_map``) into a new sync component
with K stage registers and a ``stall`` controller, as sync IR, in the form
of the hand-written answer key (``pipe_map_in_stall1``): stage registers
``s<k>_v``/``s<k>_d``; ``comb()`` drives the output from the last stage and
``in.ready = !s<K>_v || out.ready``; ``step()`` moves every stage when the
last one is empty or taken. ``f`` is computed before stage 1; stages 2..K
are registers only, for a retiming step downstream to fill (F4: cutting
``f`` at its operators doesn't shorten the path when one operator, here the
multiply, is most of it). ``replace_child`` swaps a composite's child for
the result. zuspec-be-sv emits it unchanged.
"""
from __future__ import annotations

import dataclasses as dc
from typing import Dict, List, Optional

import zuspec.ir.core as ir
from zuspec.ir.core.data_type import DataTypeArray, DataTypeComponent, DataTypeInt
from zuspec.ir.core.fields import Field, FieldInOut

from .dataflow import MapMatch


def _f(i: int) -> ir.ExprRefField:
    return ir.ExprRefField(base=ir.TypeExprRefSelf(), index=i)


def _remap(e, m: Dict[int, int]):
    """``e`` with its field indices renumbered by ``m``."""
    if isinstance(e, ir.ExprRefField) and isinstance(e.base, ir.TypeExprRefSelf):
        return dc.replace(e, index=m[e.index])
    if dc.is_dataclass(e) and not isinstance(e, type):
        ch = {}
        for f in dc.fields(e):
            v = getattr(e, f.name)
            if isinstance(v, list):
                nv = [_remap(x, m) for x in v]
                if any(a is not b for a, b in zip(nv, v)):
                    ch[f.name] = nv
            elif dc.is_dataclass(v) and not isinstance(v, type):
                nv = _remap(v, m)
                if nv is not v:
                    ch[f.name] = nv
        if ch:
            return dc.replace(e, **ch)
    return e


def stall_map(match: MapMatch, k: int, name: Optional[str] = None) -> DataTypeComponent:
    """The map of ``match`` with ``k`` stages and a stall controller."""
    if k < 1:
        raise ValueError("k >= 1")
    src = match.comp
    lane = match.lane
    lanes = match.inp.lanes

    def at(e):
        return ir.ExprSubscript(value=e, slice=ir.ExprRefLocal(name=lane)) if lane else e

    def per_lane(body: List[ir.Stmt]) -> List[ir.Stmt]:
        if not lane:
            return body
        hi = lanes if isinstance(lanes, ir.Expr) else ir.ExprConstant(value=int(lanes))
        return [ir.StmtFor(target=ir.ExprRefLocal(name=lane),
                           iter=ir.ExprCall(func=ir.ExprRefUnresolved(name="range"),
                                            args=[ir.ExprConstant(value=0), hi]),
                           body=body, orelse=[])]

    def arr(et):
        if not lane:
            return et
        dt = src.fields[match.inp.valid].datatype
        return dc.replace(dt, element_type=et)

    one = DataTypeInt(bits=1, signed=False)
    fields: List[Field] = [FieldInOut(name="clock", datatype=one, is_out=False),
                           FieldInOut(name="reset", datatype=one, is_out=False)]
    remap = {}
    for i, f in enumerate(src.fields):
        remap[i] = len(fields)
        fields.append(dc.replace(f))
    i_v, i_r, i_d = (remap[x] for x in (match.inp.valid, match.inp.ready, match.inp.data))
    o_v, o_r, o_d = (remap[x] for x in (match.out.valid, match.out.ready, match.out.data))
    dt_d = src.fields[match.out.data].datatype
    dt_d = dt_d.element_type if isinstance(dt_d, DataTypeArray) else dt_d
    sv, sd = [], []
    for s in range(1, k + 1):
        sv.append(len(fields))
        fields.append(Field(name=f"s{s}_v", datatype=arr(one), drive=ir.ProcessKind.SYNC))
        sd.append(len(fields))
        fields.append(Field(name=f"s{s}_d", datatype=arr(dt_d), drive=ir.ProcessKind.SYNC))

    last_v, last_d = _f(sv[-1]), _f(sd[-1])
    take = ir.ExprBool(op=ir.BoolOp.Or, values=[
        ir.ExprUnary(op=ir.UnaryOp.Not, operand=at(last_v)), at(_f(o_r))])

    def asg(t, v):
        return ir.StmtAssign(targets=[t], value=v)

    comb = (per_lane([asg(at(_f(o_v)), at(last_v))])
            + per_lane([asg(at(_f(o_d)), at(last_d))])
            + per_lane([asg(at(_f(i_r)), take)]))

    move: List[ir.Stmt] = []
    for s in range(k - 1, 0, -1):            # last stage first: blocking order
        move.append(asg(at(_f(sv[s])), at(_f(sv[s - 1]))))
        move.append(asg(at(_f(sd[s])), at(_f(sd[s - 1]))))
    move.append(asg(at(_f(sv[0])), at(_f(i_v))))
    move.append(asg(at(_f(sd[0])), _remap(match.data, remap)))
    clear = [asg(at(_f(v)), ir.ExprConstant(value=0)) for v in sv]
    step = [ir.StmtIf(test=_f(1), body=per_lane(clear),
                      orelse=per_lane([ir.StmtIf(test=take, body=move, orelse=[])]))]

    comp = DataTypeComponent(name=name or f"{src.name}_stall{k}", super=None,
                             template_params=list(src.template_params))
    comp.fields.extend(fields)
    comp.comb_processes.append(ir.Function(name="comb", process_kind=ir.ProcessKind.COMB,
                                           body=comb, metadata={"locals": []}))
    comp.sync_processes.append(ir.Function(
        name="step", process_kind=ir.ProcessKind.SYNC, body=step,
        metadata={"order": "blocking", "clock": _f(0), "reset": _f(1), "locals": []}))
    comp.functions.extend(src.functions)
    return comp


def replace_child(top: DataTypeComponent, inst: str, new: DataTypeComponent,
                  name: Optional[str] = None) -> DataTypeComponent:
    """Composite ``top`` with child instance ``inst`` made of ``new`` (same
    ports, plus clock and reset when ``new`` has them)."""
    kf = {f.name for f in new.fields}
    mis = []
    for mi in top.module_instances:
        if mi.name == inst:
            conns = [c for c in mi.connections if c.port not in ("clock", "reset")]
            conns = [ir.PortConnection(port=p, signal=p) for p in ("clock", "reset")
                     if p in kf] + conns
            mi = dc.replace(mi, module=new.name, connections=conns)
        mis.append(mi)
    out = dc.replace(top, name=name or top.name, module_instances=mis)
    return out


def pipeline_design(irs: Dict[str, object], top: str, inst: str, match: MapMatch, k: int,
                    name: Optional[str] = None) -> Dict[str, object]:
    """``irs`` (``elab_sync_param`` output for one variable) with ``top``'s
    child ``inst`` pipelined ``k`` deep; the result's top is ``name``."""
    new = stall_map(match, k)
    out: Dict[str, object] = {}
    for key, v in irs.items():
        if key == top:
            out[new.name] = new
            out[name or top] = replace_child(v, inst, new, name)
        else:
            out[key] = v
    return out


def project_class(comp: DataTypeComponent, type_m: Dict[str, object]) -> str:
    """A crude projection of ``comp`` back to a sync class (F6 probe): be-sv's
    statement printer with the flattened port fields turned back into view
    calls through their channel pragmas (F5a). It shows what a real
    projection needs, not what one should look like."""
    import re
    from zuspec.be.sv.sync_param import SyncParamEmitter, _decl

    em = SyncParamEmitter(comp, type_m)
    ctx = {"step": False, "reset": None, "dirty": False}
    ports: Dict[str, Dict[str, object]] = {}
    for f in comp.fields:
        p = f.pragmas or {}
        if p.get("channel_kind") == "rv":
            ports.setdefault(p["channel"], {"side": p["channel_side"], "dt": f.datatype})
            if p["channel_role"] == "data":
                ports[p["channel"]]["dt"] = f.datatype
    names = "|".join(re.escape(n) for n in ports)

    def calls(text: str) -> str:
        if not names:
            return text
        # writes: "<ch>_<role>[i] = v;" -> "<ch>[i].set_<role>(v);"
        text = re.sub(rf"^(\s*)({names})_(valid|ready|data)(\[\w+\])? = (.*);$",
                      lambda m: f"{m.group(1)}{m.group(2)}{m.group(4) or ''}"
                                f".set_{m.group(3)}({m.group(5)});", text, flags=re.M)
        return re.sub(rf"\b({names})_(valid|ready|data)(\[\w+\])?",
                      lambda m: f"{m.group(1)}{m.group(3) or ''}.get_{m.group(2)}()", text)

    tps = ", ".join(f"type {tp.name}" if tp.kind.name == "TYPE" else f"int {tp.name}"
                    for tp in comp.template_params)
    out = [f"class {comp.name} #({tps}) extends fw_component "
           f"implements fw_combinational, fw_steppable;"]
    for n, c in ports.items():
        dt = c["dt"]
        el = dt.element_type if isinstance(dt, DataTypeArray) else dt
        dim = f"[{em.expr(dt.size_expr, ctx)}]" if isinstance(dt, DataTypeArray) \
            and dt.size_expr is not None else ""
        out.append(f"    fw_rv_sp_{c['side']} #({el.ref_name}) {n}{dim};")
    for f in comp.fields:
        if not isinstance(f, FieldInOut):
            out.append(f"    {_decl(f.datatype, f.name)};")
    for fn in comp.functions:
        out.append("")
        out += [calls(x) for x in em.function(fn, False)]
    for kind, fns in (("comb", comp.comb_processes), ("step", comp.sync_processes)):
        for fn in fns:
            out.append("")
            out.append(f"    virtual function void {kind}();")
            body = "\n".join(em.stmts(fn.body, ctx, 2))
            body = re.sub(r"\breset\b", "in_reset()", body)
            out.append(calls(body))
            out.append("    endfunction")
    out.append("endclass")
    return "\n".join(out) + "\n"
