"""Compare two views' streams up to the reorderings a contract allows.

A trace is a list of events, one JSON object per line as ``fw_trace``
(src/std/order/fw_order_pkg.sv) writes them::

    {"pt": "rsp", "ev": "in"|"out", "cyc": 12, "id": 7, "key": 3, "cls": 0, "data": 99}

``ev`` "in" is an item entering the contract's scope, "out" an item leaving
it. A :class:`Rule` says which later items may pass which earlier ones; it is
the Python twin of ``fw_order_rule``.

Two traces are *the same function* when they hold the same items with the
same data and every pair the rule binds leaves in the same relative order.
:func:`check` is the single-trace check (as ``fw_order_check`` does it);
:func:`canonical` gives a form where equal means equivalent; :func:`compare`
lists the differences.
"""
from __future__ import annotations

import dataclasses as dc
import json
from pathlib import Path
from typing import Dict, FrozenSet, Iterable, List, Optional, Sequence, Tuple, Union


@dc.dataclass(frozen=True)
class Event:
    pt: str
    ev: str
    cyc: int
    id: int
    key: int = 0
    cls: int = 0
    data: int = 0


@dc.dataclass
class Rule:
    """Which reorderings a stream may show (see ``fw_order_rule``)."""
    per_key: bool = False
    allow_pass: FrozenSet[Tuple[int, int]] = frozenset()     # (earlier cls, later cls)
    strict_after: FrozenSet[Tuple[int, int]] = frozenset()
    pin_cycles: bool = False    # compare leave cycles too (cycle-exact views only)

    @classmethod
    def from_dict(cls, d: dict) -> "Rule":
        unknown = set(d) - {"per_key", "allow_pass", "strict_after", "pin_cycles"}
        if unknown:
            raise ValueError(f"unknown rule keys: {sorted(unknown)}")
        return cls(per_key=bool(d.get("per_key", False)),
                   allow_pass=frozenset(tuple(p) for p in d.get("allow_pass", [])),
                   strict_after=frozenset(tuple(p) for p in d.get("strict_after", [])),
                   pin_cycles=bool(d.get("pin_cycles", False)))

    def binds(self, earlier: Event, later: Event) -> bool:
        if self.per_key and earlier.key != later.key:
            return False
        return (earlier.cls, later.cls) not in self.allow_pass


Trace = List[Event]


def load_trace(src: Union[str, Path, Iterable[str]]) -> Trace:
    lines = Path(src).read_text().splitlines() if isinstance(src, (str, Path)) else src
    out = []
    for n, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(Event(**json.loads(line)))
        except (TypeError, ValueError) as e:
            raise ValueError(f"trace line {n}: {e}") from None
    return out


def _split(trace: Trace) -> Tuple[List[Event], List[Event]]:
    return [e for e in trace if e.ev == "in"], [e for e in trace if e.ev == "out"]


def check(trace: Trace, rule: Rule) -> List[str]:
    """Violations in one trace, in the order fw_order_check reports them."""
    errs: List[str] = []
    live: List[Event] = []
    seen, left = set(), set()
    last_cyc, last = None, []          # items that left in the current cycle
    seq: Dict[int, int] = {}
    for e in trace:
        if e.ev == "in":
            if e.id in seen:
                errs.append(f"DUPLICATE: id {e.id} entered twice")
                continue
            seen.add(e.id)
            seq[e.id] = len(seq)
            live.append(e)
            continue
        if e.id in left:
            errs.append(f"DUPLICATE: id {e.id} left twice")
            continue
        at = next((i for i, x in enumerate(live) if x.id == e.id), None)
        if at is None:
            errs.append(f"UNKNOWN: id {e.id} left but never entered")
            continue
        it = live[at]
        if it.data != e.data:
            errs.append(f"DATA: id {e.id} left with {e.data:#x}, entered with {it.data:#x}")
        for x in live[:at]:
            if rule.binds(x, it):
                errs.append(f"REORDER: id {e.id} left before earlier id {x.id}")
                break
        if e.cyc != last_cyc:
            last_cyc, last = e.cyc, []
        for x in last:
            if seq[x.id] < seq[it.id] and (x.cls, it.cls) in rule.strict_after \
                    and rule.binds(x, it):
                errs.append(f"SAME_CYCLE: id {e.id} left in cycle {e.cyc} with earlier id {x.id}")
        last.append(it)
        del live[at]
        left.add(e.id)
    errs += [f"LOST: id {x.id} never left" for x in live]
    return errs


@dc.dataclass(frozen=True)
class Canonical:
    """Equal canonical forms mean equivalent traces under the rule."""
    items: Tuple[Tuple[int, int], ...]                  # (id, data), sorted by id
    order: Tuple                                         # the bound relative orders
    cycles: Optional[Tuple[Tuple[int, int], ...]] = None  # (id, leave cycle) if pinned


def canonical(trace: Trace, rule: Rule) -> Canonical:
    ins, outs = _split(trace)
    by_id = {e.id: e for e in ins}
    items = tuple(sorted((e.id, e.data) for e in outs))
    if not rule.allow_pass:
        if rule.per_key:
            per: Dict[int, List[int]] = {}
            for e in outs:
                per.setdefault(by_id[e.id].key if e.id in by_id else e.key, []).append(e.id)
            order = tuple(sorted((k, tuple(v)) for k, v in per.items()))
        else:
            order = tuple(e.id for e in outs)
    else:
        # General rule: every bound pair (by this trace's entry order), with the
        # order it left in. Quadratic; fine for test-sized traces.
        pos = {e.id: i for i, e in enumerate(outs)}
        pairs = []
        for i, a in enumerate(ins):
            for b in ins[i + 1:]:
                if rule.binds(a, b) and a.id in pos and b.id in pos:
                    pairs.append((a.id, b.id, pos[a.id] < pos[b.id]))
        order = tuple(sorted(pairs))
    cycles = tuple(sorted((e.id, e.cyc) for e in outs)) if rule.pin_cycles else None
    return Canonical(items, order, cycles)


def compare(a: Trace, b: Trace, rule: Rule, names: Sequence[str] = ("a", "b")) -> List[str]:
    """Differences between two views; empty when they are the same function.
    Each view must also pass :func:`check` on its own."""
    diffs = [f"{names[0]}: {m}" for m in check(a, rule)] + \
            [f"{names[1]}: {m}" for m in check(b, rule)]
    ca, cb = canonical(a, rule), canonical(b, rule)
    if ca.items != cb.items:
        ia, ib = dict(ca.items), dict(cb.items)
        for i in sorted(set(ia) | set(ib)):
            if ia.get(i) != ib.get(i):
                diffs.append(f"item {i}: {names[0]}={ia.get(i)} {names[1]}={ib.get(i)}")
    if ca.order != cb.order:
        diffs.append(f"bound order differs between {names[0]} and {names[1]}")
    if ca.cycles != cb.cycles:
        diffs.append(f"leave cycles differ between {names[0]} and {names[1]} (pinned)")
    return diffs
