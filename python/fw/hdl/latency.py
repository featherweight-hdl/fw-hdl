"""The per-path latency table, from schedules and knobs.

The latency of a path, top input to top output, is the sum of its hops:

* through a proc block, from its receive on channel ``a`` to its send on
  channel ``b``: ``stage(send b) - stage(receive a)``, plus 1 for a registered
  input channel and 1 for a registered output channel (``flop`` or ``skid``;
  ``zero_latency`` and ``none`` add nothing). The stages come from the block's
  schedule and optimized IR; the registers from its codegen signature, which
  records the ``chan_interface`` flop kind the knobs set.
* through a channel between blocks: 1 for a FIFO (``fw_rv_fifo``, depth >= 1:
  no bypass), 0 for depth 0 (a wire).
* through a multi-proc block: its members' hops and its in-package
  FIFOs, the same way (:class:`GroupTiming`).
* through a structural child: the paths of its own shell, from the port the
  value enters by.
* through a block nothing schedules (a wrapper, an extern or native block):
  its ``iface.latency`` facts (:mod:`fw.hdl.facts`), fixed or a min..max
  range, else its signature's ``latency``. A declared fact no measurement has
  confirmed makes the path *unverified*.

This is the first-value latency with every input valid and every output ready;
backpressure only adds to it. The XLS signature's ``pipeline.latency`` is not
used: for procs it counts stages, not the receive-to-send distance.

    rep = report(shell, blocks)          # blocks: module -> BlockTiming
    rep.markdown(); rep.to_json()
"""
from __future__ import annotations

import dataclasses as dc
import json
import re
from typing import Dict, List, Optional, Sequence, Tuple

_OP = re.compile(r"^\s*([\w.]+): [^=]*= (receive|send)\(.*?\bchannel=(\w+)", re.M)

#: Registers that cost a cycle on a proc channel (chan_interface flop_kind).
_REG_COST = {"flop": 1, "skid": 1, "zero_latency": 0, "zerolatency": 0, "none": 0, None: 0}


@dc.dataclass
class BlockTiming:
    """One XLS proc block, as its codegen outputs describe it."""
    module: str
    stages: int
    recv_stage: Dict[str, int]          # channel -> stage of its receive
    send_stage: Dict[str, int]          # channel -> stage of its send
    flop: Dict[str, str]                # channel -> flop kind

    def latency(self, src: str, dst: str) -> Optional[int]:
        if src not in self.recv_stage or dst not in self.send_stage:
            return None
        return (_REG_COST[self.flop.get(src)] + self.send_stage[dst] - self.recv_stage[src]
                + _REG_COST[self.flop.get(dst)])

    @property
    def inputs(self) -> List[str]:
        return list(self.recv_stage)

    @property
    def outputs(self) -> List[str]:
        return list(self.send_stage)


def block_timing(module: str, opt_ir: str, schedule: str, signature=None) -> BlockTiming:
    """*opt_ir* and *schedule* are the text of codegen's ``<m>.opt.ir`` and
    ``<m>.schedule.textproto``; *signature* is its BlockSignature (or None)."""
    from .stage_tlm import parse_schedules
    scheds = parse_schedules(schedule)
    if not scheds:
        raise ValueError(f"{module}: the schedule names no function or proc")
    sched = next(iter(scheds.values())) if len(scheds) == 1 else \
        scheds.get(module) or \
        next((s for n, s in scheds.items() if n.endswith(module)), next(iter(scheds.values())))
    stage_of = {n: st for st, nodes in sched.stages.items() for n in nodes}
    recv, send = {}, {}
    for node, op, ch in _OP.findall(opt_ir):
        if node not in stage_of:
            continue
        (recv if op == "receive" else send).setdefault(ch, stage_of[node])
    flop = {}
    if signature is not None:
        flop = {c.name: c.flop_kind for c in signature.channels}
    return BlockTiming(module, sched.length, recv, send, flop)


class GroupTiming:
    """A multi-proc block seen from outside: the latency from one
    external port to another, through its members (each a :class:`BlockTiming`
    from its own proc's schedule) and the in-package FIFOs between them (1 for
    depth >= 1, 0 for a bypass wire). *entry* is the partition's ``group``
    entry; external ports' registers come from the group signature."""

    def __init__(self, module: str, entry: dict, members: Dict[str, BlockTiming]):
        self.module = module
        self.entry = entry
        self.members = members          # instance -> its proc's timing
        self._ext = {e["name"]: (e["inst"], e["port"]) for e in entry["external"]}
        self._alias = {v: k for k, v in self._ext.items()}
        self._link = {tuple(c["a"]): (c, tuple(c["b"])) for c in entry["internal"]}

    @property
    def inputs(self) -> List[str]:
        return [a for a, (i, p) in self._ext.items() if p in self.members[i].recv_stage]

    @property
    def outputs(self) -> List[str]:
        return [a for a, (i, p) in self._ext.items() if p in self.members[i].send_stage]

    def latency(self, src: str, dst: str) -> Optional[int]:
        if src not in self._ext or dst not in self._ext:
            return None
        found: List[int] = []

        def go(inst: str, port: str, acc: int, seen: frozenset):
            bt = self.members[inst]
            for o in bt.outputs:
                lat = bt.latency(port, o)
                if lat is None:
                    continue
                if self._alias.get((inst, o)) == dst:
                    found.append(acc + lat)
                link = self._link.get((inst, o))
                if link is not None and link[1] not in seen:
                    c, (ni, np) = link
                    go(ni, np, acc + lat + (1 if int(c["depth"]) else 0), seen | {link[1]})

        go(*self._ext[src], 0, frozenset())
        return max(found) if found else None


