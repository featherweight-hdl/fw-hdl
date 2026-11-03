"""RQ-F8: latency contracts, checked before and after codegen.

A contract sits in the knob file::

    contracts:
      latency:
        "in -> out":              {max: 6}          # a top path (top ports)
        "rt_table.req -> rt_table.rsp": {fixed: 2}  # one block: class.channel -> class.channel

Bounds are first-value cycles, as fw.hdl.report.Latency counts them
(channel registers included).

* **Before codegen** (:func:`precheck`): each block's latency is bounded by its
  knobs -- at least its channel registers, at most those plus
  ``pipeline_stages - 1`` -- and channels are exact. A contract that no
  knob-allowed schedule can meet is rejected here, naming the contract and the
  path, before any tool runs.
* **In codegen**: a block contract becomes an XLS ``--io_constraints`` entry
  on the receive-to-send distance (the contract minus the block's registers),
  so the scheduler itself honours it (:func:`io_constraints`).
* **After codegen** (:func:`postcheck`): the latency report's exact numbers
  are compared with every top-path contract.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from ..latency import walk

_REG = {"flop": 1, "skid": 1}


def parse_key(key: str) -> Tuple[str, str]:
    a, _, b = key.partition("->")
    return a.strip(), b.strip()


def bounds_of(spec: dict) -> Tuple[Optional[int], Optional[int]]:
    if "fixed" in spec:
        return spec["fixed"], spec["fixed"]
    return spec.get("min"), spec.get("max")


def _is_block_key(knobs, a: str, b: str) -> Optional[Tuple[str, str, str]]:
    if "." in a and "." in b:
        ba, ca = a.rsplit(".", 1)
        bb, cb = b.rsplit(".", 1)
        if ba == bb and ba in knobs.xls_blocks():
            return ba, ca, cb
    return None


def io_constraints(knobs, block: str) -> List[str]:
    """``--io_constraints`` entries for *block*'s own contracts."""
    out = []
    for key, spec in knobs.latency_contracts().items():
        a, b = parse_key(key)
        hit = _is_block_key(knobs, a, b)
        if hit is None or hit[0] != block:
            continue
        _, ci, co = hit
        regs = _REG.get(knobs.chan_flop(block, ci, "receive"), 0) + \
            _REG.get(knobs.chan_flop(block, co, "send"), 0)
        lo, hi = bounds_of(spec)
        lo = "none" if lo is None else max(0, lo - regs)
        hi = "none" if hi is None else hi - regs
        out.append(f"{ci}:recv:{co}:send:{lo}:{hi}")
    return out


def _directions(shell) -> Dict[Tuple[str, str], str]:
    tops_in = {p["name"] for p in shell.ports if p["direction"] == "in"}
    d = {}
    for b in shell.binds:
        child, port = b["port"]
        name, end = b["provider"]
        d[(child, port)] = "receive" if end in ("get_ex", "get_nb_ex") or \
            (end is None and name in tops_in) else "send"
    return d


def precheck(shell, knobs) -> List[str]:
    """Contracts no schedule the knobs allow can meet."""
    errs: List[str] = []
    cls = {c["name"]: c["class"] for c in shell.children}
    dirs = _directions(shell)
    outs: Dict[str, List[str]] = {}
    for (child, port), d in dirs.items():
        if d == "send":
            outs.setdefault(child, []).append(port)

    def block_range(child: str, pin: str, pout: str) -> Tuple[int, Optional[int]]:
        c = cls[child]
        regs = _REG.get(knobs.chan_flop(c, pin, "receive"), 0) + \
            _REG.get(knobs.chan_flop(c, pout, "send"), 0)
        stages = knobs.block_options(c).get("pipeline_stages")
        if stages is None and knobs.block_options(c).get("clock_period_ps") is not None:
            return regs, None                   # the period decides: no upper bound yet
        return regs, regs + (stages or 1) - 1

    def hops(child, port):
        return [(o, block_range(child, port, o)) for o in outs.get(child, [])]

    paths = walk(shell, hops)
    for key, spec in knobs.latency_contracts().items():
        a, b = parse_key(key)
        lo, hi = bounds_of(spec)
        blk = _is_block_key(knobs, a, b)
        if blk is not None:
            c, ci, co = blk
            insts = [n for n, k in cls.items() if k == c]
            cands = [block_range(n, ci, co) for n in insts]
            what = f"block {c} {ci} -> {co}"
        else:
            cands = []
            for src, dst, h in paths:
                if (src, dst) != (a, b):
                    continue
                plo = sum(x.cycles[0] if x.what == "block" else x.cycles for x in h)
                phi = None if any(x.what == "block" and x.cycles[1] is None for x in h) else \
                    sum(x.cycles[1] if x.what == "block" else x.cycles for x in h)
                cands.append((plo, phi))
            what = f"path {a} -> {b}"
        if not cands:
            errs.append(f"contract {key!r}: no {what} in the design")
            continue
        # The contract can be met if some candidate interval meets it.
        ok = any((hi is None or clo <= hi) and (lo is None or chi is None or chi >= lo)
                 for clo, chi in cands)
        if not ok:
            rng = ", ".join(f"{clo}..{'?' if chi is None else chi}" for clo, chi in cands)
            errs.append(f"contract {key!r} ({_spec(spec)}) cannot be met: the knobs allow "
                        f"{what} {rng} cycles ({knobs.where('contracts', 'latency', key)})")
    return errs


def postcheck(report, knobs) -> List[str]:
    """Top-path contracts against the latency report."""
    errs = []
    for key, spec in knobs.latency_contracts().items():
        a, b = parse_key(key)
        if _is_block_key(knobs, a, b):
            continue
        lo, hi = bounds_of(spec)
        for p in report.get(a, b):
            if (lo is not None and p.cycles < lo) or (hi is not None and p.cycles > hi):
                hops = " + ".join(f"{h.name}[{h.via}]={h.cycles}" for h in p.hops)
                errs.append(f"contract {key!r} ({_spec(spec)}) violated: {p.name} takes "
                            f"{p.cycles} cycles ({hops})")
    return errs


def _spec(spec: dict) -> str:
    return ", ".join(f"{k} {v}" for k, v in spec.items())
