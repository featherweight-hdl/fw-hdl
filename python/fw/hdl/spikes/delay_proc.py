"""F5c route (ii) spike: zuspec-synth's process-level delay engine choosing
pipeline cut points for a dataflow map's ``f`` (micro-pipelining-feasibility
§2 A5, §4 F5c). Throwaway quality.

``f`` is ``y = a * b + c`` on W-bit unsigned a, b, c, evaluated at 2W (SV
context width: operands zero-extended to 2W). The process is::

    forever { x = in.get(); out.put(f(x)); }

The proc IR has no stream channel type: get/put are timed call regions over
ready/valid vars (the same form zuspec-synth's own tests use,
tests/test_proc_sched_random.py ``get``/``put``). ``x`` is one 3W word
{c, b, a}; the slices are free in the delay model.
"""
from __future__ import annotations

import dataclasses as dc
from typing import Dict, List, Optional

from zuspec.synth.proc import ir as P
from zuspec.synth.proc import sched
from zuspec.synth.proc import term as T
from zuspec.synth.proc.delay import DelayModel
from zuspec.synth.proc.lower import lower
from zuspec.synth.proc.sched.delay import place
from zuspec.synth.proc.timing import _Arrival, analyze


def _v(v: P.Var) -> T.Term:
    return T.var(v.name, v.w)


def _k(k: int, w: int) -> T.Term:
    return T.const(k, w)


def f_term(x: T.Term, w: int) -> T.Term:
    """``zext(a)*zext(b) + zext(c)`` at 2W, a/b/c the W-bit slices of x."""
    a, b, c = (T.zext(T.slice_(x, i * w, w), 2 * w) for i in range(3))
    return T.add(T.mul(a, b), c)


def build(w: int) -> P.Design:
    """The one-process design for width ``w``."""
    clk, rst = P.Var("clk", 1, "in"), P.Var("rst", 1, "in")
    i_valid, i_data = P.Var("i_valid", 1, "in"), P.Var("i_data", 3 * w, "in")
    i_rdy = P.Var("i_rdy", 1)
    o_valid, o_data = P.Var("o_valid", 1), P.Var("o_data", 2 * w)
    o_ready = P.Var("o_ready", 1, "in")
    x, y = P.Var("x", 3 * w), P.Var("y", 2 * w)
    get = P.Region(timed=True, call="i.get", origin="i.get", body=[
        P.Assign(i_rdy, _k(1, 1), nb=True), P.Await(None), P.Await(_v(i_valid)),
        P.Assign(x, _v(i_data)), P.Assign(i_rdy, _k(0, 1), nb=True)])
    put = P.Region(timed=True, call="o.put", origin="o.put", body=[
        P.Assign(o_valid, _k(1, 1), nb=True), P.Assign(o_data, _v(y), nb=True),
        P.Await(None), P.Await(_v(o_ready)), P.Assign(o_valid, _k(0, 1), nb=True)])
    body = [P.Await(None, initial=True, label="top"), get,
            P.Assign(y, f_term(_v(x), w), loc="f"), put]
    proc = P.Proc("p", [P.Loop(body=body)], timed=False)
    ports = [P.Port("i_rdy_o", 1, "out", i_rdy), P.Port("o_valid_o", 1, "out", o_valid),
             P.Port("o_data_o", 2 * w, "out", o_data)]
    return P.Design(f"fpipe_w{w}", clk, rst, ports=ports,
                    vars=[clk, rst, i_valid, i_data, o_ready, i_rdy, o_valid, o_data, x, y],
                    procs=[proc])


def f_depth(w: int, model: DelayModel) -> float:
    """Model delay of ``f`` alone, from registered inputs to its output."""
    an = _Arrival(model, {"x"}, {}, model.clk_to_q)
    return an.of(f_term(T.var("x", 3 * w), w)) - model.clk_to_q


def _op(t: T.Term) -> str:
    """The costly operator an assignment's value is (after the split)."""
    return t.op if t.op != "ite" else _op(t.args[1])


def _cuts(stmts: List[P.Stmt]) -> List[str]:
    """For each 'delay' edge, 'before / after': the op an assignment
    computes, or the call region (get, put), on each side."""
    def name(s):
        if isinstance(s, P.Assign):
            return _op(s.value)
        if isinstance(s, P.Region):
            return s.call or "region"
        return "-"
    out = []
    for i, s in enumerate(stmts):
        if isinstance(s, P.Await) and s.label.startswith("delay"):
            out.append(f"{name(stmts[i - 1])} / {name(stmts[i + 1])}")
    return out


@dc.dataclass
class Result:
    w: int
    model: str
    f_depth: float
    budget: float
    edges: int
    splits: int
    cuts: List[str]
    stage_delay: List[float]       # worst arrival per state (lowered + analyzed)
    violations: List[str]

    @property
    def f_cuts(self) -> int:       # edges with f's ops on both sides
        return sum(1 for c in self.cuts if "." not in c and "-" not in c)

    @property
    def f_stages(self) -> int:
        return self.f_cuts + 1


def run(w: int, budget: float, model: Optional[DelayModel] = None) -> Result:
    model = model or DelayModel.load("unit")
    d = build(w)
    s, edges, splits, viol, why, _ = place(d, model, budget, split=True)
    loop = s.procs[0].body[0]
    s = dc.replace(s, scheduled="delay")
    # no optimize(): its sequential passes bit-blast the 2W multiplier and
    # take minutes at W=16 (the per-state arrivals don't need it)
    rep = analyze(lower(sched.finish(s)), model)
    stage = [st.worst.arrival for st in rep.states if st.worst]
    return Result(w, model.name, f_depth(w, model), budget, edges, splits,
                  _cuts(loop.body), stage,
                  [v.text(1.0, model.units) for v in viol])


def width_model() -> DelayModel:
    """Illustrative width-scaled model (not characterized): ripple add
    costs w levels, an array multiply 2w, as a rough gate-level stand-in."""
    return DelayModel.from_dict({
        "name": "width-illustrative", "units": "levels",
        "ops": {"add": {"by": "width", "points": [[1, 1, 1], [64, 64, 64]]},
                "mul": {"by": "width", "points": [[1, 2, 1], [64, 128, 64]]}}})


def sweep(ws=(8, 16, 32), divs=(1, 2, 3), model: Optional[DelayModel] = None):
    model = model or DelayModel.load("unit")
    out = []
    for w in ws:
        fd = f_depth(w, model)
        for k in divs:
            out.append(run(w, fd / k, model))
    return out


def table(rs: List[Result]) -> str:
    lines = ["| W | model | f depth | budget | edges | f stages | split | cuts | stage arrivals | violations |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rs:
        lines.append(f"| {r.w} | {r.model} | {r.f_depth:g} | {r.budget:.3g} | {r.edges} | "
                     f"{r.f_stages} | {r.splits} | {'; '.join(r.cuts) or '-'} | "
                     f"{', '.join(f'{x:g}' for x in r.stage_delay)} | {len(r.violations)} |")
    return "\n".join(lines)


if __name__ == "__main__":
    rs = sweep() + sweep(model=width_model())
    print(table(rs))
    for r in rs:
        for v in r.violations:
            print(f"W={r.w} {r.model} budget={r.budget:.3g}: {v}")