def group_timing(module: str, entry: dict, opt_ir: str, schedule: str,
                 signature=None) -> GroupTiming:
    """The :class:`GroupTiming` of a multi-proc block from its codegen
    outputs (one opt IR and one schedule for the whole package)."""
    flop = {c.name: c.flop_kind for c in signature.channels} if signature is not None else {}
    members = {}
    for m in entry["members"]:
        bt = block_timing(m["module"], opt_ir, schedule, None)
        bt.flop = {e["port"]: flop.get(e["name"]) for e in entry["external"]
                   if e["inst"] == m["name"]}
        members[m["name"]] = bt
    return GroupTiming(module, entry, members)


_SAME = object()


@dc.dataclass
class Hop:
    what: str           # "block" | "channel"
    name: str           # instance or channel name
    via: str            # "in->out" for a block, "depth=N" for a channel
    cycles: int         # the fewest cycles
    max: Optional[int] = _SAME      # the most; None: unbounded (default: = cycles)
    #: Where the number comes from: schedule, structural, declared, signature.
    source: str = "schedule"
    unverified: bool = False

    def __post_init__(self):
        if self.max is _SAME:
            self.max = self.cycles


@dc.dataclass
class _Cost:
    """A block hop's value while paths are walked (see :func:`report`)."""
    lo: int
    hi: Optional[int]
    source: str
    unverified: bool = False


@dc.dataclass
class PathLatency:
    src: str            # top input port
    dst: str            # top output port
    hops: List[Hop]

    @property
    def cycles(self) -> int:
        """The fewest cycles (the latency, when every hop is fixed)."""
        return sum(h.cycles for h in self.hops)

    @property
    def max(self) -> Optional[int]:
        """The most cycles; None when a hop is unbounded."""
        his = [h.max for h in self.hops]
        return None if None in his else sum(his)

    @property
    def unverified(self) -> bool:
        return any(h.unverified for h in self.hops)

    @property
    def range(self) -> str:
        lo, hi = self.cycles, self.max
        return str(lo) if hi == lo else f"{lo}..{'' if hi is None else hi}"

    @property
    def name(self) -> str:
        return f"{self.src} -> {self.dst}"


@dc.dataclass
class Report:
    top: str
    paths: List[PathLatency]
    notes: List[str] = dc.field(default_factory=list)

    def get(self, src: str, dst: str) -> List[PathLatency]:
        return [p for p in self.paths if p.src == src and p.dst == dst]

    def to_json(self) -> dict:
        return {"format": "fw-hdl.latency", "version": 1, "top": self.top,
                "paths": [{"src": p.src, "dst": p.dst, "cycles": p.cycles, "min": p.cycles,
                           "max": p.max, "unverified": p.unverified,
                           "hops": [dc.asdict(h) for h in p.hops]} for p in self.paths],
                "notes": self.notes}

    def markdown(self) -> str:
        L = [f"# Latency: {self.top}", "",
             "First-value latency in cycles, every input valid and every output ready.",
             "A range is min..max (no max: unbounded); * marks a declared fact no",
             "measurement has confirmed.", "",
             "| Path | Cycles | Hops |", "|---|---|---|"]
        for p in self.paths:
            hops = " + ".join(f"{h.name}[{h.via}]={_hop_cycles(h)}" for h in p.hops)
            L.append(f"| `{p.name}` | {p.range}{' *' if p.unverified else ''} | {hops} |")
        if self.notes:
            L += ["", "Notes:"] + [f"- {n}" for n in self.notes]
        return "\n".join(L) + "\n"


def _hop_cycles(h: Hop) -> str:
    r = str(h.cycles) if h.max == h.cycles else f"{h.cycles}..{'' if h.max is None else h.max}"
    if h.source not in ("schedule", "structural") and h.what == "block":
        r += f" ({h.source}{', unverified' if h.unverified else ''})"
    return r


