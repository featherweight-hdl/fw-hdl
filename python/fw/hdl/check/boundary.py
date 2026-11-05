"""Island-boundary checks on an integrated design.

The design is a set of islands joined by channels. Integrate enforces:

1. **registered boundaries** -- every channel between two blocks is registered
   in both directions: a FIFO (depth >= 1, no bypass), or the producer's
   valid/data and the consumer's ready all driven from flops. Exceptions are
   listed in the knobs (``island.exceptions``) with a reason.
2. **no combinational cycle** through depth-0 channels and unregistered block
   ports.
3. **no depth-0 loopback**: a depth-0 channel from a block back to itself
   (XLS accepts this silently; tests/xls/test_xls_facts.py).
4. **valid does not depend on ready** at any block output.

Rules 2-4 read each block's real combinational dependencies, output port ->
input ports, from its Verilog with yosys (stopping at flops), so they hold for
XLS blocks, externs and hand RTL alike.
"""
from __future__ import annotations

import dataclasses as dc
import os
import shutil
import subprocess
import tempfile
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

#: Flop cell types: a combinational cone stops here.
_FLOPS = ("$dff,$dffe,$adff,$adffe,$sdff,$sdffe,$sdffce,$dffsr,$dffsre,$aldff,$aldffe,"
          "$_DFF_P_,$_DFF_N_,$_SDFF_PP0_,$_SDFF_PP1_,$_SDFFE_PP0P_,$_SDFFE_PP1P_")


class BoundaryError(Exception):
    pass


@dc.dataclass
class Finding:
    rule: str           # "registered" | "comb_cycle" | "loopback" | "valid_on_ready"
    msg: str
    channel: Optional[str] = None

    def __str__(self) -> str:
        return f"{self.rule}: {self.msg}"


def yosys() -> Optional[str]:
    here = os.path.dirname(os.path.abspath(__file__))
    cand = os.path.join(here, *[".."] * 4, "packages", "yosys", "bin", "yosys")
    return shutil.which("yosys") or (cand if os.path.exists(cand) else None)


def comb_deps(files: Sequence[str], module: str, outputs: Sequence[str],
              inputs: Sequence[str],
              params: Optional[Dict[str, str]] = None) -> Dict[str, Set[str]]:
    """For each output port of *module*: the input ports it depends on
    combinationally (through no flop). *params*: parameter values (as
    Verilog) the module is elaborated with."""
    ys = yosys()
    if ys is None:
        raise BoundaryError("yosys not found")
    with tempfile.TemporaryDirectory() as d:
        script = [f"read_verilog -sv {' '.join(files)}"]
        script += [f"chparam -set {k} {v} {module}" for k, v in (params or {}).items()]
        script += [f"hierarchy -top {module}", "proc", "flatten", "opt_clean"]
        for i, o in enumerate(outputs):
            script.append(f"tee -q -o {d}/o{i}.txt select -list {module}/o:{o} "
                          f"%ci*:-{_FLOPS}")
        r = subprocess.run([ys, "-q", "-p", "; ".join(script)], capture_output=True, text=True)
        if r.returncode != 0:
            raise BoundaryError(f"yosys on {module}: {(r.stderr or r.stdout)[-800:]}")
        ins = set(inputs)
        out = {}
        for i, o in enumerate(outputs):
            names = {l.strip().split("/", 1)[-1] for l in open(f"{d}/o{i}.txt") if l.strip()}
            out[o] = {n for n in names if n in ins and n != o}
    return out


@dc.dataclass
class BlockPorts:
    """One block instance's channel pins and its combinational dependencies."""
    module: str
    channels: Dict[str, dict]           # channel -> {"direction", "data", "valid", "ready"}
    deps: Dict[str, Set[str]]           # output pin -> input pins

    def driven_by_flops(self, pin: str) -> bool:
        return not self.deps.get(pin)


def block_ports(sig, files: Sequence[str],
                params: Optional[Dict[str, str]] = None) -> BlockPorts:
    """From a BlockSignature and the block's Verilog (elaborated with
    *params*, a wrapped module's parameter values)."""
    chans, outs, ins = {}, [], []
    for c in sig.channels:
        p = dict(c.ports)
        p["direction"] = c.direction
        chans[c.name] = p
        if c.direction == "out":
            outs += [p[k] for k in ("data", "valid") if p.get(k)]
            ins += [p["ready"]] if p.get("ready") else []
        else:
            ins += [p[k] for k in ("data", "valid") if p.get(k)]
            outs += [p["ready"]] if p.get("ready") else []
    return BlockPorts(sig.name, chans, comb_deps(files, sig.name, outs, ins, params))


def check(shell, blocks: Dict[str, BlockPorts], exceptions: Iterable[dict] = (),
          require_registered: bool = True) -> List[Finding]:
    """*shell*: the partition; *blocks*: keyed by child instance name."""
    findings: List[Finding] = []
    waived = {e["channel"]: e for e in exceptions}
    depth = {c["name"]: int(c["depth"]) for c in shell.channels}
    ends: Dict[str, Dict[str, Tuple[str, str]]] = {}    # channel -> {"put"/"get": (child, port)}
    for b in shell.binds:
        child, port = b["port"]
        name, end = b["provider"]
        if end is None:
            continue
        ends.setdefault(name, {})["put" if end == "put_ex" else "get"] = (child, port)

    # 4. valid never depends on ready
    for inst, bp in blocks.items():
        readies = {p["ready"] for p in bp.channels.values()
                   if p["direction"] == "out" and p.get("ready")}
        for ch, p in bp.channels.items():
            if p["direction"] == "out" and p.get("valid"):
                bad = bp.deps.get(p["valid"], set()) & readies
                if bad:
                    findings.append(Finding("valid_on_ready",
                                            f"{inst}.{p['valid']} depends combinationally on "
                                            f"{', '.join(sorted(bad))}"))

    # 3. depth-0 loopback
    for name, e in ends.items():
        if depth.get(name) == 0 and "put" in e and "get" in e and e["put"][0] == e["get"][0]:
            findings.append(Finding("loopback", f"channel {name} has depth 0 and joins "
                                    f"{e['put'][0]} to itself", name))

    # 1. registered both ways
    if require_registered:
        for name, e in ends.items():
            if depth.get(name, 0) >= 1 or name in waived or "put" not in e or "get" not in e:
                continue
            (pc, pp), (cc, cp) = e["put"], e["get"]
            prod, cons = blocks.get(pc), blocks.get(cc)
            if prod is None or cons is None:
                continue
            fwd = [prod.channels[pp][k] for k in ("data", "valid") if prod.channels[pp].get(k)]
            bwd = [cons.channels[cp]["ready"]] if cons.channels[cp].get("ready") else []
            comb = [f"{pc}.{x}" for x in fwd if not prod.driven_by_flops(x)] + \
                   [f"{cc}.{x}" for x in bwd if not cons.driven_by_flops(x)]
            if comb:
                findings.append(Finding(
                    "registered", f"channel {name} (depth 0) between {pc} and {cc} is not "
                    f"registered both ways: {', '.join(comb)} combinational. Give it depth "
                    f">= 1, register the ports (xls.chan_flop: skid), or list it in "
                    f"island.exceptions with a reason", name))

    # 2. combinational cycles: nodes are (instance, pin)
    edges: Dict[Tuple[str, str], Set[Tuple[str, str]]] = {}
    for inst, bp in blocks.items():
        for o, ins in bp.deps.items():
            for i in ins:
                edges.setdefault((inst, i), set()).add((inst, o))
    for name, e in ends.items():
        if depth.get(name) != 0 or "put" not in e or "get" not in e:
            continue
        (pc, pp), (cc, cp) = e["put"], e["get"]
        if pc not in blocks or cc not in blocks:
            continue
        P, C = blocks[pc].channels[pp], blocks[cc].channels[cp]
        for k in ("data", "valid"):
            if P.get(k) and C.get(k):
                edges.setdefault((pc, P[k]), set()).add((cc, C[k]))
        if P.get("ready") and C.get("ready"):
            edges.setdefault((cc, C["ready"]), set()).add((pc, P["ready"]))
    cyc = _find_cycle(edges)
    if cyc:
        findings.append(Finding("comb_cycle", "combinational loop: " +
                                " -> ".join(f"{i}.{p}" for i, p in cyc)))
    return findings


def _find_cycle(edges) -> Optional[List]:
    WHITE, GREY, BLACK = 0, 1, 2
    color: Dict = {}
    stack: List = []

    def dfs(n):
        color[n] = GREY
        stack.append(n)
        for m in sorted(edges.get(n, ())):
            c = color.get(m, WHITE)
            if c == GREY:
                return stack[stack.index(m):] + [m]
            if c == WHITE:
                r = dfs(m)
                if r:
                    return r
        stack.pop()
        color[n] = BLACK
        return None

    for n in sorted(edges):
        if color.get(n, WHITE) == WHITE:
            r = dfs(n)
            if r:
                return r
    return None