def walk(shell, block_hops, notes: Optional[List[str]] = None, start: Optional[str] = None):
    """Every path from a top input to a top output through *shell* (the
    partition: ports, channels, children, binds), as ``(src, dst, hops)``.

    ``block_hops(child, in_port)`` gives ``[(out_port, value)]``: where a value
    entering *child* on *in_port* can leave, and at what cost (an int, or
    anything the caller adds up). A channel hop's value is 1 for a FIFO and 0
    for a wire. A cycle ends that path (noted in *notes*). With *start*, only
    the paths from that top input."""
    notes = [] if notes is None else notes
    depth = {c["name"]: int(c["depth"]) for c in shell.channels}
    consumer: Dict[Tuple[str, Optional[str]], Tuple[str, str]] = {}
    produced: Dict[Tuple[str, str], Tuple[str, Optional[str]]] = {}
    tops_in = [p["name"] for p in shell.ports if p["direction"] == "in"]
    for b in shell.binds:
        child, port = b["port"]
        prov = (b["provider"][0], b["provider"][1])
        if prov[1] in ("get_ex", "get_nb_ex") or (prov[1] is None and prov[0] in tops_in):
            consumer[prov] = (child, port)
        else:
            produced[(child, port)] = prov
    out = []

    def go(src: str, child: str, port: str, hops: List[Hop], seen: frozenset):
        for o, val in block_hops(child, port):
            h = hops + [Hop("block", child, f"{port}->{o}", val)]
            prov = produced.get((child, o))
            if prov is None:
                continue
            name, end = prov
            if end is None:                         # a top output
                out.append((src, name, h))
                continue
            nxt = consumer.get((name, "get_ex")) or consumer.get((name, "get_nb_ex"))
            if nxt is None:
                continue
            if (nxt[0], name) in seen:
                notes.append(f"path from {src} loops through channel {name}")
                continue
            go(src, nxt[0], nxt[1],
               h + [Hop("channel", name, f"depth={depth[name]}", 1 if depth[name] else 0)],
               seen | {(nxt[0], name)})

    for p in ([start] if start is not None else tops_in):
        c = consumer.get((p, None))
        if c is not None:
            go(p, c[0], c[1], [], frozenset())
    return out


def report(shell, blocks: Dict[str, "BlockTiming | GroupTiming"]) -> Report:
    """The latency of every top-input to top-output path. *blocks* is keyed
    by module name."""
    rep = Report(getattr(shell, "module", shell.top), [])
    for src, dst, h in _paths(shell, blocks, rep.notes, None, ""):
        rep.paths.append(PathLatency(src, dst, h))
    return rep


def _paths(shell, blocks, notes: List[str], start: Optional[str], prefix: str):
    """``(src, dst, [Hop])`` through *shell*, descending into structural
    children; *prefix* names the shell's instance in notes."""
    child = {c["name"]: c for c in shell.children}

    def hops(name, port):
        c = child[name]
        if c.get("engine") == "structural":
            out = []
            for _, dst, h in _paths(shell.nested(c), blocks, notes, port, f"{prefix}{name}."):
                p = PathLatency(port, dst, h)
                out.append((dst, _Cost(p.cycles, p.max, "structural", p.unverified)))
            return out
        lat = [f for f in c.get("facts", []) if f["kind"] == "iface.latency"
               and f["value"]["src"] == port]
        if lat:
            out = []
            for f in lat:
                v = f["value"]
                lo, hi = (v["fixed"], v["fixed"]) if v.get("fixed") is not None \
                    else (v["min"], v.get("max"))
                out.append((v["dst"], _Cost(lo, hi, f.get("provenance", "declared"),
                                            bool(f.get("unverified")))))
            return out
        bt = blocks.get(c["module"])
        if bt is not None:
            return [(o, bt.latency(port, o)) for o in bt.outputs
                    if bt.latency(port, o) is not None]
        sig = (c.get("extern") or {}).get("signature_json") or {}
        if sig.get("latency") is not None:
            return [(ch["name"], _Cost(sig["latency"], sig["latency"], "signature"))
                    for ch in sig.get("channels", []) if ch["direction"] == "out"]
        notes.append(f"{prefix}{name}: no timing for module {c['module']}")
        return []

    out = []
    for src, dst, h in walk(shell, hops, notes, start):
        out.append((src, dst, [Hop(x.what, x.name, x.via, x.cycles.lo, x.cycles.hi,
                                   x.cycles.source, x.cycles.unverified)
                               if isinstance(x.cycles, _Cost) else x for x in h]))
    return out


def load_blocks(files: Sequence[Tuple[str, str, str, Optional[str]]],
                groups: Optional[Dict[str, dict]] = None) -> Dict[str, "BlockTiming | GroupTiming"]:
    """``[(module, opt_ir_path, schedule_path, signature_textproto_path|None)]``;
    *groups* maps a multi-proc block's module to its partition ``group`` entry."""
    from zuspec.be.xls.signature import signature_from_codegen
    groups = groups or {}
    out = {}
    for module, opt_ir, sched, sig in files:
        s = signature_from_codegen(open(sig).read()) if sig else None
        if module in groups:
            out[module] = group_timing(module, groups[module], open(opt_ir).read(),
                                       open(sched).read(), s)
        else:
            out[module] = block_timing(module, open(opt_ir).read(), open(sched).read(), s)
    return out


def write(rep: Report, outdir: str) -> Dict[str, str]:
    import os
    os.makedirs(outdir, exist_ok=True)
    md, js = os.path.join(outdir, "latency.md"), os.path.join(outdir, "latency.json")
    with open(md, "w") as f:
        f.write(rep.markdown())
    with open(js, "w") as f:
        json.dump(rep.to_json(), f, indent=2)
    return {"md": md, "json": js}
